from os import makedirs, stat
from os.path import exists, join
from getpass import getuser
from base64 import encodestring

from cm.boot.conf import AuthorizedKeysManager, _install_authorized_keys, _install_conf_files, _configure_nginx

from test_utils import test_logger, temp_dir


class TestAuthorizedKeysManager(AuthorizedKeysManager):

    def __init__(self, mock_home_dir):
        super(TestAuthorizedKeysManager, self).__init__()
        self.mock_home_dir = mock_home_dir
        self.sudo_cmd = ""

    def _get_home_dir(self, user):
        return self.mock_home_dir


KEY1 = "ssh-dss AAAABCDEFG mary@example.org"
KEYS_USERDATA = {"authorized_keys": [KEY1],
                 "authorized_key_users": [getuser()]}


def test_install_authorized_keys_fresh():
    with temp_dir() as temp:
        _install_authorized_keys(test_logger(), KEYS_USERDATA, manager=TestAuthorizedKeysManager(temp))
        _check_key_installed(temp, KEY1)


def test_install_authorized_keys_append():
    with temp_dir() as temp:
        ssh_dir = join(temp, ".ssh")
        makedirs(ssh_dir, mode=0700)
        authorized_keys_file = join(ssh_dir, "authorized_keys")
        key2 = "ssh-rss ABCD bob@example.org"
        open(authorized_keys_file, "w").write("%s\n" % key2)
        _install_authorized_keys(test_logger(), KEYS_USERDATA, manager=TestAuthorizedKeysManager(temp))
        _check_key_installed(temp, KEY1)
        _check_key_installed(temp, key2)


def _check_key_installed(mock_home_dir, key):
    ssh_dir = join(mock_home_dir, ".ssh")
    assert exists(ssh_dir)
    assert stat(ssh_dir).st_mode & 0777 == 0700, oct(stat(ssh_dir).st_mode & 0777)
    authorized_keys_file = join(ssh_dir, "authorized_keys")
    assert exists(authorized_keys_file)
    assert open(authorized_keys_file, "r").read().find("%s\n" % key) >= 0
    assert stat(authorized_keys_file).st_mode & 0777 == 0600


def test_install_conf_files():
    with temp_dir() as temp:
        ud = {"conf_files": [{"path": join(temp, "test1"), "content": encodestring("Hello World!")}]}
        _install_conf_files(test_logger(), ud)
        assert open(join(temp, "test1"), "r").read() == "Hello World!"


TEST_NGINX_CONF = """
http {
    default_type  application/octet-stream;

    upstream galaxy_app {
        server localhost:8080;
    }
}
"""


def test_configure_nginx_simple():
    with temp_dir() as temp:
        conf_path = join(temp, "nginx.conf")
        ud = {"nginx_conf_contents": encodestring(TEST_NGINX_CONF),
              "nginx_conf_path": conf_path}
        _configure_nginx(test_logger(), ud)
        assert open(conf_path, "r").read() == TEST_NGINX_CONF


def test_configure_nginx_simple_multi_web_threads():
    with temp_dir() as temp:
        conf_path = join(temp, "nginx.conf")
        ud = {"nginx_conf_contents": encodestring(TEST_NGINX_CONF),
              "nginx_conf_path": conf_path,
              "configure_multiple_galaxy_processes": True,
              "web_thread_count": 2}
        _configure_nginx(test_logger(), ud)
        rewritten_contents = open(conf_path, "r").read()
        # Check exactly two web threads configured in nginx.conf.
        assert rewritten_contents.find("server localhost:8080;") >= 0
        assert rewritten_contents.find("server localhost:8081;") >= 0
        assert rewritten_contents.find("server localhost:8082;") == -1


def test_reconfigure_nginx_disabled():
    with temp_dir() as temp:
        conf_path = join(temp, "nginx.conf")
        ud = {"nginx_conf_contents": encodestring(TEST_NGINX_CONF),
              "nginx_conf_path": conf_path,
              "configure_multiple_galaxy_processes": True,
              "reconfigure_nginx": False,
              "web_thread_count": 2}
        _configure_nginx(test_logger(), ud)
        rewritten_contents = open(conf_path, "r").read()
        assert rewritten_contents == TEST_NGINX_CONF
