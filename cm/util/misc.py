#!/usr/bin/python
import logging, time, yaml
from boto.s3.key import Key
from boto.s3.acl import ACL
from boto.exception import S3ResponseError, EC2ResponseError
import subprocess
import threading
import datetime as dt
from tempfile import mkstemp, NamedTemporaryFile
import shutil
import os
import contextlib
import errno


log = logging.getLogger( 'cloudman' )

def load_yaml_file(filename):
    with open(filename) as ud_file:
        ud = yaml.load(ud_file)
    # log.debug("Loaded user data: %s" % ud)
    return ud
    
def dump_yaml_to_file(data, filename):
    with open(filename, 'w') as f:
        yaml.dump(data, f, default_flow_style=False)

def merge_yaml_objects(user, default):
    """Merge fields from user data (user) YAML object and default data (default)
    YAML object. If there are conflicts, value from the user data object are
    kept."""
    if isinstance(user, dict) and isinstance(default, dict):
        for k, v in default.iteritems():
            if k not in user:
                user[k] = v
            else:
                user[k] = merge_yaml_objects(user[k], v)
    return user

def shellVars2Dict(filename):
    '''Reads a file containing lines with <KEY>=<VALUE> pairs and turns it into a dict'''
    f = None
    try:
        f = open(filename, 'r')
    except IOError:
        return { }
    lines = f.readlines()
    result = { }

    for line in lines:
        parts = line.strip().partition('=')
        key = parts[0].strip()
        val = parts[2].strip()
        if key:
            result[key] = val
    return result

@contextlib.contextmanager
def flock(path, wait_delay=1):
    """
    A lockfile implementation (from http://code.activestate.com/recipes/576572/)
    It is primarily intended to be used as a semaphore with multithreaded code.
    
    Use like so:
    with flock('.lockfile'):
       # do whatever.
    """
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise
            time.sleep(wait_delay)
            continue
        else:
            break
    try:
        yield fd
    finally:
        os.close(fd)
        os.unlink(path)

def formatSeconds(delta):
    # Python 2.7 defines this function but in the mean time...
    def _total_seconds(td):
        return (td.microseconds + (td.seconds + td.days * 24 * 3600) * 10**6) / 10**6
    return '%s' % (_total_seconds(delta))

def formatDelta(delta):
    d = delta.days
    h = delta.seconds / 3600
    m = (delta.seconds % 3600) / 60
    s = delta.seconds % 60
    
    if d > 0:
        return '%sd %sh' % (d, h)
    elif h > 0:
        return '%sh %sm' % (h, m)
    else:
        return '%sm %ss' % (m, s)

def bucket_exists(s3_conn, bucket_name, validate=True):
    if s3_conn is None:
        log.debug("Checking if s3 bucket exists, no s3 connection specified... it does not")
        return False
    if bucket_name:
        try:
            b = s3_conn.lookup(bucket_name, validate=validate)
            if b:
                # log.debug("Checking if bucket '%s' exists... it does." % bucket_name)
                return True
            else:
                log.debug("Checking if bucket '%s' exists... it does not." % bucket_name)
                return False
        except S3ResponseError as e:
            log.error("Failed to lookup bucket '%s': %s" % (bucket_name, e))
    else:
        log.error("Cannot lookup bucket with no name.")
        return False

def create_bucket(s3_conn, bucket_name):
    try:
        s3_conn.create_bucket(bucket_name)
        log.debug("Created bucket '%s'." % bucket_name)
    except S3ResponseError as e:
        log.error( "Failed to create bucket '%s': %s" % (bucket_name, e))
        return False
    return True

def get_bucket(s3_conn, bucket_name, validate=True):
    """Get handle to bucket"""
    b = None
    if bucket_exists(s3_conn, bucket_name, validate):
        for i in range(0, 5):
            try:
                b = s3_conn.get_bucket(bucket_name, validate=validate)
                break
            except S3ResponseError: 
                log.error ( "Problem connecting to bucket '%s', attempt %s/5" % ( bucket_name, i+1 ) )
                time.sleep(2)
    return b

def make_bucket_public(s3_conn, bucket_name, recursive=False):
    b = get_bucket(s3_conn, bucket_name)
    if b:
        try:
            b.make_public(recursive=recursive)
            log.debug("Bucket '%s' made public" % bucket_name)
            return True
        except S3ResponseError as e:
            log.error("Could not make bucket '%s' public: %s" % (bucket_name, e))
    return False

