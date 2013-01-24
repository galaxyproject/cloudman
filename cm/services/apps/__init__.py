import commands, os
from cm.util import paths


import logging
log = logging.getLogger( 'cloudman' )

"""
Placeholder for ApplicationService methods.
"""

from cm.services import Service
from cm.services import ServiceType

class ApplicationService( Service ):

    def __init__(self, app):
        self.svc_type = ServiceType.APPLICATION        
        super(ApplicationService, self).__init__(app)

    def _check_daemon(self, service):
        """Check if 'service' daemon process is running.

        :rtype: bool
        :return: True if a process assocaited with the 'service' exists on the system,
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
            if service in ['galaxy', 'galaxy_reports']:
                system_service = 'python'
            alive_daemon_pid = commands.getoutput("ps -o comm,pid -p %s | grep %s | awk '{print $2}'" % (daemon_pid, system_service))
            if alive_daemon_pid == daemon_pid:
                # log.debug("'%s' daemon is running with PID: %s" % (service, daemon_pid))
                return True
            else:
                log.debug("'%s' daemon is NOT running any more (expected pid: '%s')." % (service, daemon_pid))
                return False

    def _get_daemon_pid(self, service):
        """Get PID of 'service' daemon as stored in the service.pid file
        in respective service directory.
        :type service: str
        :param service: Recognized values include only 'postgres', 'sge', 'galaxy'

        :rtype: int
        :return: PID, -1 if the file does not exist
        """
        if service == 'postgres':
            pid_file = '%s/postmaster.pid' % self.app.path_resolver.psql_dir
        elif service == 'sge':
            pid_file = '%s/qmaster.pid' % self.app.path_resolver.sge_cell
        elif service == 'galaxy':
            pid_file = '%s/main.pid' % self.app.path_resolver.galaxy_home
        elif service == 'galaxy_reports':
            pid_file = '%s/reports_webapp.pid' % self.app.path_resolver.galaxy_home
        else:
            return -1
        #log.debug("Checking pid file '%s' for service '%s'" % (pid_file, service))
        if os.path.isfile(pid_file):
            return commands.getoutput("head -n 1 %s" % pid_file)
        else:
            return -1
