import os
import urllib2
import subprocess
from datetime import datetime

from cm.services.apps import ApplicationService
from cm.services import service_states
from cm.services import ServiceRole
from cm.services import ServiceDependency
from cm.util import paths
from cm.util import misc
from cm.util.decorators import TestFlag, delay
from cm.util.galaxy_conf import galaxy_option_manager
from cm.util.galaxy_conf import populate_process_options
from cm.util.galaxy_conf import populate_dynamic_options
from cm.util.galaxy_conf import populate_galaxy_paths
from cm.util.galaxy_conf import populate_admin_users

import logging
log = logging.getLogger('cloudman')

NUM_START_ATTEMPTS = 2  # Number of times we attempt to start Galaxy


class GalaxyService(ApplicationService):

    def __init__(self, app):
        super(GalaxyService, self).__init__(app)
        self.name = ServiceRole.to_string(ServiceRole.GALAXY)
        self.svc_roles = [ServiceRole.GALAXY]
        self.remaining_start_attempts = NUM_START_ATTEMPTS
        self.configured = False  # Indicates if the environment for running Galaxy has been configured
        self.ssl_is_on = False
        # Environment variables to set before executing galaxy's run.sh
        self.env_vars = {}
        self.dependencies = [
            ServiceDependency(self, ServiceRole.JOB_MANAGER),
            ServiceDependency(self, ServiceRole.GALAXY_POSTGRES),
            ServiceDependency(self, ServiceRole.GALAXY_DATA),
            ServiceDependency(self, ServiceRole.GALAXY_INDICES),
            ServiceDependency(self, ServiceRole.GALAXY_TOOLS),
            ServiceDependency(self, ServiceRole.PROFTPD)
        ]
        self.option_manager = galaxy_option_manager(app)

    @property
    def galaxy_home(self):
        """
        Return the path where Galaxy application is available
        """
        return self.app.path_resolver.galaxy_home

    def start(self):
        self.state = service_states.STARTING
        self.time_started = datetime.utcnow()
        if not self.activated:
            self.activated = True
            log.debug("Service {0} self-activated".format(self.get_full_name()))
        self.manage_galaxy(True)

    def remove(self, synchronous=False):
        log.info("Removing '%s' service" % self.name)
        super(GalaxyService, self).remove(synchronous)
        self.state = service_states.SHUTTING_DOWN
        self.manage_galaxy(False)

    def restart(self):
        log.info('Restarting Galaxy service')
        self.remove()
        self.status()
        self.start()

    @TestFlag(None)
    def manage_galaxy(self, to_be_started=True):
        """
        Use this method to start and stop Galaxy application.

        :type to_be_started: bool
        :param to_be_started: If set, this method will attempt to start the
                              Galaxy application process. If not set, the
                              method will attempt to shut down the application
                              process.
        """
        log.debug("Using Galaxy from '{0}'".format(self.galaxy_home))
        os.putenv("GALAXY_HOME", self.galaxy_home)
        os.putenv("TEMP", self.app.path_resolver.galaxy_temp)
        os.putenv("TMPDIR", self.app.path_resolver.galaxy_temp)
        self.env_vars["GALAXY_HOME"] = self.galaxy_home
        self.env_vars["TEMP"] = self.app.path_resolver.galaxy_temp
        self.env_vars["TMPDIR"] = self.app.path_resolver.galaxy_temp
        conf_dir = self.option_manager.setup()
        if conf_dir:
            self.env_vars["GALAXY_UNIVERSE_CONFIG_DIR"] = conf_dir

        if self.multiple_processes():
            self.env_vars["GALAXY_RUN_ALL"] = "TRUE"
            # HACK: Galaxy has a known problem when starting from a fresh configuration
            # in multiple process mode. Each process attempts to create the same directories
            # and one or more processes can fail to start because it "failed" to create
            # said directories (because another process created them first). This hack staggers
            # the process starts in an attempt to circumvent this problem.
            patch_run_sh_command = "sudo sed -i -e \"s/server.log \\$\\@$/\\0; sleep 4/\" %s/run.sh" % self.galaxy_home
            misc.run(patch_run_sh_command)
            self.extra_daemon_args = ""
        else:
            # Instead of sticking with default paster.pid and paster.log, explicitly
            # set pid and log file to ``main.pid`` and ``main.log`` to bring single
            # process case inline with defaults for for multiple process case (i.e.
            # when GALAXY_RUN_ALL is set and multiple servers are defined).
            self.extra_daemon_args = "--pid-file=main.pid --log-file=main.log"
        if to_be_started and self.remaining_start_attempts > 0:
            self.status()
            if not self.configured:
                log.debug("Setting up Galaxy application")
                # Set job manager configs if necessary
                for job_manager_svc in self.app.manager.service_registry.active(
                        service_role=ServiceRole.JOB_MANAGER):
                    if ServiceRole.SGE in job_manager_svc.svc_roles:
                        log.debug("Running on SGE; setting env_vars")
                        self.env_vars["SGE_ROOT"] = self.app.path_resolver.sge_root,
                        self.env_vars["DRMAA_LIBRARY_PATH"] = self.app.path_resolver.drmaa_library_path
                # Make sure Galaxy home dir exists
                if not os.path.exists(self.galaxy_home):
                    log.error("Galaxy application directory '%s' does not "
                              "exist! Aborting." % self.galaxy_home)
                    log.debug("ls /mnt/: %s" % os.listdir('/mnt/'))
                    self.state = service_states.ERROR
                    self.last_state_change_time = datetime.utcnow()
                    return False
                # Ensure the necessary directories exist
                for dir_name in [paths.P_GALAXY_INDICES,
                                 ('%s/tmp/job_working_directory' %
                                  self.app.path_resolver.galaxy_data)]:
                    misc.make_dir(dir_name, 'galaxy')
                self.remaining_start_attempts -= 1
                self.configured = True
            if not self._is_galaxy_running():
                log.debug("Starting Galaxy...")
                # Make sure admin users get added
                self.update_galaxy_config()
                start_command = self.galaxy_run_command(
                    "%s --daemon" % self.extra_daemon_args)
                if not misc.run(start_command):
                    if self.remaining_start_attempts > 0:
                        self.state = service_states.UNSTARTED
                        self.last_state_change_time = datetime.utcnow()
                    else:
                        self.state = service_states.ERROR
                        self.last_state_change_time = datetime.utcnow()
            else:
                log.debug("Galaxy already running.")
        else:
            log.info("Shutting down Galaxy...")
            self.state = service_states.SHUTTING_DOWN
            stop_command = self.galaxy_run_command("%s --stop-daemon" % self.extra_daemon_args)
            if self._is_galaxy_running():
                misc.run(stop_command)
            if not self._is_galaxy_running():
                log.debug("Galaxy not running; setting service state to SHUT_DOWN.")
                self.state = service_states.SHUT_DOWN
                self.last_state_change_time = datetime.utcnow()
                # Move all log files
                subprocess.call("bash -c 'for f in $GALAXY_HOME/{main,handler,manager,web}*.log; "
                                "do mv \"$f\" \"$f.%s\"; done'" % datetime.utcnow()
                                .strftime('%H_%M'), shell=True)

    def multiple_processes(self):
        return self.app.config.multiple_processes

    def galaxy_run_command(self, args):
        """
        Compose the command used to manage Galaxy process.

        This will source Galaxy's virtualenv and compose the run command
        with provided `args`.

        :type args: string
        :param args: Arguments to feed to Galaxy's run command, for example:
                     `--daemon` or `--stop-daemon`.
        """
        env_exports = "; ".join(["export %s='%s'" % (
            key, value) for key, value in self.env_vars.iteritems()])
        venv = "source $GALAXY_HOME/.venv/bin/activate"
        run_command = '%s - galaxy -c "%s; %s; sh $GALAXY_HOME/run.sh %s"' % (
            paths.P_SU, env_exports, venv, args)
        return run_command

    @delay
    def status(self):
        """Set the status of the service based on the state of the app process."""
        old_state = self.state
        if self._is_galaxy_running():
            self.state = service_states.RUNNING
        elif (self.state == service_states.SHUTTING_DOWN or
              self.state == service_states.SHUT_DOWN or
              self.state == service_states.UNSTARTED or
              self.state == service_states.WAITING_FOR_USER_ACTION):
            pass
        else:
            if self.state == service_states.STARTING and \
                    (datetime.utcnow() - self.last_state_change_time).seconds < 60:
                # Give Galaxy a minutes to start; otherwise, because
                # the monitor is running as a separate thread, it often happens
                # that the .pid file is not yet created after the Galaxy process
                # has been started so the monitor thread erroneously reports
                # as if starting the Galaxy process has failed.
                pass
            else:
                log.error("Galaxy daemon not running.")
                if self.remaining_start_attempts > 0:
                    log.debug("Remaining Galaxy start attempts: {0}; setting svc state "
                              "to UNSTARTED".format(self.remaining_start_attempts))
                    self.state = service_states.UNSTARTED
                    self.last_state_change_time = datetime.utcnow()
                else:
                    log.debug("No remaining Galaxy start attempts; setting svc state to ERROR")
                    self.state = service_states.ERROR
                    self.last_state_change_time = datetime.utcnow()
        if old_state != self.state:
            log.info("Galaxy service state changed from '%s' to '%s'" % (
                old_state, self.state))
            self.last_state_change_time = datetime.utcnow()
            if self.state == service_states.RUNNING:
                # Once the service gets running, reset the number of start attempts
                self.remaining_start_attempts = NUM_START_ATTEMPTS
                log.debug("Granting SELECT permission to galaxyftp user on 'galaxy' database")
                misc.run('%s - postgres -c "%s -p %s galaxy -c \\\"GRANT SELECT ON galaxy_user TO galaxyftp\\\" "'
                         % (paths.P_SU, self.app.path_resolver.psql_cmd,
                            self.app.path_resolver.psql_db_port),
                         "Error granting SELECT grant to 'galaxyftp' user",
                         "Successfully added SELECT grant to 'galaxyftp' user")
            # Force cluster configuration state update on status change
            self.app.manager.console_monitor.store_cluster_config()

    def _is_galaxy_running(self):
        """Check is Galaxy process is running and the UI is accessible."""
        if self._check_daemon('galaxy'):
            dns = "http://127.0.0.1:8080"
            running_error_codes = [403]  # Error codes that indicate Galaxy is running
            try:
                urllib2.urlopen(dns)
                return True
            except urllib2.HTTPError, e:
                return e.code in running_error_codes
            except:
                return False
        else:
            log.debug("Galaxy UI does not seem to be accessible.")
            return False

    def update_galaxy_config(self):
        if self.multiple_processes():
            populate_process_options(self.option_manager)
        populate_dynamic_options(self.option_manager)
        populate_galaxy_paths(self.option_manager)
        populate_admin_users(self.option_manager)

    def add_galaxy_admin_users(self, admins_list=[]):
        populate_admin_users(self.option_manager, admins_list)
