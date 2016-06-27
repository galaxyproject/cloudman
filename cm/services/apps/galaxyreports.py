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

import logging
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
        self.conf_dir = os.path.join(self.app.path_resolver.galaxy_home, 'reports.conf.d')

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
            started = self._run("start")
            if not started:
                log.warn("Failed to setup or run galaxy reports server.")
                self.state = service_states.ERROR

    def _setup(self):
        log.debug("Running GalaxyReportsService _setup")
        reports_option_manager = DirectoryGalaxyOptionManager(self.app,
                                                              conf_dir=self.conf_dir,
                                                              conf_file_name='reports.ini')
        reports_option_manager.setup()
        file_path = os.path.join(self.app.path_resolver.galaxy_data, "files")
        misc.make_dir(file_path, owner='galaxy')
        new_file_path = os.path.join(self.app.path_resolver.galaxy_data, "tmp")
        main_props = {
            'database_connection': "postgres://galaxy@localhost:{0}/galaxy"
                                   .format(self.app.path_resolver.psql_db_port),
            'filter-with': 'proxy-prefix',
            'file_path': file_path,
            'new_file_path': new_file_path,
            'paste.app_factory': 'galaxy.webapps.reports.buildapp:app_factory',
            'use_new_layout': 'true'
        }
        proxy_props = {
            'use': 'egg:PasteDeploy#prefix',
            'prefix': '/reports',
        }
        server_props = {
            'use': "egg:Paste#http",
            'port': 9001,
            'host': '127.0.0.1',
            'use_threadpool': 'true',
            'threadpool_workers': 10
        }
        reports_option_manager.set_properties(server_props, section='server:main',
                                              description='server_main_props')
        reports_option_manager.set_properties(main_props, section='app:main',
                                              description='app_main_props')
        reports_option_manager.set_properties(proxy_props,
                                              section='filter:proxy-prefix',
                                              description='proxy_prefix_props')

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
            elif self._run("stop"):
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
        command = '%s - galaxy -c "export GALAXY_REPORTS_CONFIG_DIR=\'%s\'; sh $GALAXY_HOME/run_reports.sh %s"' % (
            paths.P_SU, self.conf_dir, args)
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
