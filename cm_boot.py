#!/usr/bin/env python
"""
Requires: 
    PyYAML http://pyyaml.org/wiki/PyYAMLDocumentation (easy_install pyyaml)
    boto http://code.google.com/p/boto/ (easy_install boto)
"""

import logging, sys, os, subprocess, yaml, tarfile, shutil, time
from boto.s3.connection import S3Connection
from boto.s3.key import Key
from boto.exception import S3ResponseError
logging.getLogger('boto').setLevel(logging.INFO) # Only log boto messages >=INFO

LOCAL_PATH = os.getcwd()
CM_HOME = '/mnt/cm'
CM_BOOT_PATH = '/tmp/cm'
USER_DATA_FILE = 'userData.yaml'
CM_REMOTE_FILENAME = 'cm.tar.gz'
CM_LOCAL_FILENAME = 'cm.tar.gz'
CM_REV_FILENAME = 'cm_revision.txt'
PRS_FILENAME = 'post_start_script' # Post start script file name - script name in cluster bucket must matchi this!
SERVICE_ROOT = 'http://s3.amazonaws.com/' # Obviously, customized for Amazon's S3
DEFAULT_BUCKET_NAME = 'cloudman'

# Logging setup
formatter = logging.Formatter("[%(levelname)s] %(module)s:%(lineno)d %(asctime)s: %(message)s")
console = logging.StreamHandler() # log to console - used during testing
# console.setLevel(logging.INFO) # accepts >INFO levels
console.setFormatter(formatter)
log_file = logging.FileHandler(os.path.join(LOCAL_PATH, "%s.log" % sys.argv[0]), 'w') # log to a file
log_file.setLevel(logging.DEBUG) # accepts all levels
log_file.setFormatter(formatter)
log = logging.root
log.addHandler( console )
log.addHandler( log_file )
log.setLevel( logging.DEBUG )

def usage():
    print "Usage: python {0} [restart]".format(sys.argv[0])
    sys.exit(1)

def _run(cmd):
    process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    if process.returncode == 0:
        log.debug("Successfully ran '%s'" % cmd)
        return True
    else:
        log.error("Error running '%s'. Process returned code '%s' and following stderr: %s" % (cmd, process.returncode, stderr))
        return False

def _make_dir(path):
    log.debug("Checking existence of directory '%s'" % path)
    if not os.path.exists( path ):
        try:
            log.debug("Creating directory '%s'" % path)
            os.makedirs(path, 0755)
            log.debug("Directory '%s' successfully created." % path)
        except OSError, e:
            log.error("Making directory '%s' failed: %s" % (path, e))
    else:
        log.debug("Directory '%s' exists." % path)

def _get_file_from_bucket(s3_conn, bucket_name, remote_filename, local_filename):
    try:
        b = s3_conn.get_bucket(bucket_name)
        k = Key(b, remote_filename)
    
        log.debug("Attempting to retrieve file '%s' from bucket '%s'" % (remote_filename, bucket_name))
        if k.exists():
            k.get_contents_to_filename(local_filename)
            log.info("Successfully retrieved file '%s' from bucket '%s' to '%s'" % (remote_filename, bucket_name, local_filename))
            return True
        else:
            log.error("File '%s' in bucket '%s' not found." % (remote_filename, bucket_name))
            return False
    except S3ResponseError, e:
        log.error("Failed to get file '%s' from bucket '%s': %s" % (remote_filename, bucket_name, e))
        return False

def _start_nginx():
    log.info("<< Starting nginx >>")
    # Because nginx needs the uplaod directory to start properly, create it now.
    # However, because user data will be mounted after boot and because given
    # directory already exists on the user's data disk, must remove it after 
    # nginx starts
    # In case an nginx configuration file different than the one on the image needs to be included 
    # local_nginx_conf_file = '/opt/galaxy/conf/nginx.conf'
    # url = 'http://userwww.service.emory.edu/~eafgan/content/nginx.conf'
    # log.info("Getting nginx conf file (using wget) from '%s' and saving it to '%s'" % (url, local_nginx_conf_file))
    # _run('wget --output-document=%s %s' % (local_nginx_conf_file, url))
    rmdir = False # Flag to indicate if a dir should be deleted
    if not os.path.exists('/mnt/galaxyData/upload_store'):
        rmdir = True
        os.makedirs('/mnt/galaxyData/upload_store')
    if not _run('/opt/galaxy/sbin/nginx'):
        _run('/etc/init.d/apache2 stop')
        _run('/opt/galaxy/sbin/nginx')
    if rmdir: 
        _run('rm -rf /mnt/galaxyData')