def make_key_public(s3_conn, bucket_name, key_name):
    b = get_bucket(s3_conn, bucket_name)
    if b:
        try:
            k = Key(b, key_name)
            if k.exists():
                k.make_public()
                log.debug("Key '%s' made public" % key_name)
                return True
        except S3ResponseError as e:
            log.error("Could not make key '%s' public: %s" % (key_name, e))
    return False

def add_bucket_user_grant(s3_conn, bucket_name, permission, cannonical_ids, recursive=False):
    """
    Boto wrapper that provides a quick way to add a canonical
    user grant to a bucket. 
    
    :type permission: string
    :param permission: The permission being granted. Should be one of:
                       (READ, WRITE, READ_ACP, WRITE_ACP, FULL_CONTROL).
    
    :type user_id: list of strings
    :param cannonical_ids: A list of strings with canonical user ids associated 
                        with the AWS account your are granting the permission to.
    
    :type recursive: boolean
    :param recursive: A boolean value to controls whether the command
                      will apply the grant to all keys within the bucket
                      or not.
    """
    b = get_bucket(s3_conn, bucket_name)
    if b:
        try:
            for c_id in cannonical_ids:
                log.debug("Adding '%s' permission for bucket '%s' for users '%s'" % (permission, bucket_name, c_id))
                b.add_user_grant(permission, c_id, recursive)
            return True
        except S3ResponseError as e:
            log.error("Could not add permission '%s' for bucket '%s': %s" % (permission, bucket_name, e))
    return False

def add_key_user_grant(s3_conn, bucket_name, key_name, permission, cannonical_ids):
    """
    Boto wrapper that provides a quick way to add a canonical
    user grant to a key. 
    
    :type permission: string
    :param permission: Name of the bucket where the key resides
    
    :type permission: string
    :param permission: Name of the key to add the permission to
    
    :type permission: string
    :param permission: The permission being granted. Should be one of:
                       (READ, WRITE, READ_ACP, WRITE_ACP, FULL_CONTROL).
    
    :type user_id: list of strings
    :param cannonical_ids: A list of strings with canonical user ids associated 
                        with the AWS account your are granting the permission to.
    """
    b = get_bucket(s3_conn, bucket_name)
    if b:
        try:
            k = Key(b, key_name)
            if k.exists():
                for c_id in cannonical_ids:
                    log.debug("Adding '%s' permission for key '%s' for user '%s'" % (permission, key_name, c_id))
                    k.add_user_grant(permission, c_id)
                return True
        except S3ResponseError as e:
            log.error("Could not add permission '%s' for bucket '%s': %s" % (permission, bucket_name, e))
    return False

def get_list_of_bucket_folder_users(s3_conn, bucket_name, folder_name, exclude_power_users=True):
    """
    Retrieve a list of users that are associated with a key in a folder (i.e., prefix) 
    in the provided bucket and have READ grant. Note that this method assumes all 
    of the keys in the given folder have the same ACL and the method thus looks 
    only at the very first key in the folder. Also, any users
    
    :type s3_conn: boto.s3.connection.S3Connection
    :param s3_conn: Established boto connection to S3 that has access to bucket_name
    
    :type bucket_name: string
    :param bucket_name: Name of the bucket in which the given folder/prefix is 
                        stored
    
    :type folder_name: string
    :param folder_name: Allows limit the listing of keys in the given bucket to a 
                   particular prefix. This has the effect of iterating through 
                   'folders' within a bucket. For example, if you call the method 
                   with folder_name='/foo/' then the iterator will only cycle
                   through the keys that begin with the string '/foo/'.
                   A valid example would be 'shared/2011-03-31--19-43/'
    
    :type exclude_power_users: boolean
    :param exclude_power_users: If True, folder users with FULL_CONTROL grant 
                   are not included in the folder user list
    """
    users=[] # Current list of users retrieved from folder's ACL
    key_list = None
    key_acl = None
    b = get_bucket(s3_conn, bucket_name)
    if b:
        try:
            key_list = b.get_all_keys(prefix=folder_name, delimiter='/')
            # for k in key_list:
            #     print k.name#, k.get_acl().acl.grants[0].type
            if len(key_list) > 0:
                key = key_list[0] # Just get one key assuming all keys will have the same ACL
                key_acl = key.get_acl()
            if key_acl:
                power_users = []
                for grant in key_acl.acl.grants:
                    # log.debug("folder_name: %s, %s, %s, %s, %s." % (folder_name, key.name, grant.type, grant.display_name, grant.permission))
                    if grant.permission == 'FULL_CONTROL':
                        power_users.append(grant.display_name)
                    if grant.type == 'Group' and 'Group' not in users:
                        # Group grants (i.e., public) are simply listed as Group under grant.type so catch that
                        users.append(u'Group')
                    elif grant.permission == 'READ' and grant.type != 'Group' and grant.display_name not in users:
                        users.append(grant.display_name)
                # Users w/ FULL_CONTROL are optionally not included in the folder user list
                if exclude_power_users:
                    for pu in power_users:
                        if pu in users:
                            users.remove(pu)
        except S3ResponseError as e:
            log.error("Error getting list of folder '%s' users for bucket '%s': %s" % (folder_name, bucket_name, e))
    # log.debug("List of users for folder '%s' in bucket '%s': %s" % (folder_name, bucket_name, users))
    return users

