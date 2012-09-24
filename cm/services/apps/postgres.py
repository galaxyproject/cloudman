import commands, os, pwd, grp

from cm.services.apps import ApplicationService
from cm.util import paths
from cm.services import service_states
from cm.util import misc

import logging
log = logging.getLogger( 'cloudman' )

class PostgresService( ApplicationService ):

    def __init__(self, app):
        super(PostgresService, self).__init__(app)
        self.svc_type = "Postgres"
        self.psql_port = paths.C_PSQL_PORT
        self.reqs = {'Filesystem': 'galaxyData'}
        
    def start(self):
        self.state = service_states.STARTING
        self.manage_postgres(True)

    def remove(self):
        log.info("Removing '%s' service" % self.svc_type)
        self.state = service_states.SHUTTING_DOWN
        self.manage_postgres(False)
    
    def manage_postgres( self, to_be_started=True ):
        if self.app.TESTFLAG is True:
            log.debug( "Attempted to manage Postgres, but TESTFLAG is set." )
            return
        psql_data_dir = paths.P_PSQL_DIR
        # Make sure postgres is owner of its directory before any operations
        if os.path.exists(os.path.split(paths.P_PSQL_DIR)[0]):
            misc.run("%s --recursive postgres:postgres %s" % (paths.P_CHOWN, os.path.split(paths.P_PSQL_DIR)[0]), "Error changing ownership of just created directory", "Successfully set ownership of Postgres data directory")
        # Check on the status of PostgreSQL server
        self.status()
        if to_be_started and not self.state==service_states.RUNNING:
            to_be_configured = False

            # Check if 'psql_data_dir' exists first; it not, configure PostgreSQL
            if not os.path.exists( psql_data_dir ):
                log.debug("{0} dir does not exist; will be configuring Postgres".format(psql_data_dir))
                to_be_configured = True

            if to_be_configured:
                log.info( "Configuring PostgreSQL with a database for Galaxy..." )
                cont = True # Flag to indicate if previous operation completed successfully 
                # Make Galaxy database directory
                if os.path.exists(paths.P_GALAXY_DATA) and not os.path.exists(psql_data_dir):
                    cont = misc.run('mkdir -p %s' % psql_data_dir, "Error creating Galaxy database cluster dir", "Successfully created Galaxy database cluster dir")
                else:
                    log.error( "'%s' directory doesn't exist yet; will configure PostgreSQL later." % paths.P_GALAXY_DATA )
                    return False
                # Change ownership of just created directory
                if cont:
                    cont = misc.run( '%s -R postgres:postgres %s/pgsql' % ( paths.P_CHOWN, paths.P_GALAXY_DATA ), "Error changing ownership of just created directory", "Successfully changed ownership of just created directory" )
                # Initialize/configure database cluster
                if cont:
                    log.debug( "Initializing PostgreSQL database for Galaxy..." )
                    cont = misc.run( '%s - postgres -c "%s/initdb -D %s"' % (paths.P_SU, paths.P_PG_HOME, psql_data_dir), "Error initializing Galaxy database", "Successfully initialized Galaxy database")
                    if cont:
                        misc.replace_string('%s/postgresql.conf' % psql_data_dir, '#port = 5432', 'port = %s' % self.psql_port)
                        os.chown('%s/postgresql.conf' % psql_data_dir, pwd.getpwnam( "postgres" )[2], grp.getgrnam( "postgres" )[2] )
                # Start PostgreSQL server so a role for Galaxy user can be created
                if cont:
                    log.debug( "Starting PostgreSQL as part of the initial setup..." )
                    cont = misc.run( '%s - postgres -c "%s/pg_ctl -w -D %s -l /tmp/pgSQL.log -o \\\"-p %s\\\" start"' % (paths.P_SU, paths.P_PG_HOME, psql_data_dir, self.psql_port), "Error starting postgres server as part of the initial configuration", "Successfully started postgres server as part of the initial configuration." )
                # Create role for galaxy user
                if cont:
                    log.debug( "PostgreSQL started OK (log available at /tmp/pgSQL.log).")
                    log.debug( "Creating role for 'galaxy' user in PostgreSQL..." )
                    cont = misc.run('%s - postgres -c "%s/psql -p %s -c \\\"CREATE ROLE galaxy LOGIN CREATEDB\\\" "' % (paths.P_SU, paths.P_PG_HOME, self.psql_port), "Error creating role for 'galaxy' user", "Successfully created role for 'galaxy' user" )
                # Create database for Galaxy, as galaxy user
                if cont:
                    log.debug( "Creating PostgreSQL database as 'galaxy' user..." )
                    cont = misc.run('%s - galaxy -c "%s/createdb -p %s galaxy"' % (paths.P_SU, paths.P_PG_HOME, self.psql_port), "Error creating 'galaxy' database", "Successfully created 'galaxy' database")
                # Now create role and permissons for galaxyftp user on the created 'galaxy' database
                if cont: 
                    log.debug( "Creating role for 'galaxyftp' user in PostgreSQL..." )
                    cont = misc.run('%s - postgres -c "%s/psql -p %s -c \\\"CREATE ROLE galaxyftp LOGIN PASSWORD \'fu5yOj2sn\'\\\" "' % (paths.P_SU, paths.P_PG_HOME, self.psql_port), "Error creating role for 'galaxyftp' user", "Successfully created role for 'galaxyftp' user" )
                else:
                    log.error("Setting up Postgres did not go smoothly.")
                    self.state = service_states.ERROR
                    return False

            # Check on the status of PostgreSQL server
            self.status()
            if to_be_started and not self.state==service_states.RUNNING:
                # Start PostgreSQL database
                log.info( "Starting PostgreSQL..." )
                misc.run( '%s -R postgres:postgres %s' % (paths.P_CHOWN, paths.P_GALAXY_DATA+'/pgsql'), "Error changing owner of postgres data dir", "Successfully changed owner of postgres data dir" )
                if misc.run( '%s - postgres -c "%s/pg_ctl -w -D %s -l /tmp/pgSQL.log -o\\\"-p %s\\\" start"' % (paths.P_SU, paths.P_PG_HOME, psql_data_dir, self.psql_port), "Error starting PostgreSQL server", "Successfully started PostgreSQL server"):
                    self.status()
                    if self.state==service_states.RUNNING:
                        log.info( "Successfully started PostgreSQL." )
                    else:
                        log.warning("Successfully started PosgreSQL but did it start and is it accessible?")
            else:
                log.debug("PostgreSQL already running (%s, %s)" % (to_be_started, self.state))
        elif not to_be_started:
            # Stop PostgreSQL database
            log.info( "Stopping PostgreSQL..." )
            self.state = service_states.SHUTTING_DOWN
            if misc.run('%s - postgres -c "%s/pg_ctl -w -D %s -o\\\"-p %s\\\" stop"' % (paths.P_SU, paths.P_PG_HOME, psql_data_dir, self.psql_port), "Encountered problem while stopping PostgreSQL", "Successfully stopped PostgreSQL"):
                self.state = service_states.SHUT_DOWN
            else:
                self.state = service_states.ERROR
                return False
                
        return True
    
    def check_postgres(self):
        """Check if PostgreSQL server is running and if 'galaxy' database exists.
        
        :rtype: bool
        :return: True if the server is running and 'galaxy' database exists,
                 False otherwise.
        """
        # log.debug("\tChecking PostgreSQL")
        if self.state==service_states.SHUTTING_DOWN or \
           self.state==service_states.SHUT_DOWN:
            return None
        elif self._check_daemon('postgres'):
            # log.debug("\tPostgreSQL daemon running. Trying to connect and select tables.")
            dbs = commands.getoutput('%s - postgres -c "%s/psql -p %s -c \\\"SELECT datname FROM PG_DATABASE;\\\" "' % (paths.P_SU, paths.P_PG_HOME, self.psql_port))
            if dbs.find('galaxy') > -1:
                # log.debug("\tPostgreSQL daemon OK, 'galaxy' database exists.")
                return True
            else:
                log.warning("\tPostgreSQL daemon OK, 'galaxy' database does NOT exist: %s" % dbs)
                return False
        elif not os.path.exists( paths.P_PSQL_DIR ):
            log.warning("PostgreSQL data directory '%s' does not exist (yet?)" % paths.P_PSQL_DIR)
            # Assume this is because user data dir has not been setup yet,
            # mark service as not-attempted yet (i.e., status: None)
            return None
        else:
            log.error("\tPostgreSQL daemon NOT running.")
            return False
    
    def status(self):
        if self.state != service_states.SHUT_DOWN:
            if self.check_postgres():
                self.state = service_states.RUNNING
    
