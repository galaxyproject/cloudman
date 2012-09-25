import socket, time
from cm.clouds.ec2 import EC2Interface
from cm.util import misc
from cm.util import paths
from urlparse import urlparse

from boto.s3.connection import S3Connection, OrdinaryCallingFormat, SubdomainCallingFormat
from boto.ec2.connection import EC2Connection
from boto.ec2.regioninfo import RegionInfo
from boto.exception import EC2ResponseError

## debugging
import traceback
class DebugException(Exception):
    pass

def stacktrace_wrapper(old_method):
            
    def _w(self,*args,**kwargs):
        try:
            raise DebugException()
        except DebugException:
            log.debug('get_all_instances() called. Trace follows...')
            traceback.print_stack()
        return old_method(self,*args,**kwargs)
    
    return _w

# EC2Connection.get_all_instances = stacktrace_wrapper(EC2Connection.get_all_instances)
            


import logging
log = logging.getLogger( 'cloudman' )

class _DummyApp:
    """to allow for checking TESTFLAG attribute if no app passed"""
    def __init__(self):
        self.TESTFLAG = False

class EucaInterface(EC2Interface):
    """
        A specialization of cm.clouds.ec2 allowing use of private Eucalyptus clouds.
        User data should also include keys s3_url and ec2_url to declare where the connection
        should be made to.    
    """
    def __init__(self, app=None):
        if not app:
            app = _DummyApp()
        super(EucaInterface, self).__init__()
        self.app = app
        self.tags_not_supported = True
        self.tags = {}
        self.local_hostname = None
        self.public_hostname = None
        self._min_boto_delay = 2
        self._instances = {}
        self._last_instance_check = None
        self._volumes = {}
        self._last_volume_check = None

    def set_configuration(self):
        super(EucaInterface,self).set_configuration()
        self.s3_url = self.user_data.get('s3_url',None)
        self.ec2_url = self.user_data.get('ec2_url',None)

    def get_ec2_connection( self ):
        if not self.ec2_conn:
            if self.ec2_url:
                url = urlparse(self.ec2_url)
                host = url.hostname
                port = url.port
                path = url.path
                if url.scheme == 'https':
                    is_secure = True
                else:
                    is_secure = False
                try:
                    log.debug('Establishing local boto EC2 connection to %s' % self.ec2_url)
                    zone = self.get_zone()
                    region = RegionInfo(name=zone,endpoint=host)
                    self.ec2_conn = EC2Connection(
                                             aws_access_key_id = self.aws_access_key, 
                                             aws_secret_access_key = self.aws_secret_key,
                                             is_secure = is_secure,
                                             host = host,
                                             port = port,
                                             path = path,
                                             region = region,
                                             debug = 2,
                    )
                    # Do a simple query to test if provided credentials are valid
                    try:
                        self.ec2_conn.get_all_instances()
                        log.debug("Got local boto EC2 connection to %s for region '%s'" % (self.ec2_url,self.ec2_conn.region.name))
                    except EC2ResponseError, e:
                        log.error("Cannot validate provided local AWS credentials to %s (A:%s, S:%s): %s" % (self.ec2_url, self.aws_access_key, self.aws_secret_key, e))
                        self.ec2_conn = False
                except Exception, e:
                    log.error(e) # to match interface for Ec2Interface
                    
            else:
                super(EucaInterface,self).get_ec2_connection() # default to ec2 connection
        return self.ec2_conn

    
    def get_s3_connection(self):
        log.debug( 'Getting boto S3 connection' )
        if self.s3_conn == None:
            log.debug("No S3 Connection, creating a new one.")
            if self.s3_url:
                url = urlparse(self.s3_url)
                host = url.hostname
                port = url.port
                path = url.path
                calling_format=SubdomainCallingFormat()
                if host.find('amazon') == -1:  # assume that non-amazon won't use <bucket>.<hostname> format
                    calling_format=OrdinaryCallingFormat()
                if url.scheme == 'https':
                    is_secure = True
                else:
                    is_secure = False
                try:
                    self.s3_conn = S3Connection(
                        aws_access_key_id = self.aws_access_key,
                        aws_secret_access_key = self.aws_secret_key,
                        is_secure = is_secure,
                        port = port,
                        host = host,
                        path = path,
                        calling_format = calling_format,
                        # debug = 2
                    )
                    log.debug('Got boto S3 connection to %s' % self.s3_url)
                except Exception, e:
                    log.error("Exception getting S3 connection: %s" % e)
            else: # default to Amazon connection
                super(EucaInterface,self).get_s3_connection()
        return self.s3_conn

    def get_user_data(self, force=False):
        if self.user_data is None or force:
            self.user_data = misc.load_yaml_file(paths.USER_DATA_FILE)
            self.aws_access_key = self.user_data.get('access_key', None)
            self.aws_secret_key = self.user_data.get('secret_key', None)
            self.s3_url = self.user_data.get('s3_url',None)
            self.ec2_url = self.user_data.get('ec2_url',None)
        return self.user_data

    def get_self_local_hostname(self):
        # Currently, Eucalyptus meta-data/local-hostname returns the IP address, not the hostname. Pull from system hostname instead
        super(EucaInterface,self).get_self_local_hostname()
        if self.local_hostname:
            toks = self.local_hostname.split('.')
            if len(toks) == 4:
                r = filter(lambda x: int(x) < 256 and x > 0, toks)
                if len(r) == 4:
                    log.debug('local hostname ({0}) appears to be an IP address.'.format(self.local_hostname))
                    self.local_hostname = None
                    
            if not self.local_hostname:
                log.debug('Fetching hostname from local system hostname()')
                self.local_hostname = socket.gethostname()
        return self.local_hostname
        
    def get_self_public_hostname(self):
        # Eucalyptus meta-data/public-hostname return the IP address. Fake it, assuming that it will be ip-NUM-NUM-NUM-NUM
        super(EucaInterface,self).get_self_public_hostname()
        if self.public_hostname:
            toks = self.public_hostname.split('.')
            if len(toks) == 4:
                r = filter(lambda x: int(x) < 256 and x > 0, toks)
                if len(r) == 4:
                    self.public_hostname = None
                    
            if not self.public_hostname:
                log.debug('Faking local hostname based on IP address {0}'.format('.'.join(toks)))
                self.public_hostname = 'ip-%s' % '-'.join(toks)
        return self.public_hostname

    def get_all_instances(self,instance_ids=None, filters=None):
            
        if isinstance(instance_ids,basestring):
            instance_ids=(instance_ids,)
            cache_key = instance_ids
        elif instance_ids:
            cache_key = ','.join(instance_ids)
        else:
            cache_key = ''
            
        # eucalyptus stops responding if you check the same thing too often
        if self._last_instance_check and cache_key in self._instances and time.time() <= self._last_instance_check + self._min_boto_delay:
            log.debug('Using cached instance information for {0}'.format(str(instance_ids)))
            reservations = self._instances[cache_key]
        else:
            reservations = self.get_ec2_connection().get_all_instances(instance_ids=instance_ids)
            # Filter for only reservations that include the filtered instance IDs. Needed because Eucalyptus doesn't filter properly
            if instance_ids:
                reservations = [r for r in reservations if [i for i in r.instances if i.id in instance_ids ] ]
            self._instances[cache_key] = reservations
            self._last_instance_check = time.time()

        if not filters:
            filters = {}
        excluded = []
        for r in reservations:
            for key in filters.keys():
                val = filters[key]
                if key.startswith('tag:'):
                    tag = key[4:]
                    if self.get_tag(r.id,tag) != val:
                        excluded.append(r)
                        continue
                else:
                    log.error('Could not filter instance on unknown filter key {0}'.format(key))
        res = [ i for i in reservations if i not in excluded]
        
        return res
    
    def get_all_volumes(self,volume_ids=None, filters=None):
        # eucalyptus does not allow filters in get_all_volumes
        if isinstance(volume_ids,basestring):
            volume_ids = (volume_ids,)
            cache_key = volume_ids
        elif volume_ids:
            cache_key = ','.join(volume_ids)
        else:
            cache_key = ''

        # eucalyptus stops responding if you check too often
        if self._last_volume_check and cache_key in self._volumes and time.time() <= self._last_volume_check + self._min_boto_delay:
            volumes = self._volumes[cache_key]
        else:
            # need to go this roundabout way to get the volume because euca does not filter the get_all_volumes request by the volume ID,
            # but keep the filter, in case it eventually does
            volumes = [ v for v in self.get_ec2_connection().get_all_volumes( volume_ids= volume_ids ) if not volume_ids or (v.id in volume_ids) ]
            self._last_volume_check = time.time()
            self._volumes[cache_key] = volumes # cache returned volumes (for this set of filters)

        if not filters:
            filters = {}
        excluded_vols = []
        for v in volumes:
            for key in filters.keys():
                val = filters[key]
                if key.startswith('tag:'):
                    tag = key[4:]
                    if self.get_tag(v.id,tag) != val:
                        # log.debug('(get_all_volumes) Excluding volume {0} because tag {1} != {2}. (is {3})'.format(v.id,tag,val,self.get_tag(v.id,tag)))
                        excluded_vols.append(v)
                elif key == 'attachment.device':
                    if v.attach_data.device != val:
                        # log.debug('(get_all_volumes) Excluding volume {0} because it is not attached as {1} (is {2})'.format(v.id,val,v.attach_data.device))
                        excluded_vols.append(v)
                elif key == 'attachment.instance-id':
                    if v.attach_data.instance_id != val:
                        # log.debug('(get_all_volume) Excluding vol {0} because it is not attached to {1} (is {2})'.format(v.id,val,v.attach_data.instance_id))
                        excluded_vols.append(v)
                else:
                    log.error('Could not filter on unknown filter key {0}'.format(key))
        vols = [v for v in volumes if v not in excluded_vols]
        # log.debug("(get_all_volumes) Returning volumes: {0}".format(vols))
        return vols
            
