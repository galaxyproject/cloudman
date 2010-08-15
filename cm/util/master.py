"""Galaxy CM master manager"""
import logging, logging.config, threading, sys, os, time, subprocess, string, tempfile, re, commands
import traceback, shutil, Queue, tarfile, pwd, grp, shutil, random, urllib2
import datetime as dt

from boto.s3.connection import S3Connection
from boto.ec2.connection import EC2Connection
from boto.exception import EC2ResponseError, S3ResponseError, BotoServerError
from boto.sqs.connection import SQSConnection
from boto.sqs.message import Message
from cm.util.bunch import Bunch

from cm.util import misc, comm, introspect
from cm.util.templates import *
from cm.util.paths import *

log = logging.getLogger( __name__ )

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


class ConsoleManager( object ):
    def __init__( self, app ):
        log.addHandler( app.logger )
        log.debug( "Initializing console manager." )
        self.app = app
        self.console_monitor = ConsoleMonitor( self.app )
        self.introspect = introspect.Introspect(self.app)
        self.volumes = {} # Elements should be of following format: [<volume id>, <device id>, <volume state flag>, <file system state flag>]
        self.root_pub_key = None
        self.cluster_status = cluster_status.OFF
        self.master_state = master_states.INITIAL_STARTUP
        self.persistent_vol_file = 'persistent-volumes-latest.txt'
        self.cluster_nodes_file = 'cluster_nodes.txt'
        self.num_workers_requested = None # Number of worker nodes requested by user
        self.create_user_data_vol = False # Indicates whether persistent user data volume should be created
        self.worker_instances = self.get_worker_instances() # actual number of worker nodes (note: this is a list of Instance objects)
        self.disk_total = "0"
        self.disk_used = "0"
        self.disk_pct = "0%"
        self.startup_time = dt.datetime.utcnow()
        
        self.start_galaxy = False
        self.galaxy_starting = False
        
        self.manager_started = False
        # Services' flags
        self.postgres_running = None
        self.sge_running = None
        self.galaxy_running = None
        self.snapshot_progress = None
        self.snapshot_status = None

        self.gc_standalone = False

        if self.app.TESTFLAG is True:
            self.volumes['galaxyTools'] = [5, 'tool_device', False, None]
            self.volumes['galaxyIndices'] = [6, 'index_device', True, None]
            self.volumes['galaxyData:0'] = [7, 'data_device', True, None]

    def recover_monitor(self, force='False'):
        if self.console_monitor:
            if force=='True':
                self.console_monitor.shutdown()
            else:
                return False
        self.console_monitor = ConsoleMonitor(self.app)
        self.console_monitor.start()
        return True

    def start( self ):
        if self.app.TESTFLAG is True:
            log.debug( "Attempted to start the ConsoleManager.  Nothing to start, passing." )
            return None
        self.manage_volumes( to_be_attached=True )
        self.manage_file_systems( to_be_mounted=True )
        self.manage_postgres( to_be_started=True )
        self.unpack_sge()
        self.configure_sge()
        self.manager_started = True
        log.info( "Completed initial cluster configuration." )

    def all_fs_status_text(self):
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
        tr = []
        for key, vol in self.volumes.iteritems():
            if vol[3] is None:
                tr.append([key, "nodata"])
                # tr.append("%s+nodata" % key)
            else:
                if vol[3] == True:
                    tr.append([key, "green"])
                    # tr.append("%s+green" % key)
                else:
                    tr.append([key, "red"])
                    # tr.append("%s+red" % key)
        return tr            


    def fs_status_text(self):
        """fs_status"""
        good_count = 0
        bad_count = 0
        if len(self.volumes) == 0:
            return "nodata"
        for vol in self.volumes.iterkeys():
            if self.volumes[vol][3] == True:
                good_count += 1
            elif self.volumes[vol][3] == False:
                bad_count += 1
        if good_count == len(self.volumes):
            return "green"
        elif bad_count > 0:
            return "red"
        else:
            return "yellow"

    def pg_status_text(self):
        """pg_status"""
        if self.postgres_running is None:
            return "nodata"
        else:
            if self.postgres_running:
                return "green"
            else:
                return "red"

    def sge_status_text(self):
        """sge_status"""
        if self.sge_running is None:
            return "nodata"
        else:
            if self.sge_running:
                return "green"
            else:
                return "red"

    def galaxy_status_text(self):
        """galaxy_status"""
        if self.galaxy_running is None:
            return "nodata"
        else:
            if self.galaxy_running:
                return "green"
            else:
                return "red"

    def get_cluster_status( self ):
        return self.cluster_status

    def get_instance_state( self ):
        return self.master_state

    def get_worker_instances( self ):
        if self.app.TESTFLAG is True:
            insts = []
            # for i in range(5):
            #     inst = Instance( self.app, inst=None, m_state="Pending" )
            #     inst.id = "WorkerInstance"
            #     insts.append(inst)
            return insts
        log.debug( "Trying to retrieve any reference to worker instances..." )
        instances = []
        s3_conn = self.app.get_s3_connection()
        log.debug( "Looking for bucket '%s'..." % self.app.shell_vars['BUCKET_NAME'] )
        b = s3_conn.lookup( self.app.shell_vars['BUCKET_NAME'] )
        if b is not None: # If bucket does not exist, start fresh
            log.debug( "Found bucket '%s'; looking for file '%s'" % ( self.app.shell_vars['BUCKET_NAME'], self.cluster_nodes_file ) )
            if misc.get_file_from_bucket( s3_conn, self.app.shell_vars['BUCKET_NAME'], self.cluster_nodes_file, self.cluster_nodes_file ):
                f = open( self.cluster_nodes_file, 'r' )
                instanceIDs = f.readlines()
                f.close()
                # Retrieve instances one at a time vs. entire list at once because some
                # might be alive while other are not and this way we'll know which ones
                ec2_conn = self.app.get_ec2_connection()
                for ID in instanceIDs:
                    ID = ID.strip() # get rid of the end line character
                    log.debug( "Trying to retrieve instance with ID '%s'..." % ID )
                    try:
                        reservation = ec2_conn.get_all_instances( ID )
                        if reservation:
                            if reservation[0].instances[0].state != 'terminated':
                                instance = Instance( self.app, inst=reservation[0].instances[0], m_state=reservation[0].instances[0].state )
                                instances.append( instance )
                                log.info( "Instance '%s' alive." % ID )
                    except EC2ResponseError, e:
                        log.debug( "Instance ID '%s' is no longer valid..." % ID )
                        log.debug( "Retrieving instance ID '%s' returned following error message: %s" % ( ID, e ) )
                if len( instances ) > 0:
                    self.save_worker_instance_IDs_to_S3( instances )
                    # Update cluster status
                    self.cluster_status = cluster_status.ON
                    self.master_state = master_states.SEND_MASTER_PUBKEY
                    self.console_monitor.last_state_change_time = dt.datetime.utcnow()
                    log.debug( "Changed state to '%s'" % self.master_state )
            else:
                log.info( "No existing instances found; starting fresh." )
        else:
            log.debug( "Bucket '%s' not found, continuing fresh." % self.app.shell_vars['BUCKET_NAME'] )

        return instances

    def shutdown( self , sd_galaxy = True, sd_sge = True, sd_postgres = True, sd_filesystems = True, sd_volumes = True, sd_instances = True, sd_volumes_delete = True):
        s3_conn = self.app.get_s3_connection()
        if sd_galaxy:
            try:
                log.info( "Initiating cluster shutdown procedure..." )
                self.master_state = master_states.SHUTTING_DOWN
                #self.console_monitor.shutdown()
                #stop galaxy
                if self.galaxy_running:
                    self.manage_galaxy( False )
            except Exception, ex:
                log.error( "Problem shutting down Galaxy, Exception: %s", ex )
        if sd_instances:
            try:
                # stop worker instances
                self.stop_worker_instances()
            except Exception, ex:
                log.error( "Unclean shutdown, Exception: %s", ex )    # Update cluster status
        if sd_sge:
            try:
                # stop SGE
                if self.sge_running:
                    self.stop_sge()
            except Exception, ex:
                log.error( "Problem shutting down SGE, Exception: %s", ex )
        if sd_postgres:
            try:
                #stop postgres
                if self.postgres_running:
                    self.manage_postgres( False )
            except Exception, ex:
                log.error( "Problem shutting down PostgreSQL, Exception: %s", ex )
        if sd_filesystems:
            try:
                #export fss
                self.manage_file_systems( False )
            except Exception, ex:
                log.error( "Problem exporting fss, Exception: %s", ex )
        if sd_volumes:
            try:
                #detach EBS volumes
                self.manage_volumes( False )
                # Delete 'attached_volumes.txt' bookkeeping file from cluster bucket
                if s3_conn is not None:
                    misc.delete_file_from_bucket(s3_conn, self.app.shell_vars['BUCKET_NAME'], 'attached_volumes.txt')
            except Exception, ex:
                log.error( "Problem detaching volumes, Exception: %s", ex )
        if sd_volumes_delete:
            try:
                # Delete 'galaxyTools' and 'galaxyIndices' EBS volumes 
                self.delete_volumes()
                # Delete 'created_volumes.txt' bookkeeping file from cluster bucket
                # if s3_conn is not None:
                #     misc.delete_file_from_bucket(s3_conn, self.app.shell_vars['BUCKET_NAME'], 'created_volumes.txt')
            except Exception, ex:
                log.error( "Problem deleting volumes, Exception: %s", ex )

        self.cluster_status = cluster_status.SHUT_DOWN
        self.master_state = master_states.SHUT_DOWN
        log.info( "Cluster shut down. Manually terminate master instance (and any remaining instances associated with this cluster) from the AWS console." )

    def set_master_state( self, new_state ):
        log.debug( "Setting master state to '%s'" % new_state )
        self.master_state = new_state

    def get_idle_instances( self ):
        # log.debug( "Looking for idle instances" )
        proc = subprocess.Popen( "export SGE_ROOT=%s; . $SGE_ROOT/default/common/settings.sh; %s/bin/lx24-amd64/qstat -f | grep all.q" % (P_SGE_ROOT, P_SGE_ROOT), shell=True, stdout=subprocess.PIPE )
        qstat_out = proc.communicate()[0]
        # log.debug( "qstat output: %s" % qstat_out )
        instances = qstat_out.splitlines()
        nodes_list = [] # list of nodes containing node's domain name and number of used processing slots
        idle_instances_dn = [] # list of domain names of idle instances 
        idle_instances = [] # Finally, list of Instance objects corresponding to idle instances
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
                        log.debug( "Marking instance '%s' with FQDN '%s' as idle." % ( w_instance.id, idle_instance_dn ) )
                        idle_instances.append( w_instance )

        return idle_instances

    def remove_instances( self, num_nodes, force=False ):
        num_nodes = int( num_nodes )
        # Decide which instance(s) to terminate, remove the from SGE and terminate
        num_instances_terminated = 0
        idle_instances = self.get_idle_instances()
        log.info( "Found '%s' idle instances; trying to remove '%s'" % ( len( idle_instances ), num_nodes ) )
        num_terminated = 0

        for i in range ( 0, num_nodes ):
            if len( idle_instances ) > 0:
                for inst in idle_instances:
                    if num_terminated < num_nodes:
                        if self.remove_sge_host( inst ) is True:
                            inst.terminate()
                            if inst in idle_instances:
                                idle_instances.remove( inst )
                            num_terminated += 1
            else:
                log.info( "No idle instances found" )
        if force is True and num_terminated < num_nodes:
            force_kill_instances = num_nodes - num_terminated
            log.info( "Forcefully terminating '%s' instances" % force_kill_instances )
            for i in range( 0, force_kill_instances ):
                for inst in self.worker_instances:
                    if self.remove_sge_host( inst ) is True:
                        inst.terminate()
                        if inst in self.worker_instances:
                            self.worker_instances.remove( inst )
                        num_terminated += 1
        if num_terminated > 0:
            log.info( "Initiated requested termination of instances. Terminating '%s' instances." % num_terminated )
        else:
            log.info( "Did not terminate any instances." )

    def remove_instance( self, instance_id = '' ):
        if instance_id == '':
            return False
        log.info( "Specific Terminate of %s instance requested." % instance_id)
        for inst in self.worker_instances:
            if inst.id == instance_id:
                if self.remove_sge_host( inst ) is True:
                    inst.terminate()
                    if inst in self.worker_instances:
                        self.worker_instances.remove( inst )
        log.info( "Initiated requested termination of instance. Terminating '%s'." % instance_id )


    def add_instances( self, num_nodes, instance_type=''):
        num_nodes = int( num_nodes )
        ec2_conn = self.app.get_ec2_connection()
        log.info( "Starting %s instance(s)..." % num_nodes )
        userData = self.app.shell_vars['CLUSTER_NAME'] + "|" + self.app.shell_vars['AWS_ACCESS_KEY'] + '|' + self.app.shell_vars['AWS_PRIVATE_KEY'] + '|' + self.app.shell_vars['PASSWORD'] + '|worker|' + self.app.get_self_private_ip()
        #log.debug( "userData: %s " % userData )
        reservation = None
        if instance_type == '':
            instance_type = self.app.get_type()
        log.debug( "Using following command: ec2_conn.run_instances( image_id='%s', min_count=1, max_count='%s', key_name='%s', security_groups=['%s'], user_data=[%s], instance_type='%s', placement='%s' )"
               % ( self.app.get_ami(), num_nodes, self.app.get_key_pair_name(), ", ".join( self.app.get_security_groups() ), userData, instance_type, self.app.get_zone() ) )
        try:
            # log.debug( "Would be starting worker instance(s)..." )
            reservation = ec2_conn.run_instances( image_id=self.app.get_ami(),
                                                  min_count=1,
                                                  max_count=num_nodes,
                                                  key_name=self.app.get_key_pair_name(),
                                                  security_groups=self.app.get_security_groups(),
                                                  user_data=userData,
                                                  instance_type=instance_type,
                                                  placement=self.app.get_zone() )
            if reservation:
                for instance in reservation.instances:
                    i = Instance( self.app, inst=instance, m_state=instance.state )
                    self.worker_instances.append( i )
                # Save list of started instances into a file on S3 to be used in case of cluster restart
                self.save_worker_instance_IDs_to_S3( self.worker_instances )

        except BotoServerError, e:
            log.error( "EC2 insufficient capacity error: %s" % str( e ) )
            return False
        except EC2ResponseError, e:
            err = "EC2 response error when starting worker nodes: %s" % str( e )
            log.error( err )
            return False
            # Update cluster status
            self.master_state = master_states.ERROR
            self.console_monitor.last_state_change_time = dt.datetime.utcnow()
            log.debug( "Changed state to '%s'" % self.master_state )
        except Exception, ex:
            err = "Error when starting worker nodes: %s" % str( ex )
            log.error( err )
            return False
            self.master_state = master_states.ERROR
            self.console_monitor.last_state_change_time = dt.datetime.utcnow()
            log.debug( "Changed state to '%s'" % self.master_state )
        
        log.debug( "Started %s instance(s)" % num_nodes )
        return True
        
    def create_user_data_volume(self, vol_size):
        ec2_conn = self.app.get_ec2_connection()
        log.info("Creating user data volume of size '%s'GB." % vol_size)
        data_vol = ec2_conn.create_volume(vol_size, self.app.get_zone())
        if data_vol:
            # Update permanent_storage_size and mark user data vol as created
            self.create_user_data_vol = False
            self.app.permanent_storage_size += int( data_vol.size )
            log.info( "Saving newly created user data volume ID (%s) to user's bucket '%s' within file '%s'."
                    % ( data_vol.id, self.app.shell_vars['BUCKET_NAME'], self.persistent_vol_file ) )
            s3_conn = self.app.get_s3_connection()
            f = open( self.persistent_vol_file, 'a' )
            f.write( '\nDATA_VOLUMES=' + str( data_vol.id ) + '\n' )
            f.close()
            misc.save_file_to_bucket( s3_conn, self.app.shell_vars['BUCKET_NAME'], self.persistent_vol_file, self.persistent_vol_file )

            # Save file to created_volumes.txt file as well
            # created_vols_file = 'created_volumes.txt'
            # f = open(created_vols_file, 'a')
            # f.write('galaxyData:0' + '@' + str(data_vol.id) + '\n')
            # f.close()
            # misc.save_file_to_bucket(s3_conn, self.app.shell_vars['BUCKET_NAME'], created_vols_file, created_vols_file)

            # Because only 1 volume may be created at cluster startup time, device id specified in P_GALAXY_DATA_MNT
            # was left open for the scenario of initial volume/file system creation  
            dev_id = P_GALAXY_DATA_MNT
            log.info( "Attaching user data volume '%s' to instance as device '%s'." % (data_vol.id, dev_id) )
            self.attach( data_vol.id, dev_id )
            self.volumes['galaxyData:0'] = [str(data_vol.id), None, None, None ] # [<volume id>, <device id>, <volume state flag>, <file system state flag>]
            self.create_galaxyData_file_system( dev_id )

            # Update attached_volumes.txt files in cluster's bucket
            attached_vols_file = 'attached_volumes.txt'
            f = open(attached_vols_file, 'a')
            f.write('galaxyData:0' + '@' + self.volumes['galaxyData:0'][0] + '@' + dev_id + '\n')
            f.close()
            misc.save_file_to_bucket(s3_conn, self.app.shell_vars['BUCKET_NAME'], attached_vols_file, attached_vols_file)
        else:
            log.error("Failed to create user data volume.")
            return False
        return True

    def init_cluster( self, num_nodes=0 ):
        self.cluster_status = cluster_status.STARTING
        log.debug( "Changed cluster_status to '%s'" % self.cluster_status )
        self.master_state = master_states.STARTING_WORKERS
        log.debug( "Changed master_state to '%s'" % self.master_state )
        ec2_conn = self.app.get_ec2_connection()
        if self.app.TESTFLAG is True:
            log.debug( "Attempted to init cluster but TESTFLAG is set. Continuing with one instance." )
            if self.create_user_data_vol:
                self.create_user_data_vol = False;
            return
        # If not there, create user data volume/fs and attach it to the instance
        if self.create_user_data_vol:
            if not self.volumes.has_key('galaxyData:0'):# not self.volumes['galaxyData:0'][2]:
                if self.create_user_data_volume(self.app.permanent_storage_size) is False:
                    return False
            else:
                log.debug("User data volume already exists. Status: '%s'" % self.volumes['galaxyData:0'])
                    
        # If postgres does not start, do not start worker instances
        if self.manage_postgres( to_be_started=True ):
            if not self.galaxy_running and not self.galaxy_starting:
                log.debug("\tMT: Setting hook to start Galaxy")
                self.start_galaxy = True
            if num_nodes > 0:
                if not self.add_instances( num_nodes ):
                    self.cluster_status = cluster_status.OFF
                    return False
                log.info( "Waiting for worker instance(s) to start..." )
            return True

    def stop_worker_instances( self ):
        log.info( "Stopping all '%s' worker instance(s)" % len(self.worker_instances) )
        to_terminate = []
        for i in self.worker_instances:
            to_terminate.append(i)
        for inst in to_terminate:
            log.debug("Initiating termination of instance '%s'" % inst.id )
            inst.terminate()
            log.debug("Initiated termination of instance '%s'" % inst.id )
            
        # Update or delete list of started instances to a file on S3 to be used in case of cluster restart
        if len( self.worker_instances ) > 0:
            self.save_worker_instance_IDs_to_S3( self.worker_instances )
        else:
            s3_conn = self.app.get_s3_connection()
            if s3_conn is not None:
                misc.delete_file_from_bucket( s3_conn, self.app.shell_vars['BUCKET_NAME'], self.cluster_nodes_file )
            
    def save_worker_instance_IDs_to_S3( self, instances ):
        """ instances must be an EC2 object"""
        if self.app.TESTFLAG is True:
            log.debug( "Attempted to save instances to S3, but TESTFLAG is set." )
            return None
        try:
            s3_conn = self.app.get_s3_connection()
            f = open( self.cluster_nodes_file, 'w' )
            for instance in instances:
                f.write( str( instance.id ) + "\n" )
            f.close()
            log.debug( "Saving list of started instances to S3 bucket '%s' as file '%s'..." % ( self.app.shell_vars['BUCKET_NAME'], self.cluster_nodes_file ) )
            misc.save_file_to_bucket( s3_conn, self.app.shell_vars['BUCKET_NAME'], self.cluster_nodes_file, self.cluster_nodes_file )
        except Exception, e:
            log.error( "Saving list of started instances to S3 bucket '%s' failed. Not retrying but continuing. Error: %s" % ( self.app.shell_vars['BUCKET_NAME'], e ) )

    def create_bucket( self, s3_conn, bucket_name ):
        if self.app.TESTFLAG is True:
            log.debug( "Attempted to create a bucket, but TESTFLAG is set." )
            return None
        try:
            log.info( "Creating user's bucket '%s' on S3..." % bucket_name )
            bucket = s3_conn.create_bucket( bucket_name )
            if bucket:
                return True
        except S3ResponseError, e:
            log.error( "Error while creating bucket '%s': %s" % ( bucket_name, e ) )
            # TODO: Add parsing of error message and check if bucket is owned by current
            # user; if so, return True 
        log.warning( "Something did not go smoothly while creating bucket '%s'" % bucket_name )
        return False

    def create_galaxyData_file_system ( self, device ):
        if self.app.TESTFLAG is True:
            log.debug( "Attempted to create galaxyData file system, but TESTFLAG is set." )
            return None
        log.info( "Creating user data file system 'galaxyData' on device '%s'." % device )
        galaxyData_dir = P_GALAXY_DATA
        os.mkdir ( galaxyData_dir )
        subprocess.call( '%s -R galaxy:galaxy %s' % (P_CHOWN, galaxyData_dir), shell=True )
        ret_code = subprocess.call( '/sbin/mkfs.xfs %s' % device, shell=True )
        if ret_code == 0:
            log.debug( "Successfully created file system 'galaxyData' on device '%s'" % device )
            self.volumes['galaxyData:0'][1] = device # Store attached device ID for given volume
            self._mount(device, galaxyData_dir)
        else:
            log.debug( "Error creating file system 'galaxyData' on device '%s'. Process returned code '%s'" % ( device, ret_code ) )

        os.mkdir( '%s/files64' % galaxyData_dir )
        os.mkdir( '%s/tmp' % galaxyData_dir )
        os.mkdir( '%s/upload_store' % galaxyData_dir )
        subprocess.call( '%s -R galaxy:galaxy %s/' % (P_CHOWN, galaxyData_dir), shell=True )

        #subprocess.call( '/usr/bin/su - galaxy -c "/usr/gnu/bin/sh $GALAXY_HOME/setup.sh"')

    def attach( self, volume_id, device ):
        """
        Attach EBS volume to the given device (using boto).
        Try it for some time.
        """
        if self.app.TESTFLAG is True:
            log.debug( "Attempted to attach EBS volume, but TESTFLAG is set." )
            return None
        log.debug("Attempting to attach volume '%s' to instance '%s' as device '%s'" % (volume_id, self.app.get_instance_id(), device))
        ec2_conn = self.app.get_ec2_connection()
        try:
            volumestatus = ec2_conn.attach_volume( volume_id, self.app.get_instance_id(), device )
        except EC2ResponseError, ( e ):
            log.info( "Attaching volume '%s' to instance '%s' as device '%s' failed. Exception: %s" % ( volume_id, self.app.get_instance_id(), device, e ) )
            return False
        except Exception, ex:
            log.info( "Unexpected Exception: Attaching volume '%s' to instance '%s' as device '%s' failed. Exception: %s" % ( volume_id, self.app.get_instance_id(), device, e ) )
            return False
        log.debug( "Attaching volume '%s' to instance '%s' as device '%s'" % ( volume_id, self.app.get_instance_id(), device ) )

        # get_all_volumes method below takes list as argument, so create on containing volume id(s)
        volumeid_list = list()
        volumeid_list.append( volume_id )
        for counter in range( 30 ):
            log.debug ( "Attach attempt %s, volume status: %s" % ( counter, volumestatus ) )
            if volumestatus == 'attached':
                log.info ( "Volume '%s' attached to instance '%s' as device '%s'" % ( volume_id, self.app.get_instance_id(), device ) )
                break
            if counter == 29:
                log.info ( "Volume '%s' FAILED to attach to instance '%s' as device '%s'. Aborting." % ( volume_id, self.app.get_instance_id(), device ) )
                return False

            volumes = ec2_conn.get_all_volumes( volume_ids=volumeid_list )
            for volume in volumes:
                volumestatus = volume.attachment_state()
            time.sleep( 3 )
        return True
        
    def detach( self, volume_id, device='N/A' ):
        if self.app.TESTFLAG is True:
            log.debug( "Attempted to detatch a device, but TESTFLAG is set." )
            return None
        log.debug( "Attempting to detach volume '%s' from instance '%s'." % ( volume_id, self.app.get_instance_id() ) )
        ec2_conn = self.app.get_ec2_connection()
        try:
            volumestatus = ec2_conn.detach_volume( volume_id, self.app.get_instance_id(), force=True )
        except EC2ResponseError, ( e ):
            log.warning( "Detaching volume '%s' from instance '%s' failed. Exception: %s" % ( volume_id, self.app.get_instance_id(), e ) )
            return False
        volumeid_list = list()
        volumeid_list.append( volume_id )

        for counter in range( 30 ):
            log.debug( "Volume '%s' status '%s'" % ( volume_id, volumestatus ) )
            if volumestatus == 'available':
                log.info ( "Volume '%s' successfully detached from instance '%s'." % ( volume_id, self.app.get_instance_id() ) )
                break
            if counter == 29:
                log.info ( "Volume '%s' FAILED to detach to instance '%s'." % ( volume_id, self.app.get_instance_id() ) )
            time.sleep( 3 )
            volumes = ec2_conn.get_all_volumes( volume_ids=volumeid_list )
            for volume in volumes:
                volumestatus = volume.status

    def get_volumes( self ):
        if self.app.TESTFLAG is True:
            log.debug( "Attempted to get volumes, but TESTFLAG is set." )
            return None
        # Test for existence of bucket and download appropriate snapshot file
        s3_conn = self.app.get_s3_connection()
        ec2_conn = self.app.get_ec2_connection()
        new_volumes = False
        created_volumes = [] # ID's of created volumes - used for restarting purposes
        
        if self.volumes is None or not self.volumes.has_key('galaxyData:0'):
            b = s3_conn.lookup( self.app.shell_vars['BUCKET_NAME'] )
            if b is not None:
                log.info( "User's bucket '%s' found; retrieving previously used snapshots." % b.name )
                #TOOD: check if this file exists and is correctly formatted
                #TODO: make sure current instance is in the same availability zone as found volume
                if misc.get_file_from_bucket( s3_conn, b.name, 'persistent-volumes-latest.txt', self.persistent_vol_file ) is True:
                    vol_vars = misc.shellVars2Dict( self.persistent_vol_file )
                    try:
                        user_data_volumes = vol_vars['DATA_VOLUMES']
                        user_data_volume_ids = user_data_volumes.split( '|' )
                        log.info("Using the following volumes as user data volumes: %s" % user_data_volume_ids)
                        for i, user_data_volume_id in enumerate( user_data_volume_ids ):
                            rs = ec2_conn.get_all_volumes( user_data_volume_id )
                            self.app.permanent_storage_size += rs[0].size
                            self.volumes['galaxyData:' + str( i ) ] = [user_data_volume_id, None, None, None]
                    except KeyError, e:
                        # User data volume ID not found. Volume might never have been created because worker
                        # nodes never got started for given cluster name or an error might have occurred in the 
                        # pipeline. For now, a new volume will be created but in future, this should
                        # probably imply user action asking them if they can provide a volume ID.
                        log.warning( "User data volume could not have been retrieved from user's persistent data file; will create a new user data volume. Error message: %s" % e )
                    except EC2ResponseError, e:
                        err = "Error retrieving user data volume with ID '%s'. Error: %s" % (user_data_volume_id, str( e ))
                        log.error( err )
                        return False
                else:
                    log.error( "Failed to get file 'persistent-volumes-latest.txt' from bucket '%s'. Reverting to default GC from bucket 'gc-snapshots'." % b.name )
                    log.info( "Using default snapshots of Tools and Indices." )
                    misc.get_file_from_bucket( s3_conn, 'gc-snapshots', 'snaps-latest.txt', self.persistent_vol_file )
                    new_volumes = True
                    vol_vars = misc.shellVars2Dict( self.persistent_vol_file )
            else:
                log.info( "User's bucket '%s' not found; using default snapshots of Tools and Indices." % self.app.shell_vars['BUCKET_NAME'] )
                misc.get_file_from_bucket( s3_conn, 'gc-snapshots', 'snaps-latest.txt', self.persistent_vol_file )
                new_volumes = True
                vol_vars = misc.shellVars2Dict( self.persistent_vol_file )

        if self.volumes is None or not self.volumes.has_key('galaxyTools'):
            tools = vol_vars['TOOLS']
            tools_snap_id = tools.split( '|' )[0]
            tools_vol_size = tools.split( '|' )[1]
            log.info( "Creating tools volume of size %sGB in '%s' zone from snapshot '%s'" % ( tools_vol_size, self.app.get_zone(), tools_snap_id ) )
            tools_vol = ec2_conn.create_volume( tools_vol_size, self.app.get_zone(), tools_snap_id )
            self.volumes['galaxyTools'] = [tools_vol.id, None, None, None]
            created_volumes.append('galaxyTools@' + tools_vol.id)

        if self.volumes is None or not self.volumes.has_key('galaxyIndices'):
            indices = vol_vars['INDICES']
            indices_snap_id = indices.split( '|' )[0]
            indices_vol_size = indices.split( '|' )[1]
            log.info( "Creating indices volume of size %sGB in '%s' zone from snapshot '%s'" % ( indices_vol_size, self.app.get_zone(), indices_snap_id ) )
            indices_vol = ec2_conn.create_volume( indices_vol_size, self.app.get_zone(), indices_snap_id )
            self.volumes['galaxyIndices'] = [indices_vol.id, None, None, None]
            created_volumes.append('galaxyIndices@' + indices_vol.id)
        
        # If volumes were created from default GC distribution, persist them in user's bucket for versioning reasons
        if new_volumes:
            if self.create_bucket( s3_conn, self.app.shell_vars['BUCKET_NAME'] ):
                log.info( "Saving tools and indices snapshot info file (%s) to user's bucket '%s'..." % ( self.persistent_vol_file, self.app.shell_vars['BUCKET_NAME'] ) )
                misc.save_file_to_bucket( s3_conn, self.app.shell_vars['BUCKET_NAME'], self.persistent_vol_file, self.persistent_vol_file )
                log.info( "Saving GC application to user's bucket '%s'" % self.app.shell_vars['BUCKET_NAME'] )
                gc_file_name = 'gc.tar.gz'
                misc.save_file_to_bucket( s3_conn, self.app.shell_vars['BUCKET_NAME'], gc_file_name, gc_file_name )
                default_GC_rev = misc.get_file_metadata(s3_conn, 'gc-default', gc_file_name, 'revision')
                if default_GC_rev:
                    misc.set_file_metadata(s3_conn, self.app.shell_vars['BUCKET_NAME'], gc_file_name, 'revision', default_GC_rev)
                
        # If changes have been made, save created_volumes to the cluster's bucket
        # self._make_file_from_list(created_volumes, 'created_volumes.txt', self.app.shell_vars['BUCKET_NAME'])
        # if len(created_volumes) > 0:
        #     vols_file = 'created_volumes.txt'
        #     f = open(vols_file, 'w')
        #     for cv in created_volumes:
        #         f.write("%s\n" % cv)
        #     f.close()
        #     log.debug( "Saving created volumes IDs to user's bucket '%s'." % self.app.shell_vars['BUCKET_NAME'] )
        #     misc.save_file_to_bucket(s3_conn, self.app.shell_vars['BUCKET_NAME'], vols_file, os.getcwd() + '/' + vols_file)

        return True
        
    def check_for_new_version_of_GC(self):
        """ Check revision metadata for GC in user's bucket and the default GC bucket.
        :rtype: bool
        :return: If default revison number of GC is greater than user's version of GC, return True.
                 Else, return False
        """
        if self.app.TESTFLAG is True:
            log.debug( "Attempted to check for new version of GC, but TESTFLAG is set." )
            return 'http://boto.s3.amazonaws.com/s3_tut.html'
        log.debug("Checking for new version of GC")
        file_name = 'gc.tar.gz'
        s3_conn = self.app.get_s3_connection()
        user_GC_rev = misc.get_file_metadata(s3_conn, self.app.shell_vars['BUCKET_NAME'], file_name, 'revision')
        default_GC_rev = misc.get_file_metadata(s3_conn, 'gc-default', file_name, 'revision')
        if user_GC_rev and default_GC_rev:
            log.debug("Revision number for user's GC: '%s'; revision number for default GC: '%s'" % (user_GC_rev, default_GC_rev))
            if default_GC_rev > user_GC_rev:
                return True
        return False

    def update_users_GC(self):
        """ If the revision number of GC in user's bucket is less than that of default GC, 
        upload the new version of GC to user's bucket. Note that the update will take effect 
        only after the next cluster reboot.
        :rtype: bool
        :return: If update was successfull, return True.
                 Else, return False
        """
        if self.app.TESTFLAG is True:
            log.debug( "Attempted to update GC, but TESTFLAG is set." )
            return None
        if self.check_for_new_version_of_GC():
            log.info("Updating GC application in user's bucket '%s'. It will be automaticaly available the next this cluster is instantiated." % self.app.shell_vars['BUCKET_NAME'] )
            s3_conn = self.app.get_s3_connection()
            if misc.get_file_from_bucket(s3_conn, 'gc-default', 'gc.tar.gz', 'gc.tar.gz_new'):
                if misc.save_file_to_bucket(s3_conn, self.app.shell_vars['BUCKET_NAME'], 'gc.tar.gz', 'gc.tar.gz_new'):
                    return True
        return False

    def manage_volumes( self, to_be_attached=True ):
        if self.app.TESTFLAG is True:
            log.debug( "Attempted to manage volumes, but TESTFLAG is set." )
            return None
                
        if to_be_attached:
            # Check the current state of attached volumes    
            self.volumes = self.introspect.check_for_existing_volumes()
            log.debug( "Initiating creation/attaching of external data volumes: '%s'" % self.volumes)
            attached_volumes = []
            
            # Create or attach necessary volumes, depending on cluster's invocation properties
            if self.get_volumes():
                if self.volumes.has_key('galaxyTools'):
                    if not self.volumes['galaxyTools'][2]:
                        # Attach 'galaxyTools' volume
                        dev_id = '/dev/sdg'
                        self.attach( self.volumes['galaxyTools'][0], dev_id  )
                        self.volumes['galaxyTools'][1] = dev_id # Store attached device ID for given volume
                        attached_volumes.append('galaxyTools' + '@' + self.volumes['galaxyTools'][0] + '@' + dev_id)
                    else:
                        log.info("'galaxyTools' data volume already attached.")
                else:
                    log.warning("'galaxyTools' volume does not seem to have been created. Not attaching it.")

                if self.volumes.has_key('galaxyIndices'):
                    if not self.volumes['galaxyIndices'][2]:
                        # Attach 'galaxyIndices' volume
                        dev_id = '/dev/sdi'
                        self.attach( self.volumes['galaxyIndices'][0], dev_id  )
                        self.volumes['galaxyIndices'][1] = dev_id # Store attached device ID for given volume
                        attached_volumes.append('galaxyIndices' + '@' + self.volumes['galaxyIndices'][0] + '@' + dev_id)
                    else:
                        log.info("'galaxyIndices' data volume already attached.")
                else:
                    log.warning("'galaxyIndices' volume does not seem to have been created. Not attaching it.")
                    
                # TODO: Once multiple data voluems can be associated with a single cluster, below implementation
                # will *not* work but will have to be redesigned.
                if self.volumes.has_key('galaxyData:0'):
                    if not self.volumes['galaxyData:0'][2]:
                        # Attach 'galaxyData' volume
                        dev_id = P_GALAXY_DATA_MNT
                        self.attach( self.volumes['galaxyData:0'][0], dev_id  )
                        self.volumes['galaxyData:0'][1] = dev_id # Store attached device ID for given volume
                        attached_volumes.append('galaxyData:0' + '@' + self.volumes['galaxyData:0'][0] + '@' + dev_id)
                    else:
                        log.info("'galaxyData' data volume already attached.")
                        ec2_conn = self.app.get_ec2_connection()
                        self.app.permanent_storage_size = misc.get_volume_size(ec2_conn, self.volumes['galaxyData:0'][0])
                        log.debug("User data volume size: %sGB" % self.app.permanent_storage_size)
                else:
                    log.warning("'galaxyData' data volume not there yet; will get it at worker instance start time.")
                
                # If changes were made, save attached_volumes to the cluster's bucket
                self._make_file_from_list(attached_volumes, 'attached_volumes.txt', self.app.shell_vars['BUCKET_NAME'])
            else:
                log.error("Could not get necessary data volumes!")
        else:
            # Detach EBS volumes
            log.debug("Initiating detaching of external data volumes: %s" % self.volumes)
            for key in self.volumes:
                self.detach(self.volumes[key][0])

    def manage_file_systems( self, to_be_mounted=True ):
        if self.app.TESTFLAG is True:
            log.debug( "Attempted to manage file systems, but TESTFLAG is set." )
            return None

        # Check the current state of attached volumes    
        self.volumes = self.introspect.check_for_existing_volumes()
        
        if to_be_mounted:
            log.debug( "Initiating mounting of file systems: %s" % self.volumes )
            # fs_success = False
            galaxyData_mounted = False
            for fs in self.volumes:
                if not self.volumes[fs][3]: # Check if the fs is already mounted
                    if fs.find( ':' ) != -1: # handle multiple volumes comprising galaxyData file system (fs)
                        # TODO: Implement this completely once functionality for composing multiple volumes into the fs is available 
                        if galaxyData_mounted:
                            continue
                        fs = str( 'galaxyData' )
                        galaxyData_mounted = True # TODO: fix this so it's set only on success
                    try:
                        mount_point = '/mnt/' + fs
                        # FIXME: fix reference to multiple volumes for galaxyData once approach is defined
                        if fs == 'galaxyData':
                            dev_id = self.volumes['galaxyData:0'][1]
                        else:
                            dev_id = self.volumes[fs][1]
                        log.debug( "Mounting file system '%s' attached as device '%s' to '%s'" % ( fs, dev_id, mount_point ) )
                        if dev_id is not None:
                            if os.path.exists(mount_point):
                                if len(os.listdir(mount_point)) != 0:
                                    log.error("Filesystem at %s already exists and is not empty." % mount_point)
                                    return False
                            else:
                                os.mkdir( mount_point )
                            self._mount(dev_id, mount_point)
                        else:
                            log.error( "Device ID for file system '%s' is None. Not mounting this file system." % fs )
                    except Exception, e:
                        log.error( "Mounting file system '%s' failed: %s" % ( fs, e ) )
                else:
                    log.info("File system '%s' already mounted." % fs)

            # Mark galaxy as being ready to start as soon as galaxyData (and galaxyTools) are available
                if os.path.exists(P_GALAXY_HOME) and os.path.exists(P_GALAXY_DATA):
                    if not self.galaxy_running and not self.galaxy_starting:
                        log.debug("\tMT: Setting hook to start Galaxy")
                        self.start_galaxy = True
        else:
            log.debug( "Initiating unmounting of file systems: %s" % self.volumes )
            # fs_success = False
            galaxyData_unmounted = False
            for fs in self.volumes:
                if fs.find( ':' ) != -1: # handle multiple volumes comprising galaxyData fs
                    if galaxyData_unmounted:
                        continue
                    fs = 'galaxyData'
                    galaxyData_unmounted = True # TODO: fix this to be set only after success
                try:
                    mount_point = '/mnt/' + fs
                    log.info( "Unmounting file system '%s' from '%s'" % ( fs, mount_point ) )
                    self._umount(mount_point)
                except Exception, e:
                    log.error( "Unmounting file system '%s' failed: %s" % ( fs, e ) )

    def delete_volumes( self ):
        if self.app.TESTFLAG is True:
            log.debug( "Attempted to get volumes, but TESTFLAG is set." )
            return None
        log.info( "Deleting galaxyTools and galaxyIndices data volumes..." )
        ec2_conn = self.app.get_ec2_connection()

        vol_id = self.volumes['galaxyTools'][0]
        log.debug( "Deleting 'galaxyTools' volume with ID '%s'..." % vol_id )
        ec2_conn.delete_volume( vol_id )

        vol_id = self.volumes['galaxyIndices'][0]
        log.debug( "Deleting 'galaxyIndices' volume with ID '%s'..." % vol_id )
        ec2_conn.delete_volume( vol_id )

    def unpack_sge( self ):
        if self.app.TESTFLAG is True:
            log.debug( "Attempted to get volumes, but TESTFLAG is set." )
            return None
        os.putenv( 'SGE_ROOT', P_SGE_ROOT )
        # Ensure needed directory exists
        if not os.path.exists( P_SGE_TARS ):
            log.error( "'%s' directory with SGE binaries does not exist! Aborting SGE setup." % P_SGE_TARS )
            return False
        if not os.path.exists( P_SGE_ROOT ):
            os.mkdir ( P_SGE_ROOT )
        # Ensure SGE_ROOT directory is empty (useful for restarts)
        if len(os.listdir(P_SGE_ROOT)) > 0:
            # Check if qmaster is running in that case
            if self.introspect.check_qmaster():
                log.info("Found SGE already running; will reconfigure it.")
                self.stop_sge()
            log.debug("Cleaning '%s' directory." % P_SGE_ROOT)
            for base, dirs, files in os.walk(P_SGE_ROOT):
                for f in files:
                    os.unlink(os.path.join(base, f))
                for d in dirs:
                    shutil.rmtree(os.path.join(base, d))

        log.debug( "Unpacking SGE to '%s'." % P_SGE_ROOT )
        tar = tarfile.open( '%s/ge-6.2u5-common.tar.gz' % P_SGE_TARS )
        tar.extractall( path=P_SGE_ROOT )
        tar.close()
        tar = tarfile.open( '%s/ge-6.2u5-bin-lx24-amd64.tar.gz' % P_SGE_TARS )
        tar.extractall( path=P_SGE_ROOT )
        tar.close()
        subprocess.call( '%s -R sgeadmin:sgeadmin %s' % (P_CHOWN, P_SGE_ROOT), shell=True )

    def configure_sge( self ):
        if self.app.TESTFLAG is True:
            log.debug( "Attempted to get volumes, but TESTFLAG is set." )
            return None
        log.info( "Configuring SGE..." )
        # Add master as an execution host
        # Additional execution hosts will be added later, as they start
        exec_nodes = self.app.get_self_private_ip() 

        SGE_config_file = '%s/galaxyEC2.conf' % P_SGE_ROOT
        f = open( SGE_config_file, 'w' )
        print >> f, SGE_INSTALL_TEMPLATE % ( self.app.get_self_private_ip(), self.app.get_self_private_ip(), exec_nodes )
        f.close()
        os.chown( SGE_config_file, pwd.getpwnam( "sgeadmin" )[2], grp.getgrnam( "sgeadmin" )[2] )
        log.debug( "Created SGE install template as file '%s'" % SGE_config_file )

        log.info( "Setting up SGE." )
        ret_code = subprocess.call( 'cd %s; ./inst_sge -m -x -auto %s' % (P_SGE_ROOT, SGE_config_file), shell=True )
        if ret_code == 0:
            log.info("Successfully setup SGE; configuring SGE")
            SGE_allq_file = '%s/all.q.conf' % P_SGE_ROOT
            f = open( SGE_allq_file, 'w' )
            print >> f, ALL_Q_TEMPLATE
            f.close()
            os.chown( SGE_allq_file, pwd.getpwnam( "sgeadmin" )[2], grp.getgrnam( "sgeadmin" )[2] )
            log.debug( "Created SGE all.q template as file '%s'" % SGE_allq_file )
            ret_code = subprocess.call( 'cd %s; ./bin/lx24-amd64/qconf -Mq %s all.q' % (P_SGE_ROOT, SGE_allq_file), shell=True )
            if ret_code == 0:
                log.debug("Successfully modified all.q")
            else:
                log.debug("Error modifying all.q, ret code: %s" % ret_code)
            
            log.debug("Configuring users' SGE profiles" )
            f = open( "/etc/bash.bashrc", 'a' )
            f.write( "\nexport SGE_ROOT=%s" % P_SGE_ROOT )
            f.write( "\n. $SGE_ROOT/default/common/settings.sh\n" )
            f.close()
        else:
            log.error( "Setting up SGE did not go smoothly, process returned code '%s'" % ret_code )

    def add_sge_host( self, inst ):
        # TODO: Should check to ensure SGE_ROOT mounted on worker
        proc = subprocess.Popen( "export SGE_ROOT=%s; . $SGE_ROOT/default/common/settings.sh; %s/bin/lx24-amd64/qconf -shgrp @allhosts" % (P_SGE_ROOT, P_SGE_ROOT), shell=True, stdout=subprocess.PIPE )
        allhosts_out = proc.communicate()[0]
        inst_ip = inst.get_private_ip()
        error = False
        if not inst_ip:
            log.error( "Instance '%s' IP not retrieved! Not adding instance to SGE exec host pool." % inst.id )
            return False
        if inst_ip not in allhosts_out:
            log.info( "Adding instance %s to SGE Execution Host list" % inst.id )
            time.sleep(10) # Wait in hope that SGE processed last host addition
            stderr = None
            stdout = None
            proc = subprocess.Popen( 'export SGE_ROOT=%s; . $SGE_ROOT/default/common/settings.sh; %s/bin/lx24-amd64/qconf -ah %s' % (P_SGE_ROOT, P_SGE_ROOT, inst_ip), shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE )
            std = proc.communicate()
            if std[0]:
                stdout = std[0]
            if std[1]:
                stderr = std[1]
            log.debug( "stdout: %s" % stdout )
            log.debug( "stderr: %s" % stderr )
            # TODO: Should be looking at return code and use stdout/err just for info about the process progress...
            # It seems that SGE prints everything to stderr
            if stderr is None or 'already exists' in stderr or 'added to administrative host list' in stderr:
                log.debug( "Successfully added instance '%s' (w/ private IP: %s) as administrative host." % (inst.id, inst.private_ip ))
            else:
                error = True
                log.debug( "Encountered problems adding instance '%s' as administrative host: %s" % ( inst.id, stderr ) )
            # if ret_code == 0:
            #     log.debug( "Successfully added instance '%s' as administrative host." % inst.id )
            # else:
            #     error = True
            #     log.error( "Failed to add instance '%s' as administrative host." % inst.id )

            # Create temp dir to hold all worker host configuration files
            host_conf_dir = "%s/host_confs" % P_SGE_ROOT
            if not os.path.exists( host_conf_dir ):
                ret_code = subprocess.call( 'mkdir -p %s' % host_conf_dir, shell=True )
                os.chown( host_conf_dir, pwd.getpwnam( "sgeadmin" )[2], grp.getgrnam( "sgeadmin" )[2] )
            host_conf = host_conf_dir + '/' + str( inst.id )
            f = open( host_conf, 'w' )
            print >> f, SGE_HOST_CONF_TEMPLATE % ( inst_ip )
            f.close()
            os.chown( host_conf, pwd.getpwnam( "sgeadmin" )[2], grp.getgrnam( "sgeadmin" )[2] )
            log.debug( "Created SGE host configuration template as file '%s'." % host_conf )
            # Add worker instance as execution host to SGE
            proc = subprocess.Popen( 'export SGE_ROOT=%s; . $SGE_ROOT/default/common/settings.sh; %s/bin/lx24-amd64/qconf -Ae %s' % (P_SGE_ROOT, P_SGE_ROOT, host_conf), shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE )
            stderr = None
            stdout = None
            std = proc.communicate()
            if std[0]:
                stdout = std[0]
            if std[1]:
                stderr = std[1]
            log.debug( "Adding SGE execution host stdout (instance: '%s', private IP: '%s'): %s" % (inst.id, inst.private_ip, stdout))
            log.debug( "Adding SGE execution host stderr (instance: '%s', private IP: '%s'): %s" % (inst.id, inst.private_ip, stderr))
            # TODO: Should be looking at return code and use stdout/err just for info about the process progress...
            if stderr is None or 'added' in stderr:
                log.debug( "Successfully added instance '%s' as execution host." % inst.id )
            elif 'already exists' in stderr:
                log.debug( "Instance '%s' already exists in exechost list: %s" % ( inst.id, stderr ) )
            else:
                error = True
                log.debug( "Encountered problems adding instance '%s' as execution host: %s" % ( inst.id, stderr ) )
            
            # Check if given instance's hostname is in @allhosts list and add it if it's not
            now = dt.datetime.utcnow()
            ah_file = '/tmp/ah_add_' + now.strftime("%H_%M_%S")
            self.write_allhosts_file( filename=ah_file, to_add = inst_ip)
            self._run('export SGE_ROOT=%s; . $SGE_ROOT/default/common/settings.sh; %s/bin/lx24-amd64/qconf -Mhgrp %s' % (P_SGE_ROOT, P_SGE_ROOT, ah_file),"Problems updating @allhosts aimed at removing '%s'" % inst.id, "Successfully updated @allhosts to remove '%s'" % inst.id)
            
            # On instance reboot, SGE might have already been configured for given instance and this
            # process will fail although instance may register fine with SGE...
            if error is False:
                log.info( "Successfully added instance '%s' to SGE" % inst.id )
        else:
            log.info( "Instance '%s' already in SGE's @allhosts" % inst.id )
            
        return True

    def stop_sge( self ):
        log.info( "Stopping SGE." )
        for inst in self.worker_instances:
            self.remove_sge_host( inst )
    
        ret_code = subprocess.call( 'export SGE_ROOT=%s; . $SGE_ROOT/default/common/settings.sh; %s/bin/lx24-amd64/qconf -km' % (P_SGE_ROOT, P_SGE_ROOT), shell=True )
        if ret_code == 0:
            log.debug( "Successfully stopped SGE master." )
        else:
            log.error( "Problems stopping SGE master; process returned code '%s'" % ret_code )

    # def write_allhosts_file_NEW_not_working(self, filename = '/tmp/ah', to_add = None, to_remove = None):
    #     ahl = []
    #     for inst in self.worker_instances:
    #         log.debug( "Adding instance IP '%s' to SGE's group config file '%s'" % ( inst.get_private_ip(), filename ) )
    #         ahl.append(inst.private_ip)
    #         
    #     # For comparisson purposes, make sure all elements are lower case
    #     for i in range(len(ahl)):
    #         ahl[i] = ahl[i].lower()
    #     
    #     # Now reasemble and save to file 'filename'
    #     if len(ahl) > 0:
    #         new_allhosts = 'group_name @allhosts \n'+'hostlist ' + ' \\\n\t '.join(ahl) + ' \\\n'
    #     else:
    #         new_allhosts = 'group_name @allhosts \nhostlist NONE\n'
    #     f = open( filename, 'w' )
    #     f.write( new_allhosts )
    #     f.close()
    #     log.debug("new_allhosts: %s" % new_allhosts)
    #     log.debug("New SGE @allhosts file written successfully to %s." % filename)
    
    def write_allhosts_file(self, filename = '/tmp/ah', to_add = None, to_remove = None):
        proc = subprocess.Popen( "export SGE_ROOT=%s; . $SGE_ROOT/default/common/settings.sh; %s/bin/lx24-amd64/qconf -shgrp @allhosts" % (P_SGE_ROOT, P_SGE_ROOT), shell=True, stdout=subprocess.PIPE )
        allhosts_out = proc.communicate()[0]
        # Parsed output is in all lower case so standardize now
        try:
            to_add = to_add.lower()
        except AttributeError: # Means, value is None
            pass
        try:
            to_remove = to_remove.lower()
        except AttributeError: # Means, value is None
            pass
        
        ahl = allhosts_out.split()
        if 'NONE' in ahl:
            ahl.remove( 'NONE' )
        if 'hostlist' in ahl:
            ahl.remove( 'hostlist' )
        if '@allhosts' in ahl:
            ahl.remove( '@allhosts' )
        if 'group_name' in ahl:
            ahl.remove( 'group_name' )            
        while '\\' in ahl: # remove all backslashes
            ahl.remove('\\')
        # For comparisson purposes, make sure all elements are lower case
        for i in range(len(ahl)):
            ahl[i] = ahl[i].lower()
        # At this point we have a clean list of instances
        log.debug( 'ahl: %s' % ahl )
        log.debug( "to_add: '%s'" % to_add )
        log.debug( "to_remove: '%s'" % to_remove )
        
        if to_add is not None:
            log.debug( "Adding instance IP '%s' to SGE's group config file %s" % ( to_add, filename ) )
            ahl.append(to_add)
        if to_remove is not None and to_remove in ahl:
            log.debug( "Removing instance IP '%s' from SGE's group config file %s" % ( to_remove, filename ) )
            ahl.remove(to_remove)
        elif to_remove is not None:
            log.debug( "Instance's IP '%s' not matched in allhosts list: %s" % ( to_remove, ahl ) )
        
        # Now reasemble and save to file 'filename'
        if len(ahl) > 0:
            new_allhosts = 'group_name @allhosts \n'+'hostlist ' + ' \\\n\t '.join(ahl) + ' \\\n'
        else:
            new_allhosts = 'group_name @allhosts \nhostlist NONE\n'
        f = open( filename, 'w' )
        f.write( new_allhosts )
        f.close()
        log.debug( "new_allhosts: %s" % new_allhosts )
        log.debug("New SGE @allhosts file written successfully to %s." % filename)
         
    def remove_sge_host( self, inst ):
        log.info( "Removing instance '%s' from SGE" % inst.id )
        log.debug( "Removing instance '%s' from SGE administrative host list" % inst.id )
        ret_code = subprocess.call( 'export SGE_ROOT=%s; . $SGE_ROOT/default/common/settings.sh; %s/bin/lx24-amd64/qconf -dh %s' % (P_SGE_ROOT, P_SGE_ROOT, inst.private_ip), shell=True )
        
        inst_ip = inst.get_private_ip()
        log.debug( "Removing instance '%s' with FQDN '%s' from SGE execution host list (including @allhosts)" % ( inst.id, inst_ip) )
        now = dt.datetime.utcnow()
        ah_file = '/tmp/ah_remove_' + now.strftime("%H_%M_%S")
        self.write_allhosts_file(filename=ah_file, to_remove = inst_ip)

        ret_code = subprocess.call( 'export SGE_ROOT=%s; . $SGE_ROOT/default/common/settings.sh; %s/bin/lx24-amd64/qconf -Mhgrp %s' % (P_SGE_ROOT, P_SGE_ROOT, ah_file), shell=True )
        if ret_code == 0:
            log.info( "Successfully updated @allhosts to remove '%s'" % inst.id )
        else:
            log.debug( "Problems updating @allhosts aimed at removing '%s'; process returned code '%s'" % ( inst.id, ret_code ) )  
        
        proc = subprocess.Popen( 'export SGE_ROOT=%s; . $SGE_ROOT/default/common/settings.sh; %s/bin/lx24-amd64/qconf -de %s' % (P_SGE_ROOT,P_SGE_ROOT, inst.private_ip), shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE )
        stderr = None
        stdout = None
        std = proc.communicate()
        if std[0]:
            stdout = std[0]
        if std[1]:
            stderr = std[1]
        # log.debug( "stdout: %s" % stdout )
        # log.debug( "stderr: %s" % stderr )
        # TODO: Should be looking at return code and use stdout/err just for info about the process progress...
        if stderr is None or 'removed' in stderr:
            ret_code = subprocess.call( 'export SGE_ROOT=%s; . $SGE_ROOT/default/common/settings.sh; /opt/sge/bin/lx24-amd64/qconf -dconf %s' % (P_SGE_ROOT, inst.private_ip), shell=True )
            log.debug( "Successfully removed instance '%s' with IP '%s' from SGE execution host list." % ( inst.id, inst_ip ) )
            return True
        elif 'does not exist' in stderr:
            log.debug( "Instance '%s' with IP '%s' not found in SGE's exechost list: %s" % ( inst.id, inst_ip, stderr ) )
            return True
        else:
            log.debug( "Failed to remove instance '%s' with FQDN '%s' from SGE execution host list: %s" % ( inst.id, inst_ip, stderr ) )
            return False
        # if ret_code == 0:
        #     ret_code = subprocess.call( 'export SGE_ROOT=/opt/sge; . $SGE_ROOT/default/common/settings.sh; /opt/sge/bin/lx24-amd64/qconf -dconf %s' % inst.private_ip, shell=True )
        #     log.debug( "Successfully removed instance '%s' with IP '%s' from SGE execution host list." % ( inst.id, inst_ip ) )
        #     return True
        # else:
        #     log.debug( "Failed to remove instance '%s' with FQDN '%s' from SGE execution host list." % ( inst.id, inst_ip ) )
        #     return False


    def manage_postgres( self, to_be_started=True ):
        if self.app.TESTFLAG is True:
            log.debug( "Attempted to manage Postgres, but TESTFLAG is set." )
            return
        psql_data_dir = P_PSQL_DIR
        
        # Check on the status of PostgreSQL server
        self.postgres_running = self.introspect.check_postgres()

        if to_be_started and not self.postgres_running:
            to_be_configured = False

            # Check if 'psql_data_dir' exists first; it not, mandate configuring of PostgreSQL
            if not os.path.exists( psql_data_dir ):
                to_be_configured = True

            if to_be_configured:
                log.info( "Configuring PostgreSQL with a database for Galaxy..." )
                # Make Galaxy database directory
                if os.path.exists(P_GALAXY_DATA) and not os.path.exists(psql_data_dir):
                    ret_code = subprocess.call( 'mkdir -p %s' % psql_data_dir, shell=True )
                else:
                    log.error( "'%s' directory doesn't exist yet; will configure PostgreSQL later." % P_GALAXY_DATA )
                    return False
                # Change ownership of just created directory
                if ret_code == 0:
                    ret_code = subprocess.call( '%s -R postgres:postgres %s/pgsql' % ( P_CHOWN, P_GALAXY_DATA ), shell=True )
                else:
                    log.error( "Creating PostgreSQL data directory did not go smoothly, process returned with code '%s'" % ret_code )
                    return False
                # Initialize/configure database cluster
                if ret_code == 0:
                    log.debug( "Initializing PostgreSQL database for Galaxy..." )
                    ret_code = subprocess.call( '%s - postgres -c "%s/initdb -D %s"' % (P_SU, P_PG_HOME, psql_data_dir), shell=True )
                else:
                    log.error( "Changing ownership of PostgreSQL data directory did not go smoothly, process returned with code '%s'" % ret_code )
                    return False
                # Start PostgreSQL server so a role for Galaxy user can be created
                if ret_code == 0:
                    log.debug( "Starting PostgreSQL as part of initial setup..." )
                    ret_code = subprocess.call( '%s - postgres -c "%s/pg_ctl -D %s -l /tmp/pgSQL.log start"' % (P_SU, P_PG_HOME, psql_data_dir), shell=True )
                    time.sleep( 5 ) # Wait for PostgreSQL to start up and start accepting connections - need a better method here!
                else:
                    log.error( "Initializing PostgreSQL database did not go smoothly, process returned with code '%s'" % ret_code )
                    # return False
                    # Maybe the database has already been initialized so try starting Postgres
                    if len(os.listdir(psql_data_dir)) > 0:
                        log.debug( "'%s' is not empty; will still try to start PostgreSQL." )
                        ret_code = subprocess.call( '%s - postgres -c "%s/pg_ctl -D %s -l /tmp/pgSQL.log start"' % (P_SU, P_PG_HOME, psql_data_dir), shell=True )
                        time.sleep( 5 ) # Wait for PostgreSQL to start up and start accepting connections - need a better method here!
                # Create role for galaxy user
                if ret_code == 0:
                    # self.postgres_running = True
                    log.debug( "PostgreSQL started OK (log available at /tmp/pgSQL.log).")
                    log.debug( "Creating role for 'galaxy' user in PostgreSQL..." )
                    ret_code = subprocess.call( '%s - postgres -c "%s/psql -c \\\"CREATE ROLE galaxy LOGIN CREATEDB\\\" "' % (P_SU, P_PG_HOME), shell=True )
                else:
                    log.error( "Starting PostgreSQL as part of initial setup did not go smoothly, process returned with code '%s'" % ret_code )
                    return False
                # Create database for Galaxy, as galaxy user
                if ret_code == 0:
                    log.debug( "Creating PostgreSQL database as 'galaxy' user..." )
                    ret_code = subprocess.call( '%s - galaxy -c "%s/createdb galaxy"' % (P_SU, P_PG_HOME), shell=True )
                else:
                    log.error( "Creating role for 'galaxy' user in PostgreSQL did not go smoothly, process returned with code '%s'" % ret_code )
                    return False
                if ret_code == 0:
                    log.debug( "Successfully created 'galaxy' database in PostgreSQL." )
                else:
                    log.error( "Creating 'galaxy' database in PostgreSQL did not go smoothly, process returned with code '%s'" % ret_code )
                    return False

            # Check on the status of PostgreSQL server
            self.postgres_running = self.introspect.check_postgres()
            
            if to_be_started and not self.postgres_running:
                # Start PostgreSQL database
                log.info( "Starting PostgreSQL..." )
                ret_code = subprocess.call( '%s -R postgres:postgres %s' % (P_CHOWN, P_GALAXY_DATA+'/pgsql'), shell=True )
                ret_code = subprocess.call( '%s - postgres -c "%s/pg_ctl -D %s -l /tmp/pgSQL.log start"' % (P_SU, P_PG_HOME, psql_data_dir), shell=True )
                if ret_code == 0:
                    time.sleep(2) # Wait for psql to start accepting connections
                    self.postgres_running = self.introspect.check_postgres()
                    if self.postgres_running:
                        log.info( "Successfully started PostgreSQL." )
                    else:
                        log.warning("Successfully started PosgreSQL but did it start?")
                else:
                    self.postgres_running = self.introspect.check_postgres()
                    log.error( "Encountered problem while starting PostgreSQL, process returned error code '%s'." % ret_code )
            else:
                log.debug( "PostgreSQL already running." )

        elif not to_be_started:
            # Stop PostgreSQL database
            log.info( "Stopping PostgreSQL..." )
            ret_code = subprocess.call( '%s - postgres -c "%s/pg_ctl -D %s stop"' % (P_SU, P_PG_HOME, psql_data_dir), shell=True )
            if ret_code == 0:
                self.postgres_running = self.introspect.check_postgres()
                log.info( "Successfully stopped PostgreSQL." )
            else:
                self.postgres_running = self.introspect.check_postgres()
                log.error( "Encountered problem while stopping PostgreSQL, process returned error code '%s'." % ret_code )
                
        return True

    def manage_galaxy( self, to_be_started=True ):
        if self.app.TESTFLAG is True:
            log.debug( "Attempted to manage Galaxy, but TESTFLAG is set." )
            return
        galaxy_home = P_GALAXY_HOME
        os.putenv( "GALAXY_HOME", galaxy_home )
        os.putenv( "TEMP", '/mnt/galaxyData/tmp' )
        if to_be_started:
            self.galaxy_running = self.introspect.check_galaxy()
            if self.galaxy_running is None:
                log.info( "Setting up Galaxy" )
                if not os.path.exists(galaxy_home):
                    log.error("Galaxy application directory '%s' does not exist! Aborting." % galaxy_home)
                    log.debug("ls /mnt/: %s" % os.listdir('/mnt/'))
                    return False
                try:
                    shutil.copy( "/tmp/ec2/universe_wsgi.ini.orig", galaxy_home + "/universe_wsgi.ini" )
                except ( IOError, os.error ), e:
                    log.warning( "Copying Galaxy configuration file failed with error: %s" % e)
                    log.info("Trying to retrieve latest one from 'gc-default' bucket..." )
                    s3_conn = self.app.get_s3_connection()
                    misc.get_file_from_bucket( s3_conn, 'gc-default', 'universe_wsgi.ini.orig', galaxy_home + '/universe_wsgi.ini' )
                try:
                    shutil.copy( "/tmp/ec2/tool_conf.xml.orig", galaxy_home + "/tool_conf.xml" )
                except ( IOError, os.error ), e:
                    log.warning( "Copying Galaxy tool configuration file from '/tmp/ec2/tool_conf.xml.orig' failed with error: %s" % e)
                
                # Ensure TEMP variable is used by Galaxy
                try:
                    subprocess.call( "sed 's/cd `dirname $0`/cd `dirname $0`; export TEMP=\/mnt\/galaxyData\/tmp/' %s/run.sh > %s/run.sh.custom" % (galaxy_home, galaxy_home), shell=True )
                    shutil.copy( galaxy_home + '/run.sh.custom', galaxy_home + '/run.sh' )
                    os.chown( galaxy_home + '/run.sh', pwd.getpwnam( "galaxy" )[2], grp.getgrnam( "galaxy" )[2] )
                except Exception, e:
                    log.debug("Problem customizing Galaxy's run.sh: %s" % e)
                 
                subprocess.call( 'sed "s/#start_job_runners = pbs/start_job_runners = sge/" $GALAXY_HOME/universe_wsgi.ini > $GALAXY_HOME/universe_wsgi.ini.custom', shell=True )
                shutil.move( galaxy_home + '/universe_wsgi.ini.custom', galaxy_home + '/universe_wsgi.ini' )
                #subprocess.call('mv $GALAXY_HOME/universe_wsgi.ini.custom $GALAXY_HOME/universe_wsgi.ini', shell=True)
                subprocess.call( 'sed "s/#default_cluster_job_runner = pbs:\/\/\//default_cluster_job_runner = sge:\/\/\//" $GALAXY_HOME/universe_wsgi.ini > $GALAXY_HOME/universe_wsgi.ini.custom', shell=True )
                shutil.move( galaxy_home + '/universe_wsgi.ini.custom', galaxy_home + '/universe_wsgi.ini' )
                #subprocess.call('mv $GALAXY_HOME/universe_wsgi.ini.custom $GALAXY_HOME/universe_wsgi.ini', shell=True)
                # Configure PATH in /etc/profile because otherwise some tools do not work
                f = open('/etc/profile', 'a')
                f.write('export PATH=/mnt/galaxyTools/tools/bin:/mnt/galaxyTools/tools/pkg/fastx_toolkit_0.0.13:/mnt/galaxyTools/tools/pkg/bowtie-0.12.5:/mnt/galaxyTools/tools/pkg/samtools-0.1.7_x86_64-linux:/mnt/galaxyTools/tools/pkg/gnuplot-4.4.0/bin:/opt/PostgreSQL/8.4/bin:$PATH\n')
                f.close()
                #subprocess.call('/usr/gnu/bin/chown galaxy:galaxy $GALAXY_HOME/universe_wsgi.ini')
                os.chown( galaxy_home + '/universe_wsgi.ini', pwd.getpwnam( "galaxy" )[2], grp.getgrnam( "galaxy" )[2] )
                
            if self.galaxy_running is False or self.galaxy_running is None:
                log.info( "Starting Galaxy..." )
                return self._run('%s - galaxy -c "export SGE_ROOT=%s; sh $GALAXY_HOME/run.sh --daemon"' % (P_SU, P_SGE_ROOT), "Error invoking Galaxy", "Successfully initiated Galaxy start.")
                # ret_code = subprocess.call( '%s - galaxy -c "export SGE_ROOT=%s; sh $GALAXY_HOME/run.sh --daemon"' % (P_SU, P_SGE_ROOT), shell=True )
                # if ret_code == 0:
                #     log.debug( "Successfully initiated Galaxy start." )
                #     return True
                # else:
                #     log.error( "Error invoking Galaxy, process returned code: %s" % ret_code )
                #     return False
            else:
                log.debug("Galaxy already running.")
        else:
            log.info( "Shutting down Galaxy..." )
            subprocess.call( '%s - galaxy -c "sh $GALAXY_HOME/run.sh --stop-daemon"' % P_SU, shell=True )
            self.galaxy_running = self.introspect.check_galaxy()
            subprocess.call( 'rm $GALAXY_HOME/paster.log', shell=True )

    def expand_user_data_volume(self, new_vol_size, snap_description=None):
        # TODO: recover services if process fails midway
        log.info("Initiating user data volume resizing to %sGB" % new_vol_size)
        # If there are worker nodes, suspend all jobs, then stop Galaxy and Postgres
        if self.get_num_available_workers() > 0:
            log.debug("Suspending SGE queue all.q")
            self._run('export SGE_ROOT=%s; . $SGE_ROOT/default/common/settings.sh; %s/bin/lx24-amd64/qmod -sq all.q' % (P_SGE_ROOT, P_SGE_ROOT), "Error suspending SGE jobs", "Successfully suspended all SGE jobs.")
        self.manage_galaxy(False)
        self.manage_postgres(False)

        # Unmount galaxyData filesystem
        mount_point = "/mnt/galaxyData"
        # log.debug("Freezing 'galaxyData' file system")
        #         if not self._run('xfs_freeze -f %s' % mount_point, "Error freezing 'galaxyData' file system", "Succesfully froze 'galaxyData' file system"):
        #             return False
        log.info( "Unmounting 'galaxyData' file system from '%s'" % mount_point)
        if not self._umount(mount_point):
            return False
        
        # Detach galaxyData volume
        if self.volumes.has_key('galaxyData:0'):
            self.detach(self.volumes['galaxyData:0'][0])
        else:
            log.error("Missing reference to the galaxyData volume.")
            return False
        
        # Create a snapshot of detached galaxyData volume 
        ec2_conn = self.app.get_ec2_connection()
        if self.volumes.has_key('galaxyData:0'):
            log.info("Initiating creation of a snapshot for the volume 'galaxyData' (vol ID: '%s')" % self.volumes['galaxyData:0'][0])
            snapshot = ec2_conn.create_snapshot(self.volumes['galaxyData:0'][0], description="galaxyData: %s" % snap_description)
            if snapshot: 
                while snapshot.status != 'completed':
                    log.debug("Snapshot '%s' progress: '%s'; status: '%s'" % (snapshot.id, snapshot.progress, snapshot.status))
                    self.snapshot_progress = snapshot.progress
                    self.snapshot_status = snapshot.status
                    time.sleep(6)
                    snapshot.update()
                log.info("Creation of a snapshot for the volume 'galaxyData' (vol ID: %s) completed: '%s'" % (self.volumes['galaxyData:0'][0], snapshot))
                self.snapshot_progress = None # Reset because of the UI
                self.snapshot_status = None # Reset because of the UI
            else:
                log.error("Could not create snapshot from volume 'galaxyData' with ID '%s'" % self.volumes['galaxyData:0'][0])
                return False
        
        # Create a new volume based on just created snapshot 
        log.info("Creating new user data volume of size %sGB." % new_vol_size)
        data_vol = ec2_conn.create_volume(new_vol_size, self.app.get_zone(), snapshot)
        if data_vol:
            if not self.volumes['galaxyData:0'][2]:
                # Attach newly created volume
                dev_id = self.volumes['galaxyData:0'][1] # Try reusing attach point
                old_vol_id = self.volumes['galaxyData:0'][0]
                for char_code in range(ord('b'), ord('d')):
                    if self.attach(data_vol.id, dev_id):
                        self.volumes['galaxyData:0'][0] = data_vol.id # Update local reference to user data volume
                        self.volumes['galaxyData:0'][1] = dev_id
                        break
                    else:
                        # Try to attach as a different device if first attempt fails
                        self.detach(data_vol.id)
                        dev_id = '/dev/sd' + chr(char_code)
                        log.error("Problem attaching newly created user data volume. Trying to attach as a different device: '%s'" % dev_id)
            else:
                log.error("Old 'galaxyData' volume appears to still be attached?")
                return False
            
            # Mount attached volume
            device = self.volumes['galaxyData:0'][1]
            galaxyData_dir = P_GALAXY_DATA
            if not self._mount(device, galaxyData_dir):
                return False
                        
            # Grow file system
            if not self._run('/usr/sbin/xfs_growfs %s' % galaxyData_dir, "Error growing file system 'galaxyData'", "Successfully grew file system 'galaxyData'"):
                return False
            
            # Update references in attached_volumes.txt and self.persistent_vol_file and save to persistent storage
            s3_conn = self.app.get_s3_connection()
            self._update_file(self.persistent_vol_file, old_vol_id, self.volumes['galaxyData:0'][0])
            misc.save_file_to_bucket(s3_conn, self.app.shell_vars['BUCKET_NAME'], self.persistent_vol_file, self.persistent_vol_file)
            attached_vols_file = 'attached_volumes.txt'
            self._update_file(attached_vols_file, old_vol_id, self.volumes['galaxyData:0'][0])
            misc.save_file_to_bucket(s3_conn, self.app.shell_vars['BUCKET_NAME'], attached_vols_file, attached_vols_file)
            
        # Resume all services
        self.manage_postgres(True)
        self.manage_galaxy(True)
        self.app.permanent_storage_size = new_vol_size
        if self.get_num_available_workers() > 0:
            return self._run('export SGE_ROOT=%s; . $SGE_ROOT/default/common/settings.sh; %s/bin/lx24-amd64/qmod -usq all.q' % (P_SGE_ROOT, P_SGE_ROOT), "Error unsuspending SGE jobs", "Successfully unsuspended all SGE jobs")
        else:
            return True
            
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
                    log.error( "Encountered a problem while creating root user's public key, \
                    process returned error code '%s'." % ret_code )
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
        if self.app.TESTFLAG is True:
            log.debug( "Attempted to get worker status, but TESTFLAG is set." )
            return {}
        """ 
        Retrieves current status of all worker instances or of only worker 
        instance whose ID was passed as the parameter. Returns a dict
        where instance ID's are the keys.
        """
        workers_status = {}

        if worker_id:
            log.info( "Checking status of instance '%s'" % worker_id )
            try:
                ec2_conn = self.app.get_ec2_connection()
                reservation = ec2_conn.get_all_instances( worker_id.strip() )
                if reservation:
                    workers_status[ reservation[0].instances[0].id ] = reservation[0].instances[0].state
            except EC2Exception, e:
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
            f = open(file_name, 'w')
            for el in input_list:
                f.write("%s\n" % el)
            f.close()

            if bucket_name is not None:
                log.debug("Saving file '%s' created from list '%s' to user's bucket '%s'." % (file_name, input_list, bucket_name))
                s3_conn = self.app.get_s3_connection()
                return misc.save_file_to_bucket(s3_conn, bucket_name, file_name, file_name)
        else:
            log.debug("Will not create file '%s' from provided list because the list is empty." % file_name)
            return False
        return True

    def _mount(self, device, mount_point):
        """ Mount file system at provided mount point. If present in /etc/exports, 
        this method enables NFS on given mount point (i.e., uncomments respective
        line in /etc/exports and restarts NFS) 
        """
        if not self._run('/bin/mount %s %s' % (device, mount_point), "Error mounting file system '%s' from '%s'" % (mount_point, device), "Successfully mounted file system '%s' from '%s'" % (mount_point, device)):
            return False

        try:
            mp = mount_point.replace('/', '\/') # Escape slashes for sed
            if self._run("/bin/sed 's/^#%s/%s/' /etc/exports > /tmp/exports.tmp" % (mp, mp), "Error removing '%s' from '/etc/exports'" % mount_point, "Successfully removed '%s' from '/etc/exports'" % mount_point):
                shutil.move( '/tmp/exports.tmp', '/etc/exports' )
                self._run("/etc/init.d/nfs-kernel-server restart", "Error restarting NFS server", "Successfully restarted NFS server")
        except Exception, e:
            log.debug("Problems configuring NFS or /etc/exports: '%s'" % e)
        return True

    def _run(self, cmd, err, ok):
        """ Convenience method for executing a shell command. """
        process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()
        # ret_code = subprocess.call(cmd, shell=True)
        if process.returncode == 0:
            log.debug(ok)
            return True
        else:
            log.error("%s, process returned code '%s' and following stderr: '%s'" % (err, process.returncode, stderr))
            return False

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
        
    def _umount(self, mount_point):
        """ Umount file system at provided mount point. If given mount point is
        present in /etc/exports, this method comments the line out and restarts 
        NFS, effectively removing the directory from NFS. If this is not done,
        umount cannot unmount given mount point saying the device is busy. 
        """
        try:
            mp = mount_point.replace('/', '\/') # Escape slashes for sed
            if self._run("/bin/sed 's/^%s/#%s/' /etc/exports > /tmp/exports.tmp" % (mp, mp), "Error removing '%s' from /etc/exports" % mount_point, "Successfully removed '%s' from /etc/exports" % mount_point):
                shutil.move( '/tmp/exports.tmp', '/etc/exports' )
                self._run("/etc/init.d/nfs-kernel-server restart", "Error restarting NFS server", "Successfully restarted NFS server")
        except Exception, e:
            log.debug("Problems configuring NFS or /etc/exports: '%s'" % e)
        if not self._run('/bin/umount -f %s' % mount_point, "Error unmounting file system '%s'" % mount_point, "Successfully unmounted file system '%s'" % mount_point):
            return False
        return True

    def get_status_dict( self ):
        if self.app.TESTFLAG:
            num_cpus = 1
            load = "0.00 0.02 0.39"
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
        return  {'id' : self.app.get_instance_id(), 'ld' : load, 'time_in_state' : misc.formatDelta(dt.datetime.utcnow() - self.startup_time), 'instance_type' : self.app.get_type() }


