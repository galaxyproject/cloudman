#!/usr/bin/env python
"""
This module is used to generate CloudMan's contextualization script ``cm_boot.py``.

Do not directly change ``cm_boot.py`` as changes will get overwritten. Instead,
make desired changes in ``cm/boot`` module and then, from CloudMan's root
directory, invoke ``python make_boot_script.py`` to  generate ``cm_boot.py``.
"""
import logging
import os
import shutil
import sys
import tarfile
import time
import urllib
import urlparse
import yaml
import platform

from boto.exception import BotoServerError, S3ResponseError
from boto.s3.connection import OrdinaryCallingFormat, S3Connection, SubdomainCallingFormat

from .util import _run, _is_running, _make_dir, _nginx_conf_file, _nginx_executable
from .conf import _install_authorized_keys, _install_conf_files, _configure_nginx
from .object_store import _get_file_from_bucket, _key_exists_in_bucket

logging.getLogger('boto').setLevel(logging.INFO)  # Only log boto messages >=INFO

LOG_PATH = '/var/log/cloudman'
CM_HOME = '/mnt/cm'
CM_BOOT_PATH = '/opt/cloudman/boot'
USER_DATA_FILE = 'userData.yaml'
SYSTEM_MESSAGES_FILE = '/mnt/cm/sysmsg.txt'
CM_REMOTE_FILENAME = 'cm.tar.gz'
CM_LOCAL_FILENAME = 'cm.tar.gz'
CM_REV_FILENAME = 'cm_revision.txt'
AMAZON_S3_URL = 'http://s3.amazonaws.com/'  # Obviously, customized for Amazon's S3
DEFAULT_BUCKET_NAME = 'cloudman'

log = None


def _setup_global_logger():
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)-5s %(module)8s:%(lineno)-3d - %(message)s")
    console = logging.StreamHandler()  # log to console - used during testing
    # console.setLevel(logging.INFO) # accepts >INFO levels
    console.setFormatter(formatter)
    log_file = logging.FileHandler(
        os.path.join(LOG_PATH, "%s.log" % os.path.basename(__file__)[:-3]), 'w')  # log to a file
    log_file.setLevel(logging.DEBUG)  # accepts all levels
    log_file.setFormatter(formatter)
    new_logger = logging.root
    new_logger.addHandler(console)
    new_logger.addHandler(log_file)
    new_logger.setLevel(logging.DEBUG)
    return new_logger


def usage():
    print "Usage: python {0} [restart]".format(sys.argv[0])
    sys.exit(1)


def _start_nginx(ud):
    log.info("<< Starting nginx >>")
    # Because nginx needs the upload directory to start properly, create it now.
    # However, because user data will be mounted after boot and because given
    # directory already exists on the user's data disk, must remove it after
    # nginx starts
    _configure_nginx(log, ud)
    # _fix_nginx_upload(ud)
    rmdir = False  # Flag to indicate if a dir should be deleted
    upload_store_dir = '/mnt/galaxy/upload_store'
    # Look for ``upload_store`` definition in nginx conf file and create that dir
    # before starting nginx if it doesn't already exist
    ul = None
    nginx_conf_file = _nginx_conf_file(log)
    if nginx_conf_file:
        with open(nginx_conf_file, 'r') as f:
            lines = f.readlines()
        for line in lines:
            if 'upload_store' in line:
                ul = line
                break
        if ul:
            try:
                upload_store_dir = ul.strip().split(' ')[1].strip(';')
            except Exception, e:
                log.error("Trouble parsing nginx conf line {0}: {1}".format(ul, e))
        if not os.path.exists(upload_store_dir):
            log.debug("Creating tmp dir for nginx {0}".format(upload_store_dir))
            try:
                os.makedirs(upload_store_dir)
                rmdir = True
            except OSError, e:
                log.error("Exception creating dir {0}: {1}".format(
                          upload_store_dir, e))
    else:
        log.error("Could not find nginx.conf: {0}".format(nginx_conf_file))
    nginx_executable = _nginx_executable(log)
    log.debug("Using '{0}' as the nginx executable".format(nginx_executable))
    _, os_release, _ = platform.linux_distribution()
    if not _is_running(log, 'nginx'):
        log.debug("nginx not running; will try and start it now")
        if '16.' in os_release:
            _run(log, 'systemctl start nginx')
        else:
            if not _run(log, nginx_executable):
                _run(log, '/etc/init.d/apache2 stop')
                _run(log, '/etc/init.d/tntnet stop')  # On Ubuntu 12.04, this server also starts?
                _run(log, nginx_executable)
    else:
        # nginx already running, so reload
        log.debug("nginx already running; reloading it")
        if '16.' in os_release:
            _run(log, 'systemctl reload nginx')
        else:
            _run(log, '{0} -s reload'.format(nginx_executable))
    if rmdir or len(os.listdir(upload_store_dir)) == 0:
        log.debug("Deleting tmp dir for nginx {0}".format(upload_store_dir))
        _run(log, 'rm -rf {0}'.format(upload_store_dir))


