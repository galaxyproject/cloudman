"""Galaxy CM master manager"""
import logging, logging.config, threading, os, time, subprocess, commands, fileinput
import shutil
import datetime as dt

from cm.util.bunch import Bunch

from cm.util import misc, comm
from cm.util import (cluster_status, instance_states, instance_lifecycle, spot_states)
from cm.services.autoscale import Autoscale
from cm.services import service_states
from cm.services.data.filesystem import Filesystem
from cm.services.apps.pss import PSS
from cm.services.apps.sge import SGEService
from cm.services.apps.galaxy import GalaxyService
from cm.services.apps.postgres import PostgresService
from cm.util.decorators import TestFlag

import cm.util.paths as paths
from boto.exception import EC2ResponseError, S3ResponseError

log = logging.getLogger('cloudman')

class ConsoleManager(object):
    def __init__(self, app):
        self.startup_time = dt.datetime.utcnow()
        log.debug( "Initializing console manager - cluster start time: %s" % self.startup_time)
        self.app = app
        self.console_monitor = ConsoleMonitor(self.app)
        self.root_pub_key = None
        self.cluster_status = cluster_status.STARTING
        self.num_workers_requested = 0 # Number of worker nodes requested by user
        # The actual number of worker nodes (note: this is a list of Instance objects)
        # (beause get_worker_instances currenlty depends on tags, which is only
        # supported by EC2, get the list of instances only for the case of EC2 cloud.
        # This initialization is applicable only for restarting the cluster)
        self.worker_instances = self.get_worker_instances() if self.app.cloud_type == 'ec2' else []
        self.disk_total = "0"
        self.disk_used = "0"
        self.disk_pct = "0%"
        self.manager_started = False
        self.cluster_manipulation_in_progress = False
        # If this is set to False, the master instance will not be an execution
        # host in SGE and thus not be running any jobs
        self.master_exec_host = True
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

    @TestFlag(False)
    def start( self ):
        """
        This method is automatically called as CloudMan starts; it tries to add
        and start available cluster services (as provided in the cluster's
        configuration and persistent data).
        """
        log.debug("ud at manager start: %s" % self.app.ud)

        self.handle_prestart_commands()

        # Always add SGE service
        self.app.manager.services.append(SGEService(self.app))

        if self.app.LOCALFLAG is True:
            self.init_cluster(cluster_type='Galaxy')

        # Add PSS service - note that this service runs only after the cluster
        # type has been selected and all of the services are in RUNNING state
        self.app.manager.services.append(PSS(self.app))

        if self.app.ud.has_key("share_string"):
            # Share string overrides everything.
            # Initialize from share, which calls add_preconfigured_services
            self.app.manager.init_shared_cluster(self.app.ud['share_string'].strip())
        elif not self.add_preconfigured_services():
            return False
        self.manager_started = True

        # Check if a previously existing cluster is being recreated or is it a new one
        if self.initial_cluster_type is not None:
            cc_detail = "Configuring a previously existing cluster of type {0}"\
                .format(self.initial_cluster_type)
        else:
            cc_detail = "This is a new cluster; waiting to configure the type."
            self.cluster_status = cluster_status.WAITING
        log.info("Completed the initial cluster startup process. {0}".format(cc_detail))
        return True

    def handle_prestart_commands(self):
        for command in self.app.ud.get("master_prestart_commands", []):
            misc.run(command)

    @TestFlag(False)
    def add_preconfigured_services(self):
        """
        Inspect the cluster configuration and persistent data to add any
        previously defined cluster services.
        """
        log.debug("Checking for and adding any previously defined cluster services")
        try:
            attached_volumes = self.get_attached_volumes()
            # Test if depricated cluster config is used and handle it
            if "static_filesystems" in self.app.ud or "data_filesystems" in self.app.ud:
                log.debug("Handling depricated cluster config")
                return self._handle_old_cluster_conf_format(attached_volumes)
            # Process the current cluster config
            if 'filesystems' in self.app.ud:
                for fs in self.app.ud['filesystems']:
                    log.debug("Adding a previously defined filesystem '{0}' of "\
                        "kind '{1}'".format(fs['name'], fs['kind']))
                    filesystem = Filesystem(self.app, fs['name'], fs.get('mount_point', None))
                    # Based on the kind, add the appropriate file system. We can
                    # handle 'volume', 'snapshot', or 'bucket' kind
                    if fs['kind'] == 'volume':
                        for vol_id in fs['ids']:
                            filesystem.add_volume(vol_id=vol_id)
                    elif fs['kind'] == 'snapshot':
                        for snap in fs['ids']:
                            # Check if an already attached volume maps to this snapshot
                            att_vol = self.get_vol_if_fs(attached_volumes, fs['name'])
                            if att_vol:
                                filesystem.add_volume(vol_id=att_vol.id, size=att_vol.size,
                                        from_snapshot_id=att_vol.snapshot_id)
                            else:
                                filesystem.add_volume(from_snapshot_id=snap)
                    elif fs['kind'] == 'bucket':
                        a_key = fs.get('access_key', None)
                        s_key = fs.get('secret_key', None)
                        filesystem.add_bucket(fs['name'], a_key, s_key)
                    self.app.manager.services.append(filesystem)
                    #self.app.manager.initial_cluster_type = 'Galaxy'
            if "services" in self.app.ud:
                for srvc in self.app.ud['services']:
                    service_name = srvc['name']
                    log.debug("Adding service: '%s'" % service_name)
                    # TODO: translation from predefined service names into classes is not quite ideal...
                    processed_service = False
                    if service_name == 'Postgres':
                        self.app.manager.services.append(PostgresService(self.app))
                        self.app.manager.initial_cluster_type = 'Galaxy'
                        processed_service = True
                    if service_name == 'Galaxy':
                        self.app.manager.services.append(GalaxyService(self.app))
                        self.app.manager.initial_cluster_type = 'Galaxy'
                        processed_service = True
                    if not processed_service:
                        log.warning("Could not find service class matching userData service entry: %s" % service_name)
            return True
        except Exception, e:
            log.error("Error reading existing cluster configuration file: %s" % e)
            self.manager_started = False
            return False

    def get_vol_if_fs(self, attached_volumes, filesystem_name):
        """
        Iterate through the list of (attached) volumes and check if any
        one of them match the current cluster name and filesystem (as stored
        in volume's tags). Return a matching volume (as a ``boto`` object) or
        ``None``.

        *Note* that this method returns the first matching volume and will thus
        not work for filesystems composed of multiple volumes.
        """
        for vol in attached_volumes:
            log.debug("Checking if vol '{0}' is file system '{1}'".format(vol.id, filesystem_name))
            if self.app.cloud_interface.get_tag(vol, 'clusterName') == self.app.ud['cluster_name'] and \
               self.app.cloud_interface.get_tag(vol, 'filesystem') == filesystem_name:
                log.debug("Identified attached volume '%s' as filesystem '%s'" % (vol.id, filesystem_name))
                return vol
        return None

    def _handle_old_cluster_conf_format(self, attached_volumes):
        """
        For backward compatibility, handle the old/deprecated cluster
        configuration/persistent data file format, e.g.,::
            data_filesystems:
              galaxyData:
              - size: 20
                vol_id: vol-edfc9280
            galaxy_home: /mnt/galaxyTools/galaxy-central
            services:
            - service: SGE
            - service: Postgres
            - service: Galaxy
            static_filesystems:
            - filesystem: galaxyIndices
              size: 700
              snap_id: !!python/unicode 'snap-5b030634'
            - filesystem: galaxyTools
              size: 2
              snap_id: !!python/unicode 'snap-1688b978'
        """
        try:
            # First make a backup of the deprecated config file
            s3_conn = self.app.cloud_interface.get_s3_connection()
            misc.copy_file_in_bucket(s3_conn, self.app.ud['bucket_cluster'], self.app.ud['bucket_cluster'],
                    'persistent_data.yaml', 'persistent_data-deprecated.yaml', validate=False)
            # Process the deprecated confgiuration now
            if "static_filesystems" in self.app.ud:
                for vol in self.app.ud['static_filesystems']:
                    fs = Filesystem(self.app, vol['filesystem'])
                    # Check if an already attached volume maps to the current filesystem
                    att_vol = self.get_vol_if_fs(attached_volumes, vol['filesystem'])
                    if att_vol:
                        fs.add_volume(vol_id=att_vol.id, size=att_vol.size,
                               from_snapshot_id=att_vol.snapshot_id)
                    else:
                        fs.add_volume(size=vol['size'], from_snapshot_id=vol['snap_id'])
                    log.debug("Adding static filesystem: '%s'" % vol['filesystem'])
                    self.app.manager.services.append(fs)
                    self.app.manager.initial_cluster_type = 'Galaxy'
            if "data_filesystems" in self.app.ud:
                for fs, vol_array in self.app.ud['data_filesystems'].iteritems():
                    log.debug("Adding a previously existing data filesystem: '%s'" % fs)
                    fs = Filesystem(self.app, fs)
                    for vol in vol_array:
                        fs.add_volume(vol_id=vol['vol_id'], size=vol['size'])
                    self.app.manager.services.append(fs)
                    self.app.manager.initial_cluster_type = 'Data'
            if "services" in self.app.ud:
                for srvc in self.app.ud['services']:
                    service_name = srvc['service']
                    log.debug("Adding service: '%s'" % service_name)
                    # TODO: translation from predefined service names into classes is not quite ideal...
                    processed_service = False
                    if service_name == 'Postgres':
                        self.app.manager.services.append(PostgresService(self.app))
                        self.app.manager.initial_cluster_type = 'Galaxy'
                        processed_service = True
                    if service_name == 'Galaxy':
                        self.app.manager.services.append(GalaxyService(self.app))
                        self.app.manager.initial_cluster_type = 'Galaxy'
                        processed_service = True
                    if not processed_service:
                        log.warning("Could not find service class matching userData service entry: %s" % service_name)
            return True
        except Exception, e:
            log.error("Error reading existing cluster configuration file: %s" % e)
            self.manager_started = False
            return False

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

    def toggle_master_as_exec_host(self, force_removal=False):
        """ By default, the master instance running all the services is also
            an execution host and is used to run jobs. This method allows one
            to toggle the master instance from being an execution host.

            :type force_removal: bool
            :param force_removal: If True, go through the process of removing
                                  the instance from being an execution host
                                  irrespective of the instance's current state.

            :rtype: bool
            :return: True if the master instance is set to be an execution host.
                     False otherwise.
        """
        sge_svc = self.get_services('SGE')[0]
        if sge_svc.state == service_states.RUNNING:
            if self.master_exec_host is True or force_removal:
                self.master_exec_host = False
                if not sge_svc._remove_instance_from_exec_list(self.app.cloud_interface.get_instance_id(),
                        self.app.cloud_interface.get_self_private_ip()):
                    # If the removal was unseccessful, reset the flag
                    self.master_exec_host = True
            else:
                self.master_exec_host = True
                if not sge_svc._add_instance_as_exec_host(self.app.cloud_interface.get_instance_id(),
                        self.app.cloud_interface.get_self_private_ip()):
                    # If the removal was unseccessful, reset the flag
                    self.master_exec_host = False
        else:
            log.warning("SGE not running thus cannot toggle master as exec host")
        return self.master_exec_host

    def get_worker_instances( self ):
        instances = []
        if self.app.TESTFLAG is True:
            #for i in range(5):
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
        except Exception, e:
            log.debug( "Error checking for attached volumes: %s" % e )
        log.debug("Attached volumes: %s" % volumes)
        return volumes

    def shutdown(self, sd_galaxy=True, sd_sge=True, sd_postgres=True, sd_filesystems=True,
                sd_instances=True, sd_autoscaling=True, delete_cluster=False, sd_spot_requests=True,
                rebooting=False):
        if self.app.TESTFLAG is True:
            log.debug("Shutting down the cluster but the TESTFLAG is set")
            return
        log.debug("List of services before shutdown: %s" % [s.get_full_name() for s in self.services])
        self.cluster_status = cluster_status.SHUTTING_DOWN
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
        if sd_spot_requests:
            for wi in self.worker_instances:
                if wi.is_spot() and not wi.spot_was_filled():
                    wi.terminate()
        # Wait for all the services to shut down before declaring the cluster shut down
        # (but don't wait indefinitely)
        # This is required becasue with the file systems being removed in parallel via
        # separate threads, those processes may not have completed by the time the
        # complete shutdown does.
        time_limit = 300 # wait for max 5 mins before shutting down
        while(time_limit > 0):
            log.debug("Waiting ({0} more seconds) for all the services to shut down.".format(time_limit))
            num_off = 0
            for srvc in self.services:
                if srvc.state == service_states.SHUT_DOWN or srvc.state == service_states.ERROR or \
                    srvc.state == service_states.UNSTARTED:
                    num_off += 1
            if num_off == len(self.services):
                log.debug("All services shut down")
                break
            elif rebooting == True:
                log.debug("Not waiting for all the services to shut down because we're just rebooting.")
                break
            sleep_time = 6
            time.sleep(sleep_time)
            time_limit -= sleep_time
        if delete_cluster:
            self.delete_cluster()
        self.cluster_status = cluster_status.TERMINATED
        log.info( "Cluster shut down at %s (uptime: %s). If not done automatically, "
            "manually terminate the master instance (and any remaining instances "
            "associated with this cluster) from the cloud console." \
            % (dt.datetime.utcnow(), (dt.datetime.utcnow()-self.startup_time)))

    def reboot(self, soft=False):
        if self.app.TESTFLAG is True:
            log.debug("Restart the cluster but the TESTFLAG is set")
            return False
        # Spot requests cannot be tagged and thus there is no good way of associating those
        # back with a cluster after a reboot so cancel those
        self.shutdown(sd_filesystems=False, sd_instances=False, rebooting=True)
        if soft:
            if misc.run("{0} restart".format(os.path.join(self.app.ud['boot_script_path'],\
                self.app.ud['boot_script_name']))):
                return True
            else:
                log.error("Trouble restarting CloudMan softly; rebooting instance now.")
        ec2_conn = self.app.cloud_interface.get_ec2_connection()
        try:
            log.debug("Rebooting self now...")
            ec2_conn.reboot_instances([self.app.cloud_interface.get_instance_id()])
            return True
        except EC2ResponseError, e:
            log.error("Error rebooting master instance (i.e., self): %s" % e)
        return False

    def terminate_master_instance(self, delete_cluster=False):
        if self.cluster_status != cluster_status.TERMINATED:
            self.shutdown(delete_cluster=delete_cluster)
        log.debug("Terminating the master instance")
        self.app.cloud_interface.terminate_instance(self.app.cloud_interface.get_instance_id())

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

    def get_idle_instances( self ):
        # log.debug( "Looking for idle instances" )
        idle_instances = [] # List of Instance objects corresponding to idle instances
        if os.path.exists('%s/default/common/settings.sh' % paths.P_SGE_ROOT):
            proc = subprocess.Popen("export SGE_ROOT=%s; . $SGE_ROOT/default/common/settings.sh; "
                "%s/bin/lx24-amd64/qstat -f | grep all.q" % (paths.P_SGE_ROOT, paths.P_SGE_ROOT), \
                shell=True, stdout=subprocess.PIPE)
            qstat_out = proc.communicate()[0]
            # log.debug( "qstat output: %s" % qstat_out )
            instances = qstat_out.splitlines()
            nodes_list = [] # list of nodes containing node's domain name and number of used processing slots
            idle_instances_dn = [] # list of domain names of idle instances
            for inst in instances:
                # Get instance domain name and # of used processing slots: ['domU-12-31-38-00-48-D1.c:0']
                nodes_list.append( inst.split( '@' )[1].split( ' ' )[0] + ':' + inst.split( '/' )[1] )
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
                     # log.debug("Trying to match worker instance with private IP '%s' to idle "
                     #    "instance '%s'" % (w_instance.get_local_hostname(), idle_instance_dn))
                     if w_instance.get_local_hostname() is not None:
                         if w_instance.get_local_hostname().lower().startswith(str(idle_instance_dn).lower()):
                            # log.debug("Marking instance '%s' with FQDN '%s' as idle." \
                            #     % (w_instance.id, idle_instance_dn))
                            idle_instances.append( w_instance )
        return idle_instances

    def remove_instances(self, num_nodes, force=False):
        """ Decide which instance(s) to terminate, remove them from SGE and terminate
        """
        num_terminated = 0
        # First look for idle instances that can be removed
        idle_instances = self.get_idle_instances()
        if len(idle_instances) > 0:
            log.info("Found %s idle instances; trying to remove %s." % (len(idle_instances), num_nodes))
            for i in range (0, num_nodes):
                for inst in idle_instances:
                    if num_terminated < num_nodes:
                        self.remove_instance(inst.id)
                        num_terminated += 1
        else:
            log.info("No idle instances found")
        log.debug("Num to terminate: %s, num terminated: %s; force set to '%s'" \
            % (num_nodes, num_terminated, force))
        # If force is set, terminate requested number of instances regardless whether they are idle
        if force is True and num_terminated < num_nodes:
            force_kill_instances = num_nodes - num_terminated
            log.info("Forcefully terminating %s instances." % force_kill_instances)
            for i in range(force_kill_instances):
                for inst in self.worker_instances:
                    if not inst.is_spot() or inst.spot_was_filled():
                        self.remove_instance(inst.id)
                        num_terminated += 1
        if num_terminated > 0:
            log.info("Initiated requested termination of instances. Terminating '%s' instances." \
                % num_terminated)
        else:
            log.info( "Did not terminate any instances." )

    def remove_instance(self, instance_id=''):
        if instance_id == '':
            log.warning("Tried to remove an instance but did not receive instance ID")
            return False
        log.info( "Specific termination of instance '%s' requested." % instance_id)
        for inst in self.worker_instances:
            if inst.id == instance_id:
                sge_svc = self.get_services('SGE')[0]
                # DBTODO Big problem here if there's a failure removing from allhosts.  Need to handle it.
                # if sge_svc.remove_sge_host(inst.get_id(), inst.get_private_ip()) is True:
                # Best-effort PATCH until above issue is handled
                if inst.get_id() is not None:
                    sge_svc.remove_sge_host(inst.get_id(), inst.get_private_ip())
                    # Remove the given instance from /etc/hosts files
                    log.debug("Removing instance {0} from /etc/hosts".format(inst.get_id()))
                    for line in fileinput.input('/etc/hosts', inplace=1):
                        line = line.strip()
                        # (print all lines except the one w/ instance IP back to the file)
                        if not inst.private_ip in line:
                            print line
                inst.terminate()
        log.info("Initiated requested termination of instance. Terminating '%s'." % instance_id)

    def reboot_instance(self, instance_id=''):
        if instance_id == '':
            log.warning("Tried to reboot an instance but did not receive instance ID")
            return False
        log.info("Specific reboot of instance '%s' requested." % instance_id)
        for inst in self.worker_instances:
            if inst.id == instance_id:
               inst.reboot()
        log.info("Initiated requested reboot of instance. Rebooting '%s'." % instance_id)

    def add_instances( self, num_nodes, instance_type='', spot_price=None):
        self.app.cloud_interface.run_instances(num=num_nodes,
                                               instance_type=instance_type,
                                               spot_price=spot_price)

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

    def init_cluster(self, cluster_type, pss=1):
        """
        Initialize the type for this cluster and start appropriate services,
        storing the cluster configuration into the cluster's bucket.

        This method applies only to a new cluster.

        :type cluster_type: string
        :param cluster_type: Type of cluster being setup. Currently, accepting
                             values ``Galaxy``, ``Data``, or ``SGE``

        :type pss: int
        :param pss: Persistent Storage Size associated with data volumes being
                    created for the cluster
        """
        def _add_data_fs():
            """
            A local convenience method used to add a new file system
            """
            fs_name = 'galaxyData'
            log.debug("Creating a new data filesystem: '%s'" % fs_name)
            fs = Filesystem(self.app, fs_name)
            fs.add_volume(size=pss)
            self.services.append(fs)

        if self.app.TESTFLAG is True and self.app.LOCALFLAG is False:
            log.debug("Attempted to initialize a new cluster of type '%s', but TESTFLAG is set." % cluster_type)
            return
        self.cluster_status = cluster_status.STARTING
        self.app.manager.initial_cluster_type = cluster_type
        log.info("Initializing a '%s' cluster." % cluster_type)
        if cluster_type == 'Galaxy':
            # Static data - get snapshot IDs from the default bucket and add respective file systems
            s3_conn = self.app.cloud_interface.get_s3_connection()
            snaps_file = 'cm_snaps.yaml'
            snaps = None
            # Get a list of auto-mount/default/read-only/reference data sources
            if misc.get_file_from_bucket(s3_conn, self.app.ud['bucket_default'], 'snaps.yaml', snaps_file):
                snaps_file = misc.load_yaml_file(snaps_file)
                snaps = snaps_file['static_filesystems']
            # Turn those data sources into file systems
            if snaps:
                attached_volumes = self.get_attached_volumes()
                for snap in snaps:
                    fs = Filesystem(self.app, snap['filesystem'])
                    # Check if an already attached volume maps to the current filesystem
                    att_vol = self.get_vol_if_fs(attached_volumes, snap['filesystem'])
                    if att_vol:
                        log.debug("{0} file system has volume(s) already attached"\
                            .format(snap['filesystem']))
                        fs.add_volume(vol_id=att_vol.id, size=att_vol.size, from_snapshot_id=att_vol.snapshot_id)
                    else:
                        log.debug("There are no volumes already attached for file system {0}"\
                            .format(snap['filesystem']))
                        fs.add_volume(size=snap['size'], from_snapshot_id=snap['snap_id'])
                    log.debug("Adding a static filesystem '{0}' with volumes '{1}'"\
                        .format(fs.get_full_name(), fs.volumes))
                    self.services.append(fs)
            # Add a file system for user's data now (OpenNebula and dummy clouds
            # do not support volumes yet so skip those)
            if self.app.cloud_type not in ['opennebula', 'dummy']:
                _add_data_fs()
            # Add PostgreSQL service
            self.services.append(PostgresService(self.app))
            # Add Galaxy service
            self.services.append(GalaxyService(self.app))
        elif cluster_type == 'Data':
            # Add a file system for user's data
            _add_data_fs()
        elif cluster_type == 'SGE':
            # SGE service is automatically added at cluster start (see ``start`` method)
            pass
        else:
            log.error("Tried to initialize a cluster but received an unknown type: '%s'" % cluster_type)

    def init_shared_cluster(self, shared_cluster_config):
        if self.app.TESTFLAG is True:
            log.debug("Attempted to initialize a shared cluster from bucket '%s', but TESTFLAG is set." % shared_cluster_config)
            return
        self.cluster_status = cluster_status.STARTING
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
                    log.debug("Dumping scpd to file {0} (which will become persistent_data.yaml): {1}".format(cc_file_name, scpd))
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
        # TODO: Reboot the instance so CloudMan source downloaded from the shared
        # instance is used
        # log.info("Rebooting the cluster so shared instance source can be reloaded.")
        # self.reboot(soft=True)
        # Reload user data and start the cluster as normally would
        self.app.ud = self.app.cloud_interface.get_user_data(force=True)
        if misc.get_file_from_bucket(s3_conn, self.app.ud['bucket_cluster'], 'persistent_data.yaml', 'pd.yaml'):
            pd = misc.load_yaml_file('pd.yaml')
            self.app.ud = misc.merge_yaml_objects(self.app.ud, pd)
        reload(paths) # Must reload because paths.py might have changes in it
        self.add_preconfigured_services()
        return True

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
        addl_data = {'shared_data_snaps': snap_ids, 'galaxy_home': paths.P_GALAXY_HOME}
        self.console_monitor.create_cluster_config_file(conf_file_name, addl_data=addl_data)
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

    def add_fs(self, bucket_name, bucket_a_key=None, bucket_s_key=None):
        log.info("Adding a file system from bucket {0} (w/ creds {1}:{2})"\
            .format(bucket_name, bucket_a_key, bucket_s_key))
        fs = Filesystem(self.app, bucket_name)
        fs.add_bucket(bucket_name, bucket_a_key, bucket_s_key)
        self.services.append(fs)
        # Inform all workers to add the same FS (the file system will be the same
        # and sharing it over NFS does not seems to work)
        for w_inst in self.worker_instances:
            w_inst.send_add_s3fs(bucket_name)
        log.debug("Master done adding FS from bucket {0}".format(bucket_name))

    def stop_worker_instances( self ):
        log.info( "Stopping all '%s' worker instance(s)" % len(self.worker_instances) )
        to_terminate = []
        for i in self.worker_instances:
            to_terminate.append(i)
        for inst in to_terminate:
            log.debug("Initiating termination of instance %s" % inst.get_desc() )
            inst.terminate()
            # log.debug("Initiated termination of instance '%s'" % inst.id )

    @TestFlag({}) #{'default_CM_rev': '64', 'user_CM_rev':'60'} # For testing
    def check_for_new_version_of_CM(self):
        """ Check revision metadata for CloudMan (CM) in user's bucket and the default CM bucket.

        :rtype: dict
        :return: A dictionary with 'default_CM_rev' and 'user_CM_rev' keys where each key
                 maps to an string representation of an int that corresponds to the version of
                 CloudMan in the default repository vs. the currently running user's version.
                 If CloudMan is unable to determine the versions, an empty dict is returned.
        """
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
            log.info("Updating CloudMan application source file in the cluster's bucket '%s'. "
                "It will be automatically available the next time this cluster is instantiated." \
                % self.app.ud['bucket_cluster'] )
            s3_conn = self.app.cloud_interface.get_s3_connection()
            # Make a copy of the old/original CM source and boot script in the cluster's bucket
            # called 'copy_name' and 'copy_boot_name', respectivley
            copy_name = "%s_%s" % (self.app.config.cloudman_source_file_name, dt.date.today())
            copy_boot_name = "%s_%s" % (self.app.ud['boot_script_name'], dt.date.today())
            if misc.copy_file_in_bucket(s3_conn, self.app.ud['bucket_cluster'],
                self.app.ud['bucket_cluster'], self.app.config.cloudman_source_file_name, copy_name) and \
                misc.copy_file_in_bucket(s3_conn, self.app.ud['bucket_cluster'],
                self.app.ud['bucket_cluster'], self.app.ud['boot_script_name'], copy_boot_name):
                # Now copy CloudMan source from the default bucket to cluster's bucket as
                # self.app.config.cloudman_source_file_name and cm_boot.py as 'boot_script_name'
                if misc.copy_file_in_bucket(s3_conn, self.app.ud['bucket_default'],
                    self.app.ud['bucket_cluster'], self.app.config.cloudman_source_file_name,
                    self.app.config.cloudman_source_file_name) and misc.copy_file_in_bucket(s3_conn,
                    self.app.ud['bucket_default'], self.app.ud['bucket_cluster'],
                    'cm_boot.py', self.app.ud['boot_script_name']):
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
        public_ip = self.app.cloud_interface.get_self_public_ip();
        if self.app.TESTFLAG:
            num_cpus = 1
            load = "0.00 0.02 0.39"
            return {'id' : 'localtest', 'ld' : load, 'time_in_state' : misc.formatSeconds(dt.datetime.utcnow() - self.startup_time), 'instance_type' : 'tester', 'public_ip' : public_ip}
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
        return  {'id' : self.app.cloud_interface.get_instance_id(), 'ld' : load, 'time_in_state' : misc.formatSeconds(dt.datetime.utcnow() - self.startup_time), 'instance_type' : self.app.cloud_interface.get_type(), 'public_ip' : public_ip }


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
        # Keep some local stats to be able to adjust system updates
        self.last_update_time = dt.datetime.utcnow()
        self.last_system_change_time = dt.datetime.utcnow()
        self.update_frequency = 10 # Frequency (in seconds) between system updates
        self.num_workers = -1
        # Start the monitor thread
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
            except Exception, e:
                log.debug("General error setting 'role' tag: %s" % e)
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

    def _update_frequency(self):
        """ Update the frequency value at which system updates are performed by the monitor.
        """
        # Check if a worker was added/removed since the last update
        if self.num_workers != len(self.app.manager.worker_instances):
            self.last_system_change_time = dt.datetime.utcnow()
            self.num_workers = len(self.app.manager.worker_instances)
        # Update frequency: as more time passes since a change in the system,
        # progressivley back off on frequency of system updates
        if (dt.datetime.utcnow() - self.last_system_change_time).seconds > 600:
            self.update_frequency = 60 # If no system changes for 10 mins, run update every minute
        elif (dt.datetime.utcnow() - self.last_system_change_time).seconds > 300:
            self.update_frequency = 30 # If no system changes for 5 mins, run update every 30 secs
        else:
            self.update_frequency = 10 # If last system change within past 5 mins, run update every 10 secs

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

    def create_cluster_config_file(self, file_name='persistent_data-current.yaml'):
        """
        Capture the current cluster configuration in a file (i.e., ``persistent_data.yaml``
        in cluster's bucket). The generated file is stored in CloudMan's running
        directory as ``file_name``.
        """
        try:
            cc = {} # cluster configuration
            svcs = [] # list of services
            fss = [] # list of filesystems
            for srvc in self.app.manager.services:
                if srvc.svc_type=='Filesystem':
                    fs = {}
                    fs['name'] = srvc.name
                    fs['mount_point'] = srvc.mount_point
                    fs['kind'] = srvc.kind
                    if srvc.kind == 'bucket':
                        fs['ids'] = [b.bucket_name for b in srvc.buckets]
                    elif srvc.kind == 'volume':
                        fs['ids'] = [v.volume_id for v in srvc.volumes]
                    elif srvc.kind == 'snapshot':
                        fs['ids'] = [v.from_snapshot_id for v in srvc.volumes]
                    else:
                        log.error("Unknown filesystem kind {0}".format(srvc.kind))
                    fss.append(fs)
                else:
                    s = {}
                    s['name'] = srvc.svc_type
                    if srvc.svc_type == 'Galaxy':
                        s['home'] = paths.P_GALAXY_HOME
                    svcs.append(s)
            cc['filesystems'] = fss
            cc['services'] = svcs
            misc.dump_yaml_to_file(cc, file_name)
            # Reload the user data object in case anything has changed
            self.app.ud = misc.merge_yaml_objects(cc, self.app.ud)
        except Exception, e:
            log.error("Problem creating cluster configuration file: '%s'" % e)
        return file_name

    def store_cluster_config(self):
        """
        Create a cluster configuration file and store it into cluster's bucket under name
        ``persistent_data.yaml``. The cluster configuration is considered the set of currently
        seen services in the master.

        In addition, store the local Galaxy configuration files to the cluster's
        bucket (do so only if they are not already there).
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
        if self.app.manager.manager_started == False:
            if not self.app.manager.start():
                log.critical("\n\n***** Manager failed to start *****\n")
                return False
        log.debug("Monitor started; manager started")
        while self.running:
            self.sleeper.sleep(4)
            if self.app.manager.cluster_status == cluster_status.TERMINATED:
                self.running = False
                return
            # In case queue connection was not established, try again (this will happen if
            # RabbitMQ does not start in time for CloudMan)
            if not self.conn.is_connected():
                log.debug("Trying to setup AMQP connection; conn = '%s'" % self.conn)
                self.conn.setup()
                continue
            # Do a periodic system state update (eg, services, workers)
            self._update_frequency()
            if (dt.datetime.utcnow() - self.last_update_time).seconds > self.update_frequency:
                self.last_update_time = dt.datetime.utcnow()
                self.app.manager.check_disk()
                for service in self.app.manager.services:
                    service.status()
                # Log current services' states (in condensed format)
                svcs_state = "S&S: "
                for s in self.app.manager.services:
                    svcs_state += "%s..%s; " % (s.get_full_name(), 'OK' if s.state=='Running' else s.state)
                log.debug(svcs_state)
                # Check the status of worker instances
                for w_instance in self.app.manager.worker_instances:
                    if w_instance.is_spot():
                        w_instance.update_spot()
                        if not w_instance.spot_was_filled():
                            # Wait until the Spot request has been filled to start
                            # treating the instance as a regular Instance
                            continue
                    # As long we we're hearing from an instance, assume all OK.
                    if (dt.datetime.utcnow() - w_instance.last_comm).seconds < 22:
                        log.debug("Instance {0} OK (heard from it {1} secs ago)".format(
                            w_instance.get_desc(), (dt.datetime.utcnow() - w_instance.last_comm).seconds))
                        continue
                    # Explicitly check the state of a quiet instance (but only periodically)
                    elif (dt.datetime.utcnow() - w_instance.last_state_update).seconds > 30:
                        log.debug("Have not checked on quiet instance {0} for a while; checking now"\
                            .format(w_instance.get_desc()))
                        w_instance.maintain()
                    else:
                        log.debug("Not checking quiet instance {0} (last check {1} secs ago)"\
                            .format(w_instance.get_desc(),
                            (dt.datetime.utcnow() - w_instance.last_state_update).seconds))
            # Check and add any new services
            added_srvcs = False # Flag to indicate if cluster conf was changed
            for service in [s for s in self.app.manager.services if s.state == service_states.UNSTARTED]:
                log.debug("Monitor adding service '%s'" % service.get_full_name())
                self.last_system_change_time = dt.datetime.utcnow()
                if service.add():
                    added_srvcs = True
            # Store cluster conf after all services have been added.
            # NOTE: this flag relies on the assumption service additions are
            # sequential (i.e., monitor waits for the service add call to complete).
            # If any of the services are to be added via separate threads, a
            # system-wide flag should probably be maintained for that particular
            # service that would indicate the configuration of the service is
            # complete. This could probably be done by monitoring
            # the service state flag that is already maintained?
            if added_srvcs and self.app.cloud_type != 'opennebula':
                self.store_cluster_config()
            # Check and grow the file system
            svcs = self.app.manager.get_services('Filesystem')
            for svc in svcs:
                if svc.name == 'galaxyData' and svc.grow is not None:
                    self.last_system_change_time = dt.datetime.utcnow()
                    self.expand_user_data_volume()
                    # Opennebula has no storage like S3, so this is not working (yet)
                    if self.app.cloud_type != 'opennebula':
                        self.store_cluster_config()
            # Check for any new AMQP messages
            m = self.conn.recv()
            while m is not None:
                def do_match():
                    match = False
                    for inst in self.app.manager.worker_instances:
                        if str(inst.id) == str(m.properties['reply_to']):
                            match = True
                            inst.handle_message( m.body )
                    return match

                if not do_match():
                    log.debug( "No instance (%s) match found for message %s; will add instance now!" \
                        % ( m.properties['reply_to'], m.body ) )
                    if self.app.manager.add_live_instance(m.properties['reply_to']):
                        do_match()
                    else:
                        log.warning("Potential error, got message from instance '%s' "
                            "but not aware of this instance. Ignoring the instance." \
                            % m.properties['reply_to'])
                m = self.conn.recv()


class Instance( object ):
    def __init__(self, app, inst=None, m_state=None, last_m_state_change=None,
                 sw_state=None, reboot_required=False, spot_request_id=None):
        self.app = app
        self.spot_request_id = spot_request_id
        self.lifecycle = instance_lifecycle.SPOT if self.spot_request_id else instance_lifecycle.ONDEMAND
        self.inst = inst # boto object of the instance
        self.spot_state = None
        self.private_ip = None
        self.public_ip = None
        self.local_hostname = None
        if inst:
            try:
                self.id = str(inst.id)
            except EC2ResponseError, e:
                log.error("Error retrieving instance id: %s" % e)
        else:
            self.id = None
        # Machine state as obtained from the cloud middleware (see instance_states Bunch)
        self.m_state = m_state
        self.last_m_state_change = dt.datetime.utcnow()
        # A time stamp when the most recent update of the instance state (m_state) took place
        self.last_state_update = dt.datetime.utcnow()
        self.sw_state = sw_state # Software state
        self.is_alive = False
        self.node_ready = False
        self.num_cpus = 1
        self.time_rebooted = dt.datetime(2012, 1, 1, 0, 0, 0) # Initialize to a date in the past
        self.reboot_count = 0
        self.REBOOT_COUNT_THRESHOLD = self.TERMINATE_COUNT_THRESHOLD = 4
        self.terminate_attempt_count = 0
        self.last_comm = dt.datetime(2012, 1, 1, 0, 0, 0) # Initialize to a date in the past
        self.nfs_data = 0
        self.nfs_tools = 0
        self.nfs_indices = 0
        self.nfs_sge = 0
        self.get_cert = 0
        self.sge_started = 0
        self.worker_status = 'Pending' # Pending, Wake, Startup, Ready, Stopping, Error
        self.load = 0
        self.type = 'Unknown'
        self.reboot_required = reboot_required
        self.update_spot()

    def maintain(self):
        """ Based on the state and status of this instance, try to do the right thing
            to keep the instance functional. Note that this may lead to terminating
            the instance.
        """
        def reboot_terminate_logic():
            """ Make a decision whether to reboot, terminate or reboot an instance.
                CALL THIS METHOD CAREFULLY because it defaults to terminating the
                instance!
            """
            if self.reboot_count < self.REBOOT_COUNT_THRESHOLD:
                self.reboot()
            elif self.terminate_attempt_count > self.TERMINATE_COUNT_THRESHOLD:
                log.info("Tried terminating instance {0} {1} times but was unsucessful. Giving up."\
                    .format(self.inst.id, self.TERMINATE_COUNT_THRESHOLD))
                self._remove_instance()
            else:
                log.info("Instance {0} not responding after {1} reboots. Terminating instance."\
                    .format(self.id, self.reboot_count))
                self.terminate()

        # Update state then do resolution
        state = self.get_m_state()
        if state == instance_states.PENDING or state == instance_states.SHUTTING_DOWN:
            if (dt.datetime.utcnow()-self.last_m_state_change).seconds > 400 and \
               (dt.datetime.utcnow()-self.time_rebooted).seconds > 300:
                log.debug("'Maintaining' instance {0} stuck in '{1}' or '{2}' states.".format(
                    self.get_desc(), instance_states.PENDING, instance_states.SHUTTING_DOWN))
                reboot_terminate_logic()
        elif state == instance_states.ERROR:
            log.debug("'Maintaining' instance {0} in '{1}' state.".format(self.get_desc(),
                instance_states.ERROR))
            reboot_terminate_logic()
        elif state == instance_states.TERMINATED:
            log.debug("'Maintaining' instance {0} in '{1}' state.".format(self.get_desc(),
                instance_states.TERMINATED))
            self._remove_instance()
        elif state == instance_states.RUNNING:
            log.debug("'Maintaining' instance {0} in '{1}' state (last comm before {2} | "
                "last m_state change before {3} | time_rebooted before {4}".format(
                self.get_desc(), instance_states.RUNNING,
                dt.timedelta(seconds=(dt.datetime.utcnow()-self.last_comm).seconds),
                dt.timedelta(seconds=(dt.datetime.utcnow()-self.last_m_state_change).seconds),
                dt.timedelta(seconds=(dt.datetime.utcnow()-self.time_rebooted).seconds)))
            if (dt.datetime.utcnow()-self.last_comm).seconds > 100 and \
               (dt.datetime.utcnow()-self.last_m_state_change).seconds > 400 and \
               (dt.datetime.utcnow()-self.time_rebooted).seconds > 300:
                reboot_terminate_logic()

    def get_cloud_instance_object(self, deep=False):
        """ Get the instance object for this instance from the library used to
            communicate with the cloud middleware. In the case of boto, this
            is the boto EC2 Instance object.

            :type deep: bool
            :param deep: If True, force the check with the cloud middleware; else
                         use local field by default

            :rtype: boto.ec2.instance.Instance (should really be a more generic repr
                    but we'll wait for OCCI or something)
            :return: cloud instance object for this instance
        """
        if self.app.TESTFLAG is True:
            log.debug("Attempted to get instance cloud object, but TESTFLAG is set. Returning None")
            return None
        if deep is True: # reset the current local instance field
            self.inst = None
        if self.inst is None and self.id is not None:
            ec2_conn = self.app.cloud_interface.get_ec2_connection()
            try:
                rs = ec2_conn.get_all_instances([self.id])
                if len(rs) == 0:
                    log.warning("Instance {0} not found on the cloud?".format(self.id))
                for r in rs:
                    # Update local fields
                    self.inst = r.instances[0]
                    self.id = r.instances[0].id
                    self.m_state = r.instances[0].state
            except EC2ResponseError, e:
                log.error("Trouble getting the cloud instance ({0}) object: {1}"\
                    .format(self.id, e))
            except Exception, e:
                log.error("Error getting the cloud instance ({0}) object: {1}"\
                    .format(self.id, e))
        elif not self.is_spot():
            log.debug("Cannot get cloud instance object without an instance ID?")
        return self.inst

    def is_spot(self):
        """ Test is this Instance is a Spot instance.

            :rtype: bool
            :return: True if the current Instance is Spot instance, False otherwise.
        """
        return self.lifecycle == instance_lifecycle.SPOT

    def spot_was_filled(self):
        """ For Spot-based instances, test if the spot request has been
            filled (ie, an instance was started)

            :rtype: bool
            :return: True if this is a Spot instance and the Spot request
                     is in state spot_states.ACTIVE. False otherwise.
        """
        self.update_spot()
        if self.is_spot() and self.spot_state == spot_states.ACTIVE:
            return True
        return False

    def get_status_dict( self ):
        toret = {'id' : self.id,
                 'ld' : self.load,
                 'time_in_state' : misc.formatSeconds(dt.datetime.utcnow() - self.last_m_state_change),
                 'nfs_data' : self.nfs_data,
                 'nfs_tools' : self.nfs_tools,
                 'nfs_indices' : self.nfs_indices,
                 'nfs_sge' : self.nfs_sge,
                 'get_cert' : self.get_cert,
                 'sge_started' : self.sge_started,
                 'worker_status' : self.worker_status,
                 'instance_state' : self.m_state,
                 'instance_type' : self.type,
                 'public_ip' : self.public_ip}

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
            return [self.id, ld, misc.formatSeconds(dt.datetime.utcnow() - self.last_m_state_change), \
                    self.nfs_data, self.nfs_tools, self.nfs_indices, self.nfs_sge, self.get_cert, \
                    self.sge_started, self.worker_status]
        else:
            return [self.id, self.m_state, misc.formatSeconds(dt.datetime.utcnow()-self.last_m_state_change),\
                    self.nfs_data, self.nfs_tools, self.nfs_indices, self.nfs_sge, self.get_cert, \
                    self.sge_started, self.worker_status]

    def get_id(self):
        if self.app.TESTFLAG is True:
            log.debug("Attempted to get instance id, but TESTFLAG is set. Returning TestInstanceID")
            return "TestInstanceID"
        if self.inst is not None and self.id is None:
            try:
                self.inst.update()
                self.id = self.inst.id
            except EC2ResponseError, e:
                log.error("Error retrieving instance id: %s" % e)
            except Exception, e:
                log.error("Exception retreiving instance object: %s" % e)
        return self.id

    def get_desc(self):
        """ Get basic but descriptive info about this instance. Useful for logging.
        """
        if self.is_spot() and not self.spot_was_filled():
            return "'{sid}'".format(sid=self.spot_request_id)
        return "'{id}' (IP: {ip})".format(id=self.get_id(), ip=self.get_public_ip())

    def reboot(self):
        """ Reboot this instance.
        """
        if self.inst is not None:
            log.info("Rebooting instance {0} (reboot #{1}).".format(self.id, self.reboot_count+1))
            try:
                self.inst.reboot()
                self.time_rebooted = dt.datetime.utcnow()
            except EC2ResponseError, e:
                log.error("Trouble rebooting instance {0}: {1}".format(self.id, e))
        else:
            log.debug("Attampted to reboot instance {0} but no instance object? (doing nothing)"\
                .format(self.get_id()))
        self.reboot_count += 1 # Increment irespective of success to allow for eventual termination

    def terminate(self):
        self.worker_status = "Stopping"
        t_thread = threading.Thread(target=self.__terminate)
        t_thread.start()

    def __terminate(self):
        inst_terminated = self.app.cloud_interface.terminate_instance(instance_id=self.id,
            spot_request_id=self.spot_request_id if self.is_spot() else None)
        self.terminate_attempt_count += 1
        if inst_terminated is False:
            log.error("Terminating instance %s did not go smoothly; instance state: '%s'" \
                % (self.get_desc(), self.get_m_state()))
        else:
            # Remove the reference to the instance object because with OpenStack &
            # boto the instance.update() method returns the instance as being
            # in 'running' state even though the instance does not even exist any more.
            self.inst = None
            self._remove_instance()

    def _remove_instance(self, force=False):
        """ A convenience method to remove the current instance from the list
            of worker instances tracked by the master object.

            :type force: bool
            :param force: Indicate if the instance should be forcefully (ie, irrespective)
                          of other logic) removed from the list of instances maintained
                          by the master object.
        """
        try:
            if self in self.app.manager.worker_instances:
                self.app.manager.worker_instances.remove(self)
                log.info("Instance '%s' removed from the internal instance list." % self.id)
        except ValueError, e:
            log.warning("Instance '%s' no longer in instance list, the global monitor probably " \
                "picked it up and deleted it already: %s" % (self.id, e))

    def instance_can_be_terminated( self ):
        log.debug( "Checking if instance '%s' can be terminated" % self.id )
        # TODO (qstat -qs {a|c|d|o|s|u|A|C|D|E|S})
        return False

    def get_m_state( self ):
        """ Update the machine state of the current instance by querying the
            cloud middleware for the instance object itself (via the instance
            id) and updating self.m_state field to match the state returned by
            the cloud middleware.
            Also, update local last_state_update timestamp.

            :rtype: String
            :return: the current state of the instance as obtained from the
                     cloud middleware
        """
        if self.app.TESTFLAG is True:
            log.debug("Getting m_state for instance {0} but TESTFLAG is set; returning 'running'"\
                .format(self.get_id()))
            return "running"
        self.last_state_update = dt.datetime.utcnow()
        self.get_cloud_instance_object(deep=True)
        if self.inst:
            try:
                state = self.inst.state
                log.debug("Requested instance {0} update; old state: {1}; new state: {2}"\
                    .format(self.get_id(), self.m_state, state))
                if state != self.m_state:
                    self.m_state = state
                    self.last_m_state_change = dt.datetime.utcnow()
            except EC2ResponseError, e:
                log.debug("Error updating instance {0} state: {1}".format(self.get_id(), e))
                self.m_state = instance_states.ERROR
        else:
            if not self.is_spot() or self.spot_was_filled():
                log.debug("Instance object {0} not found during m_state update; "
                    "setting instance state to {1}".format(self.get_id(), instance_states.TERMINATED))
                self.m_state = instance_states.TERMINATED
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

    def update_spot(self, force=False):
        """ Get an update on the state of a Spot request. If the request has entered
            spot_states.ACTIVE or spot_states.CANCELLED states, update the Instance
            object itself otherwise just update state. The method will continue to poll
            for an update until the spot request has been filled (ie, enters state
            spot_states.ACTIVE). After that, simply return the spot state (see
            force parameter).

            :type force: bool
            :param force: If True, poll for an update on the spot request,
                          irrespective of the stored spot request state.
        """
        if self.is_spot() and (force or self.spot_state != spot_states.ACTIVE):
            old_state = self.spot_state
            try:
                ec2_conn = self.app.cloud_interface.get_ec2_connection()
                reqs = ec2_conn.get_all_spot_instance_requests(request_ids=[self.spot_request_id])
                for req in reqs:
                    self.spot_state = req.state
                    # Also update the worker_status because otherwise there's no
                    # single source to distinguish between simply an instance
                    # in Pending state and a Spot request
                    self.worker_status = self.spot_state
                    # If the state has changed, do a deeper update
                    if self.spot_state != old_state:
                        if self.spot_state == spot_states.CANCELLED:
                            # The request was cancelled so remove this Instance object
                            log.info("Spot request {0} was cancelled; removing Instance object {1}"\
                                .format(self.spot_request_id, self.id))
                            self._remove_instance()
                        elif self.spot_state == spot_states.ACTIVE:
                            # We should have an instance now
                            self.id = req.instance_id
                            self.get_cloud_instance_object()
                            log.info("Spot request {0} filled with instance {1}"\
                                .format(self.spot_request_id, self.id))

            except EC2ResponseError, e:
                log.error("Trouble retrieving spot request {0}: {1}".format(self.spot_request_id, e))
        return self.spot_state

    def get_private_ip( self ):
        # log.debug("Getting instance '%s' private IP: '%s'" % ( self.id, self.private_ip ) )
        if self.app.TESTFLAG is True:
            log.debug("Attempted to get instance private IP, but TESTFLAG is set. Returning 127.0.0.1")
            self.private_ip = '127.0.0.1'
        if self.private_ip is None:
            inst = self.get_cloud_instance_object()
            if inst is not None:
                try:
                    inst.update()
                    self.private_ip = inst.private_ip_address
                except EC2ResponseError:
                    log.debug("private_ip_address for instance {0} not (yet?) available."\
                        .format(self.get_id()))
            else:
                log.debug("private_ip_address for instance {0} with no instance object not available."\
                    .format(self.get_id()))
        return self.private_ip

    def get_public_ip(self):
        if self.app.TESTFLAG is True:
            log.debug("Attempted to get instance public IP, but TESTFLAG is set. Returning 127.0.0.1")
            self.public_ip = '127.0.0.1'
        if self.public_ip is None:
            inst = self.get_cloud_instance_object()
            if inst is not None:
                try:
                    inst.update()
                    self.public_ip = inst.ip_address
                except EC2ResponseError:
                    log.debug("ip_address for instance {0} not (yet?) available.".format(self.get_id()))
            else:
                log.debug("ip_address for instance {0} with no instance object not available."\
                    .format(self.get_id()))
        return self.public_ip

    def get_local_hostname(self):
        return self.local_hostname

    def send_master_pubkey( self ):
        # log.info("\tMT: Sending MASTER_PUBKEY message: %s" % self.app.manager.get_root_public_key() )
        self.app.manager.console_monitor.conn.send( 'MASTER_PUBKEY | %s' \
            % self.app.manager.get_root_public_key(), self.id )
        log.info("Sent master public key to worker instance '%s'." % self.id)
        log.debug( "\tMT: Message MASTER_PUBKEY %s sent to '%s'" \
            % ( self.app.manager.get_root_public_key(), self.id ) )

    def send_start_sge( self ):
        log.debug( "\tMT: Sending START_SGE message to instance '%s'" % self.id )
        self.app.manager.console_monitor.conn.send( 'START_SGE', self.id )

    def send_add_s3fs(self, bucket_name):
        msg = 'ADDS3FS | {0}'.format(bucket_name)
        log.debug("\tMT: Sending message '{msg}' to instance {inst}".format(msg=msg, inst=self.id))
        self.app.manager.console_monitor.conn.send(msg, self.id)

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
                try:
                    self.local_hostname = msp[6]
                except:
                    # Older versions of CloudMan did not pass this value so if the master
                    # and the worker are running 2 diff versions (can happen after an
                    # automatic update), don't crash here.
                    self.local_hostname = self.public_ip
                log.debug("INSTANCE_ALIVE private_dns:%s public_dns:%s pone:%s type:%s ami:%s hostname: %s"\
                    % (self.private_ip,
                       self.public_ip,
                       self.zone,
                       self.type,
                       self.ami,
                       self.local_hostname))
                # Instance is alive and functional. Send master pubkey.
                self.send_master_pubkey()
                # Add hostname to /etc/hosts (for SGE config)
                if self.app.cloud_type == 'openstack':
                    worker_host_line = '{ip}\t{hostname}\n'.format(ip=self.private_ip, \
                        hostname=self.local_hostname)
                    log.debug("worker_host_line: {0}".format(worker_host_line))
                    with open('/etc/hosts', 'r+') as f:
                        hosts = f.readlines()
                        if worker_host_line not in hosts:
                            log.debug("Adding worker {0} to /etc/hosts".format(self.local_hostname))
                            f.write(worker_host_line)
                if self.app.cloud_type == 'opennebula':
                    f = open( "/etc/hosts", 'a' )
                    f.write( "%s\tworker-%s\n" %  (self.private_ip, self.id))
                    f.close()
            elif msg_type == "WORKER_H_CERT":
                self.is_alive = True #This is for the case that an existing worker is added to a new master.
                self.app.manager.save_host_cert( msg.split( " | " )[1] )
                log.debug( "Worker '%s' host certificate received and appended to /root/.ssh/known_hosts" \
                    % self.id )
                try:
                    sge_svc = self.app.manager.get_services('SGE')[0]
                    if sge_svc.add_sge_host(self.get_id(), self.get_private_ip()):
                        # Send a message to worker to start SGE
                        self.send_start_sge()
                        # If there are any bucket-based FSs, tell the worker to add those
                        fss = self.app.manager.get_services('Filesystem')
                        for fs in fss:
                            if len(fs.buckets) > 0:
                                for b in fs.buckets:
                                    self.send_add_s3fs(b.bucket_name)
                        log.info( "Waiting on worker instance '%s' to configure itself..." % self.id )
                    else:
                        log.error("Adding host to SGE did not go smoothly, "
                            "not instructing worker to configure SGE daemon.")
                except IndexError:
                    log.error("Could not get a handle on SGE service to add a host; host not added")
            elif msg_type == "NODE_READY":
                self.node_ready = True
                self.worker_status = "Ready"
                log.info( "Instance %s ready" % self.get_desc() )
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

