#!/usr/bin/env python
"\nThis module is used to generate CloudMan's contextualization script ``cm_boot.py``.\n\nDo not directly change ``cm_boot.py`` as changes will get overwritten. Instead,\nmake desired changes in ``cm/boot`` module and then, from CloudMan's root\ndirectory, invoke ``python make_boot_script.py`` to  generate ``cm_boot.py``.\n"
import logging
import os
import shutil
import sys
import tarfile
import time
import urllib
import urlparse
import yaml
from boto.exception import BotoServerError, S3ResponseError
from boto.s3.connection import OrdinaryCallingFormat, S3Connection, SubdomainCallingFormat
import os
import subprocess

def _run(log, cmd):
    if (not cmd):
        log.error("Trying to run an empty command? '{0}'".format(cmd))
        return False
    try:
        process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (stdout, stderr) = process.communicate()
        if (process.returncode == 0):
            log.debug(("Successfully ran '%s'" % cmd))
            if stdout:
                return stdout
            else:
                return True
        else:
            log.error(("Error running '%s'. Process returned code '%s' and following stderr: '%s'" % (cmd, process.returncode, stderr)))
            return False
    except Exception as e:
        log.error(("Exception running '%s': '%s'" % (cmd, e)))
        return False

def _is_running(log, process_name):
    '\n    Check if a process with ``process_name`` is running. Return ``True`` if so,\n    ``False`` otherwise.\n    '
    p = _run(log, 'ps xa | grep {0} | grep -v grep'.format(process_name))
    return (p and (process_name in p))

def _make_dir(log, path):
    log.debug(("Checking existence of directory '%s'" % path))
    if (not os.path.exists(path)):
        try:
            log.debug(("Creating directory '%s'" % path))
            os.makedirs(path, 493)
            log.debug(("Directory '%s' successfully created." % path))
        except OSError as e:
            log.error(("Making directory '%s' failed: %s" % (path, e)))
    else:
        log.debug(("Directory '%s' exists." % path))

def _which(log, program, additional_paths=[]):
    "\n    Like *NIX's ``which`` command, look for ``program`` in the user's $PATH\n    and ``additional_paths`` and return an absolute path for the ``program``. If\n    the ``program`` was not found, return ``None``.\n    "

    def _is_exec(fpath):
        log.debug(("%s is file: %s; it's executable: %s" % (fpath, os.path.isfile(fpath), os.access(fpath, os.X_OK))))
        return (os.path.isfile(fpath) and os.access(fpath, os.X_OK))
    (fpath, fname) = os.path.split(program)
    if fpath:
        if _is_exec(program):
            return program
    else:
        for path in (os.environ['PATH'].split(os.pathsep) + additional_paths):
            path = path.strip('"')
            exec_file = os.path.join(path, program)
            if _is_exec(exec_file):
                return exec_file
    return None

def _nginx_executable(log):
    '\n    Get the path of the nginx executable\n    '
    possible_paths = ['/usr/sbin', '/usr/nginx/sbin', '/opt/galaxy/pkg/nginx/sbin']
    return _which(log, 'nginx', possible_paths)

def _nginx_conf_dir():
    '\n    Look around at possible nginx directory locations (from published\n    images) and resort to a file system search\n    '
    for path in ['/etc/nginx', '/usr/nginx/conf', '/opt/galaxy/pkg/nginx/conf']:
        if os.path.exists(path):
            return path
    return ''

def _nginx_conf_file(log):
    '\n    Get the path of the nginx conf file, namely ``nginx.conf``\n    '
    path = os.path.join(_nginx_conf_dir(), 'nginx.conf')
    if os.path.exists(path):
        return path
    return None
import base64
import os
import re