def _fix_nginx_upload(ud):
    """
    Set ``max_client_body_size`` in nginx config. This is necessary for the
    Galaxy Cloud AMI ``ami-da58aab3``.
    """
    nginx_conf_path = ud.get("nginx_conf_path", _nginx_conf_file(log))
    log.info("Attempting to configure max_client_body_size in {0}".format(nginx_conf_path))
    if os.path.exists(nginx_conf_path):
        # Make sure any duplicate entries are collapsed into one (otherwise,
        # nginx won't start)
        bkup_nginx_conf_path = "/opt/cloudman/boot/original_nginx.conf"
        _run(log, "cp {0} {1}".format(nginx_conf_path, bkup_nginx_conf_path))
        _run(log, "uniq {0} > {1}".format(bkup_nginx_conf_path, nginx_conf_path))
        # Check if the directive is already defined
        already_defined = "grep 'client_max_body_size' {0}".format(nginx_conf_path)
        if not _run(log, already_defined):
            log.debug("Adding client_max_body_size to {0}".format(nginx_conf_path))
            sedargs = """'
/listen/ a\
        client_max_body_size 10G;
' -i %s""" % nginx_conf_path
            _run(log, 'sudo sed %s' % sedargs)
            _run(log, 'sudo kill -HUP `cat /opt/galaxy/pkg/nginx/logs/nginx.pid`')
        else:
            "client_max_body_size is already defined in {0}".format(
                nginx_conf_path)
    else:
        log.error("{0} not found to update".format(nginx_conf_path))


def _get_s3connection(ud):
    access_key = ud['access_key']
    secret_key = ud['secret_key']

    s3_url = ud.get('s3_url', AMAZON_S3_URL)
    cloud_type = ud.get('cloud_type', 'ec2')
    if cloud_type in ['ec2', 'eucalyptus']:
        if s3_url == AMAZON_S3_URL:
            log.info('connecting to Amazon S3 at {0}'.format(s3_url))
        else:
            log.info('connecting to custom S3 url: {0}'.format(s3_url))
        url = urlparse.urlparse(s3_url)
        if url.scheme == 'https':
            is_secure = True
        else:
            is_secure = False
        host = url.hostname
        port = url.port
        path = url.path
        if 'amazonaws' in host:  # TODO fix if anyone other than Amazon uses subdomains for buckets
            calling_format = SubdomainCallingFormat()
        else:
            calling_format = OrdinaryCallingFormat()
    else:  # submitted pre-parsed S3 URL
        # If the use has specified an alternate s3 host, such as swift (for example),
        # then create an s3 connection using their user data
        log.info("Connecting to a custom Object Store")
        is_secure = ud['is_secure']
        host = ud['s3_host']
        port = ud['s3_port']
        calling_format = OrdinaryCallingFormat()
        path = ud['s3_conn_path']

    # get boto connection
    s3_conn = None
    try:
        s3_conn = S3Connection(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            is_secure=is_secure,
            port=port,
            host=host,
            path=path,
            calling_format=calling_format,
        )
        log.debug('Got boto S3 connection: %s' % s3_conn)
    except BotoServerError as e:
        log.error("Exception getting S3 connection; {0}".format(e))

    return s3_conn


