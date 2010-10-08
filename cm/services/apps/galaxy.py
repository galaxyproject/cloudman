import os, urllib2, shutil, subprocess, pwd, grp
from datetime import datetime

from cm.services.apps import ApplicationService
from cm.services import service_states
from cm.util import paths
from cm.util import misc

import logging
log = logging.getLogger( 'cloudman' )


class GalaxyService( ApplicationService ):
    
    def __init__(self, app):
        super(GalaxyService, self).__init__(app)
        self.galaxy_home = paths.P_GALAXY_HOME
        self.svc_type = "Galaxy"
        self.configured = False # Indicates if the environment for running Galaxy has been configured
        self.reqs = {'Postgres': None,
                     'Filesystem': 'galaxyData',
                     'Filesystem': 'galaxyIndices',
                     'Filesystem': 'galaxyTools'}
    
    def start(self):
        # self.state = service_states.STARTING
        self.manage_galaxy(True)
        self.status()
    
    def remove(self):
        log.info("Removing '%s' service" % self.svc_type)
        self.state = service_states.SHUTTING_DOWN
        self.manage_galaxy(False)
    
    def manage_galaxy( self, to_be_started=True ):
        if self.app.TESTFLAG is True:
            log.debug( "Attempted to manage Galaxy, but TESTFLAG is set." )
            return
        os.putenv( "GALAXY_HOME", self.galaxy_home )
        os.putenv( "TEMP", '/mnt/galaxyData/tmp' )
        if to_be_started:
            self.status()
            if not self.configured:
                log.info( "Setting up Galaxy" )
                s3_conn = self.app.cloud_interface.get_s3_connection()
                if not os.path.exists(self.galaxy_home):
                    log.error("Galaxy application directory '%s' does not exist! Aborting." % self.galaxy_home)
                    log.debug("ls /mnt/: %s" % os.listdir('/mnt/'))
                    return False

                if not misc.get_file_from_bucket( s3_conn, self.app.ud['bucket_cluster'], 'universe_wsgi.ini.cloud', self.galaxy_home + '/universe_wsgi.ini' ):
                    log.debug("Did not get Galaxy configuration file from cluster bucket '%s'" % self.app.ud['bucket_cluster'])
                    log.debug("Trying to retrieve latest one (universe_wsgi.ini.cloud) from '%s' bucket..." % self.app.ud['bucket_default'])
                    misc.get_file_from_bucket( s3_conn, self.app.ud['bucket_default'], 'universe_wsgi.ini.cloud', self.galaxy_home + '/universe_wsgi.ini' )
                if not misc.get_file_from_bucket( s3_conn, self.app.ud['bucket_cluster'], 'tool_conf.xml.cloud', self.galaxy_home + '/tool_conf.xml' ):
                    log.debug("Did not get Galaxy tool configuration file from cluster bucket '%s'" % self.app.ud['bucket_cluster'])
                    log.debug("Trying to retrieve latest one (tool_conf.xml.cloud) from '%s' bucket..." % self.app.ud['bucket_default'])
                    misc.get_file_from_bucket( s3_conn, self.app.ud['bucket_default'], 'tool_conf.xml.cloud', self.galaxy_home + '/tool_conf.xml' )
                
                # Ensure the environment is setup for running Galaxy
                # This can also be setup on the tools snapshot and thus avoid these patches
                # try:
                #     subprocess.call( "sed 's/cd `dirname $0`/cd `dirname $0`; export TEMP=\/mnt\/galaxyData\/tmp/; export DRMAA_LIBRARY_PATH=/opt/sge/lib/lx24-amd64/libdrmaa.so.1.0' %s/run.sh > %s/run.sh.custom" % (self.galaxy_home, self.galaxy_home), shell=True )
                #     misc.run("cd %s; sed 's/pyhton/python -ES/g' run.sh.custom > run.sh" % self.galaxy_home, "Failed to adjust run.sh", "Successfully adjusted run.sh")
                #     # shutil.copy( self.galaxy_home + '/run.sh.custom', self.galaxy_home + '/run.sh' )
                #     os.chown( self.galaxy_home + '/run.sh', pwd.getpwnam( "galaxy" )[2], grp.getgrnam( "galaxy" )[2] )
                # except Exception, e:
                #     log.debug("Problem customizing Galaxy's run.sh: %s" % e)
                try:
                    misc.run("cd %s; sed 's/pyhton/python -ES/g' setup.sh > setup.sh.custom" % self.galaxy_home, "Failed to edit setup.sh", "Successfully adjusted setup.sh")
                    shutil.copy( self.galaxy_home + '/setup.sh.custom', self.galaxy_home + '/setup.sh' )
                    os.chown( self.galaxy_home + '/setup.sh', pwd.getpwnam( "galaxy" )[2], grp.getgrnam( "galaxy" )[2] )
                except Exception, e:
                    log.error("Error adjusting setup.sh: %s" % e)
                # subprocess.call( 'sed "s/#start_job_runners = pbs/start_job_runners = sge/" $GALAXY_HOME/universe_wsgi.ini > $GALAXY_HOME/universe_wsgi.ini.custom', shell=True )
                # shutil.move( self.galaxy_home + '/universe_wsgi.ini.custom', self.galaxy_home + '/universe_wsgi.ini' )
                # subprocess.call( 'sed "s/#default_cluster_job_runner = pbs:\/\/\//default_cluster_job_runner = sge:\/\/\//" $GALAXY_HOME/universe_wsgi.ini > $GALAXY_HOME/universe_wsgi.ini.custom', shell=True )
                # shutil.move( self.galaxy_home + '/universe_wsgi.ini.custom', self.galaxy_home + '/universe_wsgi.ini' )
                # Configure PATH in /etc/profile because otherwise some tools do not work
                with open('/etc/profile', 'a') as f:
                    f.write('export PATH=/mnt/galaxyTools/tools/bin:/mnt/galaxyTools/tools/pkg/fastx_toolkit_0.0.13:/mnt/galaxyTools/tools/pkg/bowtie-0.12.5:/mnt/galaxyTools/tools/pkg/samtools-0.1.7_x86_64-linux:/mnt/galaxyTools/tools/pkg/gnuplot-4.4.0/bin:/opt/PostgreSQL/8.4/bin:$PATH\n')
                os.chown(self.galaxy_home + '/universe_wsgi.ini', pwd.getpwnam("galaxy")[2], grp.getgrnam("galaxy")[2])
                self.configured = True
                
            if self.state != service_states.RUNNING:
                log.info( "Starting Galaxy..." )
                if not misc.run('%s - galaxy -c "export SGE_ROOT=%s; sh $GALAXY_HOME/run.sh --daemon"' % (paths.P_SU, paths.P_SGE_ROOT), "Error invoking Galaxy", "Successfully initiated Galaxy start."):
                    self.state = service_states.ERROR
            else:
                log.debug("Galaxy already running.")
        else:
            log.info( "Shutting down Galaxy..." )
            if misc.run('%s - galaxy -c "sh $GALAXY_HOME/run.sh --stop-daemon"' % paths.P_SU, "Error stopping Galaxy", "Successfully stopped Galaxy."):
                self.state = service_states.SHUT_DOWN
                subprocess.call( 'mv $GALAXY_HOME/paster.log $GALAXY_HOME/paster.log.%s' % datetime.utcnow().strftime('%H_%M'), shell=True )
    
    def status(self):
        """Check if Galaxy daemon is running and the UI is accessible."""
        if self._check_daemon('galaxy'):
            # log.debug("\tGalaxy daemon running. Checking if UI is accessible.")
            dns = "http://127.0.0.1:8080"
            try:
                urllib2.urlopen(dns)
                # log.debug("\tGalaxy daemon running and the UI is accessible.")
                self.state = service_states.RUNNING
            except:
                log.warning("\tGalaxy UI does not seem to be accessible.")
                self.state = service_states.STARTING
        # else:
        #     log.error("\tGalaxy daemon not running.")
        #     self.state = service_states.SHUT_DOWN
    