def get_users_with_grant_on_only_this_folder(s3_conn, bucket_name, folder_name):
    """
    This method is used when dealing with bucket permissions of shared instances. 
    The method's intent is to isolate the set of users that have (READ) grant on 
    a given folder and no other (shared) folder within the given bucket.
    Obtained results can then be used to set the permissions on the bucket root.
    
    See also: get_list_of_bucket_folder_users
    
    :type s3_conn: boto.s3.connection.S3Connection
    :param s3_conn: Established boto connection to S3 that has access to bucket_name
    
    :type bucket_name: string
    :param bucket_name: Name of the bucket in which the given folder is stored
    
    :type folder_name: string
    :param folder_name: Name of the (shared) folder whose grants will be examined
                        and compared to other (shared) folders in the same bucket.
                        A valid example would be 'shared/2011-03-31--19-43/'
    """
    users_with_grant = [] # List of users with grant on given folder and no other (shared) folder in bucket
    other_users = [] # List of users on other (shared) folders in given bucket
    folder_users = get_list_of_bucket_folder_users(s3_conn, bucket_name, folder_name)
    # log.debug("List of users on to-be-deleted shared folder '%s': %s" % (folder_name, folder_users))
    b = get_bucket(s3_conn, bucket_name)
    if b:
        try:
            # Get list of shared folders in given bucket
            folder_list = b.get_all_keys(prefix='shared/', delimiter='/')
            # Inspect each shared folder's user grants and create a list of all users
            # with grants on those folders
            for f in folder_list:
                if f.name != folder_name:
                    fu = get_list_of_bucket_folder_users(s3_conn, bucket_name, f.name)
                    for u in fu:
                        if u not in other_users:
                            other_users.append(u)
            # log.debug("List of users on other shared folders: %s" % other_users)
            # Find list of users in that have grants only on 'folder_name' and no
            # other shared folder in the given bucket
            for u in folder_users:
                if u not in other_users:
                    users_with_grant.append(u)
        except S3ResponseError as e:
            log.error("Error isolating list of folder '%s' users for bucket '%s': %s" % (folder_name, bucket_name, e))
    log.debug("List of users whose bucket grant is to be removed because shared folder '%s' is being deleted: %s" \
        % (folder_name, users_with_grant))
    return users_with_grant

