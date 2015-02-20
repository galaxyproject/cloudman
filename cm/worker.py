"""Galaxy CM worker manager"""

import commands
import datetime as dt
import grp
import json
import logging
import os
import os.path
import pwd
import shutil
import subprocess
import threading
import time

from cm.services import ServiceRole
from cm.services.apps.jobmanagers import sge
from cm.services.apps.hadoop import HadoopService
from cm.services.apps.htcondor import HTCondorService
from cm.services.apps.pss import PSSService
from cm.services.data.filesystem import Filesystem
from cm.util import comm, misc, paths
from cm.util.bunch import Bunch
from cm.util.decorators import TestFlag
from cm.util.manager import BaseConsoleManager
from cm.util.misc import flock
from cm.conftemplates import conf_manager

log = logging.getLogger('cloudman')


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
        # The following list of current mount points; each list element must
        # have the following structure: (label, local_path, type, server_path)
        self.mount_points = []
        self.nfs_data = 0
        self.nfs_tools = 0
        self.nfs_indices = 0
        self.nfs_tfs = 0  # transient file system/storage from the master
        self.nfs_sge = 0
        self.get_cert = 0
        self.sge_started = 0

        self.load = 0
        # Slurm lock file must be the same on the master
        self.slurm_lock_file = '/mnt/transient_nfs/slurm/slurm.lockfile'
        self.slurmd_added = False  # Indicated if an attempt has been made to start slurmd
        self.alias = None
        self.num_slurmd_restarts = 0
        self.max_slurmd_restarts = 3

    @property
    def local_hostname(self):
        """
        Returns the local hostname for this instance.
        """
        return self.app.cloud_interface.get_local_hostname()

    def start(self):
        self._handle_prestart_commands()

    def shutdown(self, delete_cluster=None):
        self.worker_status = worker_states.SHUTTING_DOWN
        self.console_monitor.send_node_shutting_down()
        self.console_monitor.shutdown()

    def get_cluster_status(self):
        return "This is a worker node, cluster status not available."

    def mount_disk(self, fs_type, server, path, mount_options):
        # If a path is not specific for an nfs server, and only its ip is provided,
        # assume that the target path to mount at is the path on the server as well
        if fs_type == 'nfs' and ':' not in server:
            server = server + ":" + path
        # Before mounting, check if the file system is already mounted
        mnt_location = commands.getstatusoutput("cat /proc/mounts | grep %s[[:space:]] | cut -d' ' -f1,2" % path)
        if mnt_location[0] == 0 and mnt_location[1] != '':
            log.debug("{0} is already mounted; returning code {1}".format(path,
                                                                          mnt_location[0]))
            return mnt_location[0]
        else:
            log.debug("Mounting fs of type: %s from: %s to: %s..." % (fs_type, server, path))
            if not os.path.exists(path):
                os.mkdir(path)
            options = "-o {0}".format(mount_options) if mount_options else ""
            ret_code = subprocess.call(
                "mount -t %s %s %s %s" % (fs_type, options, server, path), shell=True)
            log.debug("Process mounting '%s' returned code '%s'" % (path, ret_code))
            return ret_code

    @TestFlag(None)
    def mount_nfs(self, master_ip, mount_json):
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
                        (mp['fs_name'], mp['shared_mount_path'], mp['fs_type'], mp['server'], mp.get('mount_options', None)))
            else:
                raise Exception("Mount point parsing failure.")
        except Exception, e:
            log.error("Error mounting devices: {0}\n Attempting to continue, but failure likely...".format(e))
        # Mount SGE regardless of cluster type
        mount_points.append(('nfs_sge', self.app.path_resolver.sge_root, 'nfs', master_ip, ''))

        # Mount Hadoop regardless of cluster type
        # mount_points.append(('nfs_hadoop', paths.P_HADOOP_HOME, 'nfs', master_ip, ''))

        for i, extra_mount in enumerate(self._get_extra_nfs_mounts()):
            mount_points.append(('extra_mount_%d' % i, extra_mount, 'nfs', master_ip, ''))
        # For each main mount point, mount it and set status based on label
        for (label, path, fs_type, server, mount_options) in mount_points:
            do_mount = self.app.ud.get('mount_%s' % label, True)
            if not do_mount:
                log.debug("Skipping FS mount for {0}".format(label))
                continue
            log.debug("Mounting FS w/ label '{0}' to path: {1} from server: {2} "
                      "of type: {3} with mount_options: {4}".format(label, path,
                                                                    server,
                                                                    fs_type,
                                                                    mount_options))
            ret_code = self.mount_disk(fs_type, server, path, mount_options)
            status = 1 if int(ret_code) == 0 else -1
            # Provide a mapping between the mount point labels and the local fields
            # Given tools & data file systems have been merged, this mapping does
            # not distinguish bewteen those but simply chooses the data field.
            labels_to_fields = {
                'galaxy': 'nfs_data',
                'galaxyIndices': 'nfs_indices',
                'transient_nfs': 'nfs_tfs'
            }
            setattr(self, labels_to_fields.get(label, label), status)
            log.debug("Set FS status {0} to {1}".format(labels_to_fields.get(
                label, label), status))
        # Filter out any differences between new and old mount points and unmount
        # the extra ones
        umount_points = [ump for ump in self.mount_points if ump not in mount_points]
        for (_, old_path, _) in umount_points:
            self._umount(old_path)
        # Update the current list of mount points
        self.mount_points = mount_points

    def unmount_filesystems(self):
        log.info("Unmounting directories: {0}".format(self.mount_points))
        for mp in self.mount_points:
            self._umount(mp[1])

    def _umount(self, path):
        ret_code = subprocess.call("umount -lf '%s'" % path, shell=True)
        log.debug("Process unmounting '%s' returned code '%s'" % (path, ret_code))

    @TestFlag("TEST_WORKERHOSTCERT")
    def get_host_cert(self):
        w_cert_file = '/tmp/wCert.txt'
        cmd = 'ssh-keyscan -t rsa %s > %s' % (self.app.cloud_interface.get_fqdn(), w_cert_file)
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

    @TestFlag(None)
    def save_authorized_key(self, m_key):
        log.info(
            "Saving master's (i.e., root) authorized key to ~/.ssh/authorized_keys...")
        with open("/root/.ssh/authorized_keys", 'a') as f:
            f.write(m_key)

    def _setup_munge(self):
        """
        Copy `munge.key` from the cluster NFS to `/etc/munge/munge.key` and
        start the service. If `munge` is not installed on the instance, install
        it using `apt-get`.
        """
        # FIXME: path_resolver does not always work with workers because workers
        # do not have a notion of 'Services'
        # nfs_munge_key = os.path.join(self.app.path_resolver.slurm_root_nfs, 'munge.key')
        nfs_munge_key = '/mnt/transient_nfs/slurm/munge.key'
        local_munge_key = '/etc/munge/munge.key'
        if not os.path.exists('/etc/munge'):
            # Munge not installed so grab it
            misc.run("apt-get update; apt-get install munge libmunge-dev -y")
        if os.path.exists(nfs_munge_key):
            shutil.copyfile(nfs_munge_key, local_munge_key)
            os.chmod(local_munge_key, 0400)
            os.chown(local_munge_key, pwd.getpwnam("munge")[2], grp.getgrnam("munge")[2])
            log.debug("Copied {0} to {1}".format(nfs_munge_key, local_munge_key))
            misc.append_to_file('/etc/default/munge', 'OPTIONS="--force"')
            misc.run("service munge start")
            log.debug("Done setting up Munge")
        else:
            log.error("Required {0} not found!".format(nfs_munge_key))

    def _setup_slurmd(self):
        """
        Create a symlinke for `slurm.conf` on the cluster NFS to
        `/etc/slurm-llnl/slurm.conf`.
        This is required because `slurm-llnl` package does not respect the `-f`
        flag for a custom file location.
        """
        if not os.path.exists('/etc/slurm-llnl'):
            # Slurm package not installed so grab it
            misc.run("apt-get install slurm-llnl -y")
        # Does not work because worker class has no notion of services, which
        # are used as part the path resolver property so must hard code the path
        # nfs_slurm_conf = self.app.path_resolver.slurm_conf_nfs
        nfs_slurm_conf = '/mnt/transient_nfs/slurm/slurm.conf'
        local_slurm_conf = self.app.path_resolver.slurm_conf_local
        if not os.path.exists(local_slurm_conf) and not os.path.islink(local_slurm_conf):
            log.debug("Symlinking {0} to {1}".format(nfs_slurm_conf, local_slurm_conf))
            os.symlink(nfs_slurm_conf, local_slurm_conf)
        # Make sure the slurm tmp root dir exists and is owned by slurm user
        misc.make_dir(self.app.path_resolver.slurm_root_tmp)
        os.chown(self.app.path_resolver.slurm_root_tmp,
                 pwd.getpwnam("slurm")[2], grp.getgrnam("slurm")[2])
        log.debug("Starting slurmd as worker named {0}...".format(self.alias))
        # If adding many nodes at once, slurm.conf may be edited by the master
        # and thus the worker cannot access it so do a quick check here. Far from
        # an ideal solution but seems to work
        for i in range(10):
            if not os.path.exists(local_slurm_conf) or os.path.getsize(local_slurm_conf) == 0:
                log.debug("{0} does not exist or is empty; waiting a bit..."
                          .format(local_slurm_conf))
                time.sleep(2)
            else:
                break
        with flock(self.slurm_lock_file):
            if misc.run("/usr/sbin/slurmd -c -N {0} -L /var/log/slurm-llnl/slurmd.log"
               .format(self.alias)):
                log.debug("Started slurmd as worker named {0}".format(self.alias))
            self.slurmd_added = True

    def start_slurmd(self, alias):
        self.alias = alias
        log.info("Configuring slurmd as worker named {0}...".format(self.alias))
        self._setup_munge()
        self._setup_slurmd()

    @property
    def slurmd_status(self):
        """
        Look for PID for ``slurmd`` process and if the identified process exists
        on the system, return ``1`` else ``-1``.
        """
        if self.slurmd_added:
            daemon_pid = -1
            pid_file = self.app.path_resolver.slurmd_pid
            if os.path.isfile(pid_file):
                daemon_pid = commands.getoutput("head -n 1 %s" % pid_file)
            alive_daemon_pid = commands.getoutput("ps -o pid -p {0} --no-headers"
                                                  .format(daemon_pid)).strip()
            if alive_daemon_pid == daemon_pid:
                # log.debug("'%s' daemon is running with PID: %s" % (service,
                # daemon_pid))
                self.num_slurmd_restarts = 0
                return 1
            else:
                log.debug("'slurmd' daemon is NOT running any more (expected pid: '{0}')"
                          .format(daemon_pid))
                if self.max_slurmd_restarts > self.num_slurmd_restarts:
                    log.debug("Automatically trying to restart slurmd (attempt {0}/{1}"
                              .format(self.num_slurmd_restarts, self.max_slurmd_restarts))
                    self._setup_slurmd()
                return -1
        return 0

    @TestFlag(0)
    def start_sge(self):
        log.info("Configuring SGE...")
        sge.fix_libc()
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
        print >> f, sge._get_sge_install_conf(self.app, self.local_hostname)
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

    def sync_etc_host(self, sync_path=paths.P_ETC_TRANSIENT_PATH):
        """
        Update /etc/hosts across the cluster by fetching the master's copy
        from `sync_path`.
        """
        if os.path.exists(sync_path):
            log.debug("Replacing local /etc/hosts with %s" % sync_path)
            shutil.copyfile(sync_path, "/etc/hosts")
        else:
            log.warning("Sync path %s not available; cannot sync /etc/hosts"
                        % sync_path)

    def _get_extra_nfs_mounts(self):
        return self.app.ud.get('extra_nfs_mounts', [])