def _get_cm(ud):
    log.info("<< Downloading CloudMan >>")
    _make_dir(CM_HOME)
    local_cm_file = os.path.join(CM_HOME, CM_LOCAL_FILENAME)
    # Test for existence of user's bucket and download appropriate CM instance
    if ud.has_key('access_key') and ud.has_key('secret_key'):
        if ud['access_key'] is not None and ud['secret_key'] is not None:
            s3_conn = S3Connection(ud['access_key'], ud['secret_key'])
            b = None
            if ud.has_key('bucket_cluster'):
                b = s3_conn.lookup(ud['bucket_cluster'])
            if b is not None: # Try to retrieve user's instance of CM
                log.info("Cluster bucket '%s' found." % b.name)
                if _get_file_from_bucket(s3_conn, b.name, CM_REMOTE_FILENAME, local_cm_file):
                    _write_cm_revision_to_file(s3_conn, b.name)
                    return True
            # Retrieve default instance of CM
            log.info("Could not retrieve CloudMan from cluster bucket; using default CloudMan (%s) from bucket '%s'" % (CM_REMOTE_FILENAME, DEFAULT_BUCKET_NAME))
            if _get_file_from_bucket(s3_conn, DEFAULT_BUCKET_NAME, CM_REMOTE_FILENAME, local_cm_file):
                _write_cm_revision_to_file(s3_conn, DEFAULT_BUCKET_NAME)
                return True
    # Default to public repo and wget
    log.error("Could not retrieve CloudMan from cluster bucket.")
    url = os.path.join(SERVICE_ROOT, DEFAULT_BUCKET_NAME, CM_REMOTE_FILENAME)
    log.info("Getting CloudMan from the default repository (using wget) from '%s' and saving it to '%s'" % (url, local_cm_file))
    # This assumes the default repository/bucket is readable to anyone w/o authentication
    return _run('wget --output-document=%s %s' % (local_cm_file, url))

def _write_cm_revision_to_file(s3_conn, bucket_name):
    """ Get the revision number associated with the CM_REMOTE_FILENAME and save 
    it locally to CM_REV_FILENAME """
    with open(os.path.join(CM_HOME, CM_REV_FILENAME), 'w') as rev_file:
        rev = _get_file_metadata(s3_conn, bucket_name, CM_REMOTE_FILENAME, 'revision')
        log.debug("Revision of remote file '%s' from bucket '%s': %s" % (CM_REMOTE_FILENAME, bucket_name, rev))
        if rev:
            rev_file.write(rev)
        else:
            rev_file.write('9999999')

def _get_file_metadata(conn, bucket_name, remote_filename, metadata_key):
    """ Get metadata value for the given key. If bucket or remote_filename is not 
    found, the method returns None.    
    """
    log.debug("Getting metadata '%s' for file '%s' from bucket '%s'" % (metadata_key, remote_filename, bucket_name))
    b = None
    for i in range(0, 5):
        try:
            b = conn.get_bucket( bucket_name )
            break
        except S3ResponseError: 
            log.debug ( "Bucket '%s' not found, attempt %s/5" % ( bucket_name, i+1 ) )
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
    tar.extractall(CM_HOME) # Extract contents of downloaded file to CM_HOME

def _start_cm():
    log.debug("Copying user data file from '%s' to '%s'" % \
        (os.path.join(CM_BOOT_PATH, USER_DATA_FILE), os.path.join(CM_HOME, USER_DATA_FILE)))
    shutil.copyfile(os.path.join(CM_BOOT_PATH, USER_DATA_FILE), os.path.join(CM_HOME, USER_DATA_FILE))
    log.info("<< Starting CloudMan in %s >>" % CM_HOME)
    _run('cd %s; sh run.sh --daemon' % CM_HOME)

def _stop_cm(clean=False):
    log.info("<< Stopping CloudMan from %s >>" % CM_HOME)
    _run('cd %s; sh run.sh --stop-daemon' % CM_HOME)
    if clean:
        _run('rm -rf {0}'.format(CM_HOME))

def _start(ud):
    if _get_cm(ud):
        _unpack_cm()
        _start_cm()

def _restart_cm(ud, clean=False):
    log.info("<< Restarting CloudMan >>")
    _stop_cm(clean=clean)
    _start(ud)

def _post_start_hook(ud):
    log.info("<<Checking for post start script>>")
    local_prs_file = os.path.join(CM_HOME, PRS_FILENAME)
    # Check user data first to allow owerwriting of a potentially existing script
    if ud.has_key('post_start_script_url'):
        # This assumes the provided URL is readable to anyone w/o authentication
        _run('wget --output-document=%s %s' % (local_prs_file, ud['post_start_script_url']))
    else:
        s3_conn = S3Connection(ud['access_key'], ud['secret_key'])
        b = None
        if ud.has_key('bucket_cluster'):
            b = s3_conn.lookup(ud['bucket_cluster'])
        if b is not None: # Try to retrieve an existing cluster instance of post run script
            log.info("Cluster bucket '%s' found; getting post start script '%s'" % (b.name, PRS_FILENAME))
            _get_file_from_bucket(s3_conn, b.name, PRS_FILENAME, local_prs_file)
    if os.path.exists(local_prs_file):
        os.chmod(local_prs_file, 0755) # Ensure the script is executable
        return _run('cd %s;./%s' % (CM_HOME, PRS_FILENAME))
    else:
        log.debug("Post start script does not exist; continuing.")
        return True

def main():
    # _run('easy_install -U boto') # Update boto
    _run('easy_install oca') # temp only - this needs to be included in the AMI (incl. in CBL AMI!)
    with open(os.path.join(CM_BOOT_PATH, USER_DATA_FILE)) as ud_file:
        ud = yaml.load(ud_file)
    if len(sys.argv) > 1:
        if sys.argv[1] == 'restart':
            _restart_cm(ud, clean=True)
            sys.exit(0)
        else:
            usage()
    if not ud.has_key('no_start'):
        _start_nginx()
        _start(ud)
        # _post_start_hook(ud) # Execution of this script is moved into CloudMan, at the end of config
    log.info("---> %s done <---" % sys.argv[0])
    sys.exit(0)

if __name__ == "__main__":
    main()