class ConsoleMonitor( object ):
    def __init__( self, app ):
        self.app = app
        self.num_workers_processed = 0
        self.sge_was_setup = False
        self.last_state_change_time = None
        self.conn = comm.CMMasterComm()
        self.conn.setup()
        self.sleeper = misc.Sleeper()
        self.running = True
        self.monitor_thread = threading.Thread( target=self.__monitor )

    def start( self ):
        self.last_state_change_time = dt.datetime.utcnow()
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

    def __monitor( self ):
        #We might want to restart the monitor, but not the manager.
        if self.app.manager.manager_started == False:
            self.app.manager.start()
        timer = dt.datetime.utcnow()
        while self.running:
            self.sleeper.sleep( 3 )
            # Run services' check only periodically once we get into Ready state
            if self.app.manager.master_state == master_states.READY and (dt.datetime.utcnow() - timer).seconds > 15:
                timer = dt.datetime.utcnow()
                self.app.manager.introspect.check_all_master_services()
                # log.debug("self.app.manager.volumes: %s" % self.app.manager.volumes)
            else:
                self.app.manager.introspect.check_all_master_services()
                # log.debug("self.app.manager.volumes: %s" % self.app.manager.volumes)
            if self.app.manager.start_galaxy == True and self.app.manager.galaxy_starting == False and self.app.manager.postgres_running == True:
                self.app.manager.galaxy_starting = True
                if self.app.manager.manage_galaxy(True):
                    self.app.manager.galaxy_starting = False
                    self.app.manager.galaxy_running = True
                    self.app.manager.start_galaxy= False
                else:
                    self.app.manager.galaxy_starting = False
                    self.app.manager.start_galaxy = False

            if self.app.manager.create_user_data_vol:
                if self.app.manager.init_cluster():
                    self.app.manager.cluster_status = cluster_status.ON
                    self.app.manager.master_state = master_states.WAITING_FOR_WORKER_INIT
                    log.debug( "Changed state to '%s'" % self.app.manager.master_state )
            
            if self.app.manager.master_state == master_states.INITIAL_STARTUP:
                log.debug( "In '%s' state." % self.app.manager.master_state )
                self.app.manager.master_state = master_states.WAITING_FOR_USER_ACTION
                self.last_state_change_time = dt.datetime.utcnow()
                log.debug( "Changed state to '%s'" % self.app.manager.master_state )
            elif self.app.manager.master_state == master_states.WAITING_FOR_USER_ACTION:
                log.debug( "In '%s' state." % self.app.manager.master_state )
                #TODO This if *should* not be possible, look to remove it.
                if len( self.app.manager.worker_instances ) > 0:
                    log.debug( "There are existing worker instances, moving on..." )
                    self.app.manager.master_state = master_states.WAITING_FOR_WORKER_INIT
                    self.last_state_change_time = dt.datetime.utcnow()
                    log.debug( "Changed state to '%s'" % self.app.manager.master_state )
            elif self.app.manager.master_state == master_states.SEND_MASTER_PUBKEY:
                log.debug( "In '%s' state." % self.app.manager.master_state )
                if len( self.app.manager.worker_instances ) > 0:
                    for instance in self.app.manager.worker_instances:
                        instance.send_master_pubkey()
                    self.app.manager.master_state = master_states.WAITING_FOR_WORKER_INIT
                    log.debug( "Changed state to '%s'" % self.app.manager.master_state )
            elif self.app.manager.master_state == master_states.START_WORKERS:
                log.debug( "In '%s' state." % self.app.manager.master_state )
                num_nodes = int( self.app.manager.num_workers_requested ) - len( self.app.manager.worker_instances )
                if self.app.manager.init_cluster( num_nodes ):
                    self.app.manager.cluster_status = cluster_status.ON
                    self.app.manager.master_state = master_states.WAITING_FOR_WORKER_INIT
                    log.debug( "Changed state to '%s'" % self.app.manager.master_state )
                else:# Do basic status reporting if instances do not start properly...
                    log.error( "Encountered problems when starting instances. Currently, keeping track of '%s' instances." % len( self.app.manager.worker_instances ) )
                    if len( self.app.manager.worker_instances ) > 0:
                        self.app.manager.cluster_status = cluster_status.ON
                        self.app.manager.master_state = master_states.WAITING_FOR_WORKER_INIT
                        log.debug( "Changed state to '%s'" % self.app.manager.master_state )
            elif self.app.manager.master_state == master_states.STARTING_WORKERS:
                log.debug( "In '%s' state." % self.app.manager.master_state )
                self.app.manager.master_state = master_states.WAITING_FOR_WORKER_INIT
            elif self.app.manager.master_state == master_states.GALAXY_STARTING:
                if self.app.TESTFLAG is True:
                    log.debug( "Assume we're done here." )
                    log.debug( "\tMT: Changing state to '%s'" % master_states.READY )
                    self.app.manager.master_state = master_states.READY
                    self.last_state_change_time = dt.datetime.utcnow()
                else:
                    # Galaxy is starting.  We need to watch to see when it's available.
                    log.debug( "In '%s' state." % self.app.manager.master_state )
                    log.debug( "Checking if Galaxy UI is ready..." )
                    dns = "http://127.0.0.1:8080"
                    try:
                        urllib2.urlopen( dns )
                        log.info( "Galaxy started successfully!" )
                        log.debug( "\tMT: Changing state to '%s'" % master_states.READY )
                        self.app.manager.master_state = master_states.READY
                        self.last_state_change_time = dt.datetime.utcnow()
                        log.info( "Ready for use" )
                    except urllib2.URLError:
                        dns = None
            #TODO Dead/unresponsive Instance Logic!
            for w_instance in self.app.manager.worker_instances:
                if w_instance.check_if_instance_alive() is False:
                    log.error( "Instance '%s' terminated prematurely. Removing from SGE and local instance list." % w_instance.id )
                    self.app.manager.remove_sge_host( w_instance )
                    # Remove reference to given instance object 
                    if w_instance in self.app.manager.worker_instances:
                        self.app.manager.worker_instances.remove( w_instance )
                    # self.app.manager.add_instances(1)
                elif w_instance.get_m_state() == 'running' and ( dt.datetime.utcnow() - w_instance.last_comm ).seconds > 15:
                    w_instance.send_status_check()
            m = self.conn.recv()
            while m is not None:
                # Got message.  Demux and dispatch to particular instance.
                # log.debug( "Master received msg: '%s' from '%s'" % ( m.body, m.properties['reply_to'] ) )
                # log.debug( "Instances: %s" % len(self.app.manager.worker_instances) )
                match = False
                for inst in self.app.manager.worker_instances:
                    if inst.id == m.properties['reply_to']:
                        match = True
                        inst.handle_message( m.body )
                if match is False:
                    log.debug( "Potential error, no instance (%s) match found for message %s." % ( m.properties['reply_to'], m.body ) )
                m = self.conn.recv()


