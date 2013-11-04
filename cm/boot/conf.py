import os
from .util import _run
import base64
import re


class AuthorizedKeysManager(object):

    def __init__(self):
        self.sudo_cmd = "sudo"  # Hack to allow override sudo user during testing.

    def _get_home_dir(self, user):
        path = os.path.expanduser("~%s" % user)
        return path if os.path.exists(path) else None

    def add_authorized_key(self, log, user, authorized_key):
        home_dir = self._get_home_dir(user)
        sudo_cmd = self.sudo_cmd
        if home_dir:
            ssh_dir = os.path.join(home_dir, ".ssh")
            if not os.path.exists(ssh_dir):
                if not (_run(log, "%s mkdir -p '%s'" % (sudo_cmd, ssh_dir)) and \
                        _run(log, "%s chown %s '%s'" % (sudo_cmd, user, ssh_dir)) and \
                        _run(log, "%s chmod 700 '%s'" % (sudo_cmd, ssh_dir))):
                    return False
            authorized_keys_file = os.path.join(ssh_dir, "authorized_keys2")
            if not os.path.exists(authorized_keys_file):
                authorized_keys_file = os.path.join(ssh_dir, "authorized_keys")

            cmd = "KEY=%s; %s grep $KEY '%s' || %s echo $KEY >> '%s'" % \
                (_shellquote(authorized_key), sudo_cmd, authorized_keys_file, sudo_cmd, authorized_keys_file)
            return _run(log, cmd) and \
                   _run(log, "%s chown %s '%s'" % (sudo_cmd, user, authorized_keys_file)) and \
                   _run(log, "%s chmod 600 '%s'" % (sudo_cmd, authorized_keys_file))
        return True


def _install_authorized_keys(log, ud, manager=AuthorizedKeysManager()):
    authorized_keys = ud.get("authorized_keys", None) or []
    authorized_key_users = ud.get("authorized_key_users", ["ubuntu", "galaxy"])
    for authorized_key in authorized_keys:
        for user in authorized_key_users:
            if not manager.add_authorized_key(log, user, authorized_key):
                log.warn("Failed to add authorized_key for user %s" % user)


def _write_conf_file(log, contents_descriptor, path):
    destination_directory = os.path.dirname(path)
    if not os.path.exists(destination_directory):
        os.makedirs(destination_directory)
    if contents_descriptor.startswith("http") or contents_descriptor.startswith("ftp"):
        log.info("Fetching file from %s" % contents_descriptor)
        _run(log, "wget --output-document='%s' '%s'" % (contents_descriptor, path))
    else:
        log.info("Writing out configuration file encoded in user-data:")
        with open(path, "w") as output:
            output.write(base64.b64decode(contents_descriptor))


def _install_conf_files(log, ud):
    # Currently using this to configure nginx SSL, but it could be used
    # to configure anything really.
    conf_files = ud.get('conf_files', [])
    for conf_file_obj in conf_files:
        path = conf_file_obj.get('path', None)
        content = conf_file_obj.get('content', None)
        if path is None:
            log.warn("Found conf file with no path, skipping.")
            continue
        if content is None:
            log.warn("Found conf file with not content, skipping.")
            continue
        _write_conf_file(log, content, path)


def _configure_nginx(log, ud):
    # User specified nginx.conf file, can be specified as
    # url or base64 encoded plain-text.
    nginx_conf = ud.get("nginx_conf_contents", None)
    nginx_conf_path = ud.get("nginx_conf_path", "/usr/nginx/conf/nginx.conf")
    if nginx_conf:
        _write_conf_file(log, nginx_conf, nginx_conf_path)
    reconfigure_nginx = ud.get("reconfigure_nginx", True)
    if reconfigure_nginx:
        _reconfigure_nginx(ud, nginx_conf_path)


def _reconfigure_nginx(ud, nginx_conf_path):
    configure_multiple_galaxy_processes = ud.get(
        "configure_multiple_galaxy_processes", True)
    web_threads = ud.get("web_thread_count", 1)
    if configure_multiple_galaxy_processes and web_threads > 1:
        ports = [8080 + i for i in range(web_threads)]
        servers = ["server localhost:%d;" % port for port in ports]
        upstream_galaxy_app_conf = "upstream galaxy_app { %s } " % "".join(
            servers)
        nginx_conf = open(nginx_conf_path, "r").read()
        new_nginx_conf = re.sub("upstream galaxy_app.*\\{([^\\}]*)}",
                                upstream_galaxy_app_conf, nginx_conf)
        open(nginx_conf_path, "w").write(new_nginx_conf).close()


def _shellquote(s):
    """
    http://stackoverflow.com/questions/35817/how-to-escape-os-system-calls-in-python
    """
    return "'" + s.replace("'", "'\\''") + "'"
