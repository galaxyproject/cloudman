"""Galaxy CM worker manager"""
import logging, threading, os, os.path, subprocess,  pwd, grp, commands
import datetime as dt

from cm.util.bunch import Bunch
from cm.util import misc, comm, paths

log = logging.getLogger( 'cloudman' )


sge_install_template="""
SGE_ROOT="/opt/sge"
SGE_QMASTER_PORT="6444"
SGE_EXECD_PORT="6445"
SGE_ENABLE_SMF="false"
SGE_CLUSTER_NAME="GalaxyCloudMan"
SGE_JMX_PORT=""
SGE_JMX_SSL="false"
SGE_JMX_SSL_CLIENT="false"
SGE_JMX_SSL_KEYSTORE=""
SGE_JMX_SSL_KEYSTORE_PW=""
SGE_JVM_LIB_PATH=""
SGE_ADDITIONAL_JVM_ARGS=""
CELL_NAME="default"
ADMIN_USER=""
QMASTER_SPOOL_DIR="/opt/sge/default/spool/qmaster"
EXECD_SPOOL_DIR="/opt/sge/default/spool/execd"
GID_RANGE="20000-20100"
SPOOLING_METHOD="classic"
DB_SPOOLING_SERVER="none"
DB_SPOOLING_DIR="/opt/sge/default/spooldb"
PAR_EXECD_INST_COUNT="20"
ADMIN_HOST_LIST="%s"
SUBMIT_HOST_LIST="%s"
EXEC_HOST_LIST="%s"
EXECD_SPOOL_DIR_LOCAL=""
HOSTNAME_RESOLVING="true"
SHELL_NAME="ssh"
COPY_COMMAND="scp"
DEFAULT_DOMAIN="none"
ADMIN_MAIL="none"
ADD_TO_RC="false"
SET_FILE_PERMS="true"
RESCHEDULE_JOBS="wait"
SCHEDD_CONF="1"
SHADOW_HOST=""
EXEC_HOST_LIST_RM=""
REMOVE_RC="false"
WINDOWS_SUPPORT="false"
WIN_ADMIN_NAME="Administrator"
WIN_DOMAIN_ACCESS="false"
CSP_RECREATE="true"
CSP_COPY_CERTS="false"
CSP_COUNTRY_CODE="DE"
CSP_STATE="Germany"
CSP_LOCATION="Building"
CSP_ORGA="Organisation"
CSP_ORGA_UNIT="Organisation_unit"
CSP_MAIL_ADDRESS="name@yourdomain.com"
"""

#Worker states
worker_states = Bunch(
    WAKE = 'Wake',
    INITIAL_STARTUP = 'Startup',
    WAIT_FOR_MASTER_PKEY = 'Startup',
    WAIT_FOR_SGE = 'Startup',
    READY= 'Ready',
    SHUTTING_DOWN="Stopping",
    ERROR = 'Error'
)