class AuthorizedKeysManager(object):

    def __init__(self):
        self.sudo_cmd = 'sudo'

    def _get_home_dir(self, user):
        path = os.path.expanduser(('~%s' % user))
        return (path if os.path.exists(path) else None)

    def add_authorized_key(self, log, user, authorized_key):
        home_dir = self._get_home_dir(user)
        sudo_cmd = self.sudo_cmd
        if home_dir:
            ssh_dir = os.path.join(home_dir, '.ssh')
            if (not os.path.exists(ssh_dir)):
                if (not (_run(log, ("%s mkdir -p '%s'" % (sudo_cmd, ssh_dir))) and _run(log, ("%s chown %s '%s'" % (sudo_cmd, user, ssh_dir))) and _run(log, ("%s chmod 700 '%s'" % (sudo_cmd, ssh_dir))))):
                    return False
            authorized_keys_file = os.path.join(ssh_dir, 'authorized_keys2')
            if (not os.path.exists(authorized_keys_file)):
                authorized_keys_file = os.path.join(ssh_dir, 'authorized_keys')
            cmd = ("KEY=%s; %s grep $KEY '%s' || %s echo $KEY >> '%s'" % (_shellquote(authorized_key), sudo_cmd, authorized_keys_file, sudo_cmd, authorized_keys_file))
            return (_run(log, cmd) and _run(log, ("%s chown %s '%s'" % (sudo_cmd, user, authorized_keys_file))) and _run(log, ("%s chmod 600 '%s'" % (sudo_cmd, authorized_keys_file))))
        return True

def _install_authorized_keys(log, ud, manager=AuthorizedKeysManager()):
    authorized_keys = (ud.get('authorized_keys', None) or [])
    authorized_key_users = ud.get('authorized_key_users', ['ubuntu', 'galaxy'])
    for authorized_key in authorized_keys:
        for user in authorized_key_users:
            if (not manager.add_authorized_key(log, user, authorized_key)):
                log.warn(('Failed to add authorized_key for user %s' % user))

def _write_conf_file(log, contents_descriptor, path):
    destination_directory = os.path.dirname(path)
    if (not os.path.exists(destination_directory)):
        os.makedirs(destination_directory)
    if (contents_descriptor.startswith('http') or contents_descriptor.startswith('ftp')):
        log.info(('Fetching file from %s' % contents_descriptor))
        _run(log, ("wget --output-document='%s' '%s'" % (contents_descriptor, path)))
    else:
        log.info('Writing out configuration file encoded in user-data:')
        with open(path, 'w') as output:
            output.write(base64.b64decode(contents_descriptor))

def _install_conf_files(log, ud):
    conf_files = ud.get('conf_files', [])
    for conf_file_obj in conf_files:
        path = conf_file_obj.get('path', None)
        content = conf_file_obj.get('content', None)
        if (path is None):
            log.warn('Found conf file with no path, skipping.')
            continue
        if (content is None):
            log.warn('Found conf file with not content, skipping.')
            continue
        _write_conf_file(log, content, path)

def _configure_nginx(log, ud):
    nginx_conf = ud.get('nginx_conf_contents', None)
    nginx_conf_path = ud.get('nginx_conf_path', _nginx_conf_file(log))
    if nginx_conf:
        _write_conf_file(log, nginx_conf, nginx_conf_path)
    reconfigure_nginx = ud.get('reconfigure_nginx', True)
    if reconfigure_nginx:
        _reconfigure_nginx(ud, nginx_conf_path, log)

def _reconfigure_nginx(ud, nginx_conf_path, log):
    log.debug('Reconfiguring nginx conf')
    configure_multiple_galaxy_processes = ud.get('configure_multiple_galaxy_processes', False)
    web_threads = ud.get('web_thread_count', 3)
    if (configure_multiple_galaxy_processes and (web_threads > 1)):
        log.debug(('Reconfiguring nginx to support Galaxy running %s web threads.' % web_threads))
        ports = [(8080 + i) for i in range(web_threads)]
        servers = [('server localhost:%d;' % port) for port in ports]
        upstream_galaxy_app_conf = ('upstream galaxy_app { %s } ' % ''.join(servers))
        with open(nginx_conf_path, 'r') as old_conf:
            nginx_conf = old_conf.read()
        new_nginx_conf = re.sub('upstream galaxy_app.*\\{([^\\}]*)}', upstream_galaxy_app_conf, nginx_conf)
        with open(nginx_conf_path, 'w') as new_conf:
            new_conf.write(new_nginx_conf)

