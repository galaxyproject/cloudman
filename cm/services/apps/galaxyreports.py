from datetime import datetime
import os
import subprocess

from cm.services.apps import ApplicationService

from cm.util import paths
from cm.util import misc
from cm.services import service_states
from cm.services import ServiceRole
from cm.services import ServiceDependency
from cm.util.galaxy_conf import DirectoryGalaxyOptionManager
from cm.util.galaxy_conf import attempt_chown_galaxy

import logging
from cm.conftemplates import conf_manager
log = logging.getLogger('cloudman')
DEFAULT_REPORTS_PORT = 9001


class GalaxyReportsService(ApplicationService):

    def __init__(self, app):
        super(GalaxyReportsService, self).__init__(app)
        self.galaxy_home = self.app.path_resolver.galaxy_home
        self.reports_port = DEFAULT_REPORTS_PORT
        self.name = ServiceRole.to_string(ServiceRole.GALAXY_REPORTS)
        self.svc_roles = [ServiceRole.GALAXY_REPORTS]
        # Hopefully Galaxy dependency alone enough to ensure database migrated, etc...
        self.dependencies = [
            ServiceDependency(self, ServiceRole.GALAXY),
            ServiceDependency(self, ServiceRole.GALAXY_POSTGRES)
        ]
        self.conf_file = os.path.join(self.app.path_resolver.galaxy_home,
                                      'config/reports.yml')

    def __repr__(self):
        return "Galaxy Reports service on port {0}".format(DEFAULT_REPORTS_PORT)

    def _check_galaxy_reports_running(self):
        return self._port_bound(self.reports_port)

    def start(self):
        self.state = service_states.STARTING
        log.debug("Starting GalaxyReportsService")
        self.status()
        if not self.state == service_states.RUNNING:
            self._setup()
            started = self._run("--daemon")
            if not started:
                log.warn("Failed to setup or run galaxy reports server.")
                self.state = service_states.ERROR

    def _setup(self):
        log.debug("Running GalaxyReportsService _setup")
        # WORKAROUND: The run_reports.sh command refers to a parameter
        # named --safe-pidfile which is not supported by the uwsgi binary.
        # Replace it with --pidfile instead.
        patch_start_command = ("sudo sed -i \"s/--safe-pidfile/--pidfile/g"
                               "\" %s/scripts/common_startup_functions.sh"
                               % self.galaxy_home)
        misc.run(patch_start_command)
        # Create default output dir for files
        file_path = os.path.join(self.app.path_resolver.galaxy_home, "database/files")
        misc.make_dir(file_path, owner='galaxy')
        tmp_file_path = os.path.join(self.app.path_resolver.galaxy_home, "database/tmp")
        misc.make_dir(tmp_file_path, owner='galaxy')

        # Create the new reports config
        params = {
            'galaxy_db_port': self.app.path_resolver.psql_db_port
        }
        template = conf_manager.load_conf_template(conf_manager.GALAXY_REPORTS_TEMPLATE)
        misc.write_template_file(template, params, self.conf_file)
        attempt_chown_galaxy(self.conf_file)

    def remove(self, synchronous=False):
        """
        Remove Galaxy Reports service by stopping the application and setting
        it's state to `SHUT_DOWN`. If the app cannot be shut down, set state
        to `ERROR`.
        """

        if self.state in [service_states.RUNNING, service_states.STARTING, service_states.ERROR]:
            log.info("Removing '%s' service" % self.name)
            super(GalaxyReportsService, self).remove(synchronous)
            self.state = service_states.SHUTTING_DOWN
            log.info("Shutting down Galaxy Reports...")
            if not self._running():
                log.debug("Galaxy Reports is already not running.")
                self.state = service_states.SHUT_DOWN
            elif self._run("--stop-daemon"):
                self.state = service_states.SHUT_DOWN
                # Move all log files
                subprocess.call("bash -c 'for f in $GALAXY_HOME/reports_webapp.log; do mv \"$f\" \"$f.%s\"; done'" %
                                datetime.utcnow().strftime('%H_%M'), shell=True)
            else:
                log.info("Failed to shutdown down Galaxy Reports...")
                self.state = service_states.ERROR
        elif self.state == service_states.UNSTARTED:
            self.state = service_states.SHUT_DOWN
        else:
            log.debug("{0} service not running (state: {1}) so not removing it."
                      .format(self.name, self.state))

    def _run(self, args):
        command = '%s - galaxy -c "sh $GALAXY_HOME/run_reports.sh %s"' % (
            paths.P_SU, args)
        return misc.run(command)

    def _running(self):
        """
        Check if the app is running and return `True` if so; `False` otherwise.
        """
        if self._check_daemon('galaxyreports'):
            if self._check_galaxy_reports_running():
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
            log.error("Galaxy reports error; Galaxy reports not running")
            self.state = service_states.ERROR