def _get_cm(ud):
    log.debug("Deleting /mnt/cm dir before download")
    _run(log, 'rm -rf /mnt/cm')
    log.info("<< Downloading CloudMan >>")
    _make_dir(log, CM_HOME)
    local_cm_file = os.path.join(CM_HOME, CM_LOCAL_FILENAME)
    # See if a custom default bucket was provided and use it then
    if 'bucket_default' in ud:
        default_bucket_name = ud['bucket_default']
        log.debug("Using user-provided default bucket: {0}".format(
            default_bucket_name))
    else:
        default_bucket_name = DEFAULT_BUCKET_NAME
        log.debug("Using default bucket: {0}".format(default_bucket_name))
    use_object_store = ud.get('use_object_store', True)
    s3_conn = None
    if use_object_store and 'access_key' in ud and 'secret_key' in ud:
        if ud['access_key'] is not None and ud['secret_key'] is not None:
            s3_conn = _get_s3connection(ud)
    cm_remote_filename = ud.get('cm_remote_filename', CM_REMOTE_FILENAME)
    # Test for existence of user's bucket and download appropriate CM instance
    if s3_conn:  # if not use_object_store, then s3_connection never gets attempted
        if 'bucket_cluster' in ud:
            # Try to retrieve user's instance of CM
            if _key_exists_in_bucket(log, s3_conn, ud['bucket_cluster'], cm_remote_filename):
                log.info("CloudMan found in cluster bucket '%s'." % ud['bucket_cluster'])
                if _get_file_from_bucket(log, s3_conn, ud['bucket_cluster'],
                                         cm_remote_filename, local_cm_file):
                    # _write_cm_revision_to_file(s3_conn, ud['bucket_cluster'])
                    log.info("Restored Cloudman from bucket_cluster %s" %
                             (ud['bucket_cluster']))
                    return True
        # ELSE: Attempt to retrieve default instance of CM from local s3
        if _get_file_from_bucket(log, s3_conn, default_bucket_name, cm_remote_filename, local_cm_file):
            log.info("Retrieved CloudMan (%s) from bucket '%s' via local s3 connection" % (
                cm_remote_filename, default_bucket_name))
            # _write_cm_revision_to_file(s3_conn, default_bucket_name)
            return True
    # ELSE try from local S3
    if 's3_url' in ud:
        url = os.path.join(ud['s3_url'], default_bucket_name, cm_remote_filename)
    elif 'cloudman_repository' in ud:
        url = ud.get('cloudman_repository')
    elif ('default_bucket_url' in ud):
        url = os.path.join(ud['default_bucket_url'], cm_remote_filename)
    elif 'nectar' in ud.get('cloud_name', '').lower():
        url = "https://{0}:{1}{2}{3}{4}/{5}".format(ud['s3_host'], ud['s3_port'], ud['s3_conn_path'], 'v1/AUTH_377/', default_bucket_name, cm_remote_filename)
    else:
        url = os.path.join(
            AMAZON_S3_URL, default_bucket_name, cm_remote_filename)
    log.info("Attempting to retrieve from from %s" % (url))
    return _run(log, "wget --output-document='%s' '%s'" % (local_cm_file, url))


