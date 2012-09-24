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
                #     # shutil.copy( self.galaxy_home + '/run.sh.custom', self.galaxy_home + '/run.sh' )
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
                log.debug('%s - galaxy -c "export SGE_ROOT=%s; sh $GALAXY_HOME/run.sh --daemon"' % (paths.P_SU, paths.P_SGE_ROOT))
                if not misc.run('%s - galaxy -c "export SGE_ROOT=%s; sh $GALAXY_HOME/run.sh --daemon"' % (paths.P_SU, paths.P_SGE_ROOT), "Error invoking Galaxy", "Successfully initiated Galaxy start."):
                    self.state = service_states.ERROR
                    self.last_state_change_time = datetime.utcnow()
            else:
                log.debug("Galaxy already running.")
        else:
            log.info( "Shutting down Galaxy..." )
            if misc.run('%s - galaxy -c "sh $GALAXY_HOME/run.sh --stop-daemon"' % paths.P_SU, "Error stopping Galaxy", "Successfully stopped Galaxy."):
                self.state = service_states.SHUT_DOWN
                self.last_state_change_time = datetime.utcnow()
                subprocess.call( 'mv $GALAXY_HOME/paster.log $GALAXY_HOME/paster.log.%s' % datetime.utcnow().strftime('%H_%M'), shell=True )
    
    def status(self):
        """Check if Galaxy daemon is running and the UI is accessible."""
        old_state = self.state
        if self._check_daemon('galaxy'):
            # log.debug("\tGalaxy daemon running. Checking if UI is accessible.")
            dns = "http://127.0.0.1:8080"
            try:
                urllib2.urlopen(dns)
                # log.debug("\tGalaxy daemon running and the UI is accessible.")
                self.state = service_states.RUNNING
            except:
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

    def has_config_dir(self):
        return self.app.ud.get("galaxy_conf_dir", None) is not None

    def add_universe_option(self, name, value, section="[app:main]"):
        prefix = self.app.ud.get("option_priority", "400")
        conf_dir = self.app.ud["galaxy_conf_dir"]
        conf_file_name = "%s_cloudman_override_%s.ini" % (prefix, name)
        conf_file = os.path.join(conf_dir, conf_file_name)
        open(conf_file, "w").write("[%s]\n%s=%s" % (section, name, value))

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
