from cm.util.galaxy_conf import galaxy_option_manager
from cm.util.galaxy_conf import populate_process_options
from cm.util.galaxy_conf import populate_dynamic_options
from cm.util.galaxy_conf import populate_galaxy_paths
from cm.util.galaxy_conf import populate_admin_users
from test_utils import TestApp
from test_utils import TEST_DATA_DIR, TEST_INDICES_DIR, TEST_TOOLS_DIR
from tempfile import mkdtemp
from os.path import join
from os import rename
from ConfigParser import SafeConfigParser


def test_file_option_manager():
    app = TestApp()
    option_manager = galaxy_option_manager(app)
    option_manager.setup()
    _set_test_property(option_manager)
    test_galaxy_home = app.path_resolver.galaxy_home
    universe_path = join(test_galaxy_home, 'universe_wsgi.ini')
    with open(universe_path, 'rt') as f:
        parser = SafeConfigParser()
        parser.readfp(f)
        assert parser.get('app:main', "admin_users") == "test@example.org"


def test_on_universe_missing_uses_sample():
    app = TestApp()
    option_manager = galaxy_option_manager(app)
    option_manager.setup()

    # Rename universe_wsgi.ini to universe_wsgi.ini.sample so it is missing.
    test_galaxy_home = app.path_resolver.galaxy_home
    universe_path = join(test_galaxy_home, 'universe_wsgi.ini')
    sample_path = join(test_galaxy_home, 'universe_wsgi.ini.sample')
    rename(universe_path, sample_path)

    _set_test_property(option_manager)
    with open(universe_path, 'rt') as f:
        parser = SafeConfigParser()
        parser.readfp(f)
        assert parser.get('app:main', "admin_users") == "test@example.org"


def test_dir_option_manager():
    conf_dir = mkdtemp()
    app = TestApp(ud={"galaxy_conf_dir": conf_dir})
    option_manager = galaxy_option_manager(app)
    option_manager.setup()
    _set_test_property(option_manager)
    option_file_path = join(conf_dir, '400_cloudman_override_admin_users.ini')
    content = open(option_file_path, 'r').read()
    assert content == "[app:main]\nadmin_users=test@example.org"


def test_populate_process_options():
    app = TestApp(ud={"web_thread_count": 3, "handler_thread_count": 2})
    option_manager = TestOptionManager(app)
    populate_process_options(option_manager)
    options = option_manager.options
    # Test correct sections configured
    for name in ["web1", "web2", "handler0", "handler1", "manager0"]:
        assert "server:%s" % name in options
    for name in ["web3", "handler2"]:
        assert "server:%s" % name not in options
    # TODO: Actually test configuration of sections, thread count, etc...


def test_populate_dynamic_options():
    test_connection = "mysql:///dbserver/galaxy"
    test_runner = "pbs:///test1"
    ud = {"galaxy_universe_database_connection": test_connection,
          "galaxy_tool_runner_cooltool1": test_runner}
    app = TestApp(ud=ud)
    option_manager = TestOptionManager(app)
    populate_dynamic_options(option_manager)
    options = option_manager.options
    assert options["galaxy:tool_runners"]["cooltool1"] == test_runner
    assert options["app:main"]["database_connection"] == test_connection


def test_populate_galaxy_paths():
    app = TestApp()
    option_manager = TestOptionManager(app)
    populate_galaxy_paths(option_manager)
    main_options = option_manager.options["app:main"]
    assert main_options["genome_data_path"] == \
        join(TEST_INDICES_DIR, "genomes")
    assert main_options["len_file_path"] == \
        join(TEST_DATA_DIR, "configuration_data", "len")
    assert main_options["tool_dependency_dir"] == \
        join(TEST_TOOLS_DIR, "tools")
    assert main_options["file_path"] == \
        join(TEST_DATA_DIR, "files")
    assert main_options["new_file_path"] == \
        join(TEST_DATA_DIR, "tmp")
    assert main_options["job_working_directory"] == \
        join(TEST_DATA_DIR, "tmp", "job_working_directory")
    assert main_options["cluster_files_directory"] == \
        join(TEST_DATA_DIR, "tmp", "pbs")
    assert main_options["ftp_upload_dir"] == \
        join(TEST_DATA_DIR, "tmp", "ftp")
    assert main_options["nginx_upload_store"] == \
        join(TEST_DATA_DIR, "upload_store")


def test_populate_admin_users():
    app = TestApp(ud={"admin_users": ["mary@example.com", "bill@example.com"]})
    option_manager = TestOptionManager(app)
    populate_admin_users(option_manager)
    options = option_manager.options
    assert options["app:main"]["admin_users"] == \
        "mary@example.com,bill@example.com"


class TestOptionManager(object):

    def __init__(self, app):
        self.app = app
        self.options = {}

    def set_properties(self, properties, section="app:main", description=None, priority_offset=0):
        if section not in self.options:
            self.options[section] = {}
        self.options[section].update(properties)


def _set_test_property(option_manager):
    properties = {"admin_users": "test@example.org"}
    option_manager.set_properties(properties)
