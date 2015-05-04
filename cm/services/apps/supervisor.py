"""CloudMan service implementation for Supervisor."""
import xmlrpclib
from socket import error as socket_error

from cm.conftemplates import conf_manager
from cm.util import misc
from cm.services import ServiceRole
from cm.services import service_states
from cm.services.apps import ApplicationService

import logging
log = logging.getLogger('cloudman')


class SupervisorService(ApplicationService):
    def __init__(self, app):
        super(SupervisorService, self).__init__(app)
        self.svc_roles = [ServiceRole.SUPERVISOR]
        self.name = ServiceRole.to_string(ServiceRole.SUPERVISOR)
        self.dependencies = []
        self.sv_port = 9002
        self.pid_file = '/var/run/supervisord.pid'
        self.main_conf_file = '/etc/supervisord.conf'
        self.conf_dir = '/etc/supervisor/conf.d'
        self.server = None
        self.log_file = '/var/log/supervisor/supervisord.log'

    @property
    def supervisor(self):
        if self.server is not None:
            return self.server.supervisor
        else:
            # Try to connect to a running supervisord instance (assume
            # supervisord is running on port ``self.sv_port``)
            server = xmlrpclib.Server('http://localhost:{0}/RPC2'.format(
                                      self.sv_port))
            try:
                statename = server.supervisor.getState().get('statename', None)
                if statename == 'RUNNING':
                    self.server = server
                    return self.server.supervisor
            except xmlrpclib.Fault as flt:
                log.debug('Fault connecting to supervisord: {0}'.format(flt))
            except socket_error as serr:
                log.debug('Socket error connecting to supervisord: {0}'.format(serr))
            self.server = None
            return None

    def start(self):
        """
        Start the Supervisor service.
        """
        log.debug("Starting {0} service".format(self.name))
        self.state = service_states.STARTING
        self._configure()
        self._start_supervisord()

    def remove(self, synchronous=False):
        """
        Stop the Supervisor service.
        """
        log.info("Stopping {0} service".format(self.name))
        super(SupervisorService, self).remove(synchronous)
        self.state = service_states.SHUTTING_DOWN
        try:
            assert self.supervisor.shutdown()
            self.state = service_states.SHUT_DOWN
            self.server = None
        except:  # Let's try a more direct approach
            log.debug("Stopping supervisord with pid from {0}".format(self.pid_file))
            cmd = ('/sbin/start-stop-daemon --retry TERM/5/KILL/10 --stop '
                   '--pidfile {0}'.format(self.pid_file))
            misc.run(cmd)
            self.state = service_states.SHUT_DOWN
            self.server = None

    def _configure(self):
        """
        Setup Supervisor for running via CloudMan by creating
        ``supervisord.conf`` file.
        """
        log.debug("Configuring supervisord")
        # Create supervisord config file
        sv_vars = {
            'supervisord_pid': self.pid_file,
            'sv_port': self.sv_port,
            'conf_dir': self.conf_dir,
            'supervisord_log': self.log_file
        }
        template = conf_manager.load_conf_template(conf_manager.SUPERVISOR_TEMPLATE)
        misc.write_template_file(template, sv_vars, self.main_conf_file)
        # Make sure the config dir exists for programs managed by supervisor
        misc.make_dir(self.conf_dir)

    def _start_supervisord(self):
        """
        Start the supervisord process with ``self.main_conf_file``.
        """
        log.debug("Starting supervisord with {0}".format(self.main_conf_file))
        if misc.run('supervisord -c {0}'.format(self.main_conf_file)):
            self.server = xmlrpclib.Server('http://localhost:{0}/RPC2'.format(
                                           self.sv_port))

    def reload_config(self):
        """
        Update the list of program configurations for supervisord.

        This will reread the supervisord configuration directory
        (``self.conf_dir``) and proceed to remove/reload/add any program
        definitions as read from the conf directory.

        If the configration was reloaded succesfully, return ``True``, ``False``
        othwerise.
        """
        log.debug("Updating supervisord program list.")
        if self.supervisor is not None:
            try:
                output = self.supervisor.reloadConfig()
                added, changed, removed = output[0]
                for gname in removed:
                    self.supervisor.stopProcessGroup(gname)
                    self.supervisor.removeProcessGroup(gname)
                for gname in changed:
                    self.supervisor.stopProcessGroup(gname)
                    self.supervisor.removeProcessGroup(gname)
                    self.supervisor.addProcessGroup(gname)
                for gname in added:
                    self.supervisor.addProcessGroup(gname)
                return True
            except xmlrpclib.Fault, flt:
                    log.debug('Fault reloading supervisord config: {0}'.format(flt))
            except Exception, exc:
                log.error("Exception dealing with supervisorctl: {0}".format(exc))
        else:
            log.debug("Cannot reload supervisord conf because no server handle.")
        return False

    def start_program(self, prog_name):
        """
        Start program ``prog_name`` via supervisord.

        This will reload supervisord configuration, add the ``prog_name``
        process group and attempt to start the process. Note that the program
        configuration file already needs to have been placed into supervisord's
        configuration directory (``self.conf_dir``) before this method is called.
        """
        log.debug("Starting program {0} via supervisord.".format(prog_name))
        if self.reload_config():
            prog_status = self.get_program_status(prog_name)
            if prog_status is not 'RUNNING':
                try:
                    return self.supervisor.startProcess(prog_name)
                except xmlrpclib.Fault, flt:
                    log.error('Fault starting supervisord prog: {0}'.format(flt))
            else:
                log.debug("Not starting {0} via supervisord because it "
                          "is already RUNNING.")
        else:
            log.debug("Did not add {0} to supervisord because could not reload "
                      "supervisord config.".format(prog_name))
        return False

    def stop_program(self, prog_name):
        """
        Stop program ``prog_name`` via supervisord.
        """
        log.debug("Stopping program {0} via supervisord.".format(prog_name))
        prog_status = self.get_program_status(prog_name)
        if prog_status == 'STOPPED':
            log.debug("Program {0} already STOPPED.".format(prog_name))
            return True
        elif self.get_program_status(prog_name) is 'RUNNING':
            try:
                return self.supervisor.stopProcess(prog_name)
            except xmlrpclib.Fault, flt:
                log.error('Fault stopping supervisord prog: {0}'.format(flt))
        log.debug("Not stopping {0} via supervisord because it is not RUNNING "
                  "(it's in state {1}).".format(prog_name, prog_status))
        return False

    def get_program_info(self, prog_name):
        """
        Query supervisord for the info of program ``prog_name`` and return it
        (as a dict). If the program is not found or something unexpected
        occurs, return an empty dict.
        """
        # log.debug("Getting program {0} info from supervisord.".format(prog_name))
        if self.supervisor is not None:
            try:
                progs_info = self.supervisor.getAllProcessInfo()
                prog_info = next((prog for prog in progs_info if prog['name'] == prog_name), {})
                if not prog_info:
                    log.debug("Did not find program {0} in supervisord?".format(prog_name))
                return prog_info
            except xmlrpclib.Fault, flt:
                log.debug('Fault getting prog {0} info from supervisord: {0}'
                          .format(prog_name, flt))
        return {}

    def get_program_status(self, prog_name):
        """
        Query supervisord for the status of program ``prog_name`` and return it.
        Return ``None`` if the program is not found or something unexpected
        occurs.
        """
        # log.debug("Getting program {0} status from supervisord.".format(prog_name))
        return self.get_program_info(prog_name).get('statename', None)

    def status(self):
        """
        Check and update the status of the service (i.e., supervisord process).
        """
        if self.supervisor is not None:
            try:
                statename = self.supervisor.getState().get('statename', '')
                # Translate supervisor states to CloudMan service states
                s_to_s = {
                    'FATAL': service_states.ERROR,
                    'RUNNING': service_states.RUNNING,
                    'RESTARTING': service_states.STARTING,
                    'SHUTDOWN': service_states.SHUT_DOWN
                }
                self.state = s_to_s.get(statename, self.state)
            except xmlrpclib.Fault, flt:
                log.debug('Could not get supervisord status: {0}'.format(flt))
                self.state = service_states.ERROR
            except Exception, exc:
                log.debug("Exception checking supervisord status: {0}".format(exc))
                self.state = service_states.ERROR