def adjust_bucket_ACL(s3_conn, bucket_name, users_whose_grant_to_remove):
    """
    Adjust the ACL on given bucket and remove grants for all the mentioned users.
    
    :type s3_conn: boto.s3.connection.S3Connection
    :param s3_conn: Established boto connection to S3 that has access to bucket_name
    
    :type bucket_name: string
    :param bucket_name: Name of the bucket for which to adjust the ACL
    
    :type users_whose_grant_to_remove: list
    :param users_whose_grant_to_remove: List of user names (as defined in bucket's
                initial ACL, e.g., ['afgane', 'cloud']) whose grant is to be revoked.
    """
    bucket = get_bucket(s3_conn, bucket_name)
    if bucket:
        try:
            grants_to_keep = []
            # log.debug("All grants on bucket '%s' are following" % bucket_name)
            # Compose list of grants on the bucket that are to be kept, i.e., siphon 
            # through the list of grants for bucket's users and the list of users
            # whose grant to remove and create a list of bucket grants to keep
            for g in bucket.get_acl().acl.grants:
                # log.debug("Grant -> permission: %s, user name: %s, grant type: %s" % (g.permission, g.display_name, g.type))
                # Public (i.e., group) permissions are kept under 'type' field so check that first
                if g.type == 'Group' and 'Group' in users_whose_grant_to_remove:
                    pass
                elif g.display_name not in users_whose_grant_to_remove:
                    grants_to_keep.append(g)
            # Manipulate bucket's ACL now
            bucket_policy = bucket.get_acl() # Object for bucket's current policy (which holds the ACL)
            acl = ACL() # Object for bucket's to-be ACL
            # Add all of the exiting (i.e., grants_to_keep) grants to the new ACL object
            for gtk in grants_to_keep:
                acl.add_grant(gtk)
            # Update the policy and set bucket's ACL
            bucket_policy.acl = acl
            bucket.set_acl(bucket_policy)
            # log.debug("List of kept grants for bucket '%s'" % bucket_name)
            # for g in bucket_policy.acl.grants:
            #     log.debug("Grant -> permission: %s, user name: %s, grant type: %s" % (g.permission, g.display_name, g.type))
            log.debug("Removed grants on bucket '%s' for these users: %s" % (bucket_name, users_whose_grant_to_remove))
            return True
        except S3ResponseError as e:
            log.error("Error adjusting ACL for bucket '%s': %s" % (bucket_name, e))
    return False

def file_exists_in_bucket(s3_conn, bucket_name, remote_filename):
    """Check if remote_filename exists in bucket bucket_name.
    :rtype: bool
    :return: True if remote_filename exists in bucket_name
             False otherwise
    """
    b = get_bucket(s3_conn, bucket_name)
    if b:
        try:
            k = Key(b, remote_filename)
            if k.exists():
                return True
        except S3ResponseError:
            log.debug("Key '%s' in bucket '%s' does not exist." % (remote_filename, bucket_name))
    return False

def file_in_bucket_older_than_local(s3_conn, bucket_name, remote_filename, local_filename):
    """ Check if the file in bucket has been modified before the local file.
    :rtype: bool
    :return: True of file in bucket is older than the local file or an error 
             while checking the time occurs. False otherwise.
    """
    bucket = get_bucket(s3_conn, bucket_name)
    key = bucket.get_key(remote_filename)
    if key is not None:
        try:
            # Time format must be matched the time provided by boto field .last_modified
            k_ts = dt.datetime.strptime(key.last_modified, "%a, %d %b %Y %H:%M:%S GMT")
        except Exception as e:
            log.debug("Could not get last modified timestamp for key '%s': %s" % (remote_filename, e))
            return True
        try:
            return k_ts < dt.datetime.fromtimestamp(os.path.getmtime(local_filename))
        except Exception as e:
            log.debug("Trouble comparing local (%s) and remote (%s) file modified times: %s" % (local_filename, remote_filename, e))
            return True
    else:
        log.debug("Checking age of file in bucket (%s) against local file (%s) but file in bucket is None; updating file in bucket." \
            % (remote_filename, local_filename))
        return True

def get_file_from_bucket( conn, bucket_name, remote_filename, local_file, validate=True ):
    if bucket_exists(conn, bucket_name, validate):
        b = get_bucket(conn, bucket_name, validate)
        k = Key(b, remote_filename)
        try:
            k.get_contents_to_filename(local_file)
            log.info( "Retrieved file '%s' from bucket '%s' to '%s'." \
                         % (remote_filename, bucket_name, local_file))
        except S3ResponseError as e:
            log.debug( "Failed to get file '%s' from bucket '%s': %s" % (remote_filename, bucket_name, e))
            os.remove(local_file) # Don't leave a partially downloaded or touched file
            return False
    else:
        log.debug("Bucket '%s' does not exist, did not get remote file '%s'" % (bucket_name, remote_filename))
        return False
    return True

