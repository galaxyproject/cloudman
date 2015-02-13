import os

from cm.conftemplates import conf_manager
from cm.util import misc
from cm.util import paths
from cm.services import ServiceRole
from cm.services import service_states
from cm.services.apps import ApplicationService

import logging
log = logging.getLogger('cloudman')


class NginxService(ApplicationService):
    def __init__(self, app):
        super(NginxService, self).__init__(app)
        self.svc_roles = [ServiceRole.NGINX]
        self.name = ServiceRole.to_string(ServiceRole.NGINX)
        self.dependencies = []
        self.exe = self.app.path_resolver.nginx_executable
        self.conf_dir = self.app.path_resolver.nginx_conf_dir
        self.conf_file = self.app.path_resolver.nginx_conf_file  # Main conf file
        self.ssl_is_on = False
        # The list of services that Nginx service proxies
        self.proxied_services = ['Galaxy', 'GalaxyReports', 'Pulsar', 'ClouderaManager']
        # A list of currently active CloudMan services being proxied
        self.active_proxied = []

    def start(self):
        """
        Start Nginx web server.
        """
        log.debug("Starting Nginx service")
        self.start_webserver()

    def remove(self, synchronous=False):
        """
        Stop the Nginx web server.
        """
        log.info("Stopping Nginx service")
        super(NginxService, self).remove(synchronous)
        self.state = service_states.SHUTTING_DOWN
        self.state = service_states.SHUT_DOWN

    def start_webserver(self):
        """
        Start the Nginx web server. The process for Nginx is expected to be
        running already so basically get a handle to the process. If it's not
        running, start it.
        """
        # Remove the default server config that comes with Nginx system package
        nginx_default_server = os.path.join(self.conf_dir, 'sites-enabled', 'default')
        misc.delete_file(nginx_default_server)
        self.reconfigure(setup_ssl=self.ssl_is_on)
        # Get a handle on the server process
        if not self._check_daemon('nginx'):
            if misc.run(self.exe):
                self.state == service_states.RUNNING

    def reload(self):
        """
        Reload nginx process (`nginx -s reload`)
        """
        # TODO: run `nginx -t` before attemping to reload the process to make
        # sure the conf files are OK and thus reduce chances of screwing up
        misc.run('{0} -c {1} -s reload'.format(self.exe, self.conf_file))

    def _define_upstream_servers(self):
        """
        Generate Nginx `upstream` server definitions for select servers.
        Returns a formatted string. For example:

            upstream galaxy_app {
                server 127.0.0.1:8080;
            }
            upstream galaxy_reports_app {
                server 127.0.0.1:9001;
            }
        """
        upstream_servers = ""
        # A list of tuples of active servers. Each tuple should contain the
        # server name as the first value and the upstream server contact
        # info as the second value
        servers = []
        # Collect active servers
        galaxy_svc = self.app.manager.service_registry.get_active('Galaxy')
        if galaxy_svc:
            if not galaxy_svc.multiple_processes():
                galaxy_server = "server 127.0.0.1:8080;"
            else:
                web_thread_count = int(self.app.ud.get("web_thread_count", 3))
                galaxy_server = 'ip_hash;'
                if web_thread_count > 9:
                    log.warning("Current code supports max 9 web threads. "
                        "Setting the web thread count to 9.")
                    web_thread_count = 9
                for i in range(web_thread_count):
                    galaxy_server += "server 127.0.0.1:808%s;" % i
            servers.append(('galaxy', galaxy_server))
        cmf_svc = self.app.manager.service_registry.get_active('ClouderaManager')
        if cmf_svc:
            servers.append(('cmf', 'server 127.0.0.1:{0};'.format(cmf_svc.port)))
        # Format the active servers
        for server in servers:
            upstream_servers += '''
    upstream {0}_app {{
        {1}
    }}'''.format(server[0], server[1])
        return upstream_servers

    def _write_template_file(self, template_file, parameters, conf_file):
        """
        Given a plain text `template_file` path and appropriate `parameters`,
        load the file as a `string.Template`, substitute the `parameters` and
        write out the file to the `conf_file` path.
        """
        template = conf_manager.load_conf_template(template_file)
        t = template.substitute(parameters)
        # Write out the file
        with open(conf_file, 'w') as f:
            print >> f, t
        log.debug("Wrote Nginx config file {0}".format(conf_file))

    def reconfigure(self, setup_ssl):
        """
        (Re)Generate Nginx configuration files and reload the server process.

        :type   setup_ssl: boolean
        :param  setup_ssl: if set, force HTTPS with a self-signed certificate.
        """
        if self.exe:
            log.debug("Updating Nginx config at {0}".format(self.conf_file))
            params = {}
            # Customize the appropriate nginx template
            if setup_ssl and "1.4" in misc.getoutput("{0} -v".format(self.exe)):
                # Generate a self-signed certificate
                log.info("Generating self-signed certificate for SSL encryption")
                cert_home = "/root/.ssh/"
                certfile = os.path.join(cert_home, "instance_selfsigned_cert.pem")
                keyfile = os.path.join(cert_home, "instance_selfsigned_key.pem")
                misc.run("yes '' | openssl req -x509 -nodes -days 3650 -newkey "
                    "rsa:1024 -keyout " + keyfile + " -out " + certfile)
                misc.run("chmod 440 " + keyfile)
                server_tmplt = conf_manager.NGINX_SERVER_SSL
                log.debug("Using Nginx v1.4+ template w/ SSL")
                self.ssl_is_on = True
                nginx_tmplt = conf_manager.NGINX_14_CONF_TEMPLATE
            elif "1.4" in misc.getoutput("{0} -v".format(self.exe)):
                server_tmplt = conf_manager.NGINX_SERVER
                log.debug("Using Nginx v1.4+ template")
                nginx_tmplt = conf_manager.NGINX_14_CONF_TEMPLATE
                self.ssl_is_on = False
            else:
                server_tmplt = ""
                nginx_tmplt = conf_manager.NGINX_CONF_TEMPLATE
                self.ssl_is_on = False
                params = {
                    'galaxy_user_name': paths.GALAXY_USER_NAME,
                    'galaxy_home': paths.P_GALAXY_HOME,
                    'galaxy_data': self.app.path_resolver.galaxy_data,
                }
                log.debug("Using Nginx pre-v1.4 template")
            # Write out the main nginx.conf file
            if not params:
                params = {'galaxy_user_name': paths.GALAXY_USER_NAME}
            self._write_template_file(nginx_tmplt, params, self.conf_file)
            # Write out the default server block file
            if server_tmplt:
                # This means we're dealing with Nginx v1.4+ & split conf files
                upstream_servers = self._define_upstream_servers()
                params = {'upstream_servers': upstream_servers}
                conf_file = os.path.join(self.conf_dir, 'sites-enabled', 'default.server')
                self._write_template_file(server_tmplt, params, conf_file)
                # Pulsar has it's own server config
                pulsar_svc = self.app.manager.service_registry.get_active('Pulsar')
                if pulsar_svc:
                    pulsar_tmplt = conf_manager.NGINX_SERVER_PULSAR
                    params = {'pulsar_port': pulsar_svc.pulsar_port}
                    conf_file = os.path.join(self.conf_dir, 'sites-enabled', 'pulsar.server')
                    self._write_template_file(pulsar_tmplt, params, conf_file)
                # Write out the location blocks for hosted services
                # Always include default locations (CloudMan, VNC, error)
                default_tmplt = conf_manager.NGINX_DEFAULT
                conf_file = os.path.join(self.conf_dir, 'sites-enabled', 'default.locations')
                self._write_template_file(default_tmplt, {}, conf_file)
                # Now add running services
                reports_svc = self.app.manager.service_registry.get_active('GalaxyReports')
                reports_conf_file = os.path.join(self.conf_dir, 'sites-enabled', 'reports.locations')
                if reports_svc:
                    reports_tmplt = conf_manager.NGINX_GALAXY_REPORTS
                    params = {'reports_port': reports_svc.reports_port}
                    self._write_template_file(reports_tmplt, params, reports_conf_file)
                else:
                    misc.delete_file(reports_conf_file)
                galaxy_svc = self.app.manager.service_registry.get_active('Galaxy')
                gxy_conf_file = os.path.join(self.conf_dir, 'sites-enabled', 'galaxy.locations')
                if galaxy_svc:
                    galaxy_tmplt = conf_manager.NGINX_GALAXY
                    params = {
                        'galaxy_home': paths.P_GALAXY_HOME,
                        'galaxy_data': self.app.path_resolver.galaxy_data
                    }
                    self._write_template_file(galaxy_tmplt, params, gxy_conf_file)
                else:
                    misc.delete_file(gxy_conf_file)
                cmf_svc = self.app.manager.service_registry.get_active('ClouderaManager')
                cmf_conf_file = os.path.join(self.conf_dir, 'sites-enabled', 'cmf.locations')
                if cmf_svc:
                    cmf_tmplt = conf_manager.NGINX_CLOUDERA_MANAGER
                    self._write_template_file(cmf_tmplt, {}, cmf_conf_file)
                else:
                    misc.delete_file(cmf_conf_file)
            self.reload()
        else:
            log.warning("Cannot find nginx executable to reload nginx config (got"
                        " '{0}')".format(self.exe))

    def status(self):
        """
        Check and update the status of the service.
        """
        # Check if nginx config needs to be reconfigured
        aa = self.app.manager.service_registry.all_active(names=True)
        for s in self.app.manager.service_registry.all_active(names=True):
            if s not in self.proxied_services:
                aa.remove(s)
        if set(self.active_proxied) != set(aa):
            # There was a service change, run reconfigure
            self.active_proxied = aa
            log.debug("Nginx service detected a change in proxied services; "
                      "reconfiguring the nginx config (active proxied: {0}; "
                      "active: {1}).".format(self.active_proxied, aa))
            self.reconfigure(setup_ssl=self.ssl_is_on)
        # Check if the process is running
        if self._check_daemon('nginx'):
            self.state = service_states.RUNNING
        elif (self.state == service_states.SHUTTING_DOWN or
              self.state == service_states.SHUT_DOWN or
              self.state == service_states.UNSTARTED or
              self.state == service_states.WAITING_FOR_USER_ACTION,
              self.state == service_states.COMPLETED):
            pass
        else:
            self.state = service_states.ERROR