class ConsoleMonitor(object):
    def __init__(self, app):
        self.app = app
        self.state = worker_states.INITIAL_STARTUP
        self.running = True
        # Helper for interruptible sleep
        self.sleeper = misc.Sleeper()
        self.conn = comm.CMWorkerComm(self.app.cloud_interface.get_instance_id(
        ), self.app.ud['master_ip'])
        if not self.app.TESTFLAG:
            self.conn.setup()
        self.monitor_thread = threading.Thread(target=self.__monitor)

    def start(self):
        self.app.manager.worker_status = worker_states.WAKE
        self.last_state_change_time = dt.datetime.utcnow()
        self.monitor_thread.start()

    def send_alive_message(self):
        # If necessary, do some cloud-specific instance adjustments first
        if self.app.cloud_type in ('opennebula',):
            if not open('/etc/hostname').readline().startswith('i-'):
                # Augment /etc/hostname w/ the custom local hostname
                log.debug("Configuring hostname...")
                with open("/etc/hostname", 'w') as f:
                    f.write(self.app.manager.local_hostname)
                # Augment /etc/hosts w/ the custom local hostname
                misc.add_to_etc_hosts(self.app.ud['master_ip'],
                                      [self.app.ud['master_hostname']])
                misc.add_to_etc_hosts(self.app.cloud_interface.get_private_ip(),
                                      [self.app.manager.local_hostname])
                misc.add_to_etc_hosts(self.app.ud['master_ip'], ['ubuntu'])  # For opennebula
                # Restart hostname process or the node process?
                # ret_code = subprocess.call( "/etc/init.d/hostname restart",
                # shell=True )
                ret_code = subprocess.call("sudo telinit 6", shell=True)
                if ret_code == 0:
                    log.debug("Initiated reboot...")
                else:
                    log.debug("Problem initiating reboot!?")
        num_cpus = commands.getoutput("cat /proc/cpuinfo | grep processor | wc -l")
        total_memory = misc.meminfo().get('total', 0)
        # Compose the ALIVE message
        msg = ("ALIVE | %s | %s | %s | %s | %s | %s | %s | %s | %s" %
               (self.app.cloud_interface.get_private_ip(),
                self.app.cloud_interface.get_public_ip(),
                self.app.cloud_interface.get_zone(),
                self.app.cloud_interface.get_type(),
                self.app.cloud_interface.get_ami(),
                self.app.manager.local_hostname,
                num_cpus,
                total_memory,
                misc.get_hostname()))
        self.conn.send(msg)
        log.debug("Sending message '%s'" % msg)

    def send_worker_hostcert(self):
        host_cert = self.app.manager.get_host_cert()
        if host_cert is not None:
            m_response = "WORKER_H_CERT | %s " % host_cert
            log.debug("Composing worker host cert message: '%s'" % m_response)
            self.conn.send(m_response)
        else:
            log.error("Sending HostCert failed, HC is None.")

    def send_node_ready(self):
        num_cpus = commands.getoutput("cat /proc/cpuinfo | grep processor | wc -l")
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
        # Get the system load in the following format:
        # "0.00 0.02 0.39" for the past 1, 5, and 15 minutes, respectivley
        self.app.manager.load = (
            commands.getoutput("cat /proc/loadavg | cut -d' ' -f1-3")).strip()
        msg_body = "NODE_STATUS | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s" \
            % (self.app.manager.nfs_data,
               self.app.manager.nfs_tools,
               self.app.manager.nfs_indices,
               self.app.manager.nfs_sge,
               self.app.manager.get_cert,
               self.app.manager.sge_started,
               self.app.manager.load,
               self.app.manager.worker_status,
               self.app.manager.nfs_tfs,
               self.app.manager.slurmd_status)
        # log.debug("Sending message '%s'" % msg_body)
        self.conn.send(msg_body)

    def handle_message(self, message):
        if message.startswith("RESTART"):
            m_ip = message.split(' | ')[1]
            log.info("Master at %s requesting RESTART" % m_ip)
            self.app.ud['master_ip'] = m_ip
            self.app.manager.unmount_filesystems()
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
                pss = PSSService(self.app, instance_role='worker')
                threading.Thread(target=pss.start).start()
                self.send_node_ready()
                self.app.manager.worker_status = worker_states.READY
                self.last_state_change_time = dt.datetime.utcnow()
            else:
                log.error("Starting SGE daemon did not go smoothly; process returned code: %s" % ret_code)
                self.app.manager.worker_status = worker_states.ERROR
                self.last_state_change_time = dt.datetime.utcnow()
            # self.app.manager.start_condor(self.app.ud['master_public_ip'])
            # self.app.manager.start_hadoop()
        elif message.startswith("MOUNT"):
            # MOUNT everything in json blob.
            self.app.manager.mount_nfs(self.app.ud['master_ip'],
                                       mount_json=message.split(' | ')[1])
            # If the instance is not ``READY``, it means it's still being configured
            # so send a message to continue the handshake
            if self.app.manager.worker_status != worker_states.READY:
                self.app.manager.console_monitor.conn.send("MOUNT_DONE")
        elif message.startswith("START_SLURMD"):
            alias = message.split(' | ')[1]
            log.info("Got START_SLURMD with worker name {0}".format(alias))
            self.app.manager.start_slurmd(alias)
            # Now that the instance is ready, run the PSS service in a
            # separate thread
            pss = PSSService(self.app, instance_role='worker')
            threading.Thread(target=pss.start).start()
            self.send_node_ready()
            self.app.manager.worker_status = worker_states.READY
            self.last_state_change_time = dt.datetime.utcnow()
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
        elif message.startswith('ALIVE_REQUEST'):
            self.send_alive_message()
        elif message.startswith('SYNC_ETC_HOSTS'):
            # <KWS> syncing etc host using the master one
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
