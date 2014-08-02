"""
Placeholder for ApplicationService methods.
"""

import commands
import logging
import os

from socket import AF_INET, socket, SOCK_STREAM

log = logging.getLogger('cloudman')


from cm.services import Service
from cm.services import ServiceType


class ApplicationService(Service):

    def __init__(self, app):
        self.name = ""
        self.svc_type = ServiceType.APPLICATION
        super(ApplicationService, self).__init__(app)

    def __repr__(self):
        return self.get_full_name()

    def _check_daemon(self, service):
        """Check if 'service' daemon process is running.

        :rtype: bool
        :return: True if a process associated with the 'service' exists on the system,
                 False otherwise.
        """
        daemon_pid = self._get_daemon_pid(service)
        if daemon_pid == -1:
            return False
        else:
            # Check if given PID is actually still running
            alive_daemon_pid = None
            system_service = service
            # Galaxy deamon is named 'paster' so handle this special case
            special_services = {"galaxy": "python", "galaxyreports": "python", "lwr": "paster"}
            system_service = special_services.get(service, service)  # Default back to just service
            alive_daemon_pid = commands.getoutput(
                "ps -o comm,pid -p %s | grep %s | awk '{print $2}'" % (daemon_pid, system_service))
            if alive_daemon_pid == daemon_pid:
                # log.debug("'%s' daemon is running with PID: %s" % (service,
                # daemon_pid))
                return True
            else:
                log.debug("'%s' daemon is NOT running any more (expected pid: '%s')." % (
                    service, daemon_pid))
                return False

    def _get_daemon_pid(self, service):
        """Get PID of 'service' daemon as stored in the service.pid file
        in respective service directory.
        :type service: str
        :param service: Recognized values include only 'postgres', 'sge', 'galaxy'

        :rtype: int
        :return: PID, -1 if the file does not exist
        """
        if service == 'slurmctld':
            pid_file = self.app.path_resolver.slurmctld_pid
        elif service == 'slurmd':
            pid_file = self.app.path_resolver.slurmd_pid
        elif service == 'postgres':
            pid_file = '%s/postmaster.pid' % self.app.path_resolver.psql_dir
        elif service == 'sge':
            pid_file = '%s/qmaster.pid' % self.app.path_resolver.sge_cell
        elif service == 'galaxy':
            pid_file = '%s/main.pid' % self.app.path_resolver.galaxy_home
        elif service == 'galaxyreports':
            pid_file = '%s/reports_webapp.pid' % self.app.path_resolver.galaxy_home
        elif service == 'lwr':
            pid_file = '%s/paster.pid' % self.app.path_resolver.lwr_home
        else:
            return -1
        # log.debug("Checking pid file '%s' for service '%s'" % (pid_file,
        # service))
        if os.path.isfile(pid_file):
            return commands.getoutput("head -n 1 %s" % pid_file)
        else:
            return -1

    def _port_bound(self, port):
        """
        Determine if any process is listening on localhost on specified port.
        """
        s = socket(AF_INET, SOCK_STREAM)
        try:
            result = s.connect_ex(('127.0.0.1', port))
            return result == 0
        finally:
            s.close()
