"""Galaxy CM master manager"""
import logging, logging.config, threading, os, time, subprocess, commands
import shutil
import datetime as dt

from cm.util.bunch import Bunch

from cm.util import misc, comm
from cm.services.autoscale import Autoscale
from cm.services import service_states
from cm.services.data.filesystem import Filesystem
from cm.services.apps.pss import PSS
from cm.services.apps.sge import SGEService
from cm.services.apps.galaxy import GalaxyService
from cm.services.apps.postgres import PostgresService

import cm.util.paths as paths
from boto.exception import EC2ResponseError, BotoServerError, S3ResponseError

log = logging.getLogger('cloudman')

#Master States
master_states = Bunch( 
    INITIAL_STARTUP="Initial startup",
    WAITING_FOR_USER_ACTION="Waiting for user action",
    START_WORKERS="Start workers",
    STARTING_WORKERS="Starting workers",
    SEND_MASTER_PUBKEY="Sending master's public key",
    WAITING_FOR_WORKER_INIT="Waiting for workers",
    STARTING_SGE="Configuring SGE",
    WAITING_FOR_WORKER_SGE="Waiting for workers to start SGE",
    CONFIGURE_GALAXY="Configuring Galaxy",
    GALAXY_STARTING="Galaxy starting",
    READY="Ready",
    SHUTTING_DOWN="Shutting down",
    SHUT_DOWN="Shut down",
    ERROR="Error"
 )

cluster_status = Bunch( 
    OFF="OFF",
    ON="ON",
    STARTING="STARTING",
    SHUT_DOWN="SHUT_DOWN" # Because we don't really support cluster restart
 )


