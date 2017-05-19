import os
from os.path import join, exists
from os import makedirs, symlink, chown, walk
from shutil import copyfile, move

from ConfigParser import SafeConfigParser
from pwd import getpwnam
from grp import getgrnam

from xml.dom.minidom import parse

from .misc import run

import logging
log = logging.getLogger('cloudman')


OPTIONS_FILE_NAME = 'galaxy.ini'


def attempt_chown_galaxy_if_exists(path):
    """
    Change owner of file at specified `path` (if it exists)
    to `galaxy`.
    """
    if exists(path):
        attempt_chown_galaxy(path)


def attempt_chown_galaxy(path, recursive=False):
    """
    Change owner of file at specified `path` to `galaxy`.
    """
    if os.access(path, os.W_OK):  # don't attempt on read-only paths
        try:
            log.debug("Attempting to chown to galaxy for {0}".format(path))
            galaxy_uid = getpwnam("galaxy")[2]
            galaxy_gid = getgrnam("galaxy")[2]
            chown(path, galaxy_uid, galaxy_gid)
            if recursive:
                for root, dirs, files in walk(path):
                    for d in dirs:
                        chown(join(root, d), galaxy_uid, galaxy_gid)
                    for f in files:
                        chown(join(root, f), galaxy_uid, galaxy_gid)
        except BaseException:
            run("chown galaxy:galaxy '%s'" % path)


def populate_admin_users(option_manager, admins_list=[]):
    """
    Galaxy admin users can be set by providing them in user data
    (see below) or by calling this method and providing a user list.
    YAML format for user data for providing admin users
    (note that these users will still have to manually register
    on the given Galaxy instance):
    admin_users:
     - user@example.com
     - user2@anotherexample.edu
    """
    admins_list = admins_list or option_manager.app.config.galaxy_admin_users
    if len(admins_list) == 0:
        return False
    log.info('Setting Galaxy admin users to: %s' % admins_list)
    option_manager.set_properties({"admin_users": ",".join(admins_list)})


def populate_dynamic_options(option_manager):
    """
    Use `option_manager` to populate arbitrary app:main and galaxy:tool_runners
    properties coming in from userdata.
    """
    dynamic_option_types = {"galaxy_universe_": "app:main",
                            "galaxy_tool_runner_": "galaxy:tool_runners",
                            }
    for option_prefix, section in dynamic_option_types.iteritems():
        for key, value in option_manager.app.config.iteritems():
            if key.startswith(option_prefix):
                key = key[len(option_prefix):]
                option_manager.set_properties({key: value}, section=section)


# High-level functions that utilize option_manager interface (defined below)
# to configure Galaxy's options.
def populate_process_options(option_manager):
    """
    Configure Galaxy's options.

    Use `option_manager` to populate process (handler, manager, web) sections
    for Galaxy. Also adjust job_conf.xml to account for process setup.
    """
    log.debug("Populating Galaxy process options")
    app = option_manager.app
    web_thread_count = int(app.config.web_thread_count)
    handler_thread_count = int(app.config.get("handler_thread_count", 3))
    # Setup web threads
    [__add_server_process(option_manager, i, "web", 8080)
     for i in range(web_thread_count)]
    # Setup handler threads
    handlers = [__add_server_process(option_manager, i, "handler", 9080)
                for i in range(handler_thread_count)]
    # Setup manager thread
    __add_server_process(option_manager, 0, "manager", 8079)
    process_properties = {"job_manager": "manager0",
                          "job_handlers": ",".join(handlers)}
    option_manager.set_properties(process_properties)
    _update_job_conf(app, handler_thread_count)


