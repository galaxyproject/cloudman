import os


from cm.util import paths
from cm.util import misc
from cm.services import service_states
from cm.services import ServiceRole
from cm.services import ServiceDependency
from cm.services.apps import ApplicationService

import logging
log = logging.getLogger('cloudman')

INVOKE_SUCCESS = "Successfully invoked LWR."
INVOKE_FAILURE = "Error invoking LWR."
DEFAULT_LWR_PORT = 8913


class LwrService(ApplicationService):

    def __init__(self, app):
        super(LwrService, self).__init__(app)
        self.lwr_home = self.app.path_resolver.lwr_home
        self.lwr_port = DEFAULT_LWR_PORT
        self.name = ServiceRole.to_string(ServiceRole.LWR)
        self.svc_roles = [ServiceRole.LWR]
        self.dependencies = [
            ServiceDependency(self, ServiceRole.SGE),  # Well someday anyway :)
            ServiceDependency(self, ServiceRole.GALAXY_TOOLS)  # Anyway to make this depend on where LWR installed?
        ]

    def __rel_path(self, *args):
        return os.path.join(self.lwr_home, *args)

    def __ini_path(self):
        return self.__rel_path("server.ini")

    def _check_lwr_running(self):
        return self._port_bound(self.lwr_port)

    def start(self):
        self.state = service_states.STARTING
        self.status()
        if not self.state == service_states.RUNNING:
            self._setup()
            started = self._run("--daemon")
            if not started:
                log.warn("Failed to setup or run LWR server.")
                self.start = service_states.ERROR

    def _setup(self):
        ini_path = self.__ini_path()
        if not os.path.exists(ini_path):
            misc.run("cp '%s.sample' '%s'" % (ini_path, ini_path))
        # TODO: Configure LWR.

    def remove(self, synchronous=False):
        log.info("Removing '%s' service" % self.name)
        super(LwrService, self).remove(synchronous)
        self.state = service_states.SHUTTING_DOWN
        log.info("Shutting down LWR service...")
        if self._run("--stop-daemon"):
            self.state = service_states.SHUT_DOWN
            # TODO: Handle log files.
        else:
            log.info("Failed to shutdown down LWR service...")
            self.state = service_states.ERROR

    def _run(self, args):
        command = '%s - galaxy -c "bash %s/run.sh %s"' % (
            paths.P_SU, self.lwr_home, args)
        return misc.run(command, INVOKE_FAILURE, INVOKE_SUCCESS)

    def status(self):
        if self.state == service_states.SHUTTING_DOWN or \
            self.state == service_states.SHUT_DOWN or \
            self.state == service_states.UNSTARTED or \
                self.state == service_states.WAITING_FOR_USER_ACTION:
            pass
        elif self._check_daemon('lwr'):
            if self._check_lwr_running():
                self.state = service_states.RUNNING
        elif self.state != service_states.STARTING:
            log.error("LWR error; LWR not runnnig")
            self.state = service_states.ERROR