def save_file_to_bucket( conn, bucket_name, remote_filename, local_file ):
    b = get_bucket(conn, bucket_name)
    if b:
        k = Key( b, remote_filename )
        try:
            k.set_contents_from_filename( local_file )
            log.info( "Saved file '%s' to bucket '%s'" % ( remote_filename, bucket_name ) )
            # Store some metadata (key-value pairs) about the contents of the file being uploaded
            k.set_metadata('date_uploaded', dt.datetime.utcnow())
        except S3ResponseError as e:
            log.error( "Failed to save file local file '%s' to bucket '%s' as file '%s': %s" % ( local_file, bucket_name, remote_filename, e ) )
            return False
        return True
    else:
        log.debug("Could not connect to bucket '%s'; remote file '%s' not saved to the bucket" % (bucket_name, remote_filename))
        return False

def copy_file_in_bucket(s3_conn, src_bucket_name, dest_bucket_name, orig_filename, copy_filename, preserve_acl=True, validate=True):
    b = get_bucket(s3_conn, src_bucket_name, validate)
    if b:
        try:
            log.debug("Establishing handle with key object '%s'" % orig_filename)
            k = Key(b, orig_filename)
            log.debug("Copying file '%s/%s' to file '%s/%s'" % (src_bucket_name, orig_filename, dest_bucket_name, copy_filename))
            k.copy(dest_bucket_name, copy_filename, preserve_acl=preserve_acl)
            return True
        except S3ResponseError as e: 
            log.debug("Error copying file '%s/%s' to file '%s/%s': %s" % (src_bucket_name, orig_filename, dest_bucket_name, copy_filename, e))
    return False

def delete_file_from_bucket(conn, bucket_name, remote_filename):
    b = get_bucket(conn, bucket_name)
    if b:
        try:
            k = Key( b, remote_filename )
            log.debug( "Deleting key object '%s' from bucket '%s'" % (remote_filename, bucket_name))
            k.delete()
            return True
        except S3ResponseError as e:
            log.error("Error deleting key '%s' from bucket '%s': %s" % (remote_filename, bucket_name, e))
    return False

def delete_bucket(conn, bucket_name):
    """Delete given bucket. This method will iterate through all the keys in
    the given bucket first and delete them. Finally, the bucket will be deleted."""
    try:
        b = get_bucket(conn, bucket_name)
        if b:
            keys = b.get_all_keys()
            for key in keys:
                key.delete()
            b.delete()
            log.info("Successfully deleted cluster bucket '%s'" % bucket_name)
    except S3ResponseError as e:
        log.error("Error deleting bucket '%s': %s" % (bucket_name, e))
    return True

def get_file_metadata(conn, bucket_name, remote_filename, metadata_key):
    """ Get metadata value for the given key. If bucket or remote_filename is not 
    found, the method returns None.    
    """
    log.debug("Getting metadata '%s' for file '%s' from bucket '%s'" % (metadata_key, remote_filename, bucket_name))
    b = get_bucket(conn, bucket_name)
    if b:
        k = b.get_key(remote_filename)
        if k and metadata_key:
            return k.get_metadata(metadata_key)
    return None 

def set_file_metadata(conn, bucket_name, remote_filename, metadata_key, metadata_value):
    """ Set metadata key-value pair for the remote file. 
    :rtype: bool
    :return: If specified bucket and remote_filename exist, return True.
             Else, return False
    """
    log.debug("Setting metadata '%s' for file '%s' in bucket '%s'" % (metadata_key, remote_filename, bucket_name))

    b = get_bucket(conn, bucket_name)
    if b:
        k = b.get_key(remote_filename)
        if k and metadata_key:
            # Simply setting the metadata through set_metadata does not work.
            # Instead, must create in-place copy of the file with altered metadata:
            # http://groups.google.com/group/boto-users/browse_thread/thread/9968d3fc4fc18842/29c680aad6e31b3e#29c680aad6e31b3e 
            try:
                k.copy(bucket_name, remote_filename, metadata={metadata_key:metadata_value}, preserve_acl=True)
                return True
            except S3ResponseError as e:
                log.debug("Could not set metadata for file '%s' in bucket '%s': %e" % (remote_filename, bucket_name, e))
    return False

