"""CloudMan service implementation for Pulsar server."""
import os
import random
import string
from string import Template

from cm.util import misc
from cm.util.galaxy_conf import attempt_chown_galaxy
from cm.services import service_states
from cm.services import ServiceRole
from cm.services import ServiceDependency
from cm.services.apps import ApplicationService

import logging
log = logging.getLogger('cloudman')

app_yml = """---
private_token: $token
manager:
  type: queued_drmaa
"""

server_ini = """[server:main]
use = egg:Paste#http
port = $pulsar_port
host = 0.0.0.0
## pem file to use to enable SSL.
# ssl_pem = host.pem

[app:main]
paste.app_factory = pulsar.web.wsgi:app_factory
app_config = %(here)s/app.yml

## Configure uWSGI (if used).
[uwsgi]
master = True
paste-logger = true
socket = 0.0.0.0:3031
processes = 1
enable-threads = True


## Configure circus and chaussette (if used).
[circus]
endpoint = tcp://127.0.0.1:5555
pubsub_endpoint = tcp://127.0.0.1:5556
#stats_endpoint = tcp://127.0.0.1:5557

[watcher:web]
cmd = chaussette --fd $$(circus.sockets.web) paste:server.ini
use_sockets = True
# Pulsar must be single-process for now...
numprocesses = 1

[socket:web]
host = 0.0.0.0
port = $pulsar_port

## Configure Python loggers.
[loggers]
keys = root,pulsar

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = INFO
handlers = console

[logger_pulsar]
level = DEBUG
handlers = console
qualname = pulsar
propagate = 0

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = DEBUG
formatter = generic

[formatter_generic]
format = %(asctime)s %(levelname)-5.5s [%(name)s][%(threadName)s] %(message)s
"""

local_env_sh = """
export DRMAA_LIBRARY_PATH=/usr/lib/slurm-drmaa/lib/libdrmaa.so
export GALAXY_HOME=$galaxy_home
"""

supervisor_conf = """[program:pulsar]
user            = galaxy
directory       = /mnt/pulsar
command         = pulsar --mode 'paster' --config '/mnt/pulsar'
autostart       = false
autorestart     = true
redirect_stderr = true
stdout_logfile  = /var/log/pulsar.log
"""


class PulsarService(ApplicationService):

    def __init__(self, app):
        super(PulsarService, self).__init__(app)
        self.name = ServiceRole.to_string(ServiceRole.PULSAR)
        self.svc_roles = [ServiceRole.PULSAR]
        self.dependencies = [
            ServiceDependency(self, ServiceRole.JOB_MANAGER),
            ServiceDependency(self, ServiceRole.SUPERVISOR)
        ]
        self.pulsar_home = '/mnt/pulsar'
        self.pulsar_port = 8913
        self.supervisor_conf_dir = '/etc/supervisor/conf.d'
        self.supervisor_prog_name = 'pulsar'

    @property
    def supervisor(self):
        ss = self.app.manager.service_registry.get_active('Supervisor')
        if not ss:
            log.debug("Supervisor service not running.")
        return ss

    def start(self):
        """
        Start Pulsar service.
        """
        log.debug("Starting {0} service".format(self.name))
        self.state = service_states.STARTING
        self._configure()
        self._start_via_supervisor()

    def remove(self, synchronous=False):
        """
        Stop the Pulsar service.
        """
        log.info("Stopping {0} service".format(self.name))
        super(PulsarService, self).remove(synchronous)
        self.state = service_states.SHUTTING_DOWN
        self._stop_via_supervisor()
        self.state = service_states.SHUT_DOWN

    def _configure(self):
        """
        Configure the Pulsar application.
        """
        self.state = service_states.CONFIGURING
        misc.make_dir(self.pulsar_home)
        # Write out app.yml
        token = ''.join(random.SystemRandom().choice(string.ascii_uppercase +
                        string.lowercase + string.digits) for _ in range(25))
        app_template = Template(app_yml)
        app_yml_file = os.path.join(self.pulsar_home, 'app.yml')
        misc.write_template_file(app_template, {'token': token}, app_yml_file)
        # Write out server.ini
        srvr_template = Template(server_ini)
        server_ini_file = os.path.join(self.pulsar_home, 'server.ini')
        misc.write_template_file(srvr_template, {'pulsar_port': self.pulsar_port},
                                 server_ini_file)
        # Write out local_env.sh
        lcl_template = Template(local_env_sh)
        lcl_file = os.path.join(self.pulsar_home, 'local_env.sh')
        misc.write_template_file(lcl_template, {'galaxy_home': '/mnt/galaxy/galaxy-app'},
                                 lcl_file)
        # Set the owner to 'galaxy' system user
        attempt_chown_galaxy(self.pulsar_home, recursive=True)
        if self.supervisor:
            # Create a supervisor conf file
            supervisor_conf_file = os.path.join(self.supervisor.conf_dir,
                                                '{0}.conf'.format(self.supervisor_prog_name))
            template = Template(supervisor_conf)
            misc.write_template_file(template, None, supervisor_conf_file)
        else:
            log.warning("No supervisor service?")

    def _start_via_supervisor(self):
        """
        Start the Pulsar server via Supervisord.
        """
        log.debug("Starting {0} server via supervisord".format(self.name))
        if self.supervisor:
            self.supervisor.start_program(self.supervisor_prog_name)

    def _stop_via_supervisor(self):
        """
        Stop the Pulsar server via Supervisord.
        """
        log.debug("Stopping {0} server via supervisord".format(self.name))
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