class ConsoleManager(object):
    def __init__(self, app):
        self.startup_time = dt.datetime.utcnow()
        log.debug( "Initializing console manager - cluster start time: %s" % self.startup_time)
        self.app = app
        self.console_monitor = ConsoleMonitor(self.app)
        self.root_pub_key = None
        self.cluster_status = cluster_status.OFF
        self.master_state = master_states.INITIAL_STARTUP
        self.num_workers_requested = 0 # Number of worker nodes requested by user
        self.worker_instances = self.get_worker_instances() # The actual number of worker nodes (note: this is a list of Instance objects)
        self.disk_total = "0"
        self.disk_used = "0"
        self.disk_pct = "0%"
        self.manager_started = False
        self.cluster_manipulation_in_progress = False
        
        self.initial_cluster_type = None
        self.services = []        
    
    def _stop_app_level_services(self):
        """ Convenience function that suspends SGE jobs and removes Galaxy & 
        Postgres services, thus allowing system level operations to be performed."""
        # Suspend all SGE jobs
        log.debug("Suspending SGE queue all.q")
        misc.run('export SGE_ROOT=%s; . $SGE_ROOT/default/common/settings.sh; %s/bin/lx24-amd64/qmod -sq all.q' \
            % (paths.P_SGE_ROOT, paths.P_SGE_ROOT), "Error suspending SGE jobs", "Successfully suspended all SGE jobs.")
        # Stop application-level services managed via CloudMan
        # If additional service are to be added as things CloudMan can handle,
        # the should be added to do for-loop list (in order in which they are
        # to be removed)
        if self.initial_cluster_type == 'Galaxy':
            for svc_type in ['Galaxy', 'Postgres']:
                try:
                    svc = self.get_services(svc_type)
                    if svc:
                        svc[0].remove()
                except IndexError, e:
                    log.error("Tried removing app level service '%s' but failed: %s" \
                        % (svc_type, e))
    
    def _start_app_level_services(self):
        # Resume application-level services managed via CloudMan
        # If additional service are to be added as things CloudMan can handle,
        # the should be added to do for-loop list (in order in which they are
        # to be added)
        for svc_type in ['Postgres', 'Galaxy']:
            try:
                svc = self.get_services(svc_type)
                if svc:
                    svc[0].add()
            except IndexError, e:
                log.error("Tried adding app level service '%s' but failed: %s" \
                    % (svc_type, e))
        log.debug("Unsuspending SGE queue all.q")
        misc.run('export SGE_ROOT=%s; . $SGE_ROOT/default/common/settings.sh; %s/bin/lx24-amd64/qmod -usq all.q' \
            % (paths.P_SGE_ROOT, paths.P_SGE_ROOT), \
            "Error unsuspending SGE jobs", \
            "Successfully unsuspended all SGE jobs")
    
    def recover_monitor(self, force='False'):
        if self.console_monitor:
            if force=='True':
                self.console_monitor.shutdown()
            else:
                return False
        self.console_monitor = ConsoleMonitor(self.app)
        self.console_monitor.start()
        return True
    
    def snapshot_status(self):
        """
        Get the status of a file system volume currently being snapshoted. This
        method looks through all the file systems and all volumes assoc. with a
        file system and returns the status and progress for thee first volume
        going through the snapshot process.
        In addition, if a file system is marked as needing to 'grow' or sharing 
        the cluster is currently pending but no volumes are currently being 
        snapshoted, the method returns 'configuring' as the status.
        
        :rtype: array of strings of length 2
        :return: A pair of values as strings indicating (1) the status (e.g., 
        pending, complete) of the snapshot and (2) the progress.
        """
        fsarr = [s for s in self.services if s.svc_type == "Filesystem"]
        for fs in fsarr:
            for vol in fs.volumes:
                if vol.snapshot_status != None:
                    return (vol.snapshot_status, vol.snapshot_progress)
            # No volume is being snapshoted; check if waiting to 'grow' one
            if fs.grow:
                return ("configuring", None)
        if self.cluster_manipulation_in_progress:
            return ("configuring", None)
        return (None, None)
    
    def start( self ):
        """ This method is automatically called as CloudMan starts; it tries to add
        and start available cluster services (as provided in the cluster's 
        configuration and persistent data )"""
        log.debug("ud at manager start: %s" % self.app.ud)
        if self.app.TESTFLAG is True:
            log.debug("Attempted to start the ConsoleManager. TESTFLAG is set; nothing to start, passing.")
            return False
        self.app.manager.services.append(SGEService(self.app))
        # Add PSS service only if post_start_script_url key was provided as part of user data
        if 'post_start_script_url' in self.app.ud:
            self.app.manager.services.append(PSS(self.app))
        else:
            log.debug("'post_start_script_url' key was not provided as part of user data; not adding PSS service")
        if not self.add_preconfigured_services():
            return False
        self.manager_started = True
        log.info( "Completed initial cluster configuration." )
        return True
    
    def add_preconfigured_services(self):
        """ Inspect cluster configuration and persistent data and add 
        available/preconfigured services. """
        if self.app.TESTFLAG is True:
            log.debug("Attempted to add preconfigured cluster services but the TESTFLAG is set.")
            return None
        try:
            # Make sure we have a complete Galaxy cluster configuration and don't start partial set of services
            if self.app.ud.has_key("static_filesystems") and not self.app.ud.has_key("data_filesystems"):
                log.warning("Conflicting cluster configuration loaded; corrupted persistent_data.yaml? Starting a new cluster.")
                self.app.manager.initial_cluster_type = None
                return True # True because we're dafaulting to starting a new cluster so start the manager
            attached_volumes = self.get_attached_volumes()
            if self.app.ud.has_key("static_filesystems"):
                for vol in self.app.ud['static_filesystems']:
                    fs = Filesystem(self.app, vol['filesystem'])
                    # Check if an already attached volume maps to the current filesystem
                    att_vol = self.get_vol_if_fs(attached_volumes, vol['filesystem'])
                    if att_vol:
                        fs.add_volume(vol_id=att_vol.id, size=att_vol.size, from_snapshot_id=att_vol.snapshot_id)
                    else:
                        fs.add_volume(size=vol['size'], from_snapshot_id=vol['snap_id'])
                    log.debug("Adding static filesystem: '%s'" % vol['filesystem'])
                    self.app.manager.services.append(fs)
                    self.app.manager.initial_cluster_type = 'Galaxy'
            if self.app.ud.has_key("data_filesystems"):
                for fs, vol_array in self.app.ud['data_filesystems'].iteritems():
                    log.debug("Adding a previously existing data filesystem: '%s'" % fs)
                    fs = Filesystem(self.app, fs)
                    for vol in vol_array:
                        fs.add_volume(vol_id=vol['vol_id'], size=vol['size'])
                    self.app.manager.services.append(fs)
                    self.app.manager.initial_cluster_type = 'Data'
            if self.app.ud.has_key("services"):
                for srvc in self.app.ud['services']:
                    log.debug("Adding service: '%s'" % srvc['service'])
                    # TODO: translation from predefined service names into classes is not quite ideal...
                    if srvc['service'] == 'Postgres':
                        self.app.manager.services.append(PostgresService(self.app))
                        self.app.manager.initial_cluster_type = 'Galaxy'
                    if srvc['service'] == 'Galaxy':
                        self.app.manager.services.append(GalaxyService(self.app))
                        self.app.manager.initial_cluster_type = 'Galaxy'
            return True
        except Exception, e:
            log.error("Error in filesystem YAML: %s" % e)
            self.manager_started = False
            return False
    
    def get_vol_if_fs(self, attached_volumes, filesystem_name):
        """ Iterate through the list of (attached) volumes and check if any
        one of them matches the current cluster name and filesystem (as stored
        in volume tags). Returns a matching volume or None.
        Note that this method returns the first matching volume and will thus 
        not work for filesystems composed of multiple volumes. """
        try:
            for vol in attached_volumes:
                if self.app.cloud_interface.get_tag(vol, 'cluster_name') == self.app.ud['cluster_name'] and \
                   self.app.cloud_interface.get_tag(vol, 'filesystem') == filesystem_name:
                    log.debug("Identified attached volume '%s' as filesystem '%s'" % (vol.id, filesystem_name))
                    return vol
        except EC2ResponseError, e:
            log.debug("Error checking attached volume '%s' tags: %s" % (vol.id, e))
        return None
    
    def start_autoscaling(self, as_min, as_max, instance_type):
        as_svc = self.get_services('Autoscale')
        if not as_svc:
            self.app.manager.services.append(Autoscale(self.app, as_min, as_max, instance_type))
        else:
            log.debug("Autoscaling is already on.")
        as_svc = self.get_services('Autoscale')
        log.debug(as_svc[0])
    
    def stop_autoscaling(self):
        as_svc = self.get_services('Autoscale')
        if as_svc:
            self.app.manager.services.remove(as_svc[0])
        else:
            log.debug("Not stopping autoscaling because it is not on.")
    
    def adjust_autoscaling(self, as_min, as_max):
        as_svc = self.get_services('Autoscale')
        if as_svc:
            as_svc[0].as_min = int(as_min)
            as_svc[0].as_max = int(as_max)
            log.debug("Adjusted autoscaling limits; new min: %s, new max: %s" % (as_svc[0].as_min, as_svc[0].as_max))
        else:
            log.debug("Cannot adjust autoscaling because autoscaling is not on.")
    
    # DBTODO For now this is a quick fix to get a status.  
    # Define what 'yellow' would be, and don't just count on "Filesystem" being the only data service.
    def get_data_status(self):
        fses = self.get_services("Filesystem")
        if fses != []:
            for fs in fses:
                if fs.state == service_states.ERROR:
                    return "red"
                elif fs.state != service_states.RUNNING:
                    return "yellow"
            return "green"
        else:
            return "nodata"
    
    def get_app_status(self):
        count = 0
        for svc in self.services:   
            if svc.svc_type != "Filesystem":
                count += 1
                if svc.state == service_states.ERROR:
                    return "red"
                elif svc.state != service_states.RUNNING:
                    return "yellow"
        if count != 0:
            return "green"
        else:
            return "nodata"
    
    def get_services(self, svc_type):
        svcs = []
        for s in self.services:
            if s.svc_type == svc_type:
                svcs.append(s)
        return svcs
    
    def all_fs_status_text(self):
        return []
        tr = []
        for key, vol in self.volumes.iteritems():
            if vol[3] is None:
                tr.append("%s+nodata" % key)
            else:
                if vol[3] == True:
                    tr.append("%s+green" % key)
                else:
                    tr.append("%s+red" % key)
        return tr
    
    def all_fs_status_array(self):
        return []
        tr = []
        for key, vol in self.volumes.iteritems():
            if vol[3] is None:
                tr.append([key, "nodata"])
            else:
                if vol[3] == True:
                    tr.append([key, "green"])
                else:
                    tr.append([key, "red"])
        return tr
    
    def fs_status_text(self):
        """fs_status"""
        good_count = 0
        bad_count = 0
        fsarr = [s for s in self.services if s.svc_type == "Filesystem"]
        if len(fsarr) == 0:
            return "nodata"
        # DBTODO Fix this conflated volume/filesystem garbage.
        for fs in fsarr:
            if fs.state == service_states.RUNNING:
                good_count += 1
            else:
                bad_count += 1
        if good_count == len(fsarr):
            return "green"
        elif bad_count > 0:
            return "red"
        else:
            return "yellow"
    
    def pg_status_text(self):
        """pg_status"""
        svcarr = [s for s in self.services if s.svc_type == "Postgres"]
        if len(svcarr) > 0:
            if svcarr[0].state == service_states.RUNNING:
                return "green"
            else:
                return "red"
        else:
            return "nodata"
    
    def sge_status_text(self):
        """sge_status"""
        svcarr = [s for s in self.services if s.svc_type == "SGE"]
        if len(svcarr) > 0:
            if svcarr[0].state == service_states.RUNNING:
                return "green"
            else:
                return "red"
        else:
            return "nodata"
    
    def galaxy_status_text(self):
        """galaxy_status"""
        svcarr = [s for s in self.services if s.svc_type == "Galaxy"]
        if len(svcarr) > 0:
            if svcarr[0].state == service_states.RUNNING:
                return "green"
            else:
                return "red"
        else:
            return "nodata"
    
    def get_srvc_status(self, srvc):
        if srvc in ['Galaxy', 'SGE', 'Postgres', 'Filesystem']:
            svcarr = [s for s in self.services if s.svc_type == srvc]
            if len(svcarr) > 0:
                return srvc[0].state
            else:
                return "'%s' is not running" % srvc
        return "Service '%s' not recognized." % srvc
    
    def get_all_services_status(self):
        status_dict = {}
        for srvc in self.services:
            status_dict[srvc.svc_type] = srvc.state
        status_dict['galaxy_rev'] = self.get_galaxy_rev()
        status_dict['galaxy_admins'] = self.get_galaxy_admins()
        return status_dict
    
    def get_galaxy_rev(self):
        cmd = "%s - galaxy -c \"cd %s; hg tip | grep changeset | cut -d':' -f2,3\"" % (paths.P_SU, paths.P_GALAXY_HOME)
        process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out = process.communicate()
        if out[1] != '':
            rev = 'N/A'
        else:
            rev = out[0].strip()
        return rev 
    
    def get_galaxy_admins(self):
        admins = 'None'
        try:
            config_file = open(os.path.join(paths.P_GALAXY_HOME, 'universe_wsgi.ini'), 'r').readlines()
            for line in config_file:
                if 'admin_users' in line:
                    admins = line.split('=')[1].strip()
                    break
        except IOError:
            pass
        return admins
    
    def get_permanent_storage_size( self ):
        pss = 0
        fs_arr = [s for s in self.services if s.svc_type=='Filesystem' and s.name=='galaxyData']
        for fs in fs_arr:
            for vol in fs.volumes:
                pss += int(vol.size)
        return pss
    
    def check_disk(self):
        try:
            fs_arr = [s for s in self.services if s.svc_type=='Filesystem' and s.name=='galaxyData']
            if len(fs_arr)>0:
                disk_usage = commands.getoutput("df -h | grep galaxyData | awk '{print $2, $3, $5}'")
                disk_usage = disk_usage.split(' ')
                if len(disk_usage) == 3:
                    self.disk_total = disk_usage[0]
                    self.disk_used = disk_usage[1]
                    self.disk_pct = disk_usage[2]
        except Exception, e:
            log.error("Failure checking disk usage.  %s" % e)
    
    def get_cluster_status( self ):
        return self.cluster_status
    
    def get_instance_state( self ):
        return self.master_state
    
    def get_worker_instances( self ):
        instances = []
        if self.app.TESTFLAG is True:
            # for i in range(5):
            #     instance = Instance( self.app, inst=None, m_state="Pending" )
            #     instance.id = "WorkerInstance"
            #     instances.append(instance)
            return instances
        log.debug("Trying to discover any worker instances associated with this cluster...")
        filters = {'tag:clusterName': self.app.ud['cluster_name'], 'tag:role': 'worker'}
        try:
            ec2_conn = self.app.cloud_interface.get_ec2_connection()
            reservations = ec2_conn.get_all_instances(filters=filters)
            for reservation in reservations:
                if reservation.instances[0].state != 'terminated' and reservation.instances[0].state != 'shutting-down':
                    i = Instance(self.app, inst=reservation.instances[0], m_state=reservation.instances[0].state, reboot_required=True)
                    instances.append(i)
                    log.info( "Instance '%s' found alive (will configure it later)." % reservation.instances[0].id)
        except EC2ResponseError, e:
            log.debug( "Error checking for live instances: %s" % e )
        return instances
    
    def get_attached_volumes(self):
        """Get a list of EBS volumes attached to the current instance."""
        volumes = []
        if self.app.TESTFLAG is True:
            return volumes
        log.debug("Trying to discover any volumes attached to this instance...")
        try:
            f = {'attachment.instance-id': self.app.cloud_interface.get_instance_id()}
            volumes = self.app.cloud_interface.get_ec2_connection().get_all_volumes(filters=f)
        except EC2ResponseError, e:
            log.debug( "Error checking for attached volumes: %s" % e )
        log.debug("Attached volumes: %s" % volumes)
        return volumes
    
    def shutdown(self, sd_galaxy=True, sd_sge=True, sd_postgres=True, sd_filesystems=True, sd_instances=True, sd_autoscaling=True, delete_cluster=False):
        if self.app.TESTFLAG is True:
            log.debug("Shutting down the cluster but the TESTFLAG is set")
            return
        log.debug("List of services before shutdown: %s" % [s.get_full_name() for s in self.services])
        # Services need to be shut down in particular order
        if sd_autoscaling:
            self.stop_autoscaling()
        if sd_galaxy:
            svcs = self.get_services('Galaxy')
            for service in svcs:
                service.remove()
        if sd_postgres:
            svcs = self.get_services('Postgres')
            for service in svcs:
                service.remove()
        if sd_instances:
            self.stop_worker_instances()
        if sd_filesystems:
            svcs = self.get_services('Filesystem')
            to_remove = []
            for service in svcs:
                to_remove.append(service)
            for service in to_remove:
                log.debug("Requesting removal of '%s' as part of shutdown" % service.get_full_name())
                service.remove()
        if sd_sge:
            svcs = self.get_services('SGE')
            for service in svcs:
                service.remove()
        if delete_cluster:
            self.delete_cluster()
        self.cluster_status = cluster_status.SHUT_DOWN
        self.master_state = master_states.SHUT_DOWN
        log.info( "Cluster shut down at %s (uptime: %s). If not done automatically, manually terminate the master instance (and any remaining instances associated with this cluster) from the AWS console." % (dt.datetime.utcnow(), (dt.datetime.utcnow()-self.startup_time)))
    
    def reboot(self):
        if self.app.TESTFLAG is True:
            log.debug("Restart the cluster but the TESTFLAG is set")
            return False
        self.shutdown(sd_filesystems=False, sd_instances=False)
        ec2_conn = self.app.cloud_interface.get_ec2_connection()
        try:
            ec2_conn.reboot_instances([self.app.cloud_interface.get_instance_id()])
            return True
        except EC2ResponseError, e:
            log.error("Error rebooting master instance (i.e., self): %s" % e)
        return False
    
    def terminate_master_instance(self, delete_cluster=False):
        if not (self.cluster_status == cluster_status.SHUT_DOWN and self.master_state == master_states.SHUT_DOWN):
            self.shutdown(delete_cluster=delete_cluster)
        ec2_conn = self.app.cloud_interface.get_ec2_connection()
        try:
            ec2_conn.terminate_instances([self.app.cloud_interface.get_instance_id()])
        except EC2ResponseError, e:
            log.error("Error terminating master instance (i.e., self): %s" % e)
    
    def delete_cluster(self):
        log.info("All services shut down; deleting this cluster.")
        # Delete any remaining volume(s) assoc. w/ given cluster
        filters = {'tag:clusterName': self.app.ud['cluster_name']}
        try:
            ec2_conn = self.app.cloud_interface.get_ec2_connection()
            vols = ec2_conn.get_all_volumes(filters=filters)
            for vol in vols:
                log.debug("As part of cluster deletion, deleting volume '%s'" % vol.id)
                ec2_conn.delete_volume(vol.id)
        except EC2ResponseError, e:
            log.error("Error deleting volume %s: %s" % (vol.id, e))
        # Delete cluster bucket on S3
        s3_conn = self.app.cloud_interface.get_s3_connection()
        misc.delete_bucket(s3_conn, self.app.ud['bucket_cluster'])
    
    def clean(self):
        """ Clean the system as if it was freshly booted. All services are shut down 
        and any changes made to the system since service start are reverted (this exludes
        any data on user data file system)"""
        log.debug("Cleaning the system - all services going down")
        svcs = self.get_services('Galaxy')
        for service in svcs:
            service.remove()
        svcs = self.get_services('Postgres')
        for service in svcs:
            service.remove()
        self.stop_worker_instances()
        svcs = self.get_services('Filesystem')
        for service in svcs:
            service.clean()
        svcs = self.get_services('SGE')
        for service in svcs:
            service.clean()
    
    def set_master_state(self, new_state):
        log.debug( "Setting master state to '%s'" % new_state )
        self.master_state = new_state
    
    def get_idle_instances( self ):
        # log.debug( "Looking for idle instances" )
        idle_instances = [] # List of Instance objects corresponding to idle instances
        if os.path.exists('%s/default/common/settings.sh' % paths.P_SGE_ROOT):
            proc = subprocess.Popen( "export SGE_ROOT=%s; . $SGE_ROOT/default/common/settings.sh; %s/bin/lx24-amd64/qstat -f | grep all.q" % (paths.P_SGE_ROOT, paths.P_SGE_ROOT), shell=True, stdout=subprocess.PIPE )
            qstat_out = proc.communicate()[0]
            # log.debug( "qstat output: %s" % qstat_out )
            instances = qstat_out.splitlines()
            nodes_list = [] # list of nodes containing node's domain name and number of used processing slots
            idle_instances_dn = [] # list of domain names of idle instances 
            for inst in instances:
                nodes_list.append( inst.split( '@' )[1].split( ' ' )[0] + ':' + inst.split( '/' )[1] ) # Get instance domain name and # of used processing slots, e.g., ['domU-12-31-38-00-48-D1.c:0'] 
            # if len( nodes_list ) > 0:
            #     log.debug( "Processed qstat output: %s" % nodes_list )
        
            for node in nodes_list:
                # If number of used slots on given instance is 0, mark it as idle
                if int( node.split( ':' )[1] ) == 0:
                    idle_instances_dn.append( node.split( ':' )[0] )
            # if len( idle_instances_dn ) > 0:
            #     log.debug( "Idle instances' DNs: %s" % idle_instances_dn )
        
            for idle_instance_dn in idle_instances_dn:
                 for w_instance in self.worker_instances:
                     # log.debug( "Trying to match worker instance with private IP '%s' to idle instance '%s'" % ( w_instance.get_private_ip(), idle_instance_dn) )
                     if w_instance.get_private_ip() is not None:
                         if w_instance.get_private_ip().lower().startswith( str(idle_instance_dn).lower() ) is True:
                            # log.debug( "Marking instance '%s' with FQDN '%s' as idle." % ( w_instance.id, idle_instance_dn ) )
                            idle_instances.append( w_instance )
        return idle_instances
    
    def remove_instances(self, num_nodes, force=False):
        # Decide which instance(s) to terminate, remove the from SGE and terminate
        idle_instances = self.get_idle_instances()
        log.info( "Found '%s' idle instances; trying to remove '%s'" % ( len( idle_instances ), num_nodes ) )
        num_terminated = 0
        for i in range ( 0, num_nodes ):
            if len( idle_instances ) > 0:
                for inst in idle_instances:
                    if num_terminated < num_nodes:
                        self.remove_instance(inst.id)
                        num_terminated += 1
            else:
                log.info( "No idle instances found")
        log.debug("Num to terminate: %s, num terminated: %s; force set to '%s'" % (num_nodes, num_terminated, force))
        if force is True and num_terminated < num_nodes:
            force_kill_instances = num_nodes - num_terminated
            log.info( "Forcefully terminating '%s' instances" % force_kill_instances )
            for i in range( 0, force_kill_instances ):
                for inst in self.worker_instances:
                    self.remove_instance(inst.id)
                    num_terminated += 1
        if num_terminated > 0:
            log.info( "Initiated requested termination of instances. Terminating '%s' instances." % num_terminated )
        else:
            log.info( "Did not terminate any instances." )
    
    def remove_instance( self, instance_id='' ):
        if instance_id == '':
            log.warning("Tried to remove an instance but did not receive instance ID")
            return False
        log.info( "Specific termination of instance '%s' requested." % instance_id)
        for inst in self.worker_instances:
            if inst.id == instance_id:
                sge_svc = self.get_services('SGE')[0]
                # DBTODO Big problem here if there's a failure removing from allhosts.  Need to handle it.
                # if sge_svc.remove_sge_host(inst) is True:
                # Best-effort PATCH until above issue is handled
                sge_svc.remove_sge_host(inst)
                inst.terminate()
                if inst in self.worker_instances:
                    self.worker_instances.remove(inst)
        log.info( "Initiated requested termination of instance. Terminating '%s'." % instance_id )
    
    def add_instances( self, num_nodes, instance_type=''):
        num_nodes = int( num_nodes )
        ec2_conn = self.app.cloud_interface.get_ec2_connection()
        log.info( "Adding %s instance(s)..." % num_nodes )
        # Compose worker instance user data 
        worker_ud = {}
        worker_ud['access_key'] = self.app.ud['access_key']
        worker_ud['secret_key'] = self.app.ud['secret_key']
        if self.app.ud.has_key('password'):
            worker_ud['password'] = self.app.ud['password']
        worker_ud['cluster_name'] = self.app.ud['cluster_name']
        worker_ud['role'] = 'worker'
        worker_ud['master_ip'] = self.app.cloud_interface.get_self_private_ip()
        worker_ud_str = "\n".join(['%s: %s' % (key, value) for key, value in worker_ud.iteritems()])
        #log.debug( "Worker user data: %s " % worker_ud )
        reservation = None
        if instance_type == '':
            instance_type = self.app.cloud_interface.get_type()
        log.debug( "Using following command: ec2_conn.run_instances( image_id='%s', min_count=1, max_count='%s', key_name='%s', security_groups=['%s'], user_data=[%s], instance_type='%s', placement='%s' )"
               % ( self.app.cloud_interface.get_ami(), num_nodes, self.app.cloud_interface.get_key_pair_name(), ", ".join( self.app.cloud_interface.get_security_groups() ), worker_ud_str, instance_type, self.app.cloud_interface.get_zone() ) )
        try:
            # log.debug( "Would be starting worker instance(s)..." )
            reservation = ec2_conn.run_instances( image_id=self.app.cloud_interface.get_ami(),
                                                  min_count=1,
                                                  max_count=num_nodes,
                                                  key_name=self.app.cloud_interface.get_key_pair_name(),
                                                  security_groups=self.app.cloud_interface.get_security_groups(),
                                                  user_data=worker_ud_str,
                                                  instance_type=instance_type,
                                                  placement=self.app.cloud_interface.get_zone() )
            time.sleep(3) # Rarely, instances take a bit to register, so wait a few seconds (although this is a very poor 'solution')
            if reservation:
                for instance in reservation.instances:
                    self.app.cloud_interface.add_tag(instance, 'clusterName', self.app.ud['cluster_name'])
                    self.app.cloud_interface.add_tag(instance, 'role', worker_ud['role'])
                    i = Instance( self.app, inst=instance, m_state=instance.state )
                    self.worker_instances.append( i )
        except BotoServerError, e:
            log.error( "boto server error when starting an instance: %s" % str( e ) )
            return False
        except EC2ResponseError, e:
            err = "EC2 response error when starting worker nodes: %s" % str( e )
            log.error( err )
            return False
            # Update cluster status
            # self.master_state = master_states.ERROR
            # self.console_monitor.last_state_change_time = dt.datetime.utcnow()
            # log.debug( "Changed state to '%s'" % self.master_state )
        except Exception, ex:
            err = "Error when starting worker nodes: %s" % str( ex )
            log.error( err )
            return False
            # self.master_state = master_states.ERROR
            # self.console_monitor.last_state_change_time = dt.datetime.utcnow()
            # log.debug( "Changed state to '%s'" % self.master_state )
        
        log.debug( "Started %s instance(s)" % num_nodes )
        return True
    
    def add_live_instance(self, instance_id):
        """ Add an instance to the list of worker instances; get a handle to the
        instance object in the process. """
        try:
            log.debug("Adding live instance '%s'" % instance_id)
            ec2_conn = self.app.cloud_interface.get_ec2_connection()
            reservation = ec2_conn.get_all_instances([instance_id])
            if reservation and len(reservation[0].instances)==1:
                instance = reservation[0].instances[0]
                if instance.state != 'terminated' and instance.state != 'shutting-down':
                    i = Instance(self.app, inst=instance, m_state=instance.state)
                    self.app.cloud_interface.add_tag(instance, 'clusterName', self.app.ud['cluster_name'])
                    self.app.cloud_interface.add_tag(instance, 'role', 'worker') # Default to 'worker' role tag
                    self.worker_instances.append(i)
                else:
                    log.debug("Live instance '%s' is at the end of its life (state: %s); not adding the instance." % (instance_id, instance.state))
                return True
        except EC2ResponseError, e:
            log.debug("Problem adding a live instance (tried ID: %s): %s" % (instance_id, e))
        return False
    
    def init_cluster(self, cluster_type, pss = None):
        """ Initialize a cluster. This implies starting requested services and 
        storing cluster configuration into cluster's bucket.
        
        :type cluster_type: string
        :param cluster_type: Type of cluster being setup. Currently, accepting
            values: 'Galaxy' and 'Data'
        
        :type pss: int
        :param pss: Persistent Storage Size associated with data volumes being 
            created for the given cluster
        """
        if self.app.TESTFLAG is True:
            log.debug("Attempted to initialize a new cluster of type '%s', but TESTFLAG is set." % cluster_type)
            return
        self.app.manager.initial_cluster_type = cluster_type
        log.info("Initializing a '%s' cluster." % cluster_type)
        if cluster_type == 'Galaxy':
            # Add required services:
            # Static data - get snapshot IDs from the default bucket and add respective file systems
            s3_conn = self.app.cloud_interface.get_s3_connection()
            snaps_file = 'cm_snaps.yaml'
            snaps = None
            if self.app.ud.has_key('static_filesystems'):
                snaps = self.app.ud['static_filesystems']                
            elif misc.get_file_from_bucket(s3_conn, self.app.ud['bucket_default'], 'snaps.yaml', snaps_file):
                snaps_file = misc.load_yaml_file(snaps_file)
                snaps = snaps_file['static_filesystems']
            if snaps:
                attached_volumes = self.get_attached_volumes()
                for snap in snaps:
                    fs = Filesystem(self.app, snap['filesystem'])
                    # Check if an already attached volume maps to the current filesystem
                    att_vol = self.get_vol_if_fs(attached_volumes, snap['filesystem'])
                    if att_vol:
                        fs.add_volume(vol_id=att_vol.id, size=att_vol.size, from_snapshot_id=att_vol.snapshot_id)
                    else:
                        fs.add_volume(size=snap['size'], from_snapshot_id=snap['snap_id'])
                    log.debug("Adding static filesystem: '%s'" % snap['filesystem'])
                    self.services.append(fs)
            # User data - add a new file system for user data of size 'pss'                    
            fs_name = 'galaxyData'
            log.debug("Creating a new data filesystem: '%s'" % fs_name)
            fs = Filesystem(self.app, fs_name)
            fs.add_volume(size=pss)
            self.services.append(fs)
            # PostgreSQL
            self.services.append(PostgresService(self.app))
            # Galaxy
            self.services.append(GalaxyService(self.app))
        elif cluster_type == 'Data':
            # Add required services:
            # User data - add a new file system for user data of size 'pss'                    
            fs_name = 'galaxyData'
            log.debug("Creating a new data filesystem: '%s'" % fs_name)
            fs = Filesystem(self.app, fs_name)
            fs.add_volume(size=pss)
            self.services.append(fs)
        elif cluster_type == 'SGE':
            # Nothing to do special?
            pass
        else:
            log.error("Tried to initialize a cluster but received unknown configuration: '%s'" % cluster_type)
    
    def init_shared_cluster(self, shared_cluster_config):
        if self.app.TESTFLAG is True:
            log.debug("Attempted to initialize a shared cluster from bucket '%s', but TESTFLAG is set." % shared_cluster_config)
            return
        log.debug("Initializing a shared cluster from '%s'" % shared_cluster_config)
        s3_conn = self.app.cloud_interface.get_s3_connection()
        ec2_conn = self.app.cloud_interface.get_ec2_connection()
        try:
            shared_cluster_config = shared_cluster_config.strip('/')
            bucket_name = shared_cluster_config.split('/')[0]
            cluster_config_prefix = os.path.join(shared_cluster_config.split('/')[1], shared_cluster_config.split('/')[2])
        except Exception, e:
            log.error("Error while parsing provided shared cluster's bucket '%s': %s" % (shared_cluster_config, e))
            return False
        # Check shared cluster's bucket exists
        if not misc.bucket_exists(s3_conn, bucket_name, validate=False):
            log.error("Shared cluster's bucket '%s' does not exist or is not accessible!" % bucket_name)
            return False
        # Create the new cluster's bucket
        if not misc.bucket_exists(s3_conn, self.app.ud['bucket_cluster']):
            misc.create_bucket(s3_conn, self.app.ud['bucket_cluster'])
        # Copy contents of the shared cluster's bucket to current cluster's bucket
        fl = "shared_instance_file_list.txt"
        if misc.get_file_from_bucket(s3_conn, bucket_name, os.path.join(cluster_config_prefix, fl), fl, validate=False):
            key_list = misc.load_yaml_file(fl)
            for key in key_list:
                misc.copy_file_in_bucket(s3_conn, bucket_name, self.app.ud['bucket_cluster'], key, key.split('/')[-1], preserve_acl=False, validate=False)
        else:
            log.error("Problem copying shared cluster configuration files. Cannot continue with shared cluster initialization.")
            return False
        # Create a volume from shared cluster's data snap and set current cluster's data volume
        shared_cluster_pd_file = 'shared_p_d.yaml'
        if misc.get_file_from_bucket(s3_conn, self.app.ud['bucket_cluster'], 'persistent_data.yaml', shared_cluster_pd_file):
            scpd = misc.load_yaml_file(shared_cluster_pd_file)
            if scpd.has_key('shared_data_snaps'):
                shared_data_vol_snaps = scpd['shared_data_snaps']
                try:
                    # TODO: If support for multiple volumes comprising a file system becomes available, 
                    # this code will need to adjusted to accomodate that. Currently, the assumption is
                    # that only 1 snap ID will be provided as the data file system.
                    snap = ec2_conn.get_all_snapshots(shared_data_vol_snaps)[0]
                    data_vol = ec2_conn.create_volume(snap.volume_size, self.app.cloud_interface.get_zone(), snapshot=snap)
                    scpd['data_filesystems'] = {'galaxyData': [{'vol_id': data_vol.id, 'size': data_vol.size}]}
                    log.info("Created a data volume '%s' of size %sGB from shared cluster's snapshot '%s'" % (data_vol.id, data_vol.size, snap.id))
                    # Don't make the new cluster shared by default
                    del scpd['shared_data_snaps']
                    # Update new cluster's persistent_data.yaml
                    cc_file_name = 'cm_cluster_config.yaml'
                    misc.dump_yaml_to_file(scpd, cc_file_name)
                    misc.save_file_to_bucket(s3_conn, self.app.ud['bucket_cluster'], 'persistent_data.yaml', cc_file_name)
                except EC2ResponseError, e:
                    log.error("EC2 error creating volume from shared cluster's snapshot '%s': %s" % (shared_data_vol_snaps, e))
                    return False
                except Exception, e:
                    log.error("Error creating volume from shared cluster's snapshot '%s': %s" % (shared_data_vol_snaps, e))
                    return False
            else:
                log.error("Loaded configuration from the shared cluster does not have a reference to a shared data snapshot. Cannot continue.")
                return False
        # Reload user data and start the cluster as normally would
        self.app.ud = self.app.cloud_interface.get_user_data(force=True)
        if misc.get_file_from_bucket(s3_conn, self.app.ud['bucket_cluster'], 'persistent_data.yaml', 'pd.yaml'):
            pd = misc.load_yaml_file('pd.yaml')
            self.app.ud = misc.merge_yaml_objects(self.app.ud, pd)
        self.add_preconfigured_services()
        # In case post_start_script was provided in the shared cluster, run the service again
        self.app.manager.services.append(PSS(self.app))
    
    def share_a_cluster(self, user_ids=None, cannonical_ids=None):
        """
        Setup the environment to make the current cluster shared (via a shared  
        EBS snapshot).
        This entails stopping all services to enable creation of a snapshot of 
        the data volume, allowing others to create a volume from the created
        snapshot as well giving read permissions to cluster's bucket. If user_ids
        are not provided, the bucket and the snapshot are made public.
        
        :type user_ids: list
        :param user_ids: The numeric Amazon IDs of users (with no dashes) to 
                         give read permissions to the bucket and snapshot
        """
        if self.app.TESTFLAG is True:
            log.debug( "Attempted to share-an-instance, but TESTFLAG is set.")
            return {}
        # TODO: recover services if the process fails midway
        log.info("Setting up the cluster for sharing")
        self.cluster_manipulation_in_progress = True
        self._stop_app_level_services()
        
        # Initiate snapshot of the galaxyData file system
        snap_ids=[]
        svcs = self.app.manager.get_services('Filesystem')
        for svc in svcs:
            if svc.name == 'galaxyData':
                snap_ids = svc.snapshot(snap_description="CloudMan share-a-cluster %s; %s" \
                    % (self.app.ud['cluster_name'], self.app.ud['bucket_cluster']))
        
        # Create a new folder-like structure inside cluster's bucket and copy 
        # cluster conf files
        s3_conn = self.app.cloud_interface.get_s3_connection()
        # All of the shared cluster's config files will be stored with the specified prefix
        shared_names_root = "shared/%s" % dt.datetime.utcnow().strftime("%Y-%m-%d--%H-%M")
        # Create current cluster config and save it to cluster's shared location,
        # including the freshly generated snap IDs
        # snap_ids = ['snap-04c01768'] # For testing only
        conf_file_name = 'cm_shared_cluster_conf.yaml'
        snaps = {'shared_data_snaps': snap_ids}
        self.console_monitor.create_cluster_config_file(conf_file_name, addl_data=snaps)
        # Remove references to cluster's own data volumes
        sud = misc.load_yaml_file(conf_file_name)
        if sud.has_key('data_filesystems'):
            del sud['data_filesystems']
            misc.dump_yaml_to_file(sud, conf_file_name)
        misc.save_file_to_bucket(s3_conn, self.app.ud['bucket_cluster'], os.path.join(shared_names_root, 'persistent_data.yaml'), conf_file_name)
        # Keep track of which keys were copied into shared folder
        copied_key_names = [os.path.join(shared_names_root, 'persistent_data.yaml')]
        # Save remaining cluster configuration files 
        # conf_files = ['universe_wsgi.ini.cloud', 'tool_conf.xml.cloud', 'tool_data_table_conf.xml.cloud', 'cm.tar.gz', self.app.ud['boot_script_name']]
        try:
            # Get a list of all files stored in cluster's bucket excluding 
            # any keys that include '/' (i.e., are folders) or the previously 
            # copied 'persistent_data.yaml'. This way, if the number of config 
            # files changes in the future, this will still work
            b = s3_conn.lookup(self.app.ud['bucket_cluster'])
            keys = b.list(delimiter='/')
            conf_files = []
            for key in keys:
                if '/' not in key.name and 'persistent_data.yaml' not in key.name:
                    conf_files.append(key.name)
        except S3ResponseError, e:
            log.error("Error collecting cluster configuration files form bucket '%s': %s" % (self.app.ud['bucket_cluster'], e))
            return False
        # Copy current cluster's configuration files into the shared folder
        for conf_file in conf_files:
            if 'clusterName' not in conf_file: # Skip original cluster name file
                misc.copy_file_in_bucket(s3_conn, 
                                         self.app.ud['bucket_cluster'],
                                         self.app.ud['bucket_cluster'], 
                                         conf_file, os.path.join(shared_names_root, conf_file), 
                                         preserve_acl=False)
                copied_key_names.append(os.path.join(shared_names_root, conf_file))
        # Save the list of files contained in the shared bucket so derivative 
        # instances can know what to get with minimim permissions
        fl = "shared_instance_file_list.txt"
        misc.dump_yaml_to_file(copied_key_names, fl)
        misc.save_file_to_bucket(s3_conn, self.app.ud['bucket_cluster'], os.path.join(shared_names_root, fl), fl)
        copied_key_names.append(os.path.join(shared_names_root, fl)) # Add it to the list so it's permissions get set
        
        # Adjust permissions on the new keys and the created snapshots
        ec2_conn = self.app.cloud_interface.get_ec2_connection()
        for snap_id in snap_ids:
            try:
                if user_ids:
                    log.debug("Adding createVolumePermission for snap '%s' for users '%s'" % (snap_id, user_ids))
                    ec2_conn.modify_snapshot_attribute(snap_id, attribute='createVolumePermission', operation='add', user_ids=user_ids)
                else:
                    ec2_conn.modify_snapshot_attribute(snap_id, attribute='createVolumePermission', operation='add', groups=['all'])
            except EC2ResponseError, e:
                log.error("Error modifying snapshot '%s' attribute: %s" % (snap_id, e))
        err = False
        if cannonical_ids:
            # In order to list the keys associated with a shared instance, a user
            # must be given READ permissions on the cluster's bucket as a whole.
            # This allows a given user to list the contents of a bucket but not
            # access any of the keys other than the ones granted the permission 
            # next (i.e., keys required to bootstrap the shared instance)
            # misc.add_bucket_user_grant(s3_conn, self.app.ud['bucket_cluster'], 'READ', cannonical_ids, recursive=False)
            # Grant READ permissions for the keys required to bootstrap the shared instance
            for k_name in copied_key_names:
                if not misc.add_key_user_grant(s3_conn, self.app.ud['bucket_cluster'], k_name, 'READ', cannonical_ids):
                    log.error("Error adding READ permission for key '%s'" % k_name)
                    err = True
        else: # If no cannonical_ids are provided, means to set the permissions to public-read
            # See above, but in order to access keys, the bucket root must be given read permissions
            # FIXME: this method sets the bucket's grant to public-read and 
            # removes any individual user's grants - something share-in-instance
            # depends on down the line if the publicly shared instance is deleted
            # misc.make_bucket_public(s3_conn, self.app.ud['bucket_cluster'])
            for k_name in copied_key_names:
                if not misc.make_key_public(s3_conn, self.app.ud['bucket_cluster'], k_name):
                    log.error("Error making key '%s' public" % k_name)
                    err = True
        if err:
            # TODO: Handle this with more user input?
            log.error("Error modifying permissions for keys in bucket '%s'" % self.app.ud['bucket_cluster'])
        
        self._start_app_level_services()
        self.cluster_manipulation_in_progress = False
        return True
    
    def get_shared_instances(self):
        lst = []
        if self.app.TESTFLAG is True:
            lst.append({"bucket": "cm-7834hdoeiuwha/TESTshare/2011-08-14--03-02/", "snap": 'snap-743ddw12', "visibility": 'Shared'})
            lst.append({"bucket": "cm-7834hdoeiuwha/TESTshare/2011-08-19--10-49/", "snap": 'snap-gf69348h', "visibility": 'Public'})
            return lst
        try:
            s3_conn = self.app.cloud_interface.get_s3_connection()
            b = misc.get_bucket(s3_conn, self.app.ud['bucket_cluster'])
            if b:
                # Get a list of shared 'folders' containing clusters' configuration
                folder_list = b.list(prefix='shared/', delimiter='/')
                for folder in folder_list:
                    # Get snapshot assoc. with the current shared cluster
                    tmp_pd = 'tmp_pd.yaml'
                    if misc.get_file_from_bucket(s3_conn, self.app.ud['bucket_cluster'], os.path.join(folder.name, 'persistent_data.yaml'), tmp_pd):
                        tmp_ud = misc.load_yaml_file(tmp_pd)
                        if tmp_ud.has_key('shared_data_snaps') and len(tmp_ud['shared_data_snaps'])==1:
                            # Currently, only single data snapshot can be associated a shared instance to pull it out of the list
                            snap_id = tmp_ud['shared_data_snaps'][0]
                        else:
                            snap_id = "Missing-ERROR"
                        try:
                            os.remove(tmp_pd)
                        except OSError:
                            pass # Best effort temp file cleanup
                    else: 
                        snap_id = "Missing-ERROR"
                    # Get permission on the persistent_data file and assume all the entire cluster shares those permissions...
                    k = b.get_key(os.path.join(folder.name, 'persistent_data.yaml'))
                    if k is not None:
                        acl = k.get_acl()
                        if 'AllUsers' in str(acl):
                            visibility = 'Public'
                        else:
                            visibility = 'Shared'
                        lst.append({"bucket": os.path.join(self.app.ud['bucket_cluster'], folder.name), "snap": snap_id, "visibility": visibility})
        except S3ResponseError, e:
            log.error("Problem retrieving references to shared instances: %s" % e)
        return lst 
    
    def delete_shared_instance(self, shared_instance_folder, snap_id):
        """
        Deletes all files under shared_instance_folder (i.e., all keys with 
        'shared_instance_folder' as prefix) and snap_id, thus deleting the 
        shared instance of the given cluster.
        
        :type shared_instance_folder: str
        :param shared_instance_folder: Prefix for the shared cluster instance
            configuration (e.g., shared/2011-02-24--20-52/)
        
        :type snap_id: str
        :param snap_id: Snapshot ID to be deleted (e.g., snap-04c01768)
        """
        if self.app.TESTFLAG is True:
            log.debug("Tried deleting shared instance for folder '%s' and snap '%s' but TESTFLAG is set." % (shared_instance_folder, snap_id))
            return True
        log.debug("Calling delete shared instance for folder '%s' and snap '%s'" % (shared_instance_folder, snap_id))
        ok = True # Mark if encountered error but try to delete as much as possible
        try:
            s3_conn = self.app.cloud_interface.get_s3_connection()
            # Revoke READ grant for users associated with the instance
            # being deleted but do so only if the given users do not have 
            # access to any other shared instances.
            # users_whose_grant_to_remove = misc.get_users_with_grant_on_only_this_folder(s3_conn, self.app.ud['bucket_cluster'], shared_instance_folder)
            # if len(users_whose_grant_to_remove) > 0:
            #     misc.adjust_bucket_ACL(s3_conn, self.app.ud['bucket_cluster'], users_whose_grant_to_remove)
            # Remove keys and folder associated with the given shared instance
            b = misc.get_bucket(s3_conn, self.app.ud['bucket_cluster'])
            key_list = b.list(prefix=shared_instance_folder)
            for key in key_list:
                log.debug("As part of shared cluster instance deletion, deleting key '%s' from bucket '%s'" % (key.name, self.app.ud['bucket_cluster']))
                key.delete()
        except S3ResponseError, e:
            log.error("Problem deleting keys in '%s': %s" % (shared_instance_folder, e))
            ok = False
        # Delete the data snapshot associated with the shared instance being deleted
        try:
            ec2_conn = self.app.cloud_interface.get_ec2_connection()
            ec2_conn.delete_snapshot(snap_id)
            log.debug("As part of shared cluster instance deletion, deleted snapshot '%s'" % snap_id)
        except EC2ResponseError, e:
            log.error("As part of shared cluster instance deletion, problem deleting snapshot '%s': %s" % (snap_id, e))
            ok = False
        return ok
    
    def update_file_system(self, file_system_name):
        """ This method is used to update the underlying EBS volume/snapshot
        that is used to hold the provided file system. This is useful when
        changes have been made to the underlying file system and those changes
        wish to be preserved beyond the runtime of the current instance. After
        calling this method, terminating and starting the cluster instance over
        will preserve any changes made to the file system (provided the snapshot
        created via this method has not been deleted).
        The method performs the following steps:
        1. Suspend all application-level services
        2. Unmount and detach the volume associated with the file system
        3. Create a snapshot of the volume
        4. Delete references to the original file system's EBS volume
        5. Add a new reference to the created snapshot, which gets picked up
           by the monitor and a new volume is created and file system mounted
        6. Unsuspend services
        """
        if self.app.TESTFLAG is True:
            log.debug( "Attempted to update file system '%s', but TESTFLAG is set." % file_system_name)
            return None
        log.info("Initiating file system '%s' update." % file_system_name)
        self.cluster_manipulation_in_progress = True
        self._stop_app_level_services()
        
        # Initiate snapshot of the specified file system
        snap_ids=[]
        svcs = self.app.manager.get_services('Filesystem')
        found_fs_name = False # Flag to ensure provided fs name was actually found
        for svc in svcs:
            if svc.name == file_system_name:
                found_fs_name = True
                # Create a snapshot of the given volume/file system
                snap_ids = svc.snapshot(snap_description="File system '%s' from CloudMan instance '%s'; bucket: %s" \
                    % (file_system_name, self.app.ud['cluster_name'], self.app.ud['bucket_cluster']))
                # Remove the old volume by removing the entire service
                if len(snap_ids) > 0:
                    log.debug("Removing file system '%s' service as part of the file system update" \
                        % file_system_name)
                    svc.remove()
                    self.services.remove(svc)
                    log.debug("Creating file system '%s' from snaps '%s'" % (file_system_name, snap_ids))
                    fs = Filesystem(self.app, file_system_name)
                    for snap_id in snap_ids:
                        fs.add_volume(from_snapshot_id=snap_id)
                    self.services.append(fs)
                    # Monitor will pick up the new service and start it up but 
                    # need to wait until that happens before can add rest of 
                    # the services
                    while fs.state != service_states.RUNNING:
                        log.debug("Service '%s' not quite ready: '%s'" % (fs.get_full_name(), fs.state))
                        time.sleep(6)
        if found_fs_name:
            self._start_app_level_services()
            self.cluster_manipulation_in_progress = False
            log.info("File system '%s' update complete" % file_system_name)
            return True
        else:
            log.error("Did not find file system with name '%s'; update not performed." % file_system_name)
            return False
    
    def stop_worker_instances( self ):
        log.info( "Stopping all '%s' worker instance(s)" % len(self.worker_instances) )
        to_terminate = []
        for i in self.worker_instances:
            to_terminate.append(i)
        for inst in to_terminate:
            log.debug("Initiating termination of instance '%s'" % inst.id )
            inst.terminate()
            log.debug("Initiated termination of instance '%s'" % inst.id )
    
    def check_for_new_version_of_CM(self):
        """ Check revision metadata for CloudMan (CM) in user's bucket and the default CM bucket.
        :rtype: bool
        :return: If default revison number of CM is greater than user's version of CM, return True.
                 Else, return False
        """
        if self.app.TESTFLAG is True:
            log.debug( "Attempted to check for new version of CloudMan, but TESTFLAG is set." )
            return {} #{'default_CM_rev': '64', 'user_CM_rev':'60'} # For testing
        log.debug("Checking for new version of CloudMan")
        s3_conn = self.app.cloud_interface.get_s3_connection()
        user_CM_rev = misc.get_file_metadata(s3_conn, self.app.ud['bucket_cluster'], self.app.config.cloudman_source_file_name, 'revision')
        default_CM_rev = misc.get_file_metadata(s3_conn, self.app.ud['bucket_default'], self.app.config.cloudman_source_file_name, 'revision')
        log.debug("Revision number for user's CloudMan: '%s'; revision number for default CloudMan: '%s'" % (user_CM_rev, default_CM_rev))
        if user_CM_rev and default_CM_rev:
            try:
                if int(default_CM_rev) > int(user_CM_rev):
                    return {'default_CM_rev': default_CM_rev, 'user_CM_rev':user_CM_rev}
            except Exception:
                pass
        return {}
    
    def update_users_CM(self):
        """ If the revision number of CloudMan (CM) source file (as stored in file's metadata)
        in user's bucket is less than that of default CM, upload the new version of CM to 
        user's bucket. Note that the update will take effect only after the next cluster reboot.
        :rtype: bool
        :return: If update was successful, return True.
                 Else, return False
        """
        if self.app.TESTFLAG is True:
            log.debug( "Attempted to update CM, but TESTFLAG is set." )
            return None
        if self.check_for_new_version_of_CM():
            log.info("Updating CloudMan application source file in cluster's bucket '%s'. It will be automatically available the next this cluster is instantiated." % self.app.ud['bucket_cluster'] )
            s3_conn = self.app.cloud_interface.get_s3_connection()
            # Make a copy of the old/original CM source in cluster's bucket called 'copy_name'
            copy_name = "%s_%s" % (self.app.config.cloudman_source_file_name, dt.date.today())
            if misc.copy_file_in_bucket(s3_conn, self.app.ud['bucket_cluster'], self.app.ud['bucket_cluster'], self.app.config.cloudman_source_file_name, copy_name):
                # Copy over the default CM to cluster's bucket as self.app.config.cloudman_source_file_name
                if misc.copy_file_in_bucket(s3_conn, self.app.ud['bucket_default'], self.app.ud['bucket_cluster'], self.app.config.cloudman_source_file_name, self.app.config.cloudman_source_file_name):
                    return True
        return False
    
    def expand_user_data_volume(self, new_vol_size, snap_description=None, delete_snap=False):
        # Mark file system as needing to be expanded
        svcs = self.get_services('Filesystem')
        for svc in svcs:
            if svc.name == 'galaxyData':
                log.debug("Marking '%s' for expansion to %sGB with snap description '%s'" % (svc.get_full_name(), new_vol_size, snap_description))
                svc.grow = {'new_size': new_vol_size, 'snap_description': snap_description, 'delete_snap': delete_snap}
    
    def get_root_public_key( self ):
        if self.app.TESTFLAG is True:
            log.debug( "Attempted to get root public key, but TESTFLAG is set." )
            return "TESTFLAG_ROOTPUBLICKEY"
        if self.root_pub_key is None:
            if not os.path.exists( 'id_rsa'):
                log.debug( "Generating root user's public key..." )
                ret_code = subprocess.call( 'ssh-keygen -t rsa -N "" -f id_rsa', shell=True )
                if ret_code == 0:
                    log.info( "Successfully generated root user's public key." )
                    f = open( 'id_rsa.pub' )
                    self.root_pub_key = f.readline()
                    f.close()
                    # Must copy private key at least to /root/.ssh for passwordless login to work
                    shutil.copy2( 'id_rsa', '/root/.ssh/id_rsa' )
                    log.debug( "Successfully retrieved root user's public key from file." )
                else:
                    log.error( "Encountered a problem while creating root user's public key, process returned error code '%s'." % ret_code )
            else: # This is master restart, so 
                f = open( 'id_rsa.pub' )
                self.root_pub_key = f.readline()
                f.close()
                if not os.path.exists( '/root/.ssh/id_rsa' ):
                    # Must copy private key at least to /root/.ssh for passwordless login to work
                    shutil.copy2( 'id_rsa', '/root/.ssh/id_rsa' )
                log.info( "Successfully retrieved root user's public key from file." )
        return self.root_pub_key
    
    def save_host_cert( self, host_cert ):
        if self.app.TESTFLAG is True:
            log.debug( "Attempted to save host cert, but TESTFLAG is set." )
            return None
        log.debug( "Saving host certificate '%s'" % host_cert )
        log.debug( "Saving worker host certificate.")
        f = open( "/root/.ssh/known_hosts", 'a' )
        f.write( host_cert )
        f.close()
        return True
    
    def get_workers_status( self, worker_id=None ):
        """ 
        Retrieves current status of all worker instances or of only worker 
        instance whose ID was passed as the parameter. Returns a dict
        where instance ID's are the keys.
        """
        if self.app.TESTFLAG is True:
            log.debug( "Attempted to get worker status, but TESTFLAG is set." )
            return {}
        workers_status = {}
        if worker_id:
            log.info( "Checking status of instance '%s'" % worker_id )
            try:
                ec2_conn = self.app.cloud_interface.get_ec2_connection()
                reservation = ec2_conn.get_all_instances( worker_id.strip() )
                if reservation:
                    workers_status[ reservation[0].instances[0].id ] = reservation[0].instances[0].state
            except Exception, e:
                log.error( "Error while updating instance '%s' status: %s" % ( worker_id, e ) )
        else:
            logging.info( "Checking status of all worker nodes... " )
            for w_instance in self.app.manager.worker_instances:
                workers_status[ w_instance.id ] = w_instance.get_m_state()
        return workers_status
    
    def get_num_available_workers( self ):
        # log.debug("Gathering number of available workers" )
        num_available_nodes = 0
        for inst in self.worker_instances:
            if inst.node_ready is True:
                num_available_nodes += 1
        return num_available_nodes
    
    # ==========================================================================
    # ============================ UTILITY METHODS =============================
    # ==========================================================================          
    def _make_file_from_list(self, input_list, file_name, bucket_name=None):
        """Create a file from provided list so that each list element is
        printed on a separate line. If bucket_name parameter is provided,
        save created file to the bucket.
        
        :rtype: bool
        :return: True if a file was created and, if requested by provding 
        bucket name, successfully saved to the bucket. False if length of 
        provided list is 0 or bucket save fails.
        """
        if len(input_list) > 0:
            with open(file_name, 'w') as f:
                for el in input_list:
                    f.write("%s\n" % el)
            if bucket_name is not None:
                log.debug("Saving file '%s' created from list '%s' to user's bucket '%s'." % (file_name, input_list, bucket_name))
                s3_conn = self.app.cloud_interface.get_s3_connection()
                return misc.save_file_to_bucket(s3_conn, bucket_name, file_name, file_name)
        else:
            log.debug("Will not create file '%s' from provided list because the list is empty." % file_name)
            return False
        return True
    
    def _update_file(self, file_name, search_exp, replace_exp):
        """ Search file_name for a line containing search_exp and replace that 
        expression with replace_exp. 
        
        :type file_name: str
        :param file_name: Name of the file to modify
        :type search_exp: str
        :param search_exp: String for which to search 
        :type replace_exp: str
        :param replace_exp: String used to replace search string        
        """
        fin = open(file_name)
        fout = open("%s-tmp" % file_name, "w")
        for line in fin:
            fout.write(line.replace(search_exp, replace_exp))
        fin.close()
        fout.close()
        shutil.copy("%s-tmp" % file_name, file_name)
    
    def get_status_dict( self ):
        if self.app.TESTFLAG:
            num_cpus = 1
            load = "0.00 0.02 0.39"
            return {'id' : 'localtest', 'ld' : load, 'time_in_state' : misc.formatDelta(dt.datetime.utcnow() - self.startup_time), 'instance_type' : 'tester'}
        else:
            num_cpus = int(commands.getoutput( "cat /proc/cpuinfo | grep processor | wc -l" ))
            load = (commands.getoutput( "cat /proc/loadavg | cut -d' ' -f1-3" )).strip() # Returns system load in format "0.00 0.02 0.39" for the past 1, 5, and 15 minutes, respectivley
        if load != 0:
            lds = load.split(' ')
            if len(lds) == 3:
                load = "%s %s %s" % (float(lds[0]) / int(num_cpus), float(lds[1]) / int(num_cpus), float(lds[2]) / int(num_cpus))
            else:
                # Debug only, this should never happen.  If the interface is able to display this, there is load.
                load = "0 0 0"
        return  {'id' : self.app.cloud_interface.get_instance_id(), 'ld' : load, 'time_in_state' : misc.formatDelta(dt.datetime.utcnow() - self.startup_time), 'instance_type' : self.app.cloud_interface.get_type() }
    