def _shellquote(s):
    '\n    http://stackoverflow.com/questions/35817/how-to-escape-os-system-calls-in-python\n    '
    return (("'" + s.replace("'", "'\\''")) + "'")
from boto.exception import S3ResponseError
from boto.s3.key import Key

def _get_file_from_bucket(log, s3_conn, bucket_name, remote_filename, local_filename):
    log.debug(('Getting file %s from bucket %s' % (remote_filename, bucket_name)))
    try:
        b = s3_conn.get_bucket(bucket_name, validate=False)
        k = Key(b, remote_filename)
        log.debug(("Attempting to retrieve file '%s' from bucket '%s'" % (remote_filename, bucket_name)))
        if k.exists():
            k.get_contents_to_filename(local_filename)
            log.info(("Successfully retrieved file '%s' from bucket '%s' via connection '%s' to '%s'" % (remote_filename, bucket_name, s3_conn.host, local_filename)))
            return True
        else:
            log.error(("File '%s' in bucket '%s' not found." % (remote_filename, bucket_name)))
            return False
    except S3ResponseError as e:
        log.error(("Failed to get file '%s' from bucket '%s': %s" % (remote_filename, bucket_name, e)))
        return False

def _key_exists_in_bucket(log, s3_conn, bucket_name, key_name):
    '\n    Check if an object (ie, key) of name ``key_name`` exists in bucket\n    ``bucket_name``. Return ``True`` if so, ``False`` otherwise.\n    '
    b = s3_conn.get_bucket(bucket_name, validate=False)
    k = Key(b, key_name)
    log.debug(("Checking if key '%s' exists in bucket '%s'" % (key_name, bucket_name)))
    try:
        return k.exists()
    except S3ResponseError as e:
        log.error(("Failed to checkf if file '%s' exists in bucket '%s': %s" % (key_name, bucket_name, e)))
        return False
logging.getLogger('boto').setLevel(logging.INFO)
LOG_PATH = '/var/log/cloudman'
CM_HOME = '/mnt/cm'
CM_BOOT_PATH = '/opt/cloudman/boot'
USER_DATA_FILE = 'userData.yaml'
SYSTEM_MESSAGES_FILE = '/mnt/cm/sysmsg.txt'
CM_REMOTE_FILENAME = 'cm.tar.gz'
CM_LOCAL_FILENAME = 'cm.tar.gz'
CM_REV_FILENAME = 'cm_revision.txt'
AMAZON_S3_URL = 'http://s3.amazonaws.com/'
DEFAULT_BUCKET_NAME = 'cloudman'
log = None

def _setup_global_logger():
    formatter = logging.Formatter('%(asctime)s %(levelname)-5s %(module)8s:%(lineno)-3d - %(message)s')
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    log_file = logging.FileHandler(os.path.join(LOG_PATH, ('%s.log' % os.path.basename(__file__)[:(-3)])), 'w')
    log_file.setLevel(logging.DEBUG)
    log_file.setFormatter(formatter)
    new_logger = logging.root
    new_logger.addHandler(console)
    new_logger.addHandler(log_file)
    new_logger.setLevel(logging.DEBUG)
    return new_logger

def usage():
    print 'Usage: python {0} [restart]'.format(sys.argv[0])
    sys.exit(1)

