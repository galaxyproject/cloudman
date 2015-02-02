import os
import commands

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
        self.conf_file = self.app.path_resolver.nginx_conf_file
        self.ssl_is_on = False
        # The list of services that Nginx service proxies
        self.proxied_services = ['Galaxy', 'Pulsar', 'ClouderaManager']
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
        if not self._check_daemon('nginx'):
            if misc.run(self.exe):
                self.state == service_states.RUNNING

    def reload(self):
        """
        Reload nginx process (`nginx -s reload`)
        """
        misc.run('{0} -c {1} -s reload'.format(self.exe, self.conf_file))

    def reconfigure(self, setup_ssl=False):
        """
        (Re)Generate `nginx.conf` from a template and reload nginx process so
        config options take effect.
        """
        if self.exe:
            log.debug("Updating nginx config at {0}".format(
                      self.conf_file))
            galaxy_svc = self.app.manager.service_registry.get('Galaxy')
            galaxy_server = "server 127.0.0.1:8080;"
            if galaxy_svc and galaxy_svc.multiple_processes():
                web_thread_count = int(self.app.ud.get("web_thread_count", 3))
                galaxy_server = ''
                if web_thread_count > 9:
                    log.warning("Current code supports max 9 web threads. "
                        "Setting the web thread count to 9.")
                    web_thread_count = 9
                for i in range(web_thread_count):
                    galaxy_server += "server 127.0.0.1:808%s;" % i
            # Customize the appropriate nginx template
            if (setup_ssl and self.exe and "1.4"
               in commands.getoutput("{0} -v".format(self.exe))):
                # Generate a self-signed certificate
                log.info("Generating self-signed certificate for SSL encryption")
                cert_home = "/root/.ssh/"
                certfile = os.path.join(cert_home, "instance_selfsigned_cert.pem")
                keyfile = os.path.join(cert_home, "instance_selfsigned_key.pem")
                misc.run("yes '' | openssl req -x509 -nodes -days 3650 -newkey "
                    "rsa:1024 -keyout " + keyfile + " -out " + certfile)
                misc.run("chmod 440 " + keyfile)
                server_block_head = conf_manager.load_conf_template(
                    conf_manager.NGINX_SERVER_BLOCK_HEAD_SSL).safe_substitute()
                log.debug("Using nginx v1.4+ template w/ SSL")
                self.ssl_is_on = True
                nginx_tmplt = conf_manager.NGINX_14_CONF_TEMPLATE
            elif (self.exe and "1.4" in commands.getoutput(
                  "{0} -v".format(self.exe))):
                server_block_head = conf_manager.load_conf_template(
                    conf_manager.NGINX_SERVER_BLOCK_HEAD).safe_substitute()
                log.debug("Using nginx v1.4+ template")
                nginx_tmplt = conf_manager.NGINX_14_CONF_TEMPLATE
                self.ssl_is_on = False
            else:
                server_block_head = ""
                nginx_tmplt = conf_manager.NGINX_CONF_TEMPLATE
                self.ssl_is_on = False
            pulsar_block = ""
            if self.app.manager.service_registry.is_active('Pulsar'):
                pulsar_block = """
    upstream pulsar_app {
        server 127.0.0.1:8913;
    }
    server {
        listen                  8914;
        client_max_body_size    10G;
        proxy_read_timeout      600;

        location /jobs {
            proxy_pass http://pulsar_app;
            proxy_set_header   X-Forwarded-Host $host:$server_port;
            proxy_set_header   X-Forwarded-For  $proxy_add_x_forwarded_for;
            error_page   502    /errdoc/cm_502.html;
        }
    }
                """

            cloudera_manager_app_block = ""
            cloudera_manager_server_block = ""
            if self.app.manager.service_registry.is_active('ClouderaManager'):
                cloudera_manager_app_block = """
    upstream cmf_app {
        server 127.0.0.1:7180;
    }
                """
                cloudera_manager_server_block = """
        location /cmf {
            proxy_pass  http://cmf_app;
            proxy_set_header   X-Forwarded-Host $host;
            proxy_set_header   X-Forwarded-For  $proxy_add_x_forwarded_for;
        }
        location /static/ext{
            proxy_pass  http://cmf_app;
            proxy_set_header   X-Forwarded-Host $host;
            proxy_set_header   X-Forwarded-For  $proxy_add_x_forwarded_for;
        }
        location /static/cms{
            proxy_pass  http://cmf_app;
            proxy_set_header   X-Forwarded-Host $host;
            proxy_set_header   X-Forwarded-For  $proxy_add_x_forwarded_for;
        }
        location /static/release{
            proxy_pass  http://cmf_app;
            proxy_set_header   X-Forwarded-Host $host;
            proxy_set_header   X-Forwarded-For  $proxy_add_x_forwarded_for;
        }
        location /static/snmp{
            proxy_pass  http://cmf_app;
            proxy_set_header   X-Forwarded-Host $host;
            proxy_set_header   X-Forwarded-For  $proxy_add_x_forwarded_for;
        }
        location /static/apidocs{
            proxy_pass  http://cmf_app;
            proxy_set_header   X-Forwarded-Host $host;
            proxy_set_header   X-Forwarded-For  $proxy_add_x_forwarded_for;
        }
        location /j_spring_security_check{
            proxy_pass  http://cmf_app;
            proxy_set_header   X-Forwarded-Host $host;
            proxy_set_header   X-Forwarded-For  $proxy_add_x_forwarded_for;
        }
        location /j_spring_security_logout{
            proxy_pass  http://cmf_app;
            proxy_set_header   X-Forwarded-Host $host;
            proxy_set_header   X-Forwarded-For  $proxy_add_x_forwarded_for;
        }
        location /api/v6{
            proxy_pass  http://cmf_app;
            proxy_set_header   X-Forwarded-Host $host;
            proxy_set_header   X-Forwarded-For  $proxy_add_x_forwarded_for;
        }
                """
            nginx_conf_template = conf_manager.load_conf_template(nginx_tmplt)
            params = {
                'galaxy_user_name': paths.GALAXY_USER_NAME,
                'galaxy_home': paths.P_GALAXY_HOME,
                'galaxy_data': self.app.path_resolver.galaxy_data,
                'galaxy_server': galaxy_server,
                'server_block_head': server_block_head,
                'pulsar_block': pulsar_block,
                'cloudera_manager_app_block': cloudera_manager_app_block,
                'cloudera_manager_server_block': cloudera_manager_server_block
            }
            template = nginx_conf_template.substitute(params)
            # Write out the files
            with open(self.conf_file, 'w') as f:
                print >> f, template
            nginx_cmdline_config_file = os.path.join(self.app.path_resolver.nginx_conf_dir,
                                                     'commandline_utilities_http.conf')
            misc.run('touch {0}'.format(nginx_cmdline_config_file))
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
            self.reconfigure()
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
