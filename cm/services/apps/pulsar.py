import os

from cm.util import paths
from cm.util import misc
from cm.util import ExtractArchive
from cm.util.galaxy_conf import attempt_chown_galaxy_if_exists
from cm.services import service_states
from cm.services import ServiceRole
from cm.services import ServiceDependency
from cm.services.apps import ApplicationService

import logging
log = logging.getLogger('cloudman')

INVOKE_SUCCESS = "Successfully invoked Pulsar"
INVOKE_FAILURE = "Error invoking Pulsar"
DEFAULT_PULSAR_PORT = 8913
DEFAULT_DOWNLOAD_URL = 'http://cloudman.s3.amazonaws.com/files/pulsar/pulsar-20141219.tar.gz'


class PulsarService(ApplicationService):

    def __init__(self, app):
        super(PulsarService, self).__init__(app)
        self.pulsar_home = None
        self.pulsar_port = DEFAULT_PULSAR_PORT
        self.name = ServiceRole.to_string(ServiceRole.PULSAR)
        self.svc_roles = [ServiceRole.PULSAR]
        self.dependencies = [
            ServiceDependency(self, ServiceRole.JOB_MANAGER)
        ]

    def __rel_path(self, *args):
        return os.path.join(self.pulsar_home, *args)

    def __ini_path(self):
        return self.__rel_path("server.ini")

    def _check_pulsar_running(self):
        return self._port_bound(self.pulsar_port)

    def start(self):
        self.pulsar_home = self.app.path_resolver.pulsar_home
        self.state = service_states.STARTING
        if not self.activated:
            self.activated = True
            log.debug("Service {0} self-activated".format(self.get_full_name()))
        self.status()
        if not self.state == service_states.RUNNING:
            self._download()

    def _download(self):
        """
        Download an archive with Pulsar that's been pre-packaged/configured to
        run in the CloudMan environment.
        """
        url = self.app.config.get('pulsar_download_url', DEFAULT_DOWNLOAD_URL)
        ExtractArchive(url, os.path.dirname(self.pulsar_home),
                       callback=self._run).start()

    def _setup(self):
        log.debug("Setting up Pulsar")
        ini_path = self.__ini_path()
        if not os.path.exists(ini_path):
            misc.run("cp '%s.sample' '%s'" % (ini_path, ini_path))
        # TODO: Configure Pulsar.

    def remove(self, synchronous=False):
        """
        Remove Pulsar service by stopping the application and setting it's
        state to `SHUT_DOWN`. If the app cannot be shut down, set state to
        `ERROR`.
        """
        log.info("Removing '%s' service" % self.name)
        super(PulsarService, self).remove(synchronous)
        self.state = service_states.SHUTTING_DOWN
        if not self._running():
            log.debug("Pulsar is already not running.")
            self.state = service_states.SHUT_DOWN
        elif self.pulsar_home and self._run("--stop-daemon"):
            log.info("Shutting down Pulsar service...")
            self.state = service_states.SHUT_DOWN
            # TODO: Handle log files.
        else:
            log.info("Failed to shutdown down Pulsar service...")
            self.state = service_states.ERROR

    def _run(self, args="--daemon"):
        attempt_chown_galaxy_if_exists(self.pulsar_home)
        command = '%s - galaxy -c "bash %s/run.sh %s"' % (
            paths.P_SU, self.pulsar_home, args)
        return misc.run(command, INVOKE_FAILURE, INVOKE_SUCCESS)

    def _running(self):
        """
        Check if the app is running and return `True` if so; `False` otherwise.
        """
        if self._check_daemon('pulsar'):
            if self._check_pulsar_running():
                return True
        return False

    def status(self):
        if self.state == service_states.SHUTTING_DOWN or \
            self.state == service_states.SHUT_DOWN or \
            self.state == service_states.UNSTARTED or \
                self.state == service_states.WAITING_FOR_USER_ACTION:
            pass
        elif self._running():
                self.state = service_states.RUNNING
        elif self.state != service_states.STARTING:
            log.error("Pulsar error; Pulsar not runnnig")
            self.state = service_states.ERROR