def __add_server_process(option_manager, index, prefix, initial_port):
    app = option_manager.app
    port = initial_port + index
    threads = app.config.get("threadpool_workers", "7")
    server_options = {"use": "egg:Paste#http",
                      "port": port,
                      "host": "127.0.0.1",
                      "use_threadpool": True,
                      "threadpool_workers": threads
                      }
    server_name = "%s%d" % (prefix, index)
    if port == 8080:
        # Special case, server on port 8080 must be called main unless we want
        # to start deleting chunks of galaxy.ini.
        server_name = "main"
    option_manager.set_properties(server_options,
                                  section="server:%s" % server_name,
                                  description="server_%s" % server_name)
    return server_name


def _update_job_conf(app, num_handlers, plugin_id='slurm'):
    """
    Update Galaxy job_conf.xml.

    At the moment, only job handlers are set. Number of handlers are added that
    correspond to ``num_handlers``.
    """
    galaxy_config_dir = app.path_resolver.galaxy_config_dir
    job_conf_file_path = join(galaxy_config_dir, 'job_conf.xml')
    log.debug("Updating Galaxy's job conf file {0}".format(job_conf_file_path))

    jc = parse(job_conf_file_path)
    handlers_el = jc.getElementsByTagName('handlers')[0]
    doc_root = jc.documentElement

    hs_el = jc.createElement('handlers')
    hs_el.setAttribute('default', 'handlers')
    for i in range(num_handlers):
        h_el = jc.createElement('handler')
        h_el.setAttribute('id', 'handler%d' % i)
        h_el.setAttribute('tags', 'handlers')
        hs_el.appendChild(h_el)
        p_el = jc.createElement('plugin')
        p_el.setAttribute('id', plugin_id)
        h_el.appendChild(p_el)
    doc_root.replaceChild(hs_el, handlers_el)

    with open(job_conf_file_path, 'w') as f:
        jc.writexml(f)


# Abstraction for interacting with Galaxy's options
def galaxy_option_manager(app):
    """ Returns a high-level class for managing Galaxy options.
    """
    if "galaxy_conf_dir" in app.config:
        option_manager = DirectoryGalaxyOptionManager(app)
    else:
        option_manager = FileGalaxyOptionManager(app)
    return option_manager


def populate_galaxy_paths(option_manager):
    """
    Turn ``path_resolver`` paths and configurations into Galaxy options using
    specified ``option_manager``.
    """
    properties = {}
    path_resolver = option_manager.app.path_resolver
    properties["database_connection"] = "postgres://galaxy@localhost:{0}/galaxy"\
        .format(path_resolver.psql_db_port)
    properties["tool_dependency_dir"] = join(path_resolver.galaxy_tools, "tools")
    properties["file_path"] = join(path_resolver.galaxy_data, "files")
    temp_dir = '/mnt/galaxy/tmp'
    if not exists(temp_dir):
        makedirs(temp_dir)
    attempt_chown_galaxy(temp_dir, recursive=True)
    attempt_chown_galaxy(path_resolver.galaxy_indices, recursive=False)
    properties["new_file_path"] = temp_dir
    # This is something a user may change so this is not an ideal solution
    # but a relation to the required files is necessary so here it is.
    # properties['tool_config_file'] = "tool_conf.xml,shed_tool_conf.xml"
    tool_config_files = []
    for tcf in ['tool_conf.xml', 'shed_tool_conf.xml', 'shed_tool_conf_cloud.xml']:
        if exists(join(path_resolver.galaxy_config_dir, tcf)):
            tool_config_files.append(join(path_resolver.galaxy_config_dir, tcf))
    properties['tool_config_file'] = ','.join(tool_config_files)
    properties["job_working_directory"] = join(temp_dir, "job_working_directory")
    properties["cluster_files_directory"] = join(temp_dir, "pbs")
    properties["ftp_upload_dir"] = join(path_resolver.galaxy_data, 'tmp', "ftp")
    properties["library_import_dir"] = join(temp_dir, "library_import_dir")
    properties["nginx_upload_store"] = join(path_resolver.galaxy_data, "upload_store")
    properties['ftp_upload_site'] = option_manager.app.cloud_interface.get_public_ip()
    # Allow user data options to override these, specifically the database.
    priority_offset = -1
    option_manager.set_properties(properties, description="paths", priority_offset=priority_offset)


