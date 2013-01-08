from datetime import datetime
import os
import subprocess
import urllib2

from cm.services.apps import ApplicationService

from cm.util import paths
from cm.util import misc
from cm.services import service_states
from cm.services import ServiceRole
from cm.services import ServiceDependency
from cm.services.apps.galaxy import GalaxyService

import logging
log = logging.getLogger('cloudman')


class GalaxyReportsService(ApplicationService):

    def __init__(self, app):
        super(GalaxyReportsService, self).__init__(app)
        self.galaxy_home = paths.P_GALAXY_HOME
        self.svc_role = ServiceRole.GALAXY_REPORTS
        self.reqs = [ ServiceDependency(self, ServiceRole.GALAXY) ]  # Hopefully Galaxy dependency alone enough to ensure database migrated, etc...
        self.conf_dir = os.path.join(paths.P_GALAXY_HOME, 'reports.conf.d')

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
            self._setup()
            # --sync-config will update Galaxy Report's database settings with Galaxy's.
            started = self._run("--sync-config start")
            if not started:
                log.warn("Failed to setup or run galaxy reports server.")
                self.start = service_states.ERROR

    def _setup(self):
        # setup config dir
        conf_dir = self.conf_dir
        GalaxyService.initialize_galaxy_config_dir(conf_dir, 'reports_wsgi.ini')
        # This will ensure galaxy's run.sh file picks up the config dir.
        cloudman_specific_config = os.path.join(conf_dir, "020_cloudman.ini")
        if not os.path.exists(cloudman_specific_config):
            open(cloudman_specific_config, 'w').write("""
[filter:proxy-prefix]
use = egg:PasteDeploy#prefix
prefix = /reports

[app:main]
# Place dummy database_connection for run_reports.sh's --sync-config option to replace
database_connection = dummy
filter-with = proxy-prefix
""")

    def remove(self):
        log.info("Removing '%s' service" % self.svc_role)
        self.state = service_states.SHUTTING_DOWN
        log.info("Shutting down Galaxy Reports...")
        if self._run("stop"):
            self.state = service_states.SHUT_DOWN
            # Move all log files
            subprocess.call("bash -c 'for f in $GALAXY_HOME/reports_webapp.log; do mv \"$f\" \"$f.%s\"; done'" % datetime.utcnow().strftime('%H_%M'), shell=True)
        else:
            log.info("Failed to shutdown down Galaxy Reports...")
            self.state = service_states.ERROR

    def _run(self, args):
        command = '%s - galaxy -c "export GALAXY_REPORTS_CONFIG_DIR=\'%s\'; sh $GALAXY_HOME/run_reports.sh %s"' % (paths.P_SU, self.conf_dir, args)
        return misc.run(command, "Error invoking Galaxy Reports", "Successfully invoked Galaxy Reports.")

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
