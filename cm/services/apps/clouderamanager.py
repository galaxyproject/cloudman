import os
import time
import threading

from ansible.runner import Runner
from ansible.inventory import Inventory
from cm_api.api_client import ApiResource  # Cloudera Manager API

from cm.util import misc
import cm.util.paths as paths
from cm.services import ServiceRole
from cm.services import service_states
from cm.services.apps import ApplicationService

import logging
log = logging.getLogger('cloudman')


class ClouderaManagerService(ApplicationService):
    def __init__(self, app):
        super(ClouderaManagerService, self).__init__(app)
        self.svc_roles = [ServiceRole.CLOUDERA_MANAGER]
        self.name = ServiceRole.to_string(ServiceRole.CLOUDERA_MANAGER)
        self.dependencies = []
        self.db_pwd = misc.random_string_generator()
        # Indicate if the web server has been configured and started
        self.started = False
        self.port = 7180

    def start(self):
        """
        Start Cloudera Manager web server.
        """
        log.debug("Starting Cloudera Manager service")
        self.state = service_states.STARTING
        self.configure_db()
        self.start_webserver()

    def remove(self, synchronous=False):
        """
        Stop the Cloudera Manager web server.
        """
        log.info("Stopping Cloudera Manager service")
        super(ClouderaManagerService, self).remove(synchronous)
        self.state = service_states.SHUTTING_DOWN
        self.state = service_states.SHUT_DOWN

    def configure_db(self):
        """
        Add the necessary tables to the default PostgreSQL server running on the
        host and prepare the necessary roles and databases.
        """
        # Update psql settings
        pg_conf = paths.P_PG_CONF
        lif = ["listen_addresses = '*'",
               "shared_buffers = 256MB",
               "wal_buffers = 8MB",
               "checkpoint_segments = 16",
               "checkpoint_completion_target = 0.9"]
        for l in lif:
            log.debug("Updating PostgreSQL conf file {0} setting: {1}".format(pg_conf, l))
            regexp = ' '.join(l.split(' ')[:2])
            try:
                Runner(inventory=Inventory(['localhost']),
                       transport='local',
                       sudo=True,
                       sudo_user='postgres',
                       module_name="lineinfile",
                       module_args=('dest={0} backup=yes line="{1}" owner=postgres regexp="{2}"'
                                    .format(pg_conf, l, regexp))
                       ).run()
            except Exception, e:
                log.error("Exception updating psql conf {0}: {1}".format(l, e))
        # Restart psql
        misc.run("service postgresql restart")
        # Add required roles to the main Postgres server
        roles = ['scm', 'amon', 'rman', 'hive']
        for role in roles:
            log.debug("Adding PostgreSQL role {0} (with pwd: {1})".format(role,
                      self.db_pwd))
            try:
                Runner(inventory=Inventory(['localhost']),
                       transport='local',
                       sudo=True,
                       sudo_user='postgres',
                       module_name="postgresql_user",
                       module_args=("name={0} role_attr_flags=LOGIN password={1}"
                                    .format(role, self.db_pwd))
                       ).run()
            except Exception, e:
                log.error("Exception creating psql role {0}: {1}".format(role, e))
        # Create required databases
        databases = ['scm', 'amon', 'rman', 'metastore']
        for db in databases:
            owner = db
            if db == 'metastore':
                owner = 'hive'
            log.debug("Creating database {0} with owner {1}".format(db, owner))
            try:
                r = Runner(inventory=Inventory(['localhost']),
                           transport='local',
                           sudo=True,
                           sudo_user='postgres',
                           module_name="postgresql_db",
                           module_args=("name={0} owner={1} encoding='UTF-8'"
                                    .format(db, owner))
                           ).run()
                if r.get('contacted', {}).get('localhost', {}).get('failed'):
                    msg = r.get('contacted', {}).get('localhost', {}).get('msg', 'N/A')
                    log.error("Creating the database filed: {0}".format(msg))
            except Exception, e:
                log.error("Exception creating database {0}: {1}".format(db, e))
        # Alter one of the DBs
        sql_cmds = [
            "ALTER DATABASE metastore SET standard_conforming_strings = off"
        ]
        for sql_cmd in sql_cmds:
            misc.run_psql_command(sql_cmd, 'postgres', self.app.path_resolver.psql_cmd, 5432)
        # Prepare the scm database
        cmd = ("/usr/share/cmf/schema/scm_prepare_database.sh -h localhost postgresql scm scm {0}"
               .format(self.db_pwd))
        misc.run(cmd)
        # Make sure we have a clean DB env
        f = '/etc/cloudera-scm-server/db.mgmt.properties'
        if os.path.exists(f):
            log.debug("Deleting file {0}".format(f))
            os.remove(f)

    def start_webserver(self):
        """
        Start the Cloudera Manager web server (defaults to port 7180)
        """
        def _disable_referer_check():
            log.debug("Disabling refered check")
            api = ApiResource("127.0.0.1", username="admin", password="admin")
            cm = api.get_cloudera_manager()
            config = {u'REFERER_CHECK': u'false'}
            done = False
            self.state = service_states.CONFIGURING
            while not done:
                try:
                    cm.update_config(config)
                    log.debug("Succesfully disabled referer check")
                    done = True
                    self.started = True
                except Exception:
                    log.debug("Still have not disabled referer check...")
                    time.sleep(15)

        if misc.run("service cloudera-scm-server start"):
            # This method may take a while so spawn it off
            threading.Thread(target=_disable_referer_check).start()

    def status(self):
        """
        Check and update the status of the service.
        """
        if self.state == service_states.UNSTARTED or \
           self.state == service_states.STARTING or \
           self.state == service_states.SHUTTING_DOWN or \
           self.state == service_states.SHUT_DOWN or \
           self.state == service_states.WAITING_FOR_USER_ACTION:
            pass
        elif 'running' not in misc.getoutput('service cloudera-scm-server status',
           quiet=True):
            log.error("Cloudera server not running!")
            self.state = service_states.ERROR
        elif not self.started:
            pass
        else:
            self.state = service_states.RUNNING