class ConsoleMonitor( object ):
    def __init__( self, app ):
        self.app = app
        self.num_workers_processed = 0
        self.sge_was_setup = False
        self.last_state_change_time = None
        self.conn = comm.CMMasterComm()
        if not self.app.TESTFLAG:
            self.conn.setup()
        self.sleeper = misc.Sleeper()
        self.running = True
        self.prs_saved = False # A flag to indicate if 'post run script' has been updated in the cluster bucket
        self.monitor_thread = threading.Thread( target=self.__monitor )
    
    def start( self ):
        self.last_state_change_time = dt.datetime.utcnow()
        if not self.app.TESTFLAG:
            # Set 'role' and 'clusterName' tags for the master instance
            try:
                i_id = self.app.cloud_interface.get_instance_id()
                ec2_conn = self.app.cloud_interface.get_ec2_connection()
                ir = ec2_conn.get_all_instances([i_id])
                self.app.cloud_interface.add_tag(ir[0].instances[0], 'clusterName', self.app.ud['cluster_name'])
                self.app.cloud_interface.add_tag(ir[0].instances[0], 'role', self.app.ud['role'])
            except EC2ResponseError, e:
                log.debug("Error setting 'role' tag: %s" % e)
        self.monitor_thread.start()
    
    def shutdown( self ):
        """Attempts to gracefully shut down the worker thread"""
        log.info( "Stop signal received; deleting SQS queue..." )
        try:
            log.info( "Sending stop signal to worker thread" )
            if self.conn:
                self.conn.shutdown()
            self.running = False
            self.sleeper.wake()
            log.info( "Console manager stopped" )
        except:
            pass
    
    def update_instance_sw_state( self, inst_id, state ):
        """ 
        :type inst_id: string
        :type state: string 
        """
        log.debug( "Updating local ref to instance '%s' state to '%s'" % ( inst_id, state ) )
        for inst in self.app.manager.worker_instances:
            if inst.id == inst_id:
                inst.sw_state = state
    
    def expand_user_data_volume(self):
        # TODO: recover services if process fails midway
        log.info("Initiating user data volume resizing")
        self.app.manager._stop_app_level_services()
                
        # Grow galaxyData filesystem
        svcs = self.app.manager.get_services('Filesystem')
        for svc in svcs:
            if svc.name == 'galaxyData':
                log.debug("Expanding '%s'" % svc.get_full_name())
                svc.expand()
        
        self.app.manager._start_app_level_services()
        return True
    
    def create_cluster_config_file(self, file_name=None, addl_data=None):
        """ Take the current cluster service configuration and create a file 
        representation of it; by default, store the file in the current directory.
        
        :type file_name: string
        :param file_name: Name (or full path) of the file to save the configuration to
        
        :type addl_data: dict of strings
        :param addl_data: Any additional data to be included in the configuration
        
        :rtype: string
        :return: name of the newly created cluster configuration file 
        """
        try:
            cc = {} # cluster configuration
            svl = [] # static volume list
            dvd = {} # data volume dict
            if addl_data:
                cc = addl_data
            for srvc in self.app.manager.services:
                if srvc.svc_type=='Filesystem':
                    dvd_arr = []
                    for vol in srvc.volumes:
                        if vol.static and srvc.name!='galaxyData':
                            svl.append({'filesystem': srvc.name, 'snap_id': vol.get_from_snap_id(), 'size': int(vol.size)})
                        else:
                            dvd_arr.append({'vol_id': str(vol.volume_id), 'size': int(vol.size)})
                    if dvd_arr:
                        dvd[srvc.name] = dvd_arr
                else:
                    if cc.has_key('services'):
                        cc['services'].append({'service': srvc.svc_type})
                    else:
                        cc['services'] = [{'service':srvc.svc_type}]
            if svl: cc['static_filesystems'] = svl
            if dvd: cc['data_filesystems'] = dvd
            cc_file_name = file_name if file_name else 'cm_cluster_config.yaml'
            misc.dump_yaml_to_file(cc, cc_file_name)
            # Reload the user data object in case anything has changed
            self.app.ud = misc.merge_yaml_objects(cc, self.app.ud)
        except Exception, e:
            log.error("Problem creating cluster configuration file: '%s'" % e)
        return cc_file_name
    
    def store_cluster_config(self):
        """Create a cluster configuration file and store it into cluster bucket under name
        'persistent_data.yaml'. The cluster configuration is considered the set of currently
        seen services in the master. 
        In addition, local Galaxy configuration files, if they do not exist in 
        the cluster bucket, are saved to the bucket.
        """
        s3_conn = self.app.cloud_interface.get_s3_connection()
        if not misc.bucket_exists(s3_conn, self.app.ud['bucket_cluster']):
            misc.create_bucket(s3_conn, self.app.ud['bucket_cluster'])
        # Save/update the current Galaxy cluster configuration to cluster's bucket
        cc_file_name = self.create_cluster_config_file()
        misc.save_file_to_bucket(s3_conn, self.app.ud['bucket_cluster'], 'persistent_data.yaml', cc_file_name)
        # Ensure Galaxy config files are stored in the cluster's bucket, 
        # but only after Galaxy has been configured and is running (this ensures
        # that the configuration files get loaded from proper S3 bucket rather
        # than potentially being owerwritten by files that might exist on the snap)
        try:
            galaxy_svc = self.app.manager.get_services('Galaxy')[0]
            if galaxy_svc.running():
                for f_name in ['universe_wsgi.ini', 'tool_conf.xml', 'tool_data_table_conf.xml']:
                    if (not misc.file_exists_in_bucket(s3_conn, self.app.ud['bucket_cluster'], '%s.cloud' % f_name) and os.path.exists(os.path.join(paths.P_GALAXY_HOME, f_name))) or \
                       (misc.file_in_bucket_older_than_local(s3_conn, self.app.ud['bucket_cluster'], '%s.cloud' % f_name, os.path.join(paths.P_GALAXY_HOME, f_name))):
                        log.debug("Saving current Galaxy configuration file '%s' to cluster bucket '%s' as '%s.cloud'" % (f_name, self.app.ud['bucket_cluster'], f_name))
                        misc.save_file_to_bucket(s3_conn, self.app.ud['bucket_cluster'], '%s.cloud' % f_name, os.path.join(paths.P_GALAXY_HOME, f_name))
        except:
            pass
        # If not existent, save current boot script cm_boot.py to cluster's bucket
        if not misc.file_exists_in_bucket(s3_conn, self.app.ud['bucket_cluster'], self.app.ud['boot_script_name']) and os.path.exists(os.path.join(self.app.ud['boot_script_path'], self.app.ud['boot_script_name'])):
            log.debug("Saving current instance boot script (%s) to cluster bucket '%s' as '%s'" % (os.path.join(self.app.ud['boot_script_path'], self.app.ud['boot_script_name']), self.app.ud['bucket_cluster'], self.app.ud['boot_script_name']))
            misc.save_file_to_bucket(s3_conn, self.app.ud['bucket_cluster'], self.app.ud['boot_script_name'], os.path.join(self.app.ud['boot_script_path'], self.app.ud['boot_script_name']))
        # At start or local file update, save/update current post start script to cluster's bucket
        prs_filename = 'post_start_script'
        prs_file = os.path.join(self.app.ud['cloudman_home'], prs_filename)
        if misc.file_in_bucket_older_than_local(s3_conn, self.app.ud['bucket_cluster'], prs_filename, prs_file) or not self.prs_saved:
            # Also see cm_boot.sh because the name and the path of the post start
            # script must match what's used below!
            if os.path.exists(prs_file):
                log.debug("Saving current instance post start script (%s) to cluster bucket '%s' as '%s'" \
                    % (prs_file, self.app.ud['bucket_cluster'], prs_filename))
                if misc.save_file_to_bucket(s3_conn, self.app.ud['bucket_cluster'], prs_filename, prs_file):
                    self.prs_saved = True
            else:
                log.debug("No instance post start script (%s)" % prs_file)
        # If not existent, save CloudMan source to cluster's bucket, including file's metadata
        if not misc.file_exists_in_bucket(s3_conn, self.app.ud['bucket_cluster'], 'cm.tar.gz') and os.path.exists(os.path.join(self.app.ud['cloudman_home'], 'cm.tar.gz')):
            log.debug("Saving CloudMan source (%s) to cluster bucket '%s' as '%s'" % (os.path.join(self.app.ud['cloudman_home'], 'cm.tar.gz'), self.app.ud['bucket_cluster'], 'cm.tar.gz'))
            misc.save_file_to_bucket(s3_conn, self.app.ud['bucket_cluster'], 'cm.tar.gz', os.path.join(self.app.ud['cloudman_home'], 'cm.tar.gz'))
            try:
                with open(os.path.join(self.app.ud['cloudman_home'], 'cm_revision.txt'), 'r') as rev_file:
                    rev = rev_file.read()
                misc.set_file_metadata(s3_conn, self.app.ud['bucket_cluster'], 'cm.tar.gz', 'revision', rev)
            except Exception, e:
                log.debug("Error setting revision metadata on newly copied cm.tar.gz in bucket %s: %s" % (self.app.ud['bucket_cluster'], e))
        # Create an empty file whose name is the name of this cluster (useful as a reference)
        cn_file = os.path.join(self.app.ud['cloudman_home'], "%s.clusterName" % self.app.ud['cluster_name'])
        if not misc.file_exists_in_bucket(s3_conn, self.app.ud['bucket_cluster'], "%s.clusterName" % self.app.ud['cluster_name']):
            with open(cn_file, 'w'):
                pass
            if os.path.exists(cn_file):
                log.debug("Saving '%s' file to cluster bucket '%s' as '%s.clusterName'" % (cn_file, self.app.ud['bucket_cluster'], self.app.ud['cluster_name']))
                misc.save_file_to_bucket(s3_conn, self.app.ud['bucket_cluster'], "%s.clusterName" % self.app.ud['cluster_name'], cn_file)
    
    def __monitor( self ):
        timer = dt.datetime.utcnow()
        if self.app.manager.manager_started == False:
            if not self.app.manager.start():
                log.error("***** Manager failed to start *****")
                return False
        log.debug("Monitor started; manager started")
        while self.running:
            self.sleeper.sleep( 4 )
            if self.app.manager.cluster_status == cluster_status.SHUT_DOWN:
                self.running = False
                return
            # In case queue connection was not established, try again (this will happen if
            # RabbitMQ does not start in time for CloudMan)
            if not self.conn.is_connected():
                log.debug("Trying to setup AMQP connection; conn = '%s'" % self.conn)
                self.conn.setup()
                continue
            # Do periodic service state update
            if (dt.datetime.utcnow() - timer).seconds > 15:
                timer = dt.datetime.utcnow()
                self.app.manager.check_disk()
                for service in self.app.manager.services:
                    service.status()
                # Log current services' states (in condensed format)
                svcs_state = "S&S: "
                for s in self.app.manager.services:
                    svcs_state += "%s..%s; " % (s.get_full_name(), 'OK' if s.state=='Running' else s.state)
                log.debug(svcs_state)
            # Check and add any new services
            added_srvcs = False # Flag to indicate if cluster conf was changed
            for service in [s for s in self.app.manager.services if s.state == service_states.UNSTARTED]:
                added_srvcs = True
                log.debug("Monitor adding service '%s'" % service.get_full_name())
                service.add()
            # Store cluster conf after all services have been added.
            # NOTE: this flag relies on the assumption service additions are
            # sequential (i.e., monitor waits for the service add call to complete).
            # If any of the services are to be added via separate threads, a
            # system-wide flag should probably be maintained for that particular
            # service that would indicate the configuration of the service is
            # complete. This could probably be done by monitoring
            # the service state flag that is already maintained?
            if added_srvcs:
                self.store_cluster_config()
            # Check and grow file system
            svcs = self.app.manager.get_services('Filesystem')
            for svc in svcs:
                if svc.name == 'galaxyData' and svc.grow is not None:
                     self.expand_user_data_volume()
                     self.store_cluster_config()
            # Check status of worker instances
            for w_instance in self.app.manager.worker_instances:
                if w_instance.check_if_instance_alive() is False:
                    log.error( "Instance '%s' terminated prematurely. Removing from SGE and local instance list." % w_instance.id )
                    try:
                        sge_svc = self.app.manager.get_services('SGE')[0]
                        sge_svc.remove_sge_host(w_instance)
                    except IndexError:
                        # SGE not available yet?
                        #log.error("Could not get a handle on SGE service")
                        pass
                    # Remove reference to given instance object 
                    if w_instance in self.app.manager.worker_instances:
                        self.app.manager.worker_instances.remove( w_instance )
                elif w_instance.get_m_state() == 'running' and ( dt.datetime.utcnow() - w_instance.last_comm ).seconds > 15:
                    w_instance.send_status_check()
                if w_instance.reboot_required:
                    try:
                        ec2_conn = self.app.cloud_interface.get_ec2_connection()
                        log.debug("Instance '%s' reboot required. Rebooting now." % w_instance.id)
                        ec2_conn.reboot_instances([w_instance.id])
                        w_instance.reboot_required = False
                    except EC2ResponseError, e:
                        log.debug("Error rebooting instance '%s': %s" % (w_instance.id, e))
            m = self.conn.recv()
            while m is not None:
                def do_match():
                    match = False
                    for inst in self.app.manager.worker_instances:
                        if inst.id == m.properties['reply_to']:
                            match = True
                            inst.handle_message( m.body )
                    return match
                
                if not do_match():
                    log.debug( "No instance (%s) match found for message %s; will add instance now!" % ( m.properties['reply_to'], m.body ) )
                    if self.app.manager.add_live_instance(m.properties['reply_to']):
                        do_match()
                    else:
                        log.warning("Potential error, got message from instance '%s' but not aware of this instance. Ignoring the instance." % m.properties['reply_to'])
                m = self.conn.recv()
    

