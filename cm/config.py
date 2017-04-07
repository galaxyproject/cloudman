"""Universe configuration builder."""
import logging
import logging.config
import logging.handlers
import os
import sys
import traceback

from requests_futures.sessions import FuturesSession

import cm.util.paths as paths

log = logging.getLogger('cloudman')

DEFAULT_INSTANCE_REBOOT_TIMEOUT = 500
DEFAULT_INSTANCE_COMM_TIMEOUT = 180
DEFAULT_INSTANCE_STATE_CHANGE_WAIT = 400
DEFAULT_INSTANCE_REBOOT_ATTEMPTS = 4
DEFAULT_INSTANCE_TERMINATE_ATTEMPTS = 4
DEFAULT_INSTANCE_TYPES = {
    "amazon": [
        ("", "Same as Master"),
        ("", "-------------"),
        ("c3.large", "Compute optimized Large (2 vCPU/4GB RAM)"),
        ("c3.2xlarge", "Compute optimized 2xLarge (8 vCPU/15GB RAM)"),
        ("c3.8xlarge", "Compute optimized 8xLarge (32 vCPU/60GB RAM)"),
        # R3 instance types require HVM virtualization and appropriate AMI so omit
        ("", "-------------"),
        ("r3.large", "Memory optimized Large (2 vCPU/15GB RAM)"),
        ("r3.2xlarge", "Memory optimized 2xLarge (8 vCPU/61GB RAM)"),
        ("r3.8xlarge", "Memory optimized 8xLarge (32 vCPU/244GB RAM)"),
        ("", "-------------"),
        ("custom_instance_type", "Custom instance type")
    ],
    "nectar": [
        ("", "Same as Master"),
        ("m1.small", "Small"),
        ("m1.medium", "Medium"),
        ("m1.large", "Large"),
        ("m1.xlarge", "Extra Large"),
        ("m1.xxlarge", "Extra Extra Large"),
        ("custom_instance_type", "Custom instance type")
    ],
    "hpcloud": [
        ("", "Same as Master"),
        ("standard.xsmall", "Extra Small"),
        ("standard.small", "Small"),
        ("standard.medium", "Medium"),
        ("standard.large", "Large"),
        ("standard.xlarge", "Extra Large"),
        ("standard.2xlarge", "Extra Extra Large"),
    ],
    "ict-tas": [
        ("", "Same as Master"),
        ("m1.small", "Small"),
        ("m1.medium", "Medium"),
        ("m1.xlarge", "Extra Large"),
        ("m1.xxlarge", "Extra Extra Large"),
    ],
    "default": [
        ("", "Same as Master"),
        ("custom_instance_type", "Custom instance type")
    ]
}


class ConfigurationError(Exception):
    pass


class Configuration(dict):

    def __init__(self, app, kwargs, ud):
        # Configuration data sources
        self.app = app
        self.config_dict = kwargs
        self._user_data = ud
        self._rebuild_combined_config()
        self._galaxy_admin_users = ud.get('admin_users', [])

    def _rebuild_combined_config(self):
        """
        Build dictionary in reverse order of resolution
        """
        self.clear()
        self.update(self.config_dict)
        self.update(self.user_data)
        self.update(self._extract_env_vars())

    def _extract_env_vars(self):
        return {key.upper(): os.environ[key.upper()] for key in os.environ if key.startswith("CM_")}

