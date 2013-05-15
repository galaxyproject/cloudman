"""Galaxy CM worker manager"""
import commands
import grp
import logging
import os
import os.path
import pwd
import subprocess
import threading
import datetime as dt
import shutil
import json


from cm.util.bunch import Bunch
from cm.util import misc, comm, paths
from cm.util.manager import BaseConsoleManager
from cm.services import ServiceRole
from cm.services.apps.pss import PSS
from cm.services.data.filesystem import Filesystem
from cm.services.apps.hadoop import HadoopService
from cm.services.apps.htcondor import HTCondorService

log = logging.getLogger('cloudman')


sge_install_template = """
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

# Worker states
worker_states = Bunch(
    WAKE='Wake',
    INITIAL_STARTUP='Startup',
    WAIT_FOR_MASTER_PKEY='Startup',
    WAIT_FOR_SGE='Startup',
    READY='Ready',
    SHUTTING_DOWN="Stopping",
    ERROR='Error'
)


class ConsoleManager(BaseConsoleManager):
    node_type = "worker"

    def __init__(self, app):
        self.app = app
        self.console_monitor = ConsoleMonitor(self.app)
        self.worker_status = worker_states.WAKE
        self.worker_instances = []  # Needed because of UI and number of nodes value
        # Default to the most comprehensive type
        self.cluster_type = self.app.ud.get('cluster_type', 'Galaxy')
        self.mount_points = []  # A list of current mount points; each list element must have the
                                # following structure: (label, local_path, nfs_server_ip)
        self.nfs_data = 0
        self.nfs_tools = 0
        self.nfs_indices = 0
        self.nfs_tfs = 0  # transient file system/storage from the master
        self.nfs_sge = 0
        self.get_cert = 0
        self.sge_started = 0
        self.custom_hostname = None

        self.load = 0

    @property
    def local_hostname(self):
        """
        Returns the local hostname for this instance.
        """
        return self.app.cloud_interface.get_local_hostname()
        # Not working (SGE cannot resolve master host)
        if not self.custom_hostname:
            self.custom_hostname = "{0}-{1}".format(self.app.cloud_interface.get_instance_id(),
                                                    self.app.cloud_interface.get_private_ip())
        return self.custom_hostname

    def start(self):
        self._handle_prestart_commands()
        # self.mount_nfs( self.app.ud['master_ip'] )
        misc.add_to_etc_hosts(
            self.app.ud['master_hostname'], self.app.ud['master_ip'])

    def shutdown(self, delete_cluster=None):
        self.worker_status = worker_states.SHUTTING_DOWN
        self.console_monitor.send_node_shutting_down()
        self.console_monitor.shutdown()

    def get_cluster_status(self):
        return "This is a worker node, cluster status not available."

    def mount_disk(self, master_ip, path, source_path=None):
        if source_path is None:
            source_path = path
        # Before mounting, check if the file system is already mounted
        mnt_location = commands.getstatusoutput("cat /proc/mounts | grep %s[[:space:]] | cut -d' ' -f1,2"
                                                % path)
        if mnt_location[0] == 0 and mnt_location[1] != '':
            log.debug("{0} is already mounted".format(path))
            return mnt_location[0]
        else:
            log.debug("Mounting %s:%s to %s..." % (master_ip, source_path, path))
            if not os.path.exists(path):
                os.mkdir(path)
            ret_code = subprocess.call(
                "mount %s:%s %s" % (master_ip, source_path, path), shell=True)
            log.debug(
                "Process mounting '%s' returned code '%s'" % (path, ret_code))
            return ret_code

    def mount_nfs(self, master_ip, mount_json):
        if self.app.TESTFLAG is True:
            log.debug("Attempted to mount NFS, but TESTFLAG is set.")
            return
        mount_points = []
        try:
            # Try to load mount points from json dispatch
            try:
                mount_points_dict = json.loads(mount_json.strip())
            except Exception, e:
                log.error("json load exception: %s" % e)
            log.debug("mount_points_dict: %s" % mount_points_dict)
            if 'mount_points' in mount_points_dict:
                for mp in mount_points_dict['mount_points']:
                    # TODO use the actual filesystem name for accounting/status
                    # updates
                    mount_points.append(
                        (mp['fs_name'], mp['shared_mount_path'], mp['nfs_server']))
            else:
                raise Exception("Mount point parsing failure.")
        except:
            # malformed json, revert to old behavior.
            log.info("Mounting NFS directories from master with IP address: %s..." %
                     master_ip)
            # Build list of mounts based on cluster type
            if self.cluster_type == 'Galaxy':
                mount_points.append(
                    ('nfs_tools', self.app.path_resolver.galaxy_tools, master_ip))
                mount_points.append(
                    ('nfs_indices', self.app.path_resolver.galaxy_indices, master_ip))
            if self.cluster_type == 'Galaxy' or self.cluster_type == 'Data':
                mount_points.append(
                    ('nfs_data', self.app.path_resolver.galaxy_data, master_ip))
            # Mount master's transient storage regardless of cluster type
            mount_points.append(('nfs_tfs', '/mnt/transient_nfs', master_ip))
        # Mount SGE regardless of cluster type
        mount_points.append(('nfs_sge', self.app.path_resolver.sge_root, master_ip))

        # <KWS>Mount Hadoop regardless of cluster type
        mount_points.append(('nfs_hadoop', paths.P_HADOOP_HOME, master_ip))

        # Mount master's transient storage regardless of cluster type
        # mount_points.append(('nfs_tfs', '/mnt/transient_nfs'))

        for i, extra_mount in enumerate(self._get_extra_nfs_mounts()):
            mount_points.append(('extra_mount_%d' % i, extra_mount, master_ip))
        # For each main mount point, mount it and set status based on label
        for (label, path, nfs_server) in mount_points:
            log.debug("Mounting FS w/ label '{0}' to path: {1} from nfs_server: {2}".format(
                label, path, nfs_server))
            do_mount = self.app.ud.get('mount_%s' % label, True)
            if not do_mount:
                continue
            source_path = None
            # See if a specific path on the nfs_server is used
            if ':' in nfs_server:
                source_path = nfs_server.split(':')[1]  # Must do [1] first bc. of var reassignment
                nfs_server = nfs_server.split(':')[0]
            ret_code = self.mount_disk(nfs_server, path, source_path)
            status = 1 if ret_code == 0 else -1
            setattr(self, label, status)
        # Filter out any differences between new and old mount points and unmount
        # the extra ones
        umount_points = [ump for ump in self.mount_points if ump not in mount_points]
        for (_, old_path, _) in umount_points:
            self._umount(old_path)
        # Update the current list of mount points
        self.mount_points = mount_points
        # If the instance is not ``READY``, it means it's still being configured
        # so send a message to continue the handshake
        if self.worker_status != worker_states.READY:
            self.console_monitor.conn.send("MOUNT_DONE")

    def unmount_nfs(self):
        log.info("Unmounting NFS directories: {0}".format(self.mount_points))
        for mp in self.mount_points:
            self._umount(mp[1])

    def _umount(self, path):
        ret_code = subprocess.call("umount -lf '%s'" % path, shell=True)
        log.debug("Process unmounting '%s' returned code '%s'" % (path, ret_code))

    def get_host_cert(self):
        if self.app.TESTFLAG is True:
            log.debug("Attempted to get host cert, but TESTFLAG is set.")
            return "TEST_WORKERHOSTCERT"
        w_cert_file = '/tmp/wCert.txt'
        cmd = '%s - sgeadmin -c "ssh-keyscan -t rsa %s > %s"' % (
            paths.P_SU, self.app.cloud_interface.get_fqdn(), w_cert_file)
        log.info("Retrieving worker host certificate; cmd: {0}".format(cmd))
        ret_code = subprocess.call(cmd, shell=True)
        if ret_code == 0:
            f = open(w_cert_file, 'r')
            host_cert = f.readline()
            f.close()
            self.get_cert = 1
            self.console_monitor.send_node_status()
            return host_cert
        else:
            log.error(
                "Error retrieving host cert. Process returned code '%s'" % ret_code)
            self.get_cert = -1
            self.console_monitor.send_node_status()
            return None

    def save_authorized_key(self, m_key):
        if self.app.TESTFLAG is True:
            log.debug("Attempted to save authorized key, but TESTFLAG is set.")
            return
        log.info(
            "Saving master's (i.e., root) authorized key to ~/.ssh/authorized_keys...")
        with open("/root/.ssh/authorized_keys", 'a') as f:
            f.write(m_key)

    def start_sge(self):
        if self.app.TESTFLAG is True:
            fakeretcode = 0
            log.debug("Attempted to start SGE, but TESTFLAG is set.  Returning retcode %s" %
                      fakeretcode)
            return fakeretcode
        log.info("Configuring SGE...")
        # Check if /lib64/libc.so.6 exists - it's required by SGE but on
        # Ubuntu 11.04 the location and name of the library have changed
        if not os.path.exists('/lib64/libc.so.6'):
            if os.path.exists('/lib64/x86_64-linux-gnu/libc-2.13.so'):
                os.symlink(
                    '/lib64/x86_64-linux-gnu/libc-2.13.so', '/lib64/libc.so.6')
            # Ubuntu 11.10 support
            elif os.path.exists("/lib/x86_64-linux-gnu/libc-2.13.so"):
                os.symlink(
                    "/lib/x86_64-linux-gnu/libc-2.13.so", "/lib64/libc.so.6")
            # Kernel 3.2 support (Ubuntu 12.04)
            elif os.path.exists("/lib/x86_64-linux-gnu/libc-2.15.so"):
                os.symlink(
                    "/lib/x86_64-linux-gnu/libc-2.15.so", "/lib64/libc.so.6")
            else:
                log.error(
                    "SGE config is likely to fail because '/lib64/libc.so.6' lib does not exists...")
        # Ensure lines starting with 127.0.1. are not included in /etc/hosts
        # because SGE fails to install if that's the case. This line is added
        # to /etc/hosts by cloud-init
        # (http://www.cs.nott.ac.uk/~aas/Software%2520Installation%2520and%2520Development%2520Problems.html)
        misc.run(
            "sed -i.bak '/^127.0.1./s/^/# (Commented by CloudMan) /' /etc/hosts")
        log.debug("Configuring users' SGE profiles...")
        f = open(paths.LOGIN_SHELL_SCRIPT, 'a')
        f.write("\nexport SGE_ROOT=%s" % self.app.path_resolver.sge_root)
        f.write("\n. $SGE_ROOT/default/common/settings.sh\n")
        f.close()

        SGE_config_file = '/tmp/galaxyEC2_configuration.conf'
        f = open(SGE_config_file, 'w')
        print >> f, sge_install_template % (self.local_hostname,
                                            self.local_hostname, self.local_hostname)
        f.close()
        os.chown(SGE_config_file, pwd.getpwnam("sgeadmin")[2],
                 grp.getgrnam("sgeadmin")[2])
        log.info(
            "Created SGE install template as file '%s'." % SGE_config_file)

        cmd = 'cd %s; ./inst_sge -x -noremote -auto %s' % (
            self.app.path_resolver.sge_root, SGE_config_file)
        log.info("Setting up SGE; cmd: {0}".format(cmd))
        ret_code = subprocess.call(cmd, shell=True)

        if ret_code == 0:
            self.sge_started = 1
            log.debug("Successfully configured SGE.")
        else:
            self.sge_started = -1
            log.error(
                "Setting up SGE did not go smoothly, process returned with code '%s'" % ret_code)

        self.console_monitor.send_node_status()
        return ret_code

    # # Configure hadoop necessary environment for further use
    # # by hadoop instalation process through SGE
    def start_hadoop(self):
        # KWS: Optionally add Hadoop service based on config setting
        if self.app.config.hadoop_enabled:
            self.hadoop = HadoopService(self.app)
            self.hadoop.configure_hadoop()

    def start_condor(self, host_ip):
        """
        Configure and start condor worker node to join the master pool.
        """
        if self.app.config.condor_enabled:
            self.condor = HTCondorService(self.app, "worker", host_ip)
            self.condor.start()

    # #<KWS>
    # Updating etc host by fetching the master's etc/hosts file
    # # this is necessary for hadoop ssh component
    def sync_etc_host(self, sync_path=paths.P_ETC_TRANSIENT_PATH):

        shutil.copyfile(sync_path, "/etc/hosts")

    def _get_extra_nfs_mounts(self):
        return self.app.ud.get('extra_nfs_mounts', [])


class ConsoleMonitor(object):
    def __init__(self, app):
        self.app = app
        self.waiting = []
        self.state = worker_states.INITIAL_STARTUP
        self.running = True
        # Helper for interruptible sleep
        self.sleeper = misc.Sleeper()
        self.conn = comm.CMWorkerComm(self.app.cloud_interface.get_instance_id(
        ), self.app.ud['master_ip'])
        if self.app.TESTFLAG is True:
            log.debug("Attempted to get host cert, but TESTFLAG is set.")
        else:
            self.conn.setup()
        self.monitor_thread = threading.Thread(target=self.__monitor)

    def start(self):
        self.app.manager.worker_status = worker_states.WAKE
        self.last_state_change_time = dt.datetime.utcnow()
        self.monitor_thread.start()

    def get_msg(self, m_tag):
        msg = self.conn.recv()
        if msg:
            if msg.body.startswith(m_tag):
                log.debug("Got message: %s" % msg.body)
                return msg.body

    def send_alive_message(self):
        # If necessary, do some cloud-specific instance adjustments first
        if self.app.cloud_type in ('opennebula',):
            if not open('/etc/hostname').readline().startswith('i-'):
                # Augment /etc/hostname w/ the custom local hostname
                log.debug("Configuring hostname...")
                with open("/etc/hostname", 'w') as f:
                    f.write(self.app.manager.local_hostname)
                # Augment /etc/hosts w/ the custom local hostname
                misc.add_to_etc_hosts(
                    self.app.ud['master_hostname'], self.app.ud['master_ip'])
                misc.add_to_etc_hosts(self.app.manager.local_hostname,
                                      self.app.cloud_interface.get_private_ip())
                misc.add_to_etc_hosts(
                    self.app.ud['master_ip'], 'ubuntu')  # For opennebula
                # Restart hostname process or the node process?
                # ret_code = subprocess.call( "/etc/init.d/hostname restart",
                # shell=True )
                ret_code = subprocess.call("sudo telinit 6", shell=True)
                if ret_code == 0:
                    log.debug("Initiated reboot...")
                else:
                    log.debug("Problem initiating reboot!?")
        # Compose the ALIVE message
        msg = "ALIVE | %s | %s | %s | %s | %s | %s" % (self.app.cloud_interface.get_private_ip(),
                                                       self.app.cloud_interface.get_public_ip(),
                                                       self.app.cloud_interface.get_zone(
                                                       ),
                                                       self.app.cloud_interface.get_type(
                                                       ),
                                                       self.app.cloud_interface.get_ami(),
                                                       self.app.manager.local_hostname)
        self.conn.send(msg)
        log.debug("Sending message '%s'" % msg)

    def send_worker_hostcert(self):
        host_cert = self.app.manager.get_host_cert()
        if host_cert != None:
            m_response = "WORKER_H_CERT | %s " % host_cert
            log.debug("Composing worker host cert message: '%s'" % m_response)
            self.conn.send(m_response)
        else:
            log.error("Sending HostCert failed, HC is None.")

    def send_node_ready(self):
        num_cpus = commands.getoutput(
            "cat /proc/cpuinfo | grep processor | wc -l")
        msg_body = "NODE_READY | %s | %s" % (
            self.app.cloud_interface.get_instance_id(), num_cpus)
        log.debug("Sending message '%s'" % msg_body)
        log.info("Instance '%s' done configuring itself, sending NODE_READY." %
                 self.app.cloud_interface.get_instance_id())
        self.conn.send(msg_body)

    def send_node_shutting_down(self):
        msg_body = "NODE_SHUTTING_DOWN | %s | %s" \
            % (self.app.manager.worker_status, self.app.cloud_interface.get_instance_id())
        log.debug("Sending message '%s'" % msg_body)
        self.conn.send(msg_body)

    def send_node_status(self):
        # Gett the system load in the following format:
        # "0.00 0.02 0.39" for the past 1, 5, and 15 minutes, respectivley
        self.app.manager.load = (
            commands.getoutput("cat /proc/loadavg | cut -d' ' -f1-3")).strip()
        msg_body = "NODE_STATUS | %s | %s | %s | %s | %s | %s | %s | %s | %s" \
            % (self.app.manager.nfs_data,
               self.app.manager.nfs_tools,
               self.app.manager.nfs_indices,
               self.app.manager.nfs_sge,
               self.app.manager.get_cert,
               self.app.manager.sge_started,
               self.app.manager.load,
               self.app.manager.worker_status,
               self.app.manager.nfs_tfs)
        log.debug("Sending message '%s'" % msg_body)
        self.conn.send(msg_body)

    def handle_message(self, message):
        if message.startswith("RESTART"):
            m_ip = message.split(' | ')[1]
            log.info("Master at %s requesting RESTART" % m_ip)
            self.app.ud['master_ip'] = m_ip
            self.app.manager.unmount_nfs()
            self.app.manager.mount_nfs(self.app.ud['master_ip'])
            self.send_alive_message()

        elif message.startswith("MASTER_PUBKEY"):
            m_key = message.split(' | ')[1]
            log.info(
                "Got master public key (%s). Saving root's public key..." % m_key)
            self.app.manager.save_authorized_key(m_key)
            self.send_worker_hostcert()
            log.info("WORKER_H_CERT message sent; changing state to '%s'" %
                     worker_states.WAIT_FOR_SGE)
            self.app.manager.worker_status = worker_states.WAIT_FOR_SGE
            self.last_state_change_time = dt.datetime.utcnow()
        elif message.startswith("START_SGE"):
            ret_code = self.app.manager.start_sge()
            if ret_code == 0:
                log.info("SGE daemon started successfully.")
                # Now that the instance is ready, run the PSS service in a
                # separate thread
                pss = PSS(self.app, instance_role='worker')
                threading.Thread(target=pss.start).start()
                self.send_node_ready()
                self.app.manager.worker_status = worker_states.READY
                self.last_state_change_time = dt.datetime.utcnow()
            else:
                log.error(
                    "Starting SGE daemon did not go smoothly; process returned code: %s" % ret_code)
                self.app.manager.worker_status = worker_states.ERROR
                self.last_state_change_time = dt.datetime.utcnow()
            self.app.manager.start_condor(self.app.ud['master_public_ip'])
            self.app.manager.start_hadoop()
        elif message.startswith("MOUNT"):
            # MOUNT everything in json blob.
            self.app.manager.mount_nfs(self.app.ud['master_ip'],
                mount_json=message.split(' | ')[1])
        elif message.startswith("STATUS_CHECK"):
            self.send_node_status()
        elif message.startswith("REBOOT"):
            log.info("Received reboot command")
            ret_code = subprocess.call("sudo telinit 6", shell=True)
        elif message.startswith("ADDS3FS"):
            bucket_name = message.split(' | ')[1]
            svc_roles = message.split(' | ')[2]
            log.info("Adding s3fs file system from bucket {0}".format(bucket_name))
            fs = Filesystem(self.app, bucket_name, ServiceRole.from_string_array(svc_roles))
            fs.add_bucket(bucket_name)
            fs.add()
            log.debug("Worker done adding FS from bucket {0}".format(bucket_name))
        # elif message.startswith("ADD_NFS_FS"):
        #     nfs_server_info = message.split(' | ')[1]
        #     # Try to load NFS server info from JSON message body
        #     try:
        #         nfs_server_info = json.loads(nfs_server_info.strip())
        #     except Exception, e:
        #         log.error("NFS server JSON load exception: %s" % e)
        #     self.app.manager.add_nfs_fs(nfs_server_info)
        elif message.startswith('ALIVE_REQUEST'):
            self.send_alive_message()
        elif message.startswith('SYNC_ETC_HOSTS'):
            # <KWS> syncing etc host using the master one
            sync_path = message.split(' | ')[1]
            self.app.manager.sync_etc_host()

        else:
            log.debug("Unknown message '%s'" % message)

    def __monitor(self):
        self.app.manager.start()
        while self.running:
            # In case queue connection was not established, try again (this will happen if
            # RabbitMQ does not start in time for CloudMan)
            if not self.conn.is_connected():
                log.debug(
                    "Trying to setup AMQP connection; conn = '%s'" % self.conn)
                self.conn.setup()
                continue
            # Make this more robust, trying to reconnect to a lost queue, etc.
            # self.app.manager.introspect.check_all_worker_services()
            if self.conn:
                if self.app.manager.worker_status == worker_states.WAKE:
                    self.send_alive_message()
                    self.app.manager.worker_status = worker_states.INITIAL_STARTUP
                # elif (dt.datetime.utcnow() - self.last_state_change_time).seconds > 720 and self.app.manager.worker_status != worker_states.ERROR:
                #         log.info( "Stuck in state '%s' too long, reseting and trying again..." % self.app.manager.worker_status )
                #         self.app.manager.worker_status = worker_states.INITIAL_STARTUP
                #         self.last_state_change_time = dt.datetime.utcnow()
                try:
                    m = self.conn.recv()
                except IOError, e:
                    if self.app.cloud_type == 'opennebula':
                        log.debug("Failed connecting to master: %s" % e)
                        log.debug("Trying to reboot the system")
                        subprocess.call('sudo telinit 6', shell=True)
                    else:
                        log.warning("IO trouble receiving msg: {0}".format(e))

                while m is not None:
                    self.handle_message(m.body)
                    m = self.conn.recv()
                # Regularly send a status update message
                self.send_node_status()
            else:
                self.running = False
                log.error("Communication queue not available, terminating.")
            self.sleeper.sleep(10)

    def shutdown(self):
        """Attempts to gracefully shut down the worker thread"""
        log.info("Sending stop signal to worker thread")
        self.running = False
        self.sleeper.wake()
        log.info("Console manager stopped")
