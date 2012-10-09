import os, urllib2, shutil, subprocess, pwd, grp
from datetime import datetime

from cm.services.apps import ApplicationService
from cm.services import service_states
from cm.util import paths
from cm.util import misc

import logging
log = logging.getLogger('cloudman')


class GalaxyService(ApplicationService):
    
    def __init__(self, app):
        super(GalaxyService, self).__init__(app)
        self.galaxy_home = paths.P_GALAXY_HOME
        log.debug("Using Galaxy from '{0}'".format(self.galaxy_home))
        self.svc_type = "Galaxy"
        self.configured = False # Indicates if the environment for running Galaxy has been configured
        # Environment variables to set before executing galaxy's run.sh
        self.env_vars = {"SGE_ROOT": paths.P_SGE_ROOT}
        self.reqs = {'Postgres': None,
                     'Filesystem': 'galaxyData',
                     'Filesystem': 'galaxyIndices',
                     'Filesystem': 'galaxyTools'}
    
    def start(self):
        self.manage_galaxy(True)
        self.status()
    
    def remove(self):
        log.info("Removing '%s' service" % self.svc_type)
        self.state = service_states.SHUTTING_DOWN
        self.last_state_change_time = datetime.utcnow()
        self.manage_galaxy(False)
    
    def restart(self):
        log.info('Restarting Galaxy service')
        self.remove()
        self.status()
        self.start()
    
    def manage_galaxy( self, to_be_started=True ):
        if self.app.TESTFLAG is True and self.app.LOCALFLAG is False:
            log.debug( "Attempted to manage Galaxy, but TESTFLAG is set." )
            return
        os.putenv( "GALAXY_HOME", self.galaxy_home )
        os.putenv( "TEMP", '/mnt/galaxyData/tmp' )
        # Setup configuration directory for galaxy if galaxy_conf_dir specified 
        # in user-data.
        if self.has_config_dir():
            self.setup_config_dir()
        if to_be_started:
            self.status()
            if not self.configured:
                log.info( "Setting up Galaxy application" )
                s3_conn = None
                if self.app.use_object_store:
                    s3_conn = self.app.cloud_interface.get_s3_connection()
                if not os.path.exists(self.galaxy_home):
                    log.error("Galaxy application directory '%s' does not exist! Aborting." % self.galaxy_home)
                    log.debug("ls /mnt/: %s" % os.listdir('/mnt/'))
                    self.state = service_states.ERROR
                    self.last_state_change_time = datetime.utcnow()
                    return False
                # Retrieve config files from a persistent data repository (i.e., S3)
                if not misc.get_file_from_bucket( s3_conn, self.app.ud['bucket_cluster'], 'universe_wsgi.ini.cloud', self.galaxy_home + '/universe_wsgi.ini' ):
                    log.debug("Did not get Galaxy configuration file from cluster bucket '%s'" % self.app.ud['bucket_cluster'])
                    log.debug("Trying to retrieve latest one (universe_wsgi.ini.cloud) from '%s' bucket..." % self.app.ud['bucket_default'])
                    misc.get_file_from_bucket( s3_conn, self.app.ud['bucket_default'], 'universe_wsgi.ini.cloud', self.galaxy_home + '/universe_wsgi.ini' )
                self.add_galaxy_admin_users()
                self.add_dynamic_galaxy_options()
                # TODO: Pick better name
                if self.app.ud.get("configure_multiple_galaxy_processes", False):
                    self.configure_multiple_galaxy_processes()
                    self.extra_daemon_args = ""
                else:
                    # Instead of sticking with default paster.pid and paster.log, explictly
                    # set pid and log file to main.pid and main.log to bring single process
                    # case inline with defaults for for multiple process case (i.e. when 
                    # GALAXY_RUN_ALL is set and multiple servers are defined).
                    self.extra_daemon_args = "--pid-file=main.pid --log-file=main.log"
                universe_wsgi_path = os.path.join(self.galaxy_home, "universe_wsgi.ini")
                self._attempt_chown_galaxy_if_exists(universe_wsgi_path)
                if not misc.get_file_from_bucket( s3_conn, self.app.ud['bucket_cluster'], 'tool_conf.xml.cloud', self.galaxy_home + '/tool_conf.xml' ):
                    log.debug("Did not get Galaxy tool configuration file from cluster bucket '%s'" % self.app.ud['bucket_cluster'])
                    log.debug("Trying to retrieve latest one (tool_conf.xml.cloud) from '%s' bucket..." % self.app.ud['bucket_default'])
                    misc.get_file_from_bucket( s3_conn, self.app.ud['bucket_default'], 'tool_conf.xml.cloud', self.galaxy_home + '/tool_conf.xml' )
                tool_conf_path = os.path.join(self.galaxy_home, "tool_conf.xml")
                self._attempt_chown_galaxy_if_exists(tool_conf_path)
                if not misc.get_file_from_bucket( s3_conn, self.app.ud['bucket_cluster'], 'tool_data_table_conf.xml.cloud', self.galaxy_home + '/tool_data_table_conf.xml.cloud' ):
                    log.debug("Did not get Galaxy tool_data_table_conf.xml.cloud file from cluster bucket '%s'" % self.app.ud['bucket_cluster'])
                    log.debug("Trying to retrieve latest one (tool_data_table_conf.xml.cloud) from '%s' bucket..." % self.app.ud['bucket_default'])
                    misc.get_file_from_bucket( s3_conn, self.app.ud['bucket_default'], 'tool_data_table_conf.xml.cloud', self.galaxy_home + '/tool_data_table_conf.xml.cloud' )
                try:
                    tool_data_table_conf_path = os.path.join(self.galaxy_home, 'tool_data_table_conf.xml.cloud')
                    if os.path.exists(tool_data_table_conf_path):
                        shutil.copy(tool_data_table_conf_path, '%s/tool_data_table_conf.xml' % self.galaxy_home)
                        self._attempt_chown_galaxy(self.galaxy_home + '/tool_data_table_conf.xml')
                except:
                    pass
                # 
                #===============================================================
                
                # Make sure the temporary job_working_directory exists on user data volume (defined in universe_wsgi.ini.cloud)
                if not os.path.exists('%s/tmp/job_working_directory' % paths.P_GALAXY_DATA):
                    os.makedirs('%s/tmp/job_working_directory/' % paths.P_GALAXY_DATA)
                self._attempt_chown_galaxy('%s/tmp/job_working_directory/' % paths.P_GALAXY_DATA)
                # Setup environemnt for the FTP server and start it
                if not os.path.exists('%s/tmp/ftp' % paths.P_GALAXY_DATA):
                    os.makedirs('%s/tmp/ftp' % paths.P_GALAXY_DATA)
                misc.run('/etc/init.d/proftpd start', 'Failed to start FTP server', "Started FTP server")
                # TEMPORARY ONLY - UNTIL SAMTOOLS WRAPPER IS CONVERTED TO USE DATA TABLES
                if os.path.exists('/mnt/galaxyIndices/locfiles/sam_fa_indices.loc'):
                    shutil.copy('/mnt/galaxyIndices/locfiles/sam_fa_indices.loc', '%s/tool-data/sam_fa_indices.loc' % paths.P_GALAXY_HOME)
                # Ensure the environment is setup for running Galaxy
                # This can also be setup on the tools snapshot and thus avoid these patches
                # try:
                #     subprocess.call( "sed 's/cd `dirname $0`/cd `dirname $0`; export TEMP=\/mnt\/galaxyData\/tmp/; export DRMAA_LIBRARY_PATH=/opt/sge/lib/lx24-amd64/libdrmaa.so.1.0' %s/run.sh > %s/run.sh.custom" % (self.galaxy_home, self.galaxy_home), shell=True )
                #     misc.run("cd %s; sed 's/pyhton/python -ES/g' run.sh.custom > run.sh" % self.galaxy_home, "Failed to adjust run.sh", "Successfully adjusted run.sh")
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
                # os.chown(self.galaxy_home + '/universe_wsgi.ini', pwd.getpwnam("galaxy")[2], grp.getgrnam("galaxy")[2])
                self.configured = True
            if self.state != service_states.RUNNING:
                log.info( "Starting Galaxy..." )
                # Make sure admin users get added
                self.add_galaxy_admin_users()
                start_command = self.galaxy_run_command("%s --daemon" % self.extra_daemon_args)
                log.debug(start_command)
                if not misc.run(start_command, "Error invoking Galaxy", "Successfully initiated Galaxy start."):
                    self.state = service_states.ERROR
                    self.last_state_change_time = datetime.utcnow()
            else:
                log.debug("Galaxy already running.")
        else:
            log.info( "Shutting down Galaxy..." )
            if misc.run(self.galaxy_run_command("--stop-daemon"), "Error stopping Galaxy", "Successfully stopped Galaxy."):
                self.state = service_states.SHUT_DOWN
                self.last_state_change_time = datetime.utcnow()
                # Move all log files
                subprocess.call("bash -c 'for f in $GALAXY_HOME/*.log; do mv \"$f\" \"$f.%s\"; done'" % datetime.utcnow().strftime('%H_%M'), shell=True)

    def galaxy_run_command(self, args):
        env_exports = "; ".join(["export %s='%s'" % (key, value) for key, value in self.env_vars.iteritems()])
        run_command = '%s - galaxy -c "%s; sh $GALAXY_HOME/run.sh %s"' % (paths.P_SU, env_exports, args)
        return run_command

    def status(self):
        """Check if Galaxy daemon is running and the UI is accessible."""
        old_state = self.state
        if self._check_daemon('galaxy'):
            # log.debug("\tGalaxy daemon running. Checking if UI is accessible.")
            if self._is_galaxy_running():
                self.state = service_states.RUNNING
            else:
                log.debug("\tGalaxy UI does not seem to be accessible.")
                self.state = service_states.STARTING
        elif self.state==service_states.SHUTTING_DOWN or \
             self.state==service_states.SHUT_DOWN or \
             self.state==service_states.UNSTARTED or \
             self.state==service_states.WAITING_FOR_USER_ACTION:
             # self.state==service_states.STARTING:
            pass
        else:
            if self.state == service_states.STARTING and \
                (datetime.utcnow() - self.last_state_change_time).seconds < 60:
                # Give Galaxy a minutes to start; otherwise, because
                # the monitor is running as a separate thread, it often happens
                # that the .pid file is not yet created after the Galaxy process
                # has been started so the monitor thread erroneously reports
                # as if starting the Galaxy proces has failed.
                pass
            else:
                log.error("\tGalaxy daemon not running.")
                self.state = service_states.ERROR
        if old_state != self.state:
            log.info("Galaxy service state changed from '%s' to '%s'" % (old_state, self.state))
            self.last_state_change_time = datetime.utcnow()
            if self.state == service_states.RUNNING:
                log.debug("Granting SELECT permission to galaxyftp user on 'galaxy' database")
                misc.run('%s - postgres -c "%s/psql -p %s galaxy -c \\\"GRANT SELECT ON galaxy_user TO galaxyftp\\\" "' % (paths.P_SU, paths.P_PG_HOME, paths.C_PSQL_PORT), "Error granting SELECT grant to 'galaxyftp' user", "Successfully added SELECT grant to 'galaxyftp' user" )
            # Force cluster configuration state update on status change
            self.app.manager.console_monitor.store_cluster_config()

    def _is_galaxy_running(self):
        dns = "http://127.0.0.1:8080"
        running_error_codes = [403]  # Error codes that indicate Galaxy is running
        try:
            urllib2.urlopen(dns)
            return True
        except urllib2.HTTPError, e:
            return e.code in running_error_codes
        except:
            return False

    def has_config_dir(self):
        return self.app.ud.get("galaxy_conf_dir", None) is not None

    def setup_config_dir(self):
        conf_dir = self.get_galaxy_conf_dir()
        # If config dir does not exist, create it and put default
        # galaxy properties in with low priority.
        if not os.path.exists(conf_dir):
            os.makedirs(conf_dir)
            defaults_source = os.path.join(self.galaxy_home, "universe_wsgi.ini.sample")
            defaults_destination = os.path.join(conf_dir, "010_universe_wsgi_defaults.ini")
            os.symlink(defaults_source, defaults_destination)
        # This will ensure galaxy's run.sh file picks up the config dir.
        self.env_vars["GALAXY_UNIVERSE_CONFIG_DIR"] = conf_dir

    def get_galaxy_conf_dir(self):
        return self.app.ud.get("galaxy_conf_dir", None)

    def configure_multiple_galaxy_processes(self):
        if not self.has_config_dir():
            log.warn("Must specify a galaxy configuration directory (via galaxy_conf_dir) in order to create a multiple Galaxy processes.")
            return
        web_thread_count = int(self.app.ud.get("web_thread_count", 1))
        handler_thread_count = int(self.app.ud.get("handler_thread_count", 1))
        [self.add_server_process(i, "web", 8080) for i in range(web_thread_count)]
        handlers = [self.add_server_process(i, "handler", 9080) for i in range(handler_thread_count)]
        self.add_server_process(0, "manager", 8079)
        self.add_universe_option("job_manager", "manager0")
        self.add_universe_option("job_handlers", ",".join(handlers))
        self.env_vars["GALAXY_RUN_ALL"] = "TRUE"

        # HACK: Galaxy has a known problem when starting from a fresh configuration
        # in multiple process mode. Each process attempts to create the same directories
        # and one or more processes can fail to start because it "failed" to create
        # said directories (because another process created them first). This hack staggers
        # the process starts in an attempt to circumvent this problem.
        patch_run_sh_command = "sudo sed -i -e \"s/server.log \\$\\@$/\\0; sleep 10/\" %s/run.sh" % self.galaxy_home
        misc.run(patch_run_sh_command)

    def add_server_process(self, index, prefix, initial_port):
        port = initial_port + index
        server_options = {"use": "egg:Paste#http",
                          "port": port,
                          "use_threadpool": True,
                          "threadpool_workers": self.app.ud.get("threadpool_workers", "7")
                          }
        server_name = "%s%d" % (prefix, index)
        if port == 8080:
            # Special case, server on port 8080 must be called main unless we want
            # to start deleting chunks of universe_wsgi.ini.
            server_name = "main"
        self.add_universe_options(server_options, "server_%s" % server_name, section="server:%s" % server_name)
        return server_name

    def add_universe_option(self, name, value, section="app:main"):
        options = {name: value}
        self.add_universe_options(options, name, section)

    def add_universe_options(self, options, description, section="app:main"):
        prefix = self.app.ud.get("option_priority", "400")
        conf_dir = self.get_galaxy_conf_dir()
        conf_file_name = "%s_cloudman_override_%s.ini" % (prefix, description)
        conf_file = os.path.join(conf_dir, conf_file_name)
        props_str = "\n".join(["%s=%s" % (k, v) for k, v in options.iteritems()])
        open(conf_file, "w").write("[%s]\n%s" % (section, props_str))

    def add_dynamic_galaxy_options(self):
        if not self.has_config_dir():
            return False
        dynamic_option_types = {"galaxy_universe_": "app:main",
                                "galaxy_tool_runner_": "galaxy:tool_runners",
                                }
        for option_prefix, section in dynamic_option_types.iteritems():
            for key, value in self.app.ud.iteritems():
                if key.startswith(option_prefix):
                    key = key[len(option_prefix):]
                    self.add_universe_option(key, value, section)

    def add_galaxy_admin_users(self, admins_list=[]):
        """ Galaxy admin users can now be added by providing them in user data
            (see below) or by calling this method and providing a user list.
            YAML format for user data for providing admin users
            (note that these users will still have to manually register on the given cloud instance):
            admin_users:
             - user@example.com
             - user2@anotherexample.edu """
        for admin in self.app.ud.get('admin_users', []):
            if admin not in admins_list:
                    admins_list.append(admin)
        if len(admins_list) == 0:
            return False
        log.info('Adding Galaxy admin users: %s' % admins_list)
        if self.has_config_dir():
            self.add_universe_option("admin_users", ",".join(admins_list))
        else:
            edited = False
            config_file_path = os.path.join(self.galaxy_home, 'universe_wsgi.ini')
            new_config_file_path = os.path.join(self.galaxy_home, 'universe_wsgi.ini.new')
            with open(config_file_path, 'r') as f:
                config_file = f.readlines()
            new_config_file = open(new_config_file_path, 'w')
            for line in config_file:
                # Add all of the users in admins_list if no admin users exist
                if '#admin_users = None' in line:
                    line = line.replace('#admin_users = None', 'admin_users = %s' % ', '\
                        .join(str(a) for a in admins_list))
                    edited = True
                # Add only admin users that don't already exist in the admin user list
                if not edited and 'admin_users' in line:
                    if line.endswith('\n'):
                        line = line.rstrip('\n') + ', '
                    for admin in admins_list:
                        if admin not in line:
                            line += "%s, " % admin
                    if line.endswith(', '):
                        line = line[:-2] + '\n'  # remove trailing space and comma and add newline
                    edited = True
                new_config_file.write(line)
            new_config_file.close()
            shutil.move(new_config_file_path, config_file_path)
            # Change the owner of the file to galaxy user
            self._attempt_chown_galaxy(config_file_path)

    def _attempt_chown_galaxy_if_exists(self, path):
        if os.path.exists(path):
            self._attempt_chown_galaxy(path)

    def _attempt_chown_galaxy(self, path):
        try:
            galaxy_uid = pwd.getpwnam("galaxy")[2]
            galaxy_gid = grp.getgrnam("galaxy")[2]
            os.chown(path, galaxy_uid, galaxy_gid)
        except OSError:
            misc.run("chown galaxy:galaxy '%s'" % path)
