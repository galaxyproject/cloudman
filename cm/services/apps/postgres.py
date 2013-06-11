import commands
import os
import pwd
import grp

from cm.services.apps import ApplicationService
from cm.util import paths
from cm.services import service_states
from cm.services import ServiceRole
from cm.services import ServiceDependency
from cm.util import misc

import logging
log = logging.getLogger('cloudman')


class PostgresService(ApplicationService):

    def __init__(self, app):
        super(PostgresService, self).__init__(app)
        self.name = ServiceRole.to_string(ServiceRole.GALAXY_POSTGRES)
        self.svc_roles = [ServiceRole.GALAXY_POSTGRES]
        self.psql_port = paths.C_PSQL_PORT
        self.dependencies = [ServiceDependency(self, ServiceRole.GALAXY_DATA),
                     ServiceDependency(self, ServiceRole.MIGRATION)]

    def start(self):
        self.state = service_states.STARTING
        self.manage_postgres(True)

    def remove(self, synchronous=False):
        log.info("Removing '%s' service" % self.name)
        super(PostgresService, self).remove(synchronous)
        # Stop only if currently running
        if self.state == service_states.RUNNING:
            self.state = service_states.SHUTTING_DOWN
            self.manage_postgres(False)
        elif self.state == service_states.UNSTARTED:
            self.state = service_states.SHUT_DOWN
        else:
            log.debug("{0} service is not running (state: {1}) so not stopping it."
                      .format(self.name, self.state))
        # TODO: Should we completely remove self?

    def manage_postgres(self, to_be_started=True):
        if self.app.TESTFLAG is True:
            log.debug("Attempted to manage Postgres, but TESTFLAG is set.")
            return
        psql_data_dir = self.app.path_resolver.psql_dir
        # Make sure postgres is owner of its directory before any operations
        if os.path.exists(self.app.path_resolver.psql_dir):
            misc.run(
                "%s --recursive postgres:postgres %s" % (
                    paths.P_CHOWN, psql_data_dir),
                "Error setting ownership of Postgres data directory %s" % psql_data_dir,
                "Successfully set ownership of Postgres data directory %s" % psql_data_dir)
        # Check on the status of PostgreSQL server
        self.status()
        if to_be_started and not self.state == service_states.RUNNING:
            to_be_configured = False

            # Check if 'psql_data_dir' exists first; it not, configure
            # PostgreSQL
            if not os.path.exists(psql_data_dir):
                log.debug("{0} dir does not exist; will be configuring Postgres".format(
                    psql_data_dir))
                to_be_configured = True

            if to_be_configured:
                log.debug(
                    "Configuring PostgreSQL with a database for Galaxy...")
                cont = True  # Flag to indicate if previous operation completed successfully
                # Make Galaxy database directory
                if os.path.exists(self.app.path_resolver.galaxy_data) and not os.path.exists(psql_data_dir):
                    cont = misc.run('mkdir -p %s' % psql_data_dir,
                                    "Error creating Galaxy database cluster dir", "Successfully created Galaxy database cluster dir")
                else:
                    log.error("'%s' directory doesn't exist yet; will configure PostgreSQL later." %
                              self.app.path_resolver.galaxy_data)
                    return False
                # Change ownership of just created directory
                if cont:
                    cont = misc.run(
                        '%s -R postgres:postgres %s' % (
                            paths.P_CHOWN, psql_data_dir),
                        "Error changing ownership of just created directory", "Successfully changed ownership of just created directory")
                # Initialize/configure database cluster
                if cont:
                    log.debug(
                        "Initializing PostgreSQL database for Galaxy...")
                    cont = misc.run('%s - postgres -c "%s/initdb -D %s"' % (
                        paths.P_SU, self.app.path_resolver.pg_home, psql_data_dir), "Error initializing Galaxy database", "Successfully initialized Galaxy database")
                    if cont:
                        misc.replace_string(
                            '%s/postgresql.conf' % psql_data_dir,
                            '#port = 5432', 'port = %s' % self.psql_port)
                        os.chown('%s/postgresql.conf' % psql_data_dir, pwd.getpwnam(
                            "postgres")[2], grp.getgrnam("postgres")[2])
                # Start PostgreSQL server so a role for Galaxy user can be
                # created
                if cont:
                    log.debug(
                        "Starting PostgreSQL as part of the initial setup...")
                    cont = misc.run('%s - postgres -c "%s/pg_ctl -w -D %s -l /tmp/pgSQL.log -o \\\"-p %s\\\" start"' % (
                        paths.P_SU, self.app.path_resolver.pg_home, psql_data_dir, self.psql_port), "Error starting postgres server as part of the initial configuration", "Successfully started postgres server as part of the initial configuration.")
                # Create role for galaxy user
                if cont:
                    log.debug(
                        "PostgreSQL started OK (log available at /tmp/pgSQL.log).")
                    log.debug(
                        "Creating role for 'galaxy' user in PostgreSQL...")
                    cont = misc.run(
                        '%s - postgres -c "%s/psql -p %s -c \\\"CREATE ROLE galaxy LOGIN CREATEDB\\\" "' % (
                            paths.P_SU, self.app.path_resolver.pg_home, self.psql_port),
                        "Error creating role for 'galaxy' user", "Successfully created role for 'galaxy' user")
                # Create database for Galaxy, as galaxy user
                if cont:
                    log.debug(
                        "Creating PostgreSQL database as 'galaxy' user...")
                    cont = misc.run('%s - galaxy -c "%s/createdb -p %s galaxy"' % (
                        paths.P_SU, self.app.path_resolver.pg_home, self.psql_port), "Error creating 'galaxy' database", "Successfully created 'galaxy' database")
                # Now create role and permissons for galaxyftp user on the
                # created 'galaxy' database
                if cont:
                    log.debug(
                        "Creating role for 'galaxyftp' user in PostgreSQL...")
                    cont = misc.run(
                        '%s - postgres -c "%s/psql -p %s -c \\\"CREATE ROLE galaxyftp LOGIN PASSWORD \'fu5yOj2sn\'\\\" "' % (
                            paths.P_SU, self.app.path_resolver.pg_home, self.psql_port),
                        "Error creating role for 'galaxyftp' user", "Successfully created role for 'galaxyftp' user")
                else:
                    log.error("Setting up Postgres did not go smoothly.")
                    self.state = service_states.ERROR
                    return False

            # Check on the status of PostgreSQL server
            self.status()
            if to_be_started and not self.state == service_states.RUNNING:
                # Start PostgreSQL database
                log.debug("Starting PostgreSQL...")
                if misc.run('%s - postgres -c "%s/pg_ctl -w -D %s -l /tmp/pgSQL.log -o\\\"-p %s\\\" start"' %
                           (paths.P_SU,
                            self.app.path_resolver.pg_home, psql_data_dir, self.psql_port),
                            "Error starting PostgreSQL server in %s" % psql_data_dir,
                            "Successfully started PostgreSQL server in %s" % psql_data_dir):
                    self.status()
            else:
                log.debug("PostgreSQL already running (%s, %s)" % (
                    to_be_started, self.state))
        elif not to_be_started:
            # Stop PostgreSQL database
            log.info("Stopping PostgreSQL...")
            self.state = service_states.SHUTTING_DOWN
            if misc.run('%s - postgres -c "%s/pg_ctl -w -D %s -o\\\"-p %s\\\" stop"'
               % (paths.P_SU, self.app.path_resolver.pg_home, psql_data_dir, self.psql_port)):
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
        if self.state == service_states.SHUTTING_DOWN or \
                self.state == service_states.SHUT_DOWN:
            return None
        elif self._check_daemon('postgres'):
            # log.debug("\tPostgreSQL daemon running. Trying to connect and
            # select tables.")
            dbs = commands.getoutput(
                '%s - postgres -c "%s/psql -p %s -c \\\"SELECT datname FROM PG_DATABASE;\\\" "' % (paths.P_SU,
                                                                                                   self.app.path_resolver.pg_home, self.psql_port))
            if dbs.find('galaxy') > -1:
                # log.debug("\tPostgreSQL daemon OK, 'galaxy' database
                # exists.")
                return True
            else:
                log.warning(
                    "PostgreSQL daemon OK, 'galaxy' database does NOT exist: %s" % dbs)
                return False
        elif not os.path.exists(self.app.path_resolver.psql_dir):
            log.warning("PostgreSQL data directory '%s' does not exist (yet?)" %
                        self.app.path_resolver.psql_dir)
            # Assume this is because user data dir has not been setup yet,
            # mark service as not-attempted yet (i.e., status: None)
            return None
        else:
            log.error("PostgreSQL daemon NOT running.")
            return False

    def status(self):
        if self.state != service_states.SHUT_DOWN:
            if self.check_postgres():
                self.state = service_states.RUNNING
