import os
import shutil
import urllib2
import commands
import subprocess
from datetime import datetime
from string import Template

from cm.conftemplates import nginx
from cm.services.apps import ApplicationService
from cm.services import service_states
from cm.services import ServiceRole
from cm.services import ServiceDependency
from cm.util import paths
from cm.util import misc
from cm.util.decorators import TestFlag
from cm.util.galaxy_conf import attempt_chown_galaxy, attempt_chown_galaxy_if_exists
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
        # Environment variables to set before executing galaxy's run.sh
        self.env_vars = {
            "SGE_ROOT": self.app.path_resolver.sge_root,
            "DRMAA_LIBRARY_PATH": self.app.path_resolver.drmaa_library_path
        }
        self.dependencies = [
            ServiceDependency(self, ServiceRole.SGE),
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
        self.manage_galaxy(True)
        self.status()

    def remove(self, synchronous=False):
        log.info("Removing '%s' service" % self.name)
        super(GalaxyService, self).remove(synchronous)
        if self.state == service_states.RUNNING:
            self.state = service_states.SHUTTING_DOWN
            self.last_state_change_time = datetime.utcnow()
            self.manage_galaxy(False)
        elif self.state == service_states.UNSTARTED:
            self.state = service_states.SHUT_DOWN
        else:
            log.debug("Galaxy service not running (state: {0}) so not stopping it."
                      .format(self.state))

    def restart(self):
        log.info('Restarting Galaxy service')
        self.remove()
        self.status()
        self.start()

    @TestFlag(None)
    def manage_galaxy(self, to_be_started=True):
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

        if self._multiple_processes():
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
            # If not provided as part of user data, update nginx conf with
            # current paths
            if self.app.ud.get('nginx_conf_contents', None) is None:
                self.configure_nginx()
            if not self.configured:
                log.debug("Setting up Galaxy application")
                s3_conn = self.app.cloud_interface.get_s3_connection()
                if not os.path.exists(self.galaxy_home):
                    log.error("Galaxy application directory '%s' does not exist! Aborting." %
                              self.galaxy_home)
                    log.debug("ls /mnt/: %s" % os.listdir('/mnt/'))
                    self.state = service_states.ERROR
                    self.last_state_change_time = datetime.utcnow()
                    return False
                # If a configuration file is not already in Galaxy's dir,
                # retrieve it from a persistent data repository (i.e., S3)
                if s3_conn:
                    for f_name in ['universe_wsgi.ini',
                                   'tool_conf.xml',
                                   'tool_data_table_conf.xml',
                                   'shed_tool_conf.xml',
                                   'datatypes_conf.xml',
                                   'shed_tool_data_table_conf.xml']:
                        f_path = os.path.join(self.galaxy_home, f_name)
                        if not os.path.exists(f_path):
                            if not misc.get_file_from_bucket(s3_conn, self.app.ud['bucket_cluster'],
                                    '{0}.cloud'.format(f_name), f_path):
                                # We did not get the config file from cluster's
                                # bucket so get it from the default bucket
                                log.debug("Did not get Galaxy configuration file " +
                                          "'{0}' from cluster bucket '{1}'"
                                          .format(f_name, self.app.ud['bucket_cluster']))
                                log.debug("Trying to retrieve one ({0}.cloud) "
                                          "from the default '{1}' bucket."
                                          .format(f_name, self.app.ud['bucket_default']))
                                local_file = os.path.join(self.galaxy_home, f_name)
                                misc.get_file_from_bucket(s3_conn,
                                    self.app.ud['bucket_default'], '{0}.cloud'.format(f_name),
                                    local_file)
                                attempt_chown_galaxy_if_exists(local_file)

                # Make sure the temporary job_working_directory exists on user
                # data volume (defined in universe_wsgi.ini.cloud)
                if not os.path.exists('%s/tmp/job_working_directory' % self.app.path_resolver.galaxy_data):
                    os.makedirs('%s/tmp/job_working_directory/' % self.app.path_resolver.galaxy_data)
                attempt_chown_galaxy('%s/tmp/job_working_directory/' % self.app.path_resolver.galaxy_data)
                # Make sure the default shed_tools directory exists
                if not os.path.exists('%s/../shed_tools' % self.app.path_resolver.galaxy_data):
                    os.makedirs('%s/../shed_tools/' % self.app.path_resolver.galaxy_data)
                attempt_chown_galaxy('%s/../shed_tools/' % self.app.path_resolver.galaxy_data)
                # TEMPORARY ONLY - UNTIL SAMTOOLS WRAPPER IS CONVERTED TO USE
                # DATA TABLES
                if os.path.exists('/mnt/galaxyIndices/locfiles/sam_fa_indices.loc'):
                    shutil.copy(
                        '/mnt/galaxyIndices/locfiles/sam_fa_indices.loc',
                        '%s/tool-data/sam_fa_indices.loc' % self.galaxy_home)
                # Ensure the environment is setup for running Galaxy
                # This can also be setup on the tools snapshot and thus avoid these patches
                # try:
                #     subprocess.call( "sed 's/cd `dirname $0`/cd `dirname $0`; export TEMP=\/mnt\/galaxyData\/tmp/; export DRMAA_LIBRARY_PATH=/opt/sge/lib/lx24-amd64/libdrmaa.so.1.0' %s/run.sh > %s/run.sh.custom" % (self.galaxy_home, self.galaxy_home), shell=True )
                #     misc.run("cd %s; sed 's/python/python -ES/g' run.sh.custom > run.sh" % self.galaxy_home, "Failed to adjust run.sh", "Successfully adjusted run.sh")
                #     shutil.copy( self.galaxy_home + '/run.sh.custom', self.galaxy_home + '/run.sh' )
                #     os.chown( self.galaxy_home + '/run.sh', pwd.getpwnam( "galaxy" )[2], grp.getgrnam( "galaxy" )[2] )
                # except Exception, e:
                #     log.debug("Problem customizing Galaxy's run.sh: %s" % e)
                # try:
                #     misc.run("cd %s; sed 's/pyhton/python -ES/g' setup.sh > setup.sh.custom" % self.galaxy_home, "Failed to edit setup.sh", "Successfully adjusted setup.sh")
                #     shutil.copy( self.galaxy_home + '/setup.sh.custom', self.galaxy_home + '/setup.sh' )
                #     os.chown( self.galaxy_home + '/setup.sh', pwd.getpwnam( "galaxy" )[2], grp.getgrnam( "galaxy" )[2] )
                # except Exception, e:
                #     log.error("Error adjusting setup.sh: %s" % e)
                # subprocess.call( 'sed "s/#start_job_runners = pbs/start_job_runners = sge/" $GALAXY_HOME/universe_wsgi.ini > $GALAXY_HOME/universe_wsgi.ini.custom', shell=True )
                # shutil.move( self.galaxy_home + '/universe_wsgi.ini.custom', self.galaxy_home + '/universe_wsgi.ini' )
                # subprocess.call( 'sed "s/#default_cluster_job_runner = pbs:\/\/\//default_cluster_job_runner = sge:\/\/\//" $GALAXY_HOME/universe_wsgi.ini > $GALAXY_HOME/universe_wsgi.ini.custom', shell=True )
                # shutil.move( self.galaxy_home + '/universe_wsgi.ini.custom', self.galaxy_home + '/universe_wsgi.ini' )
                # Configure PATH in /etc/profile because otherwise some tools do not work
                # with open('/etc/profile', 'a') as f:
                #     f.write('export PATH=/mnt/galaxyTools/tools/bin:/mnt/galaxyTools/tools/pkg/fastx_toolkit_0.0.13:/mnt/galaxyTools/tools/pkg/bowtie-0.12.5:/mnt/galaxyTools/tools/pkg/samtools-0.1.7_x86_64-linux:/mnt/galaxyTools/tools/pkg/gnuplot-4.4.0/bin:/opt/PostgreSQL/8.4/bin:$PATH\n')
                # os.chown(self.galaxy_home + '/universe_wsgi.ini',
                # pwd.getpwnam("galaxy")[2], grp.getgrnam("galaxy")[2])
                self.remaining_start_attempts -= 1
                self.configured = True
            if self.state != service_states.RUNNING:
                log.debug("Starting Galaxy...")
                # Make sure admin users get added
                self.update_galaxy_config()
                start_command = self.galaxy_run_command(
                    "%s --daemon" % self.extra_daemon_args)
                log.debug(start_command)
                if not misc.run(start_command, "Error invoking Galaxy",
                        "Successfully initiated Galaxy start from {0}.".format(self.galaxy_home)):
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
            if misc.run(stop_command):
                self.state = service_states.SHUT_DOWN
                self.last_state_change_time = datetime.utcnow()
                # Move all log files
                subprocess.call("bash -c 'for f in $GALAXY_HOME/{main,handler,manager,web}*.log; do mv \"$f\" \"$f.%s\"; done'"
                    % datetime.utcnow().strftime('%H_%M'), shell=True)

    def _multiple_processes(self):
        return self.app.ud.get("configure_multiple_galaxy_processes", True)

    def galaxy_run_command(self, args):
        env_exports = "; ".join(["export %s='%s'" % (
            key, value) for key, value in self.env_vars.iteritems()])
        run_command = '%s - galaxy -c "%s; sh $GALAXY_HOME/run.sh %s"' % (
            paths.P_SU, env_exports, args)
        return run_command

    def status(self):
        """Check if Galaxy daemon is running and the UI is accessible."""
        old_state = self.state
        if self._check_daemon('galaxy'):
            # log.debug("Galaxy daemon running. Checking if UI is accessible.")
            if self._is_galaxy_running():
                self.state = service_states.RUNNING
            else:
                log.debug("Galaxy UI does not seem to be accessible.")
                self.state = service_states.STARTING
        elif self.state == service_states.SHUTTING_DOWN or \
            self.state == service_states.SHUT_DOWN or \
            self.state == service_states.UNSTARTED or \
                self.state == service_states.WAITING_FOR_USER_ACTION:
             # self.state==service_states.STARTING:
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
                    log.debug("Remaining Galaxy start attempts: {0}; setting svc state to UNSTARTED"
                        .format(self.remaining_start_attempts))
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
                misc.run('%s - postgres -c "%s/psql -p %s galaxy -c \\\"GRANT SELECT ON galaxy_user TO galaxyftp\\\" "'
                         % (paths.P_SU, self.app.path_resolver.pg_home, paths.C_PSQL_PORT),
                         "Error granting SELECT grant to 'galaxyftp' user",
                         "Successfully added SELECT grant to 'galaxyftp' user")
            # Force cluster configuration state update on status change
            self.app.manager.console_monitor.store_cluster_config()

    def _is_galaxy_running(self):
        dns = "http://127.0.0.1:8080"
        running_error_codes = [403]
            # Error codes that indicate Galaxy is running
        try:
            urllib2.urlopen(dns)
            return True
        except urllib2.HTTPError, e:
            return e.code in running_error_codes
        except:
            return False

    def update_galaxy_config(self):
        if self._multiple_processes():
            populate_process_options(self.option_manager)
        populate_dynamic_options(self.option_manager)
        populate_galaxy_paths(self.option_manager)
        populate_admin_users(self.option_manager)

    def add_galaxy_admin_users(self, admins_list=[]):
        populate_admin_users(self.option_manager, admins_list)

    def configure_nginx(self):
        """
        Generate nginx.conf from a template and reload nginx process so config
        options take effect
        """
        nginx_dir = self.app.path_resolver.nginx_dir
        if nginx_dir:
            galaxy_server = "server localhost:8080;"
            if self._multiple_processes():
                web_thread_count = int(self.app.ud.get("web_thread_count", 3))
                galaxy_server = ''
                if web_thread_count > 9:
                    log.warning("Current code supports max 9 web threads. "
                        "Setting the web thread count to 9.")
                    web_thread_count = 9
                for i in range(web_thread_count):
                    galaxy_server += "server localhost:808%s;" % i
            # Customize the appropriate nginx template
            if "1.4" in commands.getoutput("/usr/nginx/sbin/nginx -v"):
                log.debug("Using nginx v1.4+ template")
                nginx_tmplt = nginx.NGINX_14_CONF_TEMPLATE
            else:
                nginx_tmplt = nginx.NGINX_CONF_TEMPLATE
            nginx_conf_template = Template(nginx_tmplt)
            params = {
                'galaxy_home': self.galaxy_home,
                'galaxy_data': self.app.path_resolver.galaxy_data,
                'galaxy_server': galaxy_server
            }
            template = nginx_conf_template.substitute(params)

            # Write out the files
            nginx_config_file = os.path.join(nginx_dir, 'conf', 'nginx.conf')
            with open(nginx_config_file, 'w') as f:
                print >> f, template

            nginx_cmdline_config_file = os.path.join(nginx_dir, 'conf', 'commandline_utilities_http.conf')
            misc.run('touch {0}'.format(nginx_cmdline_config_file))
            # Reload nginx process, specifying the newly generated config file
            misc.run('{0} -c {1} -s reload'.format(
                os.path.join(nginx_dir, 'sbin', 'nginx'), nginx_config_file))
        else:
            log.warning("Cannot find nginx directory to reload nginx config")
