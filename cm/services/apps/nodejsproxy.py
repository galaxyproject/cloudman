"""CloudMan service implementation for Galaxy NodeJS Proxy server."""
import os
from string import Template

from cm.util import misc
import cm.util.paths as paths
from cm.services import ServiceRole
from cm.services import ServiceDependency
from cm.services import service_states
from cm.services.apps import ApplicationService

import logging
log = logging.getLogger('cloudman')

supervisor_conf = """;
; This file is maintained by CloudMan - CHANGES WILL BE OVERWRITTEN!
;

[program:$supervisor_prog_name]
directory       = $galaxy_home
command         = $galaxy_home/lib/galaxy/web/proxy/js/lib/main.js \
  --sessions database/session_map.sqlite --ip 0.0.0.0 --port $np_port
autostart       = false
autorestart     = unexpected
user            = $galaxy_user
startsecs       = 5
redirect_stderr = true
"""


class NodejsProxyService(ApplicationService):
    def __init__(self, app):
        super(NodejsProxyService, self).__init__(app)
        self.svc_roles = [ServiceRole.NODEJSPROXY]
        self.name = ServiceRole.to_string(ServiceRole.NODEJSPROXY)
        self.dependencies = [ServiceDependency(self, ServiceRole.GALAXY_TOOLS),
                             ServiceDependency(self, ServiceRole.SUPERVISOR)]
        self.np_port = 8800
        self.supervisor_conf_dir = '/etc/supervisor/conf.d'
        self.supervisor_prog_name = 'galaxy_nodejs_proxy'

    @property
    def supervisor(self):
        ss = self.app.manager.service_registry.get_active('Supervisor')
        if not ss:
            log.debug("No supervisor service object?!?")
        return ss

    def start(self):
        """
        Start NodeJS Proxy service.
        """
        log.debug("Starting NodeJS Proxy service")
        self.state = service_states.STARTING
        self._configure()
        self._start_via_supervisor()

    def remove(self, synchronous=False):
        """
        Stop the NodeJS Proxy service.
        """
        log.info("Stopping NodeJS Proxy service")
        super(NodejsProxyService, self).remove(synchronous)
        self.state = service_states.SHUTTING_DOWN
        self._stop_via_supervisor()
        self.state = service_states.SHUT_DOWN

    def _configure(self):
        """
        Setup NodeJS Proxy within CloudMan and Galaxy contexts.

        This will create a config file for Supervisor while other,
        Galaxy-specific, requirements are assumed present
        (https://wiki.galaxyproject.org/Admin/IEs).
        """
        log.debug("Configuring NodeJS Proxy.")
        template_vars = {
            'supervisor_prog_name': self.supervisor_prog_name,
            'galaxy_home': self.app.path_resolver.galaxy_home,
            'np_port': self.np_port,
            'galaxy_user': paths.GALAXY_USER_NAME
        }
        if self.supervisor:
            supervisor_conf_file = os.path.join(self.supervisor.conf_dir,
                                                '{0}.conf'.format(self.supervisor_prog_name))
            template = Template(supervisor_conf)
            misc.write_template_file(template, template_vars, supervisor_conf_file)
            return True
        return False

    def _start_via_supervisor(self):
        """
        Start the NodeJS Proxy server via Supervisord.
        """
        log.debug("Starting NodeJS Proxy server via supervisord")
        if self.supervisor:
            self.supervisor.start_program(self.supervisor_prog_name)

    def _stop_via_supervisor(self):
        """
        Stop the NodeJS Proxy server via Supervisord.
        """
        log.debug("Stopping NodeJS Proxy server via supervisord")
        if self.supervisor:
            self.supervisor.stop_program(self.supervisor_prog_name)

    def status(self):
        """
        Check and update the status of the service.
        """
        if self.supervisor:
            statename = self.supervisor.get_program_status(self.supervisor_prog_name)
            # Translate supervisor states to CloudMan service states
            # http://supervisord.org/subprocess.html#process-states
            s_to_s = {
                'STOPPED': service_states.SHUT_DOWN,
                'STARTING': service_states.STARTING,
                'RUNNING': service_states.RUNNING,
                'BACKOFF': service_states.STARTING,
                'STOPPING': service_states.SHUTTING_DOWN,
                'EXITED': service_states.SHUT_DOWN,
                'FATAL': service_states.ERROR,
                'UNKNOWN': service_states.UNSTARTED
            }
            self.state = s_to_s.get(statename, self.state)