class ConsoleManager( object ):
    def __init__( self, app ):
        self.app = app
        self.console_monitor = ConsoleMonitor( self.app )
        self.worker_status = worker_states.WAKE
        self.worker_instances = [] # Needed because of UI and number of nodes value 
        
        self.nfs_data = 0
        self.nfs_tools = 0
        self.nfs_indices = 0
        self.nfs_sge = 0
        self.get_cert = 0
        self.sge_started = 0
        
        self.load = 0
        
    def start( self ):
        self.mount_nfs( self.app.ud['master_ip'] )
        # misc.run("stop mountall", "Failed to stop mountall process", "Successfully stopped mountall process") # Ubuntu 10.04 bug 649591
    
    def shutdown( self, delete_cluster=None ):
        self.worker_status = worker_states.SHUTTING_DOWN
        self.console_monitor.send_node_shutting_down()
        self.console_monitor.shutdown()
    
    def get_cluster_status( self ):
		return "This is a worker node, cluster status not available."
    
    def get_instance_state( self ):
        return self.worker_status    
    
    def mount_disk(self, master_ip, path):
        log.debug( "Mounting %s..." % path)
        if not os.path.exists( path ):
            os.mkdir( path )
        ret_code = subprocess.call( "mount %s:%s %s" % (master_ip, path, path), shell=True )
        log.debug( "Process mounting '%s' returned code '%s'" % (path, ret_code) )
        return ret_code
    
    def mount_nfs( self, master_ip ):
        if self.app.TESTFLAG is True:
            log.debug("Attempted to mount NFS, but TESTFLAG is set.")
            return
        log.info( "Mounting NFS directories from master with IP address: %s..." % master_ip )
        
        ret_code = self.mount_disk(master_ip, '/mnt/galaxyData')
        if ret_code == 0:
            self.nfs_data = 1
        else:
            self.nfs_data = -1
        
        ret_code = self.mount_disk(master_ip, '/mnt/galaxyTools')
        if ret_code == 0:
            self.nfs_tools = 1
        else:
            self.nfs_tools = -1
        
        ret_code = self.mount_disk(master_ip, '/mnt/galaxyIndices')
        if ret_code == 0:
            self.nfs_indices = 1
        else:
            self.nfs_indices = -1
        
        ret_code = self.mount_disk(master_ip, '/opt/sge')
        if ret_code == 0:
            self.nfs_sge = 1
        else:
            self.nfs_sge = -1
        
        self.console_monitor.send_node_status()
    
    def unmount_nfs( self ):
        log.info( "Unmounting NFS directories..." )
        ret_code = subprocess.call( "umount -lf /mnt/galaxyData", shell=True )
        log.debug( "Process unmounting '/mnt/galaxyData' returned code '%s'" % ret_code )
        
        ret_code = subprocess.call( "umount -lf /mnt/galaxyTools", shell=True )
        log.debug( "Process unmounting '/mnt/galaxyTools' returned code '%s'" % ret_code )
        
        ret_code = subprocess.call( "umount -lf /mnt/galaxyIndices", shell=True )
        log.debug( "Process unmounting '/mnt/galaxyIndices' returned code '%s'" % ret_code )
        
        ret_code = subprocess.call( "umount -lf %s" % paths.P_SGE_ROOT, shell=True )
        log.debug( "Process unmounting '%s' returned code '%s'" % (paths.P_SGE_ROOT, ret_code) )
    
    def get_host_cert(self ):
        if self.app.TESTFLAG is True:
            log.debug("Attempted to get host cert, but TESTFLAG is set.")
            return "TEST_WORKERHOSTCERT"
        log.info( "Retrieving worker host certificate..." )
        w_cert_file = '/tmp/wCert.txt'
        ret_code = subprocess.call( '%s - sgeadmin -c "ssh-keyscan -t rsa %s > %s"' % (paths.P_SU, self.app.cloud_interface.get_fqdn(), w_cert_file), shell=True )
        if ret_code == 0:
            f = open( w_cert_file, 'r' )
            host_cert = f.readline()
            f.close()
            self.get_cert = 1
            self.console_monitor.send_node_status()
            return host_cert
        else:
            log.error( "Error retrieving host cert. Process returned code '%s'" % ret_code )
            self.get_cert = -1
            self.console_monitor.send_node_status()
            return None
    
    def save_authorized_key( self, m_key ):
        if self.app.TESTFLAG is True:
            log.debug("Attempted to save authorized key, but TESTFLAG is set.")
            return
        log.info( "Saving master's (i.e., root) authorized key to ~/.ssh/authorized_keys..." )
        with open( "/root/.ssh/authorized_keys", 'a' ) as f:
            f.write( m_key )
    
    def start_sge(self ):
        if self.app.TESTFLAG is True:
            fakeretcode = 0
            log.debug("Attempted to start SGE, but TESTFLAG is set.  Returning retcode %s" % fakeretcode)
            return fakeretcode
        log.info( "Configuring SGE..." )
        # Check if /lib64/libc.so.6 exists - it's required by SGE but on 
        # Ubuntu 11.04 the location and name of the library have changed
        if not os.path.exists('/lib64/libc.so.6'):
            if os.path.exists('/lib64/x86_64-linux-gnu/libc-2.13.so'):
                os.symlink('/lib64/x86_64-linux-gnu/libc-2.13.so', '/lib64/libc.so.6')
            else:
                log.debug("SGE config is likely to fail because '/lib64/libc.so.6' lib does not exists...")
        log.debug( "Configuring users' SGE profiles..." )
        f = open( "/etc/bash.bashrc", 'a' )
        f.write( "\nexport SGE_ROOT=%s" % paths.P_SGE_ROOT )
        f.write( "\n. $SGE_ROOT/default/common/settings.sh\n" )
        f.close()
        
        SGE_config_file = '/tmp/galaxyEC2_configuration.conf'
        f = open( SGE_config_file, 'w' )
        print >> f, sge_install_template % ( self.app.cloud_interface.get_self_local_hostname(), "", self.app.cloud_interface.get_self_local_hostname() )
        f.close()
        os.chown( SGE_config_file, pwd.getpwnam("sgeadmin")[2], grp.getgrnam("sgeadmin")[2] )
        log.info( "Created SGE install template as file '%s'." % SGE_config_file )
        
        log.info( "Setting up SGE..." )
        ret_code = subprocess.call( 'cd %s; ./inst_sge -x -noremote -auto %s' % (paths.P_SGE_ROOT, SGE_config_file), shell=True )
        if ret_code == 0:
            self.sge_started = 1
            log.debug( "Successfully configured SGE." )
        else:
            self.sge_started = -1
            log.error( "Setting up SGE did not go smoothly, process returned with code '%s'" % ret_code )
        
        self.console_monitor.send_node_status()
        return ret_code
    