def check_process_running(proc_in):
    ps = subprocess.Popen("ps ax", shell=True, stdout=subprocess.PIPE)
    lines = ps.communicate()[0]
    for line in lines.split('\n'):
        if line.find(proc_in) != -1:
            log.debug(line)
    ps.stdout.close()
    ps.wait()
    
def get_volume_size(ec2_conn, vol_id):
    log.debug("Getting size of volume '%s'" % vol_id) 
    try: 
        vol = ec2_conn.get_all_volumes(vol_id)
    except EC2ResponseError as e:
        log.error("Volume ID '%s' returned an error: %s" % (vol_id, e))
        return 0 

    if len(vol) > 0: 
        # We're only looking for the first vol bc. that's all we asked for
        return vol[0].size
    else:
        return 0

def run(cmd, err=None, ok=None):
    """ Convenience method for executing a shell command. """
    # Predefine err and ok mesages to include the command being run
    if err is None:
        err = "---> PROBLEM"
    if ok is None:
        ok = "'%s' command OK" % cmd
    process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    if process.returncode == 0:
        log.debug(ok)
        if stdout:
            return stdout
        else:
            return True
    else:
        log.error("%s, running command '%s' returned code '%s' and following stderr: '%s'" % (err, cmd, process.returncode, stderr))
        return False

def replace_string(file_name, pattern, subst):
    """Replace string in a file
    :type file_name: str
    :param file_name: Full path to the file where the string is to be replaced

    :type pattern: str
    :param pattern: String pattern to search for
    
    :type subst: str
    :param subst: String pattern to replace search pattern with 
    """
    # Create temp file
    fh, abs_path = mkstemp()
    new_file = open(abs_path,'w')
    old_file = open(file_name)
    for line in old_file:
        new_file.write(line.replace(pattern, subst))
    # Close temp file
    new_file.close()
    os.close(fh)
    old_file.close()
    # Remove original file
    os.remove(file_name)
    # Move new file
    shutil.move(abs_path, file_name)

def _if_not_installed(prog_name):
    """Decorator that checks if a callable program is installed.
    """
    def argcatcher(func):
        def decorator(*args, **kwargs):
            log.debug("Checking if {0} is installed".format(prog_name))
            process = subprocess.Popen(prog_name, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = process.communicate()
            if process.returncode == 127:
                log.debug("{0} is *not* installed".format(prog_name))
                return func(*args, **kwargs)
            else:
                log.debug("{0} is installed".format(prog_name))
        return decorator
    return argcatcher

def add_to_etc_hosts(hostname, ip_address):
    try:
        etc_hosts = open('/etc/hosts','r')
        tmp = NamedTemporaryFile()
        for l in etc_hosts:
            if not hostname in l:
                tmp.write(l)
        etc_hosts.close()
        # add a line for the new hostname
        tmp.write('{0} {1}\n'.format(ip_address, hostname))

        # make sure changes are written to disk
        tmp.flush()
        os.fsync(tmp.fileno())
        # swap out /etc/hosts
        run('cp /etc/hosts /etc/hosts.orig')
        run('cp {0} /etc/hosts'.format(tmp.name))
        run('chmod 644 /etc/hosts')
    except (IOError, OSError) as e:
        log.error('could not update /etc/hosts. {0}'.format(e))

def remove_from_etc_hosts(hostname):
    try:
        etc_hosts = open('/etc/hosts','r')
        tmp = NamedTemporaryFile()
        for l in etc_hosts:
            if not hostname in l:
                tmp.write(l)
        etc_hosts.close()

        # make sure changes are written to disk
        tmp.flush()
        os.fsync(tmp.fileno())
        # swap out /etc/hosts
        run('cp /etc/hosts /etc/hosts.orig')
        run('cp {0} /etc/hosts'.format(tmp.name))
        run('chmod 644 /etc/hosts')
    except (IOError, OSError) as e:
        log.error('could not update /etc/hosts. {0}'.format(e))

class Sleeper( object ):
    """
    Provides a 'sleep' method that sleeps for a number of seconds *unless*
    the notify method is called (from a different thread).
    """
    def __init__( self ):
        self.condition = threading.Condition()
    def sleep( self, seconds ):
        self.condition.acquire()
        self.condition.wait( seconds )
        self.condition.release()
    def wake( self ):
        self.condition.acquire()
        self.condition.notify()
        self.condition.release()