# A debug version of __contains__, in case you need to trace the provenance of a variable """
#     def __dontains__(self, value):
#         if not value:
#             log.debug("Key not found: {0}".format(value))
#             return False
#         elif value.startswith("cm_") and value.upper() in os.environ:
#             log.debug("Key: {0} found in os.environ. CM_ auto prepended.".format(value))
#             return True
#         elif "CM_" + value.upper() in os.environ:
#             log.debug("Key: {0} found in os.environ.".format(value))
#             return True
#         elif value in self.user_data:
#             log.debug("Key: {0} found in user_data.".format(value))
#             return True
#         elif value in self.config_dict:
#             log.debug("Key: {0} found in cm_wsgi.ini.".format(value))
#             return True

    def __getitem__(self, key):
        """
        Resolves configuration variables hierarchically.
        The order of resolution is:
        1. Environment variables ("CM_" is prepended to key if required, to
           avoid conflict with general environment variables. Env vars are
           expected to be in upper case)
        2. User Data
        3. cm_wsgi.ini
        """
        key = key.lower()

        if key.startswith("cm_") and key.upper() in self:
            return dict.__getitem__(self, key.upper())
        elif "CM_" + key.upper() in self:
            return dict.__getitem__(self, "CM_" + key.upper())
        else:
            return dict.__getitem__(self, key)

    def validate(self):
        # Check that required directories exist
        for path in self.root_dir, self.template_path:
            if not os.path.isdir(path):
                raise ConfigurationError(
                    "Directory does not exist: %s" % path)

    @property
    def user_data(self):
        return self._user_data

    @user_data.setter
    def user_data(self, value):
        self._user_data = value
        self._rebuild_combined_config()

    @property
    def filesystem_templates(self):
        if 'filesystem_templates' not in self:
            log.debug("filesystem_templates not found in config {0}; loading "
                      "legacy snapshot data.".format(self))
            self['filesystem_templates'] = self.app.manager.load_legacy_snapshot_data()
        return self.get('filesystem_templates')

    @property
    def cluster_templates(self):
        return self.get('cluster_templates', None)

    @property
    def galaxy_admin_users(self):
        return self._galaxy_admin_users

    @galaxy_admin_users.setter
    def galaxy_admin_users(self, admins_list):
        self._galaxy_admin_users = admins_list

    @property
    def root_dir(self):
        return self.get('root_dir', '.')

    @property
    def template_path(self):
        """If 'path' is relative make absolute by prepending 'root'"""
        template_path = self.get("template_path", "templates")
        if not(os.path.isabs(template_path)):
            path = os.path.join(self.root_dir, template_path)
        return path

    @property
    def cloudman_source_file_name(self):
        return self.get("cloudman_file_name", "cm.tar.gz")

    @property
    def cloud_name(self):
        return self.get('cloud_name', 'amazon').lower()

    @property
    def cloud_type(self):
        return self.get('cloud_type', 'ec2').lower()

    @property
    def multiple_processes(self):
        return self.get("configure_multiple_galaxy_processes", False)

    @property
    def condor_enabled(self):
        return self.get("condor_enabled", False)

    @property
    def hadoop_enabled(self):
        return self.get("hadoop_enabled", False)

    @property
    def worker_initial_count(self):
        """
        If supplied via user data, launch that many workers after launch.
        """
        if os.path.exists(paths.REBOOT_FLAG_FILE):
            return 0
        wic = self.get("worker_initial_count", 0)
        if isinstance(wic, int):
            return wic
        elif wic.isdigit():
            return int(wic)
        return 0

    @property
    def instance_reboot_timeout(self):
        return self.get("instance_reboot_timeout", DEFAULT_INSTANCE_REBOOT_TIMEOUT)

    @property
    def instance_comm_timeout(self):
        return self.get("instance_comm_timeout", DEFAULT_INSTANCE_COMM_TIMEOUT)

    @property
    def instance_state_change_wait(self):
        return self.get("instance_state_change_wait", DEFAULT_INSTANCE_STATE_CHANGE_WAIT)

    @property
    def instance_reboot_attempts(self):
        return self.get("instance_reboot_attempts", DEFAULT_INSTANCE_REBOOT_ATTEMPTS)

    @property
    def instance_terminate_attempts(self):
        return self.get("instance_terminate_attempts", DEFAULT_INSTANCE_TERMINATE_ATTEMPTS)

    @property
    def instance_types(self):
        if self.get("instance_types"):
            # Manually specified instance types
            user_data_instance_types = self.get("instance_types")
            instance_types = [(type_def["key"], type_def["name"]) for type_def in user_data_instance_types]
            return instance_types
        else:
            keys = [key for key in DEFAULT_INSTANCE_TYPES.keys() if key in self.cloud_name]
            if keys:
                return DEFAULT_INSTANCE_TYPES.get(keys[0])
            else:
                return DEFAULT_INSTANCE_TYPES.get("default")

    @property
    def cloudman_repo_url(self):
        return self.get("CM_url", "https://bitbucket.org/galaxy/cloudman/commits/all?page=tip&search=")

    @property
    def ignore_unsatisfiable_dependencies(self):
        return self.get("ignore_unsatisfiable_dependencies", False)

    @ignore_unsatisfiable_dependencies.setter
    def ignore_unsatisfiable_dependencies(self, value):
        self['ignore_unsatisfiable_dependencies'] = value

    @property
    def web_thread_count(self):
        return self.get("web_thread_count", 3)

    @property
    def info_brand(self):
        return self.get("brand", "")

    @property
    def info_wiki_url(self):
        return self.get("wiki_url", "http://g2.trac.bx.psu.edu/")

    @property
    def info_bugs_email(self):
        return self.get("bugs_email", "mailto:galaxy-bugs@bx.psu.edu")

    @property
    def info_blog_url(self):
        return self.get("blog_url", "http://g2.trac.bx.psu.edu/blog")

    @property
    def info_screencasts_url(self):
        return self.get("screencasts_url", "http://main.g2.bx.psu.edu/u/aun1/p/screencasts")