class ConsoleMonitor( object ):
    def __init__( self, app):
        self.app = app
        self.waiting = []
        self.state = worker_states.INITIAL_STARTUP
        self.running = True
        # Helper for interruptable sleep
        self.sleeper = misc.Sleeper()
        self.conn = comm.CMWorkerComm(self.app.cloud_interface.get_instance_id(), self.app.ud['master_ip'])
        if self.app.TESTFLAG is True:
            log.debug("Attempted to get host cert, but TESTFLAG is set.")
        else:
            self.conn.setup()
        self.monitor_thread = threading.Thread( target=self.__monitor )
    
    def start( self ):
        self.app.manager.worker_status = worker_states.WAKE
        self.last_state_change_time = dt.datetime.utcnow()
        self.monitor_thread.start()
    
    def get_msg(self, m_tag):
        msg = self.conn.recv()
        if msg:
            if msg.body.startswith(m_tag):
                log.debug( "Got message: %s" % msg.body )
                return msg.body
    
    def send_alive_message( self ):
        msg = "ALIVE | %s | %s | %s | %s | %s" % (self.app.cloud_interface.get_self_local_hostname(), 
                                                  self.app.cloud_interface.get_self_public_hostname(), 
                                                  self.app.cloud_interface.get_zone(), 
                                                  self.app.cloud_interface.get_type(), 
                                                  self.app.cloud_interface.get_ami())
        self.conn.send(msg)
        log.debug( "Sending message '%s'" % msg )
    
    def send_worker_hostcert(self):
        host_cert = self.app.manager.get_host_cert()
        if host_cert != None:
            m_response = "WORKER_H_CERT | %s " % host_cert
            log.debug( "Composing worker host cert message: '%s'" % m_response )
            self.conn.send(m_response)
        else:
            log.error("Sending HostCert failed, HC is None.")
    
    def send_node_ready(self):
        num_cpus = commands.getoutput( "cat /proc/cpuinfo | grep processor | wc -l" )
        msg_body = "NODE_READY | %s | %s" % (self.app.cloud_interface.get_instance_id(), num_cpus)
        log.debug( "Sending message '%s'" % msg_body )
        log.info( "Instance '%s' done configuring itself, sending NODE_READY." % self.app.cloud_interface.get_instance_id() )
        self.conn.send(msg_body)
    
    def send_node_shutting_down(self):
        msg_body = "NODE_SHUTTING_DOWN | %s | %s" % (self.app.manager.worker_status, self.app.cloud_interface.get_instance_id())
        log.debug( "Sending message '%s'" % msg_body )
        self.conn.send(msg_body)
    
    def send_node_status(self):
        self.app.manager.load = (commands.getoutput( "cat /proc/loadavg | cut -d' ' -f1-3" )).strip() # Returns system load in format "0.00 0.02 0.39" for the past 1, 5, and 15 minutes, respectivley
        msg_body = "NODE_STATUS | %s | %s | %s | %s | %s | %s | %s | %s" % (self.app.manager.nfs_data, self.app.manager.nfs_tools, self.app.manager.nfs_indices, self.app.manager.nfs_sge, self.app.manager.get_cert, self.app.manager.sge_started, self.app.manager.load, self.app.manager.worker_status)
        log.debug("Sending message '%s'" % msg_body)
        self.conn.send(msg_body)
    
    def handle_message(self, message):
        if message.startswith("RESTART"):
            m_ip = message.split(' | ')[1]
            log.info("Master at %s requesting RESTART" % m_ip)
            self.app.ud['master_ip'] = m_ip
            self.app.manager.unmount_nfs()
            self.app.manager.mount_nfs( self.app.ud['master_ip'] )
            self.send_alive_message()
        elif message.startswith("MASTER_PUBKEY"):
            m_key = message.split(' | ')[1]
            log.info("Got master public key (%s). Saving root's public key..." % m_key )
            self.app.manager.save_authorized_key( m_key )
            self.send_worker_hostcert()
            log.info( "WORKER_H_CERT message sent; changing state to '%s'" % worker_states.WAIT_FOR_SGE )
            self.app.manager.worker_status = worker_states.WAIT_FOR_SGE
            self.last_state_change_time = dt.datetime.utcnow()
        elif message.startswith("START_SGE"):
            ret_code = self.app.manager.start_sge()
            if ret_code == 0:
                log.info( "SGE daemon started successfully." )
                self.send_node_ready()
                self.app.manager.worker_status = worker_states.READY
                self.last_state_change_time = dt.datetime.utcnow()
            else:
                log.error( "Starting SGE daemon did not go smoothly; process returned code: %s" % ret_code )
                self.app.manager.worker_status = worker_states.ERROR
                self.last_state_change_time = dt.datetime.utcnow()
        elif message.startswith("STATUS_CHECK"):
            self.send_node_status()
        else:
            log.debug("Unknown message '%s'" % message)
    
    def __monitor( self ):
        self.app.manager.start()
        while self.running:
            #Make this more robust, trying to reconnect to a lost queue, etc.
            #self.app.manager.introspect.check_all_worker_services()
            if self.conn:
                if self.app.manager.worker_status == worker_states.WAKE:
                    self.send_alive_message()
                    self.app.manager.worker_status = worker_states.INITIAL_STARTUP
                # elif (dt.datetime.utcnow() - self.last_state_change_time).seconds > 720 and self.app.manager.worker_status != worker_states.ERROR:
                #         log.info( "Stuck in state '%s' too long, reseting and trying again..." % self.app.manager.worker_status )
                #         self.app.manager.worker_status = worker_states.INITIAL_STARTUP
                #         self.last_state_change_time = dt.datetime.utcnow()
                m = self.conn.recv()
                while m is not None:
                    self.handle_message(m.body)
                    m = self.conn.recv()
            else:
                self.running = False
                log.error("Communication queue not available, terminating.")
            self.sleeper.sleep( 2 )
    
    def shutdown( self ):
        """Attempts to gracefully shut down the worker thread"""
        log.info( "Sending stop signal to worker thread" )
        self.running = False
        self.sleeper.wake()
        log.info( "Console manager stopped" )
    
