"""
CloudMan service encapsulating ProFTPd application
"""
import os
import urllib

from cm.conftemplates import conf_manager
from cm.services import service_states
from cm.services import ServiceDependency
from cm.services import ServiceRole
from cm.services.apps import ApplicationService
from cm.util import misc
from cm.util import paths
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
        log.debug("Configuring ProFTPd")
        # Because we're rewriting the proftpd config file below, update the
        # password for PostgreSQL galaxyftp user
        gftp_pwd = self.app.path_resolver.proftpd_galaxyftp_user_pwd
        log.debug("Setting psql password for galaxyftp role to {0}".format(gftp_pwd))
        # Check if galaxtftp role already exists
        cmd = ('{0} - postgres -c"{1} -p {2} -tAc\\\"SELECT 1 FROM pg_roles WHERE rolname=\'galaxyftp\'\\\""'
               .format(paths.P_SU, self.app.path_resolver.psql_cmd,
                       self.app.path_resolver.psql_db_port))
        role = 'ALTER' if misc.getoutput(cmd) == '1' else 'CREATE'
        # Now either CREATE or ALTER the galaxyftp role to set the permissions
        cmd = ('{0} - postgres -c"{1} -p {4} -c\\\"{2} ROLE galaxyftp LOGIN PASSWORD \'{3}\'\\\""'
               .format(paths.P_SU, self.app.path_resolver.psql_cmd, role,
                       gftp_pwd, self.app.path_resolver.psql_db_port))
        misc.run(cmd)
        # Update the config to match the current environment
        proftpd_tmplt = conf_manager.PROFTPD_CONF_TEMPLATE
        proftpd_conf_template = conf_manager.load_conf_template(proftpd_tmplt)
        params = {
            'galaxy_user_name': paths.GALAXY_USER_NAME,
            'galaxyftp_user_name': 'galaxyftp',
            'psql_galaxyftp_password': gftp_pwd,
            'galaxy_db_port': self.app.path_resolver.psql_db_port,
            'galaxyFS_base_path': self.app.path_resolver.galaxy_data
        }
        template = proftpd_conf_template.substitute(params)
        # Write out the config file
        with open(self.app.path_resolver.proftpd_conf_file, 'w') as f:
            print >> f, template
        log.debug("Updated ProFTPd conf file {0}".format(
                  self.app.path_resolver.proftpd_conf_file))
        # Place the FTP welcome message file
        urllib.urlretrieve("https://s3.amazonaws.com/cloudman/files/proftpd_welcome.txt",
                           "/usr/proftpd/etc/welcome_msg.txt")
        # Setup the Galaxy data dir for FTP
        ftp_data_dir = '%s/tmp/ftp' % self.app.path_resolver.galaxy_data
        if not os.path.exists(ftp_data_dir):
            os.makedirs(ftp_data_dir)
        attempt_chown_galaxy(ftp_data_dir)
        # Some images have vsFTPd server included so stop it first
        vsFTPd_exists = misc.run('status vsftpd', quiet=True)
        if vsFTPd_exists and 'start/running' in vsFTPd_exists:
            log.debug("Stopping vsFTPd")
            misc.run('stop vsftpd')
        # Start the server now
        if misc.run('/etc/init.d/proftpd start'):
            self.state = service_states.RUNNING
            return True
        else:
            log.error("Trouble starting ProFTPd")
            self.state = service_states.ERROR
            return False

    def status(self):
        """
        TODO Check and update the status of ProFTPd service.
        """
        return self.state