# TODO: REFACTOR - This method doesn't belong here
def configure_logging(config):
    """
    Allow some basic logging configuration to be read from the cherrpy
    config.
    """
    # format = config.get( "log_format", "%(name)s %(levelname)s %(asctime)s
    # %(message)s" )
    log_format = config.get(
        "log_format", "%(asctime)s %(levelname)-7s %(module)12s:%(lineno)-4d %(message)s")
    level = logging._levelNames[config.get("log_level", "DEBUG")]
    destination = config.get("log_destination", "stdout")
    log.info("Logging at '%s' level to '%s'" % (level, destination))
    # Get root logger
    root = logging.getLogger()
    # Set level
    root.setLevel(level)
    # Turn down paste httpserver logging
    if level <= logging.DEBUG:
        logging.getLogger(
            "paste.httpserver.ThreadPool").setLevel(logging.WARN)
    # Remove old handlers
    for h in root.handlers[:]:
        root.removeHandler(h)
    # Create handler
    if destination == "stdout":
        handler = logging.StreamHandler(sys.stdout)
    else:
        handler = logging.FileHandler(destination)
    # Create formatter
    formatter = logging.Formatter(log_format)
    # Hook everything up
    handler.setFormatter(formatter)
    root.addHandler(handler)
    # Add loggly handler
    loggly_token = config.get('cm_loggly_token', None)
    if loggly_token is not None:
        loggly_handler = HTTPSHandler(
            url="https://logs-01.loggly.com/inputs/{0}/tag/python"
            .format(loggly_token))
        loggly_handler.setFormatter(formatter)
        log.addHandler(loggly_handler)
        # requests is chatty with our default log level so elevate its level
        logging.getLogger('requests').setLevel(logging.INFO)

session = FuturesSession()


class HTTPSHandler(logging.Handler):
    """A custom log handler for POSTing logs to an HTTPS server."""

    def __init__(self, url, fqdn=False, localname=None, facility=None):
        logging.Handler.__init__(self)
        self.url = url
        self.fqdn = fqdn
        self.localname = localname
        self.facility = facility

    def get_full_message(self, record):
        if record.exc_info:
            return '\n'.join(traceback.format_exception(*record.exc_info))
        else:
            return record.getMessage()

    def emit(self, record):
        try:
            payload = self.format(record)
            session.post(self.url, data=payload)
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            self.handleError(record)
