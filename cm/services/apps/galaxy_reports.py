import urllib2

from cm.services.apps import ApplicationService

from cm.util import paths
from cm.util import misc
from cm.services import service_states

import logging
log = logging.getLogger('cloudman')


class GalaxyReportsService(ApplicationService):

    def __init__(self, app):
        super(GalaxyReportsService, self).__init__(app)
        self.galaxy_home = paths.P_GALAXY_HOME
        self.svc_type = "GalaxyReports"
        self.reqs = {'Galaxy': None}  # Hopefully Galaxy dependency alone enough to ensure database migrated, etc...

    def _check_galaxy_reports_running(self):
        dns = "http://127.0.0.1:9001"
        try:
            urllib2.urlopen(dns)
            return True
        except:
            return False

    def start(self):
        self.state = service_states.STARTING
        self.status()
        if not self.state == service_states.RUNNING:
            started_successfully = False
            # --sync-config will update Galaxy Report's database settings with Galaxy's.
            started = self._run("--sync-config start")
            if started:
                self.status()
                if self.state == service_states.RUNNING:
                    log.info("Successfully started PostgreSQL.")
                    started_successfully = True
            if not started_successfully:
                log.warning("Failed to setup or run galaxy reports server.")
                self.start = service_states.ERROR

    def remove(self):
        log.info("Removing '%s' service" % self.svc_type)
        self.state = service_states.SHUTTING_DOWN
        log.info("Shutting down Galaxy Reports...")
        if self._run("stop"):
            self.state = service_states.SHUT_DOWN
        else:
            log.info("Failed to shutdown down Galaxy Reports...")
            self.state = service_states.ERROR

    def _run(self, args):
        command = '%s - galaxy -c "sh $GALAXY_HOME/run_reports.sh %s"' % (paths.P_SU, args)
        misc.run(command, "Error invoking Galaxy Reports", "Successfully invoked Galaxy Reports.")

    def status(self):
        if self.state == service_states.SHUTTING_DOWN or \
           self.state == service_states.SHUT_DOWN or \
           self.state == service_states.UNSTARTED or \
           self.state == service_states.WAITING_FOR_USER_ACTION:
            pass
        elif self._check_daemon('galaxy_reports'):
            if self._check_galaxy_reports_running():
                self.state = service_states.RUNNING
        elif self.state != service_states.STARTING:
            log.error("Galaxy reports error; Galaxy reports not runnnig")
            self.state = service_states.ERROR