def _start_nginx(ud):
    log.info('<< Starting nginx >>')
    _configure_nginx(log, ud)
    rmdir = False
    upload_store_dir = '/mnt/galaxy/upload_store'
    ul = None
    nginx_conf_file = _nginx_conf_file(log)
    if nginx_conf_file:
        with open(nginx_conf_file, 'r') as f:
            lines = f.readlines()
        for line in lines:
            if ('upload_store' in line):
                ul = line
                break
        if ul:
            try:
                upload_store_dir = ul.strip().split(' ')[1].strip(';')
            except Exception as e:
                log.error('Trouble parsing nginx conf line {0}: {1}'.format(ul, e))
        if (not os.path.exists(upload_store_dir)):
            log.debug('Creating tmp dir for nginx {0}'.format(upload_store_dir))
            try:
                os.makedirs(upload_store_dir)
                rmdir = True
            except OSError as e:
                log.error('Exception creating dir {0}: {1}'.format(upload_store_dir, e))
    else:
        log.error('Could not find nginx.conf: {0}'.format(nginx_conf_file))
    nginx_executable = _nginx_executable(log)
    log.debug("Using '{0}' as the nginx executable".format(nginx_executable))
    if (not _is_running(log, 'nginx')):
        log.debug('nginx not running; will try and start it now')
        if (not _run(log, nginx_executable)):
            _run(log, '/etc/init.d/apache2 stop')
            _run(log, '/etc/init.d/tntnet stop')
            _run(log, nginx_executable)
    else:
        log.debug('nginx already running; reloading it')
        _run(log, '{0} -s reload'.format(nginx_executable))
    if (rmdir or (len(os.listdir(upload_store_dir)) == 0)):
        log.debug('Deleting tmp dir for nginx {0}'.format(upload_store_dir))
        _run(log, 'rm -rf {0}'.format(upload_store_dir))

def _fix_nginx_upload(ud):
    '\n    Set ``max_client_body_size`` in nginx config. This is necessary for the\n    Galaxy Cloud AMI ``ami-da58aab3``.\n    '
    nginx_conf_path = ud.get('nginx_conf_path', _nginx_conf_file(log))
    log.info('Attempting to configure max_client_body_size in {0}'.format(nginx_conf_path))
    if os.path.exists(nginx_conf_path):
        bkup_nginx_conf_path = '/opt/cloudman/boot/original_nginx.conf'
        _run(log, 'cp {0} {1}'.format(nginx_conf_path, bkup_nginx_conf_path))
        _run(log, 'uniq {0} > {1}'.format(bkup_nginx_conf_path, nginx_conf_path))
        already_defined = "grep 'client_max_body_size' {0}".format(nginx_conf_path)
        if (not _run(log, already_defined)):
            log.debug('Adding client_max_body_size to {0}'.format(nginx_conf_path))
            sedargs = ("'\n/listen/ a        client_max_body_size 10G;\n' -i %s" % nginx_conf_path)
            _run(log, ('sudo sed %s' % sedargs))
            _run(log, 'sudo kill -HUP `cat /opt/galaxy/pkg/nginx/logs/nginx.pid`')
        else:
            'client_max_body_size is already defined in {0}'.format(nginx_conf_path)
    else:
        log.error('{0} not found to update'.format(nginx_conf_path))

def _get_s3connection(ud):
    access_key = ud['access_key']
    secret_key = ud['secret_key']
    s3_url = ud.get('s3_url', AMAZON_S3_URL)
    cloud_type = ud.get('cloud_type', 'ec2')
    if (cloud_type in ['ec2', 'eucalyptus']):
        if (s3_url == AMAZON_S3_URL):
            log.info('connecting to Amazon S3 at {0}'.format(s3_url))
        else:
            log.info('connecting to custom S3 url: {0}'.format(s3_url))
        url = urlparse.urlparse(s3_url)
        if (url.scheme == 'https'):
            is_secure = True
        else:
            is_secure = False
        host = url.hostname
        port = url.port
        path = url.path
        if ('amazonaws' in host):
            calling_format = SubdomainCallingFormat()
        else:
            calling_format = OrdinaryCallingFormat()
    else:
        log.info('Connecting to a custom Object Store')
        is_secure = ud['is_secure']
        host = ud['s3_host']
        port = ud['s3_port']
        calling_format = OrdinaryCallingFormat()
        path = ud['s3_conn_path']
    s3_conn = None
    try:
        s3_conn = S3Connection(aws_access_key_id=access_key, aws_secret_access_key=secret_key, is_secure=is_secure, port=port, host=host, path=path, calling_format=calling_format)
        log.debug(('Got boto S3 connection: %s' % s3_conn))
    except BotoServerError as e:
        log.error('Exception getting S3 connection; {0}'.format(e))
    return s3_conn