class Instance( object ):
    def __init__( self, app, inst=None, m_state=None, last_m_state_change=None, sw_state=None ):
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
        t_thread = threading.Thread( target=self.__terminate() )
        t_thread.start()

    def __terminate( self ):
        log.info ( "Terminating instance '%s'" % self.id )
        ec2_conn = self.app.get_ec2_connection()
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
        self.app.manager.console_monitor.conn.send( 'RESTART | %s' % self.app.get_self_private_ip(), self.id )
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
            log.debug( "Worker instance '%s' status: '%s' (time in this state: %s sec)" % ( self.id, state, ( dt.datetime.utcnow() - self.last_m_state_change ).seconds ) )
        if self.app.TESTFLAG is True:
            return True
        # If an instance has been in state 'running' for a while we still have not heard from it, check on it 
        # DBTODO Figure out something better for state management.
        if state == 'running' and not self.is_alive and ( dt.datetime.utcnow() - self.last_m_state_change ).seconds > 300 and ( dt.datetime.utcnow() - self.time_rebooted ).seconds > 200:
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
                if self.app.manager.add_sge_host( self ):
                    # Now send message to worker to start SGE  
                    self.send_start_sge()
                    log.info( "Waiting on worker instance '%s' to configure itself..." % self.id )
                else:
                    log.error( "Adding host to SGE did not go smoothly, not instructing worker to configure SGE daemon." )
            elif msg_type == "NODE_READY":
                self.node_ready = True
                self.worker_status = "Ready"
                log.info( "Instance '%s' ready" % self.id )
                msplit = msg.split( ' | ' )
                try:
                    self.num_cpus = int(msplit[2])
                except Exception, e:
                    log.debug("Instance '%s' num CPUs is not int? '%s'" % (self.id, msplit[2]))
                log.debug("Instance '%s' reported as having '%s' CPUs." % (self.id, self.num_cpus))
                if not self.app.manager.galaxy_running and not self.app.manager.galaxy_starting:
                    log.debug("\tMT: Setting hook to start Galaxy")
                    self.app.manager.start_galaxy = True
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