class Instance( object ):
    def __init__( self, app, inst=None, m_state=None, last_m_state_change=None, sw_state=None, reboot_required=False):
        self.app = app
        self.inst = inst
        self.id = None
        self.private_ip = None
        if inst:
            try:
                self.id = inst.id
            except EC2ResponseError, e:
                log.error( "Error retrieving instance id: %s" % e )
        self.m_state = m_state
        self.last_m_state_change = dt.datetime.utcnow()
        self.sw_state = sw_state
        self.is_alive = False
        self.node_ready = False
        self.num_cpus = 1
        self.time_rebooted = dt.datetime.utcnow()
        self.reboot_count = 0
        self.last_comm = dt.datetime.utcnow()
        self.nfs_data = 0
        self.nfs_tools = 0
        self.nfs_indices = 0
        self.nfs_sge = 0
        self.get_cert = 0
        self.sge_started = 0
        self.worker_status = 'Pending'
        self.load = 0
        self.type = 'Unknown'
        self.reboot_required = reboot_required
    
    def get_status_dict( self ):
        toret = {'id' : self.id, 
                 'ld' : self.load,
                 'time_in_state' : misc.formatDelta(dt.datetime.utcnow() - self.last_m_state_change), 
                 'nfs_data' : self.nfs_data, 
                 'nfs_tools' : self.nfs_tools, 
                 'nfs_indices' : self.nfs_indices, 
                 'nfs_sge' : self.nfs_sge, 
                 'get_cert' : self.get_cert, 
                 'sge_started' : self.sge_started, 
                 'worker_status' : self.worker_status,
                 'instance_state' : self.m_state,
                 'instance_type' : self.type}
                
        if self.load != 0:
            lds = self.load.split(' ')
            if len(lds) == 3:
                toret['ld'] = "%s %s %s" % (float(lds[0]) / self.num_cpus, float(lds[1]) / self.num_cpus, float(lds[2]) / self.num_cpus)
        return toret
    
    def get_status_array( self ):
        if self.m_state.lower() == "running": #For extra states.
            if self.is_alive is not True:
                ld = "Starting"
            elif self.load != 0:
                lds = self.load.split(' ')
                if len(lds) == 3:
                    try:
                        load1 = float(lds[0]) / self.num_cpus
                        load2 = float(lds[1]) / self.num_cpus
                        load3 = float(lds[2]) / self.num_cpus
                        ld = "%s %s %s" % (load1, load2, load3)
                    except Exception, e:
                        log.debug("Problems normalizing load: %s" % e)
                        ld = self.load
                else:
                    ld = self.load
            elif self.node_ready:
                ld = "Running"
            return [self.id, ld, misc.formatDelta(dt.datetime.utcnow() - self.last_m_state_change), self.nfs_data, self.nfs_tools, self.nfs_indices, self.nfs_sge, self.get_cert, self.sge_started, self.worker_status]
        else:
            return [self.id, self.m_state, misc.formatDelta(dt.datetime.utcnow() - self.last_m_state_change), self.nfs_data, self.nfs_tools, self.nfs_indices, self.nfs_sge, self.get_cert, self.sge_started, self.worker_status]
        
    def get_id( self ):
        if self.app.TESTFLAG is True:
            log.debug( "Attempted to get instance id, but TESTFLAG is set. Returning TestInstanceID" )
            return "TestInstanceID"
        if self.inst and not self.id:
            try:
                self.inst.update()
                self.id = self.inst.id
            except EC2ResponseError, e:
                log.error( "Error retrieving instance id: %s" % e )
        return self.id
    
    def terminate( self ):
        self.worker_status = "Stopping"
        t_thread = threading.Thread( target=self.__terminate )
        t_thread.start()
    
    def __terminate( self ):
        log.info ( "Terminating instance '%s'" % self.id )
        ec2_conn = self.app.cloud_interface.get_ec2_connection()
        inst_terminated = False
        try:
            ti = ec2_conn.terminate_instances( [self.id] )
            if ti:
                log.info( "Successfully initiated termination of instance '%s'" % self.id )
                for i in range( 0, 30 ):
                    if self.get_m_state() == 'terminated':
                        log.info ( "Instance '%s' successfully terminated." % self.id )
                        inst_terminated = True
                        try:
                            if self in self.app.manager.worker_instances:
                                self.app.manager.worker_instances.remove( self )
                                log.info ( "Instance '%s' removed from internal instance list." % self.id )
                        except ValueError, ve:
                            log.warning( "Instance '%s' no longer in instance list, global monitor probably picked it up and deleted it already: %s" % ( self.id, ve ) )
                        break
                    else:
                        time.sleep( 4 )
        except Exception, e:
            log.error( "Exception terminating instance '%s': %s" % ( self.id, e ) )
        if inst_terminated is False:
            log.error( "Terminating instance '%s' did not go smoothly; instance state: '%s'" % ( self.id, self.m_state ) )
    
    def instance_can_be_terminated( self ):
        log.debug( "Checking if instance '%s' can be terminated" % self.id )
        # TODO (qstat -qs {a|c|d|o|s|u|A|C|D|E|S})
        return False
    
    def get_m_state( self ):
        if self.app.TESTFLAG is True:
            return "running"
        if self.inst:
            try:
                self.inst.update()
                state = self.inst.state
                if state != self.m_state:
                    self.m_state = state
                    self.last_m_state_change = dt.datetime.utcnow()
            except EC2ResponseError, e:
                log.debug( "Error updating instance state: %s" % e )
        return self.m_state
    
    def send_status_check( self ):
        # log.debug("\tMT: Sending STATUS_CHECK message" )
        if self.app.TESTFLAG is True:
            return
        self.app.manager.console_monitor.conn.send( 'STATUS_CHECK', self.id )
        # log.debug( "\tMT: Message STATUS_CHECK sent; waiting on response" )
    
    def send_worker_restart( self ):
        # log.info("\tMT: Sending restart message to worker %s" % self.id)
        if self.app.TESTFLAG is True:
            return
        self.app.manager.console_monitor.conn.send( 'RESTART | %s' % self.app.cloud_interface.get_self_private_ip(), self.id )
        log.info( "\tMT: Sent RESTART message to worker '%s'" % self.id )
    
    def check_if_instance_alive( self ):
        # log.debug( "In '%s' state." % self.app.manager.master_state )
        # log.debug("\tMT: Waiting on worker instance(s) to start up (wait time: %s sec)..." % (dt.datetime.utcnow() - self.last_state_change_time).seconds )
        state = self.get_m_state()
        
        # Somtimes, an instance is terminated by Amazon prematurely so try to catch it 
        if state == 'terminated':
            log.error( "Worker instance '%s' seems to have terminated prematurely." % self.id )
            return False
        elif state == 'pending': # Display pending instances status to console log
            log.debug( "Worker instance '%s' status: '%s' (time in this state: %s sec)" % ( self.id, state, ( dt.datetime.utcnow() - self.last_m_state_change ).seconds ) )
        else:
            # log.debug( "Worker instance '%s' status: '%s' (time in this state: %s sec)" % ( self.id, state, ( dt.datetime.utcnow() - self.last_m_state_change ).seconds ) )
            pass
        if self.app.TESTFLAG is True:
            return True
        # If an instance has been in state 'running' for a while we still have not heard from it, check on it 
        # DBTODO Figure out something better for state management.
        if state == 'running' and not self.is_alive and (dt.datetime.utcnow()-self.last_m_state_change).seconds>400 and (dt.datetime.utcnow()-self.time_rebooted).seconds>300:
            if self.reboot_count < 4:
                log.info( "Instance '%s' not responding, rebooting instance..." % self.inst.id )
                self.inst.reboot()
                self.reboot_count += 1
                self.time_rebooted = dt.datetime.utcnow()
            else:
                log.info( "Instance '%s' not responding after %s reboots. Terminating instance..." % ( self.inst.id, self.reboot_count ) )
                self.terminate()
        return True
    
    def get_private_ip( self ):
        #log.debug("Getting instance '%s' private IP: '%s'" % ( self.id, self.private_ip ) )
        return self.private_ip
    
    def send_master_pubkey( self ):