def _get_cm(ud):
    log.debug('Deleting /mnt/cm dir before download')
    _run(log, 'rm -rf /mnt/cm')
    log.info('<< Downloading CloudMan >>')
    _make_dir(log, CM_HOME)
    local_cm_file = os.path.join(CM_HOME, CM_LOCAL_FILENAME)
    if ('bucket_default' in ud):
        default_bucket_name = ud['bucket_default']
        log.debug('Using user-provided default bucket: {0}'.format(default_bucket_name))
    else:
        default_bucket_name = DEFAULT_BUCKET_NAME
        log.debug('Using default bucket: {0}'.format(default_bucket_name))
    use_object_store = ud.get('use_object_store', True)
    s3_conn = None
    if (use_object_store and ('access_key' in ud) and ('secret_key' in ud)):
        if ((ud['access_key'] is not None) and (ud['secret_key'] is not None)):
            s3_conn = _get_s3connection(ud)
    if s3_conn:
        if ('bucket_cluster' in ud):
            if _key_exists_in_bucket(log, s3_conn, ud['bucket_cluster'], CM_REMOTE_FILENAME):
                log.info(("CloudMan found in cluster bucket '%s'." % ud['bucket_cluster']))
                if _get_file_from_bucket(log, s3_conn, ud['bucket_cluster'], CM_REMOTE_FILENAME, local_cm_file):
                    log.info(('Restored Cloudman from bucket_cluster %s' % ud['bucket_cluster']))
                    return True
        if _get_file_from_bucket(log, s3_conn, default_bucket_name, CM_REMOTE_FILENAME, local_cm_file):
            log.info(("Retrieved CloudMan (%s) from bucket '%s' via local s3 connection" % (CM_REMOTE_FILENAME, default_bucket_name)))
            return True
    if ('s3_url' in ud):
        url = os.path.join(ud['s3_url'], default_bucket_name, CM_REMOTE_FILENAME)
    elif ('cloudman_repository' in ud):
        url = ud.get('cloudman_repository')
    elif ('default_bucket_url' in ud):
        url = os.path.join(ud['default_bucket_url'], CM_REMOTE_FILENAME)
    elif ('nectar' in ud.get('cloud_name', '').lower()):
        url = 'https://{0}:{1}{2}{3}{4}/{5}'.format(ud['s3_host'], ud['s3_port'], ud['s3_conn_path'], 'V1/AUTH_377/', default_bucket_name, CM_REMOTE_FILENAME)
    else:
        url = os.path.join(AMAZON_S3_URL, default_bucket_name, CM_REMOTE_FILENAME)
    log.info(('Attempting to retrieve from from %s' % url))
    return _run(log, ("wget --output-document='%s' '%s'" % (local_cm_file, url)))

def _write_cm_revision_to_file(s3_conn, bucket_name):
    ' Get the revision number associated with the CM_REMOTE_FILENAME and save\n    it locally to CM_REV_FILENAME '
    with open(os.path.join(CM_HOME, CM_REV_FILENAME), 'w') as rev_file:
        rev = _get_file_metadata(s3_conn, bucket_name, CM_REMOTE_FILENAME, 'revision')
        log.debug(("Revision of remote file '%s' from bucket '%s': %s" % (CM_REMOTE_FILENAME, bucket_name, rev)))
        if rev:
            rev_file.write(rev)
        else:
            rev_file.write('9999999')