def _write_cm_revision_to_file(s3_conn, bucket_name):
    """ Get the revision number associated with the CM_REMOTE_FILENAME and save
    it locally to CM_REV_FILENAME """
    with open(os.path.join(CM_HOME, CM_REV_FILENAME), 'w') as rev_file:
        cm_remote_filename = ud.get('cm_remote_filename', CM_REMOTE_FILENAME)
        rev = _get_file_metadata(s3_conn, bucket_name, cm_remote_filename,
                                 'revision')
        log.debug("Revision of remote file '%s' from bucket '%s': %s" % (
            cm_remote_filename, bucket_name, rev))
        if rev:
            rev_file.write(rev)
        else:
            rev_file.write('9999999')


def _get_file_metadata(conn, bucket_name, remote_filename, metadata_key):
    """
    Get ``metadata_key`` value for the given key. If ``bucket_name`` or
    ``remote_filename`` is not found, the method returns ``None``.
    """
    log.debug("Getting metadata '%s' for file '%s' from bucket '%s'" %
              (metadata_key, remote_filename, bucket_name))
    b = None
    for i in range(0, 5):
        try:
            b = conn.get_bucket(bucket_name)
            break
        except S3ResponseError:
            log.debug(
                "Bucket '%s' not found, attempt %s/5" % (bucket_name, i + 1))
            time.sleep(2)
    if b is not None:
        k = b.get_key(remote_filename)
        if k and metadata_key:
            return k.get_metadata(metadata_key)
    return None


def _unpack_cm():
    local_path = os.path.join(CM_HOME, CM_LOCAL_FILENAME)
    log.info("<< Unpacking CloudMan from %s >>" % local_path)
    tar = tarfile.open(local_path, "r:gz")
    tar.extractall(CM_HOME)  # Extract contents of downloaded file to CM_HOME
    if ("run.sh" not in tar.getnames() and './run.sh' not in tar.getnames()):
        # In this case (e.g. direct download from bitbucket) cloudman
        # was extracted into a subdirectory of CM_HOME. Find that
        # subdirectory and move all the files in it back to CM_HOME.
        first_entry = tar.getnames()[0]
        extracted_dir = first_entry.split("/")[0]
        for extracted_file in os.listdir(os.path.join(CM_HOME, extracted_dir)):
            shutil.move(
                os.path.join(CM_HOME, extracted_dir, extracted_file), CM_HOME)


def _cm_venv_path():
    return os.path.join(CM_BOOT_PATH, '.venv')


def _cm_venv_activate_command():
    return os.path.join(_cm_venv_path(), 'bin/activate')


def _with_cm_venv(cmd):
    return (". {0} && {1}".format(_cm_venv_activate_command(), cmd))


def _cm_virtualenv_exists():
    """
    Check if cloudman's virtualenv exists. If so, return ``True``;
    Otherwise, return ``False``.
    """
    if os.path.exists(_cm_venv_activate_command()):
        log.debug("virtualenv seems to be installed")
        return True
    log.debug("virtualenv does not exist")
    return False


def _cm_create_virtualenv():
    """
    Creates a virtualenv for cloudman
    """
    _run(log, "virtualenv {0}".format(_cm_venv_path()))


def _get_cm_control_command(action='--daemon', ex_cmd=None, ex_options=None):
    """
    Compose a system level command used to control (i.e., start/stop) CloudMan.
    Accepted values to the ``action`` argument are: ``--daemon``, ``--stop-daemon``
    or ``--reload``. Note that this method will check if a virtualenv
    ``cm_venv_name`` exists and, if it does, the returned control command
    will include activation of the virtualenv. If the extra command ``ex_cmd``
    is provided, insert that command into the returned activation command.
    If ``ex_options`` is provided, append those to the end of the command.

    Example return string: ``cd /mnt/cm; [ex_cmd]; sh run.sh --daemon``
    """
    if _cm_virtualenv_exists():
        cmd = _with_cm_venv("cd {0}; {1}; sh run.sh {2} {3}"
                            .format(CM_HOME, ex_cmd, action, ex_options))
    else:
        cmd = ("cd {0}; {1}; sh run.sh {2} {3}"
               .format(CM_HOME, ex_cmd, action, ex_options))
    return cmd


