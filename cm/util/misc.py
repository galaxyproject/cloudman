#!/usr/bin/python
import logging, time
from boto.s3.connection import S3Connection
from boto.s3.key import Key
from boto.exception import S3ResponseError
import subprocess
import threading
import datetime as dt

from cm.util.paths import *

log = logging.getLogger( __name__ )

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

def get_file_from_bucket( conn, bucket_name, remote_filename, local_file ):
    log.debug( "Establishing handle with bucket '%s'..." % bucket_name )
    b = conn.lookup( bucket_name )
    if b is not None:
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
      log.debug("Bucket '%s' does not exist, did not get file '%s'" % (bucket_name, remote_filename))
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
			log.error ( "Bucket '%s' not found, attempt %s/5" % ( bucket_name, i ) )
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
		except S3ResponseError, e: 
			log.error ( "Bucket '%s' not found, attempt %s/5" % ( bucket_name, i ) )
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
			log.error ( "Bucket '%s' not found, attempt %s/5" % ( bucket_name, i ) )
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
    
class Introspection( object ):
    def check_all( self ):
        log.debug( "Checking all services..." )
        self.check_nfs()
        self.check_zpools()

    def _exec( self, cmd, ok_msg, err_msg ):
        log.debug( "Executing cmd: '%s'" % cmd )
        ret_code = subprocess.call( cmd, shell=True )
        if ret_code == 0:
            log.debug( ok_msg )
            return True
        else:
            log.error( err_msg )
            return False

    def _check_srvc( self, stdout_value, srvc ):
        """ Simple string search for 'srvc' in 'stdout_value' with OK (True)/not OK (False) notification """
        if srvc in stdout_value:
            log.debug( "'%s'.....................OK" % srvc )
            return True
        else:
            log.debug( "'%s'................not OK!" % srvc )
            return False  

    def check_nfs( self ):
        log.debug( "Checking status of NFS..." )
        log.debug( "Checking NFS server..." )
        proc = subprocess.Popen('/usr/bin/svcs nfs/server',
                       shell=True,
                       stdout=subprocess.PIPE )
        stdout_value = proc.communicate()[0]
        if 'online' in stdout_value:
            log.debug( "NFS server..............OK" )
        else:
            log.debug( "NFS server.........not OK!" )

        log.debug( "Checking directories..." )
        proc = subprocess.Popen( '/usr/sbin/dfshares', 
                                 shell=True,
                                 stdout=subprocess.PIPE )
        stdout_value = proc.communicate()[0]
        self._check_srvc( stdout_value, 'galaxyData')
        self._check_srvc( stdout_value, 'galaxyIndices')
        self._check_srvc( stdout_value, 'galaxyTools')
        self._check_srvc( stdout_value, 'opt/sge')

    def _check_zpool( self, zpool_name ):
        if self._exec('/usr/sbin/zpool list -o name,health %s' % zpool_name, '%s zpool OK' % zpool_name, '%s zpool not OK' % zpool_name ):
            return True
        else:
            return False

#        if not os.path.exists( '/%s' % zpool_dir ):
#            log.debug( "'/%s' not OK!" % zpool_dir )
#            return False
#        
#        log.debug( "'/%s' OK" % zpool_dir )
#        return True

    def check_zpools( self ):
        log.debug( "Checking zpools..." )
        self._check_zpool('galaxyData')
        self._check_zpool('galaxyTools')
        self._check_zpool('galaxyIndices')



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