def _get_file_metadata(conn, bucket_name, remote_filename, metadata_key):
    '\n    Get ``metadata_key`` value for the given key. If ``bucket_name`` or\n    ``remote_filename`` is not found, the method returns ``None``.\n    '
    log.debug(("Getting metadata '%s' for file '%s' from bucket '%s'" % (metadata_key, remote_filename, bucket_name)))
    b = None
    for i in range(0, 5):
        try:
            b = conn.get_bucket(bucket_name)
            break
        except S3ResponseError:
            log.debug(("Bucket '%s' not found, attempt %s/5" % (bucket_name, (i + 1))))
            time.sleep(2)
    if (b is not None):
        k = b.get_key(remote_filename)
        if (k and metadata_key):
            return k.get_metadata(metadata_key)
    return None

def _unpack_cm():
    local_path = os.path.join(CM_HOME, CM_LOCAL_FILENAME)
    log.info(('<< Unpacking CloudMan from %s >>' % local_path))
    tar = tarfile.open(local_path, 'r:gz')
    tar.extractall(CM_HOME)
    if (('run.sh' not in tar.getnames()) and ('./run.sh' not in tar.getnames())):
        first_entry = tar.getnames()[0]
        extracted_dir = first_entry.split('/')[0]
        for extracted_file in os.listdir(os.path.join(CM_HOME, extracted_dir)):
            shutil.move(os.path.join(CM_HOME, extracted_dir, extracted_file), CM_HOME)

def _venvburrito_home_dir():
    return os.getenv('HOME', '/home/ubuntu')

def _venvburrito_path():
    home_dir = _venvburrito_home_dir()
    vb_path = os.path.join(home_dir, '.venvburrito/startup.sh')
    return vb_path

def _with_venvburrito(cmd):
    home_dir = _venvburrito_home_dir()
    vb_path = _venvburrito_path()
    return "/bin/bash -l -c 'VIRTUALENVWRAPPER_LOG_DIR=/tmp/; HOME={0}; . {1}; {2}'".format(home_dir, vb_path, cmd)

def _virtualenv_exists(venv_name='CM'):
    '\n    Check if virtual-burrito is installed and if a virtualenv named ``venv_name``\n    exists. If so, return ``True``; ``False`` otherwise.\n    '
    if os.path.exists(_venvburrito_path()):
        log.debug('virtual-burrito seems to be installed')
        cm_venv = _run(log, _with_venvburrito('lsvirtualenv | grep {0}'.format(venv_name)))
        if (cm_venv and (venv_name in cm_venv)):
            log.debug("'{0}' virtualenv found".format(venv_name))
            return True
    log.debug("virtual-burrito not installed or '{0}' virtualenv does not exist".format(venv_name))
    return False

def _get_cm_control_command(action='--daemon', cm_venv_name='CM', ex_cmd=None, ex_options=None):
    '\n    Compose a system level command used to control (i.e., start/stop) CloudMan.\n    Accepted values to the ``action`` argument are: ``--daemon``, ``--stop-daemon``\n    or ``--reload``. Note that this method will check if a virtualenv\n    ``cm_venv_name`` exists and, if it does, the returned control command\n    will include activation of the virtualenv. If the extra command ``ex_cmd``\n    is provided, insert that command into the returned activation command.\n    If ``ex_options`` is provided, append those to the end of the command.\n\n    Example return string: ``cd /mnt/cm; [ex_cmd]; sh run.sh --daemon``\n    '
    if _virtualenv_exists(cm_venv_name):
        cmd = _with_venvburrito('workon {0}; cd {1}; {3}; sh run.sh {2} {4}'.format(cm_venv_name, CM_HOME, action, ex_cmd, ex_options))
    else:
        cmd = 'cd {0}; {2}; sh run.sh {1} {3}'.format(CM_HOME, action, ex_cmd, ex_options)
    return cmd

