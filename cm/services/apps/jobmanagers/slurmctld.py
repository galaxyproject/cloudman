import os
import pwd
import grp
import time
import shutil
import commands

from cm.conftemplates import conf_manager
from cm.services import service_states
from cm.services import ServiceRole
from cm.services import ServiceDependency
from cm.services.apps.jobmanagers import BaseJobManager
from cm.services.apps.jobmanagers.slurminfo import SlurmInfo
from cm.util import misc
from cm.util.misc import flock

import logging
log = logging.getLogger('cloudman')


class SlurmctldService(BaseJobManager):
    def __init__(self, app):
        super(SlurmctldService, self).__init__(app)
        self.svc_roles = [ServiceRole.SLURMCTLD, ServiceRole.JOB_MANAGER]
        self.name = ServiceRole.to_string(ServiceRole.SLURMCTLD)
        self.dependencies = [
            ServiceDependency(self, ServiceRole.MIGRATION),
            ServiceDependency(self, ServiceRole.TRANSIENT_NFS),
        ]
        self.slurm_info = SlurmInfo()
        self.num_restarts = 0
        self.max_restarts = 3
        # This must be the same on the workers
        self.slurm_lock_file = os.path.join(self.app.path_resolver.slurm_root_nfs,
                                            'slurm.lockfile')
        # Following a cluster reboot, this file may have been left over so
        # clean it up before starting the service
        if os.path.exists(self.slurm_lock_file):
            os.remove(self.slurm_lock_file)

    def start(self):
        """
        Start this service. This method is automatically called when the service
        is added.
        """
        log.debug("Starting {0} service".format(self.name))
        self.state = service_states.STARTING
        self._setup_munge()
        self._setup_slurm()

    def remove(self, synchronous=False):
        if self._check_daemon('slurmctld'):
            log.info("Removing {0} service".format(self.name))
            super(SlurmctldService, self).remove(synchronous)
            self.state = service_states.SHUTTING_DOWN
            misc.run("/usr/bin/scontrol shutdown")
            time.sleep(3)
            misc.run("/sbin/start-stop-daemon --retry TERM/5/KILL/10 --stop "
                     "--exec /usr/sbin/slurmctld")
            misc.run("service munge stop")
            self.state = service_states.SHUT_DOWN
        else:
            log.debug("Tried to remove {0} service but no deamon running?"
                      .format(self.name))

    def _setup_munge(self):
        """
        Setup Munge (used by Slurm as a user auth mechanism)
        """
        log.debug("Setting up Munge (for Slurm)...")
        if not os.path.exists('/etc/munge'):
            # Munge not installed so grab it
            misc.run("apt-get update; apt-get install munge libmunge-dev -y")
        misc.run("/usr/sbin/create-munge-key")
        misc.append_to_file('/etc/default/munge', 'OPTIONS="--force"')
        misc.run("service munge start")
        log.debug("Done setting up Munge")
        # Copy the munge key to cluster NFS
        if not os.path.exists(self.app.path_resolver.slurm_root_nfs):
            misc.make_dir(self.app.path_resolver.slurm_root_nfs)
        nfs_munge_key = os.path.join(self.app.path_resolver.slurm_root_nfs, 'munge.key')
        shutil.copyfile('/etc/munge/munge.key', nfs_munge_key)
        os.chmod(nfs_munge_key, 0400)
        log.debug("Copied /etc/munge/munge.key to {0}".format(nfs_munge_key))

    def _setup_slurm(self):
        """
        Setup ``slurmctld`` process.
        """
        log.debug("Setting up Slurmctld... (if stuck here for a while, check {0})"
                  .format(self.slurm_lock_file))
        if not os.path.exists('/etc/slurm-llnl'):
            # Slurm package not installed so grab it
            misc.run("apt-get install slurm-llnl -y")
        self._setup_slurm_conf()
        self._start_slurmctld()
        log.debug("Done setting up Slurmctld")

    def _setup_slurm_conf(self):
        """
        Setup ``slurm.conf`` configuration file
        """
        def _worker_nodes_conf():
            """
            Compose the conf lines pertaining to the worker nodes. Return two
            lists of strings: a one-per-line node specifications (eg,
            ``NodeName=w1 NodeAddr=<private_IP> Weight=5 State=UNKNOWN``) and
            a list of node names (eg, w1, w2).
            Note that only nodes in status ``Ready`` or ``Startup`` will be
            included.
            """
            wnc = ''
            wnn = ''
            for i, w in enumerate(self.app.manager.worker_instances):
                if w.worker_status in ['Ready', 'Startup']:
                    wnc += ('NodeName={0} NodeAddr={1} CPUs={2} RealMemory={3} Weight=5 State=UNKNOWN\n'
                            .format(w.alias, w.private_ip, w.num_cpus,
                                    max(1, w.total_memory / 1024)))
                    wnn += ',{0}'.format(w.alias)
            log.debug("Worker node names to include in slurm.conf: {0}".format(wnn[1:]))
            return wnc, wnn

        def _build_slurm_conf():
            log.debug("Setting slurm.conf parameters")
            # Make sure the slurm root dir exists and is owned by slurm user
            misc.make_dir(self.app.path_resolver.slurm_root_tmp)
            os.chown(self.app.path_resolver.slurm_root_tmp,
                     pwd.getpwnam("slurm")[2], grp.getgrnam("slurm")[2])
            worker_nodes, worker_names = _worker_nodes_conf()
            slurm_conf_template = conf_manager.load_conf_template(conf_manager.SLURM_CONF_TEMPLATE)
            slurm_conf_params = {
                "master_hostname": misc.get_hostname(),
                "num_cpus": max(self.app.manager.num_cpus - 1, 1),  # Reserve 1 CPU
                "total_memory": max(1, self.app.manager.total_memory / 1024),
                "slurm_root_tmp": self.app.path_resolver.slurm_root_tmp,
                "worker_nodes": worker_nodes,
                "worker_names": worker_names
            }
            return slurm_conf_template.substitute(slurm_conf_params)

        if not os.path.exists(self.app.path_resolver.slurm_root_nfs):
            misc.make_dir(self.app.path_resolver.slurm_root_nfs)
        nfs_slurm_conf = self.app.path_resolver.slurm_conf_nfs
        local_slurm_conf = self.app.path_resolver.slurm_conf_local
        # Ocasionally, NFS file is unavailable so try a few times
        for i in range(5):
            with flock(self.slurm_lock_file):
                log.debug("Setting up {0} (attempt {1}/5)".format(nfs_slurm_conf, i))
                try:
                    with open(nfs_slurm_conf, 'w') as f:
                        print >> f, _build_slurm_conf()
                    log.debug("Created slurm.conf as {0}".format(nfs_slurm_conf))
                    break
                except IOError, e:
                    log.error("Trouble creating {0}: {1}".format(nfs_slurm_conf, e))
                    time.sleep(2)
        # Make the conf file available on the cluster-wide NFS file system
        # slurm-llnl package does not respect -f flag to specify a custom
        # location of the file so need to have a copy
        if not os.path.exists(local_slurm_conf) and not os.path.islink(local_slurm_conf):
            log.debug("Symlinking {0} to {1}".format(nfs_slurm_conf, local_slurm_conf))
            os.symlink(nfs_slurm_conf, local_slurm_conf)

    def _start_slurmctld(self):
        """
        Start the ``slurmctld`` controller process
        """
        log.debug("Starting slurmctld...")
        if misc.run("/usr/sbin/slurmctld -L /var/log/slurm-llnl/slurmctld.log"):
            self.state = service_states.RUNNING
            log.debug("Started slurmctld")
        else:
            self.state = service_states.ERROR

    def _reconfigure_cluster(self):
        """
        (Re)configure the cluster (ie, job manager) to match the current set of
        resources. The method will (re)generate ``slurm.conf`` and issue
        ``scontrol reconfigure`` command that will update all Slurm damemons.
        """
        log.debug("Reconfiguring Slurm cluster")
        self._setup_slurm_conf()
        return misc.run("/usr/bin/scontrol reconfigure")

    def add_node(self, instance):
        """
        Reconfigure the entire cluster to include all and only the instances in
        state ``Running`` or ``Startup``.

        Note that as a consequence of how Slurm is administered (ie, at the
        cluster level vs. individual node level), this method does not use the
        ``BaseJobManager``-requried ``instance`` parameter.
        """
        log.debug("Adding node {0} into Slurm cluster".format(instance.alias))
        return self._reconfigure_cluster()

    def remove_node(self, instance):
        """
        Reconfigure the entire cluster to include all and only the instances in
        state ``Running`` or ``Startup``.

        Note that as a consequence of how Slurm is administered (ie, at the
        cluster level vs. individual node level), this method does not use the
        ``BaseJobManager``-requried ``instance`` parameter.
        """
        log.debug("Removing node {0} from Slurm cluster".format(instance.alias))
        self.disable_node(instance.alias, instance.private_ip, state="DOWN")
        return self._reconfigure_cluster()

    def enable_node(self, alias, address):
        """
        Enable node identified by ``alias`` for running jobs by setting it's
        state to ``RESUME``. Note that this assumes the node is, on the back end,
        properly configured and will communicate with the master node to confirm
        its status. Note that ``address`` parameter is not used in this
        implementation.
        """
        return misc.run("/usr/bin/scontrol update NodeName={0} State=RESUME"
                        .format(alias))

    def disable_node(self, alias, address, state="DRAIN", reason="CloudMan-disabled"):
        """
        Disable the node identified by ``alias`` from running jobs by setting
        it's state to ``state`` (eg, ``DOWN``, ``DRAIN``). If desired, can also
        specify why the node is being disbled by providing a ``reason``. Note
        that ``address`` parameter is not used in this implementation.

        Setting the node state to ``DRAIN`` will allow the currently running
        job(s) to complete before Slurm will set the node state to ``DOWN``.
        Setting the node state to ``DOWN`` will cause all running and suspended
        jobs on that node to be terminated (and automatically rescheduled on a
        different node).
        """
        return misc.run('/usr/bin/scontrol update NodeName={0} Reason="{1}" State={2}'
                        .format(alias, reason, state))

    def idle_nodes(self):
        """
        Get a listing of nodes that are currently not executing any jobs. Return
        a list of strings containing node names/aliases (as registered with Slurm)
        (eg, ``['master', 'w1', 'w2']``).
        """
        # Get a listing of idle nodes as reported by Slurm's sinfo command. The
        # format of the returned string is as follows: 'master,w1,w2'
        idle_nodes = []
        try:
            idle_nodes = commands.getoutput("sinfo -o '%T %n' -h | grep -E 'idle|down' | awk '{ print $NF }' "
                                            "| tr '\n' ',' | sed '$ s/,$//'").split(",")
        except Exception, e:
            log.error("Trouble getting idle nodes from Slurm: {0}".format(e))
        # log.debug("Slurm idle nodes: %s" % idle_nodes)
        return idle_nodes

    def suspend_queue(self, queue_name='main'):
        """
        Suspend ``queue_name`` queue from running jobs.
        """
        log.debug("Suspending Slurm partition {0}".format(queue_name))
        misc.run('/usr/bin/scontrol update PartitionName={0} State=DOWN'.format(queue_name))

    def unsuspend_queue(self, queue_name='main'):
        """
        Unsuspend ``queue_name`` queue so it can run jobs.
        """
        log.debug("Unsuspending Slurm partition {0}".format(queue_name))
        misc.run('/usr/bin/scontrol update PartitionName={0} State=UP'.format(queue_name))

    def jobs(self):
        """
        Return a list of jobs currently registered with the job mamanger.
        """
        return self.slurm_info.jobs

    def status(self):
        """
        Check and update the status of Slurmctld service. If the service state is
        ``SHUTTING_DOWN``, ``SHUT_DOWN``, ``UNSTARTED``, or ``WAITING_FOR_USER_ACTION``,
        the method doesn't do anything. Otherwise, it updates service status (see
        ``check_slurm``) by setting ``self.state``, whose value is always the method's
        return value.
        """
        if self.state == service_states.SHUTTING_DOWN or \
           self.state == service_states.SHUT_DOWN or \
           self.state == service_states.UNSTARTED or \
           self.state == service_states.WAITING_FOR_USER_ACTION:
            pass
        elif self._check_daemon('slurmctld'):
            self.state = service_states.RUNNING
            self.num_restarts = 0  # Reset the restart counter once we're running
        elif self.state != service_states.STARTING:
            self.state = service_states.ERROR
            log.error("Slurm error: slurmctld not running; setting service state "
                      "to {0}".format(self.state))
            # Ocasionally, things just need another kick
            if self.max_restarts > self.num_restarts:
                self.num_restarts += 1
                log.debug("Automatically trying to restart slurmcrld (attempt {0}/{1}"
                          .format(self.num_restarts, self.max_restarts))
                self.start()
        return self.state