def _start_cm():
    if not _cm_virtualenv_exists():
        _cm_create_virtualenv()
    src = os.path.join(CM_BOOT_PATH, USER_DATA_FILE)
    dest = os.path.join(CM_HOME, USER_DATA_FILE)
    log.debug("Copying user data file from '{0}' to '{1}'".format(src, dest))
    shutil.copyfile(src, dest)
    os.chmod(dest, 0600)
    log.info("<< Starting CloudMan in %s >>" % CM_HOME)
    ex_cmd = "pip install -r {0}".format(os.path.join(CM_HOME, "requirements.txt"))
    ex_options = "--log-file=/var/log/cloudman/cloudman.log"
    _run(log, _get_cm_control_command(action='--daemon', ex_cmd=ex_cmd,
                                      ex_options=ex_options))


def _stop_cm(clean=False):
    log.info("<< Stopping CloudMan from %s >>" % CM_HOME)
    _run(log, _get_cm_control_command(action='--stop-daemon'))
    if clean:
        _run(log, 'rm -rf {0}'.format(CM_HOME))


def _start(ud):
    if _get_cm(ud):
        _unpack_cm()
        _start_cm()


def _restart_cm(ud, clean=False):
    log.info("<< Restarting CloudMan >>")
    _stop_cm(clean=clean)
    _start(ud)


def _fix_etc_hosts():
    """ Without editing /etc/hosts, there are issues with hostname command
        on NeCTAR (and consequently with setting up SGE).
    """
    # TODO decide if this should be done in ec2autorun instead
    try:
        log.debug("Fixing /etc/hosts on NeCTAR")
        fp = urllib.urlopen('http://169.254.169.254/latest/meta-data/local-ipv4')
        ip = fp.read()
        fp = urllib.urlopen('http://169.254.169.254/latest/meta-data/public-hostname')
        hn = fp.read()
        line = "{ip} {hn1} {hn2}".format(ip=ip, hn1=hn, hn2=hn.split('.')[0])
        with open('/etc/hosts', 'a+') as f:
            if not any(line.strip() == x.rstrip('\r\n') for x in f):
                log.debug("Appending line %s to /etc/hosts" % line)
                f.write("# Added by CloudMan for NeCTAR\n")
                f.write(line + '\n')
    except Exception, e:
        log.error("Trouble fixing /etc/hosts on NeCTAR: {0}".format(e))


def _system_message(message_contents):
    """ Create SYSTEM_MESSAGES_FILE file w/contents as specified.
    This file is displayed in the UI, and can be embedded in nginx 502 (/opt/galaxy/pkg/nginx/html/errdoc/gc2_502.html)
    """
    # First write contents to file.
    if os.path.exists(SYSTEM_MESSAGES_FILE):
        with open(SYSTEM_MESSAGES_FILE, 'a+') as f:
            f.write(message_contents)
    # Copy message to appropriate places in nginx err_502.html pages.
    # possible_nginx_paths = ['/opt/galaxy/pkg/nginx/html/errdoc/gc2_502.html',
    #                         '/usr/nginx/html/errdoc/gc2_502.html']


def main():
    global log
    log = _setup_global_logger()
    with open(os.path.join(CM_BOOT_PATH, USER_DATA_FILE)) as ud_file:
        ud = yaml.load(ud_file)
    if len(sys.argv) > 1:
        if sys.argv[1] == 'restart':
            _restart_cm(ud, clean=True)
            sys.exit(0)
        else:
            usage()

    _install_conf_files(log, ud)
    _install_authorized_keys(log, ud)

    if 'no_start' not in ud:
        _start_nginx(ud)
        _start(ud)
    log.info("---> %s done <---" % sys.argv[0])
    sys.exit(0)

if __name__ == "__main__":
    main()