#        log.info("\tMT: Sending MASTER_PUBKEY message: %s" % self.app.manager.get_root_public_key() )
        self.app.manager.console_monitor.conn.send( 'MASTER_PUBKEY | %s' % self.app.manager.get_root_public_key(), self.id )
        log.info("Sent master public key to worker instance '%s'." % self.id)
        log.debug( "\tMT: Message MASTER_PUBKEY %s sent to '%s'" % ( self.app.manager.get_root_public_key(), self.id ) )
    
    def send_start_sge( self ):
        log.debug( "\tMT: Sending START_SGE message to instance '%s'" % self.id )
        self.app.manager.console_monitor.conn.send( 'START_SGE', self.id )
    
    def handle_message( self, msg ):
        # log.debug( "Handling message: %s from %s" % ( msg, self.id ) )
        self.is_alive = True
        self.last_comm = dt.datetime.utcnow()
        #Transition from states to a particular response.
        if self.app.manager.console_monitor.conn:
            msg_type = msg.split( ' | ' )[0]
            if msg_type == "ALIVE":
                self.worker_status = "Starting"
                log.info( "Instance '%s' reported alive" % self.id )
                msp = msg.split(' | ')
                self.private_ip = msp[1]
                self.public_ip = msp[2]
                self.zone = msp[3]
                self.type = msp[4]
                self.ami = msp[5]
                log.debug("INSTANCE_ALIVE private_dns:%s  public_dns:%s  zone:%s  type:%s  ami:%s" % (self.private_ip, 
                                                                                                      self.public_ip, 
                                                                                                      self.zone, 
                                                                                                      self.type, 
                                                                                                      self.ami))
                # Instance is alive and functional. Send master pubkey.
                self.send_master_pubkey()
            elif msg_type == "WORKER_H_CERT":
                self.is_alive = True #This is for the case that an existing worker is added to a new master.
                self.app.manager.save_host_cert( msg.split( " | " )[1] )
                log.debug( "Worker '%s' host certificate received and appended to /root/.ssh/known_hosts" % self.id )
                try:
                    sge_svc = self.app.manager.get_services('SGE')[0]
                    if sge_svc.add_sge_host( self ):
                        # Now send message to worker to start SGE  
                        self.send_start_sge()
                        log.info( "Waiting on worker instance '%s' to configure itself..." % self.id )
                    else:
                        log.error( "Adding host to SGE did not go smoothly, not instructing worker to configure SGE daemon." )
                except IndexError:
                    log.error("Could not get a handle on SGE service to add a host; host not added")
            elif msg_type == "NODE_READY":
                self.node_ready = True
                self.worker_status = "Ready"
                log.info( "Instance '%s' ready" % self.id )
                msplit = msg.split( ' | ' )
                try:
                    self.num_cpus = int(msplit[2])
                except:
                    log.debug("Instance '%s' num CPUs is not int? '%s'" % (self.id, msplit[2]))
                log.debug("Instance '%s' reported as having '%s' CPUs." % (self.id, self.num_cpus))
            elif msg_type == "NODE_STATUS":
                msplit = msg.split( ' | ' )
                self.nfs_data = msplit[1]
                self.nfs_tools = msplit[2]
                self.nfs_indices = msplit[3]
                self.nfs_sge = msplit[4]
                self.get_cert = msplit[5]
                self.sge_started = msplit[6]
                self.load = msplit[7]
                self.worker_status = msplit[8]
            elif msg_type == 'NODE_SHUTTING_DOWN':
                msplit = msg.split( ' | ' )
                self.worker_status = msplit[1]
            else: # Catch-all condition
               log.debug( "Unknown Message: %s" % msg )
        else:
            log.error( "Epic Failure, squeue not available?" )
    
