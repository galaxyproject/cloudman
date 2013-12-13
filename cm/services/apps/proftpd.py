"""
CloudMan service encapsulating ProFTPd application
"""
import os

from cm.util import misc
from cm.util import paths
from cm.services import ServiceRole
from cm.services import service_states
from cm.services import ServiceDependency
from cm.services.apps import ApplicationService
from cm.util.galaxy_conf import attempt_chown_galaxy

import logging
log = logging.getLogger('cloudman')


class ProFTPdService(ApplicationService):
    def __init__(self, app):
        """
        Initialize the service class by setting role and indicating dependencies
        """
        super(ProFTPdService, self).__init__(app)
        log.debug("Initializing ProFTPdService")
        self.svc_roles = [ServiceRole.PROFTPD]
        self.name = ServiceRole.to_string(ServiceRole.PROFTPD)
        self.dependencies = [ServiceDependency(self, ServiceRole.GALAXY_POSTGRES),
            ServiceDependency(self, ServiceRole.GALAXY_DATA)]

    def start(self):
        """
        Start ProFTPd service
        """
        log.debug("Initiating ProFTPd service start")
        self.state = service_states.STARTING
        self.configure_proftpd()

    def remove(self):
        """
        Shut down ProFTPd service.
        """
        log.info("Shutting down ProFTPd service")
        self.state = service_states.SHUTTING_DOWN
        misc.run("/etc/init.d/proftpd stop")
        self.state = service_states.SHUT_DOWN

    def configure_proftpd(self):
        """
        Configure environment for running ProFTPd service.
        """
        # In the config, set the port on which postgres is running
        log.debug("Configuring ProFTPd")
        # This is a bit dodgy but ports are hardcoded in CBL so shoudl be a pretty
        # safe bet for the time being
        misc.replace_string('/usr/proftpd/etc/proftpd.conf',
            'galaxy@localhost:5840', 'galaxy@localhost:{0}'.format(paths.C_PSQL_PORT))
        misc.replace_string('/usr/proftpd/etc/proftpd.conf',
            '/mnt/galaxyData', self.app.path_resolver.galaxy_data)
        # Setup the data dir for FTP
        ftp_data_dir = '%s/tmp/ftp' % self.app.path_resolver.galaxy_data
        if not os.path.exists(ftp_data_dir):
            os.makedirs(ftp_data_dir)
        attempt_chown_galaxy(ftp_data_dir)
        # Start the server now
        if misc.run('/etc/init.d/proftpd start'):
            self.state = service_states.RUNNING
            return True
        else:
            log.debug("Trouble starting ProFTPd")
            return False

    def status(self):
        """
        TODO Check and update the status of ProFTPd service.
        """
        return self.state
