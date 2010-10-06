import commands, os
from cm.util import paths


import logging
log = logging.getLogger(__name__)

"""
Placeholder for ApplicationService methods.
"""

from cm.services import Service

class ApplicationService( Service ):
    
    def __init__(self, app):
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
            # Galaxy deamon is named 'paster' so handle this special case
            if service == 'galaxy':
                service = 'python'
            alive_daemon_pid = commands.getoutput("ps -o comm,pid -p %s | grep %s | awk '{print $2}'" % (daemon_pid, service))
            if service == 'python':
                service = 'galaxy'
            if alive_daemon_pid == daemon_pid:
                # log.debug("\t'%s' daemon is running with PID: %s" % (service, daemon_pid))
                return True
            else:
                log.debug("\t'%s' daemon is NOT running any more (expected pid: '%s')." % (service, daemon_pid))
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
            pid_file = '%s/postmaster.pid' % paths.P_PSQL_DIR
        elif service == 'sge':
            pid_file = '%s/qmaster.pid' % paths.P_SGE_CELL
        elif service == 'galaxy':
            pid_file = '%s/paster.pid' % paths.P_GALAXY_HOME
        else:
            return -1
        # log.debug("\tChecking pid file '%s' for service '%s'" % (pid_file, service))
        if os.path.isfile(pid_file):
            return commands.getoutput("head -n 1 %s" % pid_file)
        else:
            return -1
