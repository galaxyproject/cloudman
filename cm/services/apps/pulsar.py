import os

from cm.util import paths
from cm.util import misc
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
DEFAULT_DOWNLOAD_URL = 'https://s3.amazonaws.com/cloudman/files/pulsar/pulsar-20141110.tar.gz'


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
        self.status()
        if not self.state == service_states.RUNNING:
            self._download()
            # self._setup()
            started = self._run("--daemon")
            if not started:
                log.warn("Failed to setup or run Pulsar server.")
                self.state = service_states.ERROR

    def _download(self):
        """
        Download an archive with Pulsar that's been pre-packaged/configured to
        run in the CloudMan environment.
        """
        url = self.app.ud.get('pulsar_download_url', DEFAULT_DOWNLOAD_URL)
        misc.extract_archive_content_to_path(url, os.path.dirname(self.pulsar_home))
        attempt_chown_galaxy_if_exists(self.pulsar_home)

    def _setup(self):
        ini_path = self.__ini_path()
        if not os.path.exists(ini_path):
            misc.run("cp '%s.sample' '%s'" % (ini_path, ini_path))
        # TODO: Configure Pulsar.

    def remove(self, synchronous=False):
        log.info("Removing '%s' service" % self.name)
        super(PulsarService, self).remove(synchronous)
        self.state = service_states.SHUTTING_DOWN
        if self.pulsar_home and self._run("--stop-daemon"):
            log.info("Shutting down Pulsar service...")
            self.state = service_states.SHUT_DOWN
            # TODO: Handle log files.
        else:
            log.info("Failed to shutdown down Pulsar service...")
            self.state = service_states.ERROR

    def _run(self, args):
        command = '%s - galaxy -c "bash %s/run.sh %s"' % (
            paths.P_SU, self.pulsar_home, args)
        return misc.run(command, INVOKE_FAILURE, INVOKE_SUCCESS)

    def status(self):
        if self.state == service_states.SHUTTING_DOWN or \
            self.state == service_states.SHUT_DOWN or \
            self.state == service_states.UNSTARTED or \
                self.state == service_states.WAITING_FOR_USER_ACTION:
            pass
        elif self._check_daemon('pulsar'):
            if self._check_pulsar_running():
                self.state = service_states.RUNNING
        elif self.state != service_states.STARTING:
            log.error("Pulsar error; Pulsar not runnnig")
            self.state = service_states.ERROR