def _start_cm():
    src = os.path.join(CM_BOOT_PATH, USER_DATA_FILE)
    dest = os.path.join(CM_HOME, USER_DATA_FILE)
    log.debug("Copying user data file from '{0}' to '{1}'".format(src, dest))
    shutil.copyfile(src, dest)
    os.chmod(dest, 384)
    log.info(('<< Starting CloudMan in %s >>' % CM_HOME))
    ex_cmd = 'pip install -r {0}'.format(os.path.join(CM_HOME, 'requirements.txt'))
    ex_options = '--log-file=/var/log/cloudman/cloudman.log'
    _run(log, _get_cm_control_command(action='--daemon', ex_cmd=ex_cmd, ex_options=ex_options))

def _stop_cm(clean=False):
    log.info(('<< Stopping CloudMan from %s >>' % CM_HOME))
    _run(log, _get_cm_control_command(action='--stop-daemon'))
    if clean:
        _run(log, 'rm -rf {0}'.format(CM_HOME))

def _start(ud):
    if _get_cm(ud):
        _unpack_cm()
        _start_cm()

def _restart_cm(ud, clean=False):
    log.info('<< Restarting CloudMan >>')
    _stop_cm(clean=clean)
    _start(ud)

def _fix_etc_hosts():
    ' Without editing /etc/hosts, there are issues with hostname command\n        on NeCTAR (and consequently with setting up SGE).\n    '
    try:
        log.debug('Fixing /etc/hosts on NeCTAR')
        fp = urllib.urlopen('http://169.254.169.254/latest/meta-data/local-ipv4')
        ip = fp.read()
        fp = urllib.urlopen('http://169.254.169.254/latest/meta-data/public-hostname')
        hn = fp.read()
        line = '{ip} {hn1} {hn2}'.format(ip=ip, hn1=hn, hn2=hn.split('.')[0])
        with open('/etc/hosts', 'a+') as f:
            if (not any(((line.strip() == x.rstrip('\r\n')) for x in f))):
                log.debug(('Appending line %s to /etc/hosts' % line))
                f.write('# Added by CloudMan for NeCTAR\n')
                f.write((line + '\n'))
    except Exception as e:
        log.error('Trouble fixing /etc/hosts on NeCTAR: {0}'.format(e))

def _system_message(message_contents):
    ' Create SYSTEM_MESSAGES_FILE file w/contents as specified.\n    This file is displayed in the UI, and can be embedded in nginx 502 (/opt/galaxy/pkg/nginx/html/errdoc/gc2_502.html)\n    '
    if os.path.exists(SYSTEM_MESSAGES_FILE):
        with open(SYSTEM_MESSAGES_FILE, 'a+') as f:
            f.write(message_contents)

def main():
    global log
    log = _setup_global_logger()
    if (not _virtualenv_exists()):
        _run(log, 'easy_install oca')
        _run(log, 'easy_install Mako==0.7.0')
        _run(log, 'easy_install boto==2.30.0')
        _run(log, 'easy_install hoover')
    with open(os.path.join(CM_BOOT_PATH, USER_DATA_FILE)) as ud_file:
        ud = yaml.load(ud_file)
    if (len(sys.argv) > 1):
        if (sys.argv[1] == 'restart'):
            _restart_cm(ud, clean=True)
            sys.exit(0)
        else:
            usage()
    _install_conf_files(log, ud)
    _install_authorized_keys(log, ud)
    if ('no_start' not in ud):
        if ('nectar' in ud.get('cloud_name', '').lower()):
            _fix_etc_hosts()
        _start_nginx(ud)
        _start(ud)
    log.info(('---> %s done <---' % sys.argv[0]))
    sys.exit(0)
if (__name__ == '__main__'):
    main()