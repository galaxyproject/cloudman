from cm.services import service_states
from cm.services import ServiceRole
from cm.services import ServiceDependency
from cm.services.apps.jobmanagers import BaseJobManager
from cm.util import misc

import logging
log = logging.getLogger('cloudman')


class SlurmdService(BaseJobManager):
    def __init__(self, app):
        super(SlurmdService, self).__init__(app)
        self.svc_roles = [ServiceRole.SLURMD]
        self.name = ServiceRole.to_string(ServiceRole.SLURMD)
        self.dependencies = [
            ServiceDependency(self, ServiceRole.SLURMCTLD),
        ]
        self.num_restarts = 0
        self.max_restarts = 3

    def start(self):
        """
        Start this service. This method is automatically called when the service
        is added.
        """
        log.debug("Starting {0} service".format(self.name))
        self.state = service_states.STARTING
        self._setup_slurm()
        self.state = service_states.RUNNING

    def remove(self, synchronous=False):
        if self._check_daemon('slurmd'):
            log.info("Removing {0} service".format(self.name))
            super(SlurmdService, self).remove(synchronous)
            self.state = service_states.SHUTTING_DOWN
            misc.run("/sbin/start-stop-daemon --retry TERM/5/KILL/10 --stop "
                     "--exec /usr/sbin/slurmd")
            self.state = service_states.SHUT_DOWN
        else:
            log.debug("Tried to remove {0} service but no deamon running?"
                      .format(self.name))

    def _setup_slurm(self):
        """
        Setup Slurm, including ``slurmctld`` the controller and a ``slurmd`` worker
        daemon processes.
        """
        log.debug("Setting up Slurmd...")
        self._start_slurmd()
        log.debug("Done setting up Slurmd")

    def _start_slurmd(self):
        """
        Start the ``slurmd`` worker daemon process
        """
        log.debug("Starting slurmd...")
        if misc.run("/usr/sbin/slurmd -c -N master -L /var/log/slurm-llnl/slurmd.log"):
            self.state = service_states.RUNNING
            log.debug("Started slurmd")
        else:
            self.state = service_states.ERROR

    def status(self):
        """
        Check and update the status of Slurmd service. If the service state is
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
        elif self._check_daemon('slurmd'):
            self.state = service_states.RUNNING
            self.num_restarts = 0  # Reset the restart counter once we're running
        elif self.state != service_states.STARTING:
            self.state = service_states.ERROR
            log.error("Slurm error: slurmd not running; setting service state "
                      "to {0}".format(self.state))
            if self.max_restarts > self.num_restarts:
                self.num_restarts += 1
                log.debug("Automatically trying to restart slurmd (attempt {0}/{1}"
                          .format(self.num_restarts, self.max_restarts))
                self.start()
        return self.state