class FileGalaxyOptionManager(object):

    """
    Default Galaxy option manager, modifies `$galaxy_config_dir/$OPTIONS_FILE_NAME`
    directly.
    """

    def __init__(self, app):
        self.app = app

    def setup(self):
        """ setup should return conf_dir, in this case there is none."""
        return None

    def set_properties(self, properties, section="app:main", description=None,
                       priority_offset=0):
        """
        Rewrite Galaxy's conf file `OPTIONS_FILE_NAME` to set options.
        """
        galaxy_config_dir = self.app.path_resolver.galaxy_config_dir
        config_file_path = join(galaxy_config_dir, OPTIONS_FILE_NAME)
        log.debug("Rewriting Galaxy's main config file {0} with properties {1}"
                  .format(config_file_path, properties))
        input_config_file_path = config_file_path
        if not exists(input_config_file_path):
            input_config_file_path = "%s.sample" % config_file_path
        parser = SafeConfigParser()
        configfile = open(input_config_file_path, 'rt')
        parser.readfp(configfile)
        if not parser.has_section(section):
            parser.add_section(section)
        for key, value in properties.iteritems():
            parser.set(section, key, str(value))
        configfile.close()
        new_config_file_path = join(galaxy_config_dir, '{0}.new'.format(OPTIONS_FILE_NAME))
        with open(new_config_file_path, 'wt') as output_file:
            parser.write(output_file)
        move(new_config_file_path, config_file_path)
        attempt_chown_galaxy(config_file_path)


class DirectoryGalaxyOptionManager(object):

    """
    When `galaxy_conf_dir` in specified in UserData this is used to
    manage Galaxy's options.
    """

    def __init__(self, app, conf_dir=None, conf_file_name=OPTIONS_FILE_NAME):
        self.app = app
        if not conf_dir:
            conf_dir = app.config["galaxy_conf_dir"]
        self.conf_dir = conf_dir
        self.conf_file_name = conf_file_name

    def setup(self):
        """ Setup the configuration directory and return conf_dir. """
        self.__initialize_galaxy_config_dir()
        return self.conf_dir

    def __initialize_galaxy_config_dir(self):
        conf_dir = self.conf_dir
        if not exists(conf_dir):
            makedirs(conf_dir)
            defaults_destination = join(conf_dir, "010_%s" % self.conf_file_name)
            galaxy_config_dir = self.app.path_resolver.galaxy_config_dir
            config_file_path = join(galaxy_config_dir, self.conf_file_name)
            if not exists(config_file_path):
                # Fresh install, take the opportunity to just link in defaults
                sample_name = "%s.sample" % self.conf_file_name
                defaults_source = join(galaxy_config_dir, sample_name)
                symlink(defaults_source, defaults_destination)
            else:
                # CloudMan has previously been run without the galaxy_conf_dir
                # option enabled. Users may have made modifications to
                # universe_wsgi.ini that I guess we should preserve for
                # backward compatibility.
                defaults_source = join(galaxy_config_dir, self.conf_file_name)
                copyfile(defaults_source, defaults_destination)

    def set_properties(self, properties, section="app:main", description=None, priority_offset=0):
        if not properties:
            return

        priority = int(self.app.config.get("galaxy_option_priority", "400")) + priority_offset
        conf_dir = self.conf_dir
        if description is None:
            description = properties.keys()[0]
        conf_file_name = "%s_cloudman_override_%s.ini" % (str(priority), description)
        conf_file = join(conf_dir, conf_file_name)
        props_str = "\n".join(
            ["%s=%s" % (k, v) for k, v in properties.iteritems()])
        with open(conf_file, "w") as f:
            f.write("[%s]\n%s" % (section, props_str))
