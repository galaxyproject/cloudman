#!/usr/bin/python
import logging, time, yaml
from boto.s3.key import Key
from boto.exception import S3ResponseError, EC2ResponseError
import subprocess
import threading
import datetime as dt
from tempfile import mkstemp
from shutil import move
from os import remove, close


log = logging.getLogger( __name__ )

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
    if isinstance(user,dict) and isinstance(default,dict):
        for k,v in default.iteritems():
            if k not in user:
                user[k] = v
            else:
                user[k] = merge_yaml_objects(user[k],v)
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

def bucket_exists(s3_conn, bucket_name):
    if bucket_name is not None:
        try:
            b = None
            b = s3_conn.lookup(bucket_name)
            if b is not None:
                # log.debug("Checking if bucket '%s' exists... it does." % bucket_name)
                return True
            else:
                log.debug("Checking if bucket '%s' exists... it does not." % bucket_name)
                return False
        except Exception, e:
            log.error("Failed to lookup bucket '%s': %s" % (bucket_name, e))
    else:
        log.error("Cannot lookup bucket with no name.")
        return False

def create_bucket(s3_conn, bucket_name):
    try:
        s3_conn.create_bucket(bucket_name)
        log.debug("Created bucket '%s'." % bucket_name)
    except S3ResponseError, e:
        log.error( "Failed to create bucket '%s': %s" % (bucket_name, e))
        return False
    return True

def _get_bucket(s3_conn, bucket_name):
    """Get handle to bucket"""
    b = None
    for i in range(0, 5):
		try:
			b = s3_conn.get_bucket( bucket_name )
			break
		except S3ResponseError: 
			log.error ( "Problem connecting to bucket '%s', attempt %s/5" % ( bucket_name, i+1 ) )
			time.sleep(2)
    return b

def file_exists_in_bucket(s3_conn, bucket_name, remote_filename):
    """Check if remote_filename exists in bucket bucket_name.
    :rtype: bool
    :return: True if remote_filename exists in bucket_name
             False otherwise
    """
    b = None
    if bucket_exists(s3_conn, bucket_name):
        b = _get_bucket(s3_conn, bucket_name)
        
    if b is not None:
		k = Key(b, remote_filename)
		if k.exists():
		    return True
    return False

def get_file_from_bucket( conn, bucket_name, remote_filename, local_file ):
    log.debug( "Establishing handle with bucket '%s'" % bucket_name )
    if bucket_exists(conn, bucket_name):
        b = conn.get_bucket( bucket_name )
        # log.debug( "Establishing handle with key object '%s'..." % remote_filename )
        k = Key( b, remote_filename )
        try:
            k.get_contents_to_filename( local_file )
            log.info( "Successfully retrieved file '%s' from bucket '%s' to '%s'." \
                         % (remote_filename, bucket_name, local_file))
        except S3ResponseError, e:
            log.error( "Failed to get file '%s' from bucket '%s': %s" % (remote_filename, bucket_name, e))
            return False
    else:
      log.debug("Bucket '%s' does not exist, did not get remote file '%s'" % (bucket_name, remote_filename))
      return False
      
    return True

def save_file_to_bucket( conn, bucket_name, remote_filename, local_file ):
    # log.debug( "Establishing handle with bucket '%s'..." % bucket_name )
    b = None
    for i in range(0, 5):
		try:
			b = conn.get_bucket( bucket_name )
			break
		except S3ResponseError, e: 
			log.error ( "Bucket '%s' not found, attempt %s/5" % ( bucket_name, i+1 ) )
			time.sleep(2)
	    	
    if b is not None:
        # log.debug( "Establishing handle with key object '%s'..." % remote_filename )
		k = Key( b, remote_filename )
		log.debug( "Attempting to save file '%s' to bucket '%s'..." % (remote_filename, bucket_name))
		try:
		    k.set_contents_from_filename( local_file )
		    log.info( "Successfully saved file '%s' to bucket '%s'." \
		                 % ( remote_filename, bucket_name ) )
		    # Store some metadata (key-value pairs) about the contents of the file being uploaded
		    k.set_metadata('date_uploaded', dt.datetime.utcnow())
		except S3ResponseError, e:
		     log.error( "Failed to save file local file '%s' to bucket '%s' as file '%s': %s" % ( local_file, bucket_name, remote_filename, e ) )
		     return False
		return True
    else:
        log.debug("Could not connect to bucket '%s'; remote file '%s' not saved to the bucket" % (bucket_name, remote_filename))
        return False
         
def delete_file_from_bucket( conn, bucket_name, remote_filename ):
	log.debug( "Establishing handle with bucket '%s'..." % bucket_name )
	b = conn.get_bucket( bucket_name )
	log.debug( "Establishing handle with key object '%s'" % remote_filename )
	k = Key( b, remote_filename )
	log.debug( "Deleting key object '%s'" % remote_filename )
	k.delete()

def get_file_metadata(conn, bucket_name, remote_filename, metadata_key):
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
			log.error ( "Bucket '%s' not found, attempt %s/5" % ( bucket_name, i+1 ) )
			time.sleep(2)

    if b is not None:
        k = b.get_key(remote_filename)
        if k and metadata_key:
            return k.get_metadata(metadata_key)
    return None 

def set_file_metadata(conn, bucket_name, remote_filename, metadata_key, metadata_value):
    """ Set metadata key-value pair for the remote file. 
    :rtype: bool
    :return: If specified bucket and remote_file name exist, return True.
             Else, return False
    """
    log.debug("Setting metadata '%s' for file '%s' in bucket '%s'" % (metadata_key, remote_filename, bucket_name))

    b = None
    for i in range(0, 5):
		try:
			b = conn.get_bucket( bucket_name )
			break
		except S3ResponseError, e: 
			log.error ( "Bucket '%s' not found, attempt %s/5" % ( bucket_name, i+1 ) )
			time.sleep(2)

    if b is not None:
        k = b.get_key(remote_filename)
        if k and metadata_key:
            # Simply setting the metadata through set_metadata does not work.
            # Instead, must create in-place copy of the file with altered metadata:
            # http://groups.google.com/group/boto-users/browse_thread/thread/9968d3fc4fc18842/29c680aad6e31b3e#29c680aad6e31b3e 
            try:
                k.copy(bucket_name, remote_filename, metadata={metadata_key:metadata_value}, preserve_acl=True)
                return True
            except Exception, e:
                log.error("Could not set metadata for file '%s' in bucket '%s': %e" % (remote_filename, bucket_name, e))
    return False

def check_process_running(proc_in):
    ps = subprocess.Popen("ps ax", shell=True, stdout=subprocess.PIPE)
    lines = str(ps.communicate()[0], 'utf-8')
    for line in lines.split('\n'):
        if line.find(proc_in) != -1:
            print(line)
    ps.stdout.close()
    ps.wait()
    
def get_volume_size(ec2_conn, vol_id):
    log.debug("Getting size of volume '%s'" % vol_id) 
    try: 
        vol = ec2_conn.get_all_volumes(vol_id)
    except EC2ResponseError, e:
        log.error("Volume ID '%s' returned an error: %s" % (vol_id, e))
        return 0 

    if len(vol) > 0: 
        # We're only looking for the first vol bc. that's all we asked for
        return vol[0].size
    else:
        return 0

def run(cmd, err, ok):
    """ Convenience method for executing a shell command. """
    process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    if process.returncode == 0:
        log.debug(ok)
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
    close(fh)
    old_file.close()
    # Remove original file
    remove(file_name)
    # Move new file
    move(abs_path, file_name)


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
