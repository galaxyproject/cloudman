import os
import time
import threading
# import subprocess
import socket
# import re

from ansible.runner import Runner
from ansible.inventory import Inventory
from cm_api.api_client import ApiResource  # Cloudera Manager API
# from cm_api.endpoints.clusters import ApiCluster
# from cm_api.endpoints.clusters import create_cluster
# from cm_api.endpoints.parcels import ApiParcel
from cm_api.endpoints.parcels import get_parcel
# from cm_api.endpoints.cms import ClouderaManager
from cm_api.endpoints.services import ApiServiceSetupInfo
# from cm_api.endpoints.services import ApiService, create_service
# from cm_api.endpoints.types import ApiCommand, ApiRoleConfigGroupRef
# from cm_api.endpoints.role_config_groups import get_role_config_group
# from cm_api.endpoints.role_config_groups import ApiRoleConfigGroup
# from cm_api.endpoints.roles import ApiRole
from time import sleep

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
        self.cm_port = 7180

        # Default cluster configuration
        # TODO - read local cloud host name!
        self.cm_host = socket.gethostname()
        self.host_list = [self.cm_host]
        self.cluster_name = "Cluster 1"
        self.cdh_version = "CDH5"
        self.cdh_version_number = "5"
        self.cm_username = "admin"
        self.cm_password = "admin"
        self.cm_service_name = "ManagementService"
        self.host_username = "ubuntu"
        self.host_password = self.app.config.get('password')
        self.cm_repo_url = None
        self.service_types_and_names = {
            "HDFS": "HDFS",
            "YARN": "YARN",
            "ZOOKEEPER": "ZooKeeper"
        }

    @property
    def cm_api_resource(self):
        return ApiResource(self.cm_host, self.cm_port,
                           self.cm_username, self.cm_password)

    @property
    def cm_manager(self):
        return self.cm_api_resource.get_cloudera_manager()

    def start(self):
        """
        Start Cloudera Manager web server.
        """
        log.debug("Starting Cloudera Manager service")
        self.state = service_states.STARTING
        misc.run('/sbin/sysctl vm.swappiness=0')  # Recommended by Cloudera
        threading.Thread(target=self.__start).start()

    def __start(self):
        """
        Start all the service components.

        Intended to be called in a dedicated thread.
        """
        try:
            self.configure_db()
            self.start_webserver()
            self.create_default_cluster()
            self.setup_cluster()
        except Exception, exc:
            log.error("Exception creating a cluster: {0}".format(exc))

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
            config = {u'REFERER_CHECK': u'false'}
            done = False
            self.state = service_states.CONFIGURING
            while not done:
                try:
                    self.cm_manager.update_config(config)
                    log.debug("Succesfully disabled referer check")
                    done = True
                    self.started = True
                except Exception:
                    log.debug("Still have not disabled referer check... ")
                    time.sleep(5)

        if misc.run("service cloudera-scm-server start"):
            _disable_referer_check()

    def create_default_cluster(self):
        """
        Create a default cluster and Cloudera Manager Service on master host
        """
        log.info("Creating Cloudera cluster: '{0}'. Please wait...".format(self.cluster_name))

        # Create new admin user (use 'ubuntu' and password provided at cloudman startup)
        # and delete the default 'admin' user in Cloudera Manager Service
        self.cm_api_resource.create_user(self.host_username, self.host_password, ['ROLE_ADMIN'])
        old_admin = self.cm_username
        self.cm_username = self.host_username
        self.cm_password = self.host_password
        log.debug("Deleting the default user 'admin'...")
        self.cm_api_resource.delete_user(old_admin)

        self.cm_host = socket.gethostname()
        self.host_list = [self.cm_host]

        # create the management service
        # first check if mamagement service already exists
        service_setup = ApiServiceSetupInfo(name=self.cm_service_name, type="MGMT")
        self.cm_manager.create_mgmt_service(service_setup)

        # install hosts on this CM instance
        cmd = self.cm_manager.host_install(self.host_username, self.host_list,
                                           password=self.host_password,
                                           cm_repo_url=self.cm_repo_url)
        log.debug("Installing hosts. This might take a while...")
        while cmd.success is None:
            sleep(5)
            cmd = cmd.fetch()

        if cmd.success is not True:
            log.error("Adding hosts to Cloudera Manager failed: {0}".format(cmd.resultMessage))

        log.debug("Host added to Cloudera Manager")

        # first auto-assign roles and auto-configure the CM service
        self.cm_manager.auto_assign_roles()
        self.cm_manager.auto_configure()

        # create a cluster on that instance
        cluster = self.cm_api_resource.create_cluster(self.cluster_name, self.cdh_version)
        log.debug("Cloudera cluster: {0} created".format(self.cluster_name))

        # add all hosts on the cluster
        cluster.add_hosts(self.host_list)

        cluster = self.cm_api_resource.get_cluster(self.cluster_name)

        # get and list all available parcels
        parcels_list = []
        log.debug("Installing parcels...")
        for p in cluster.get_all_parcels():
            print '\t' + p.product + ' ' + p.version
            if p.version.startswith(self.cdh_version_number) and p.product == "CDH":
                parcels_list.append(p)

        if len(parcels_list) == 0:
            log.error("No {0} parcel found!".format(self.cdh_version))

        cdh_parcel = parcels_list[0]
        for p in parcels_list:
            if p.version > cdh_parcel.version:
                cdh_parcel = p

        # download the parcel
        log.debug("Starting parcel downloading...")
        cmd = cdh_parcel.start_download()
        if cmd.success is not True:
            log.error("Parcel download failed!")

        # make sure the download finishes
        while cdh_parcel.stage != 'DOWNLOADED':
            sleep(5)
            cdh_parcel = get_parcel(self.cm_api_resource, cdh_parcel.product, cdh_parcel.version, self.cluster_name)

        log.debug("Parcel: {0} {1} downloaded".format(cdh_parcel.product, cdh_parcel.version))

        # distribute the parcel
        log.debug("Distributing parcels...")
        cmd = cdh_parcel.start_distribution()
        if cmd.success is not True:
            log.error("Parcel distribution failed!")

        # make sure the distribution finishes
        while cdh_parcel.stage != "DISTRIBUTED":
            sleep(5)
            cdh_parcel = get_parcel(self.cm_api_resource, cdh_parcel.product, cdh_parcel.version, self.cluster_name)

        log.debug("Parcel: {0} {1} distributed".format(cdh_parcel.product, cdh_parcel.version))

        # activate the parcel
        log.debug("Activating parcels...")
        cmd = cdh_parcel.activate()
        if cmd.success is not True:
            log.error("Parcel activation failed!")

        # make sure the activation finishes
        while cdh_parcel.stage != "ACTIVATED":
            cdh_parcel = get_parcel(self.cm_api_resource, cdh_parcel.product, cdh_parcel.version, self.cluster_name)

        log.debug("Parcel: {0} {1} activated".format(cdh_parcel.product, cdh_parcel.version))

        # inspect hosts and print the result
        log.debug("Inspecting hosts. This might take a few minutes")

        cmd = self.cm_manager.inspect_hosts()
        while cmd.success is None:
            sleep(5)
            cmd = cmd.fetch()

        if cmd.success is not True:
            log.error("Host inpsection failed!")

        log.debug("Hosts successfully inspected:\n".format(cmd.resultMessage))
        log.info("Cluster '{0}' installed".format(self.cluster_name))

    def setup_cluster(self):
        """
        Setup the default cluster and start basic services (HDFS, YARN and ZOOKEEPER)
        """
        log.info("Setting up cluster services...")
        # get the cluster
        cluster = self.cm_api_resource.get_cluster(self.cluster_name)

        # create all the services we want to add; we will only create one instance of each
        for s in self.service_types_and_names.keys():
            service_name = self.service_types_and_names[s]
            cluster.create_service(service_name, s)
            log.debug("Service: {0} added".format(service_name))

        # auto-assign roles
        cluster.auto_assign_roles()
        cluster.auto_configure()

        # start the management service
        cm_service = self.cm_manager.get_service()
        # create_CM_roles(master_node, cm_service)
        cm_service.start().wait()

        # execute the first run command
        log.debug("Executing first run command. This might take a while...")
        cmd = cluster.first_run()

        while cmd.success is None:
            sleep(5)
            cmd = cmd.fetch()

        if cmd.success is not True:
            log.error("The first run command failed: {0}".format(cmd.resultMessage()))

        log.info("First run successfully executed. Your cluster has been set up!")

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
