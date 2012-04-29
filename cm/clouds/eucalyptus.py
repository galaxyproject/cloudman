import urllib, socket
from cm.clouds.ec2 import EC2Interface
from cm.util import misc
from cm.util import paths
from urlparse import urlparse

from boto.s3.connection import S3Connection, OrdinaryCallingFormat, SubdomainCallingFormat
from boto.ec2.connection import EC2Connection
from boto.ec2.regioninfo import RegionInfo
from boto.exception import EC2ResponseError

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
        self.s3_url = None
        self.ec2_url = None
        self.tags_not_supported = False
        self.tags = {}

    def get_ec2_connection( self ):
        if self.ec2_conn == None:
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
                                             # debug = 2,
                    )
                    # Do a simple query to test if provided credentials are valid
                    try:
                        self.ec2_conn.get_all_instances()
                        log.debug("Got local boto EC2 connection to %s for region '%s'" % (self.ec2_url,self.ec2_conn.region.name))
                    except EC2ResponseError, e:
                        log.error("Cannot validate provided local AWS credentials to %s (A:%s, S:%s): %s" % (self.ec2_url, self.aws_access_key, self.aws_secret_key, e))
                        self.ec2_conn = False
                except Exception, e:
                    log.error(e)
            else:
                try:
                    log.debug('Establishing boto EC2 connection')
                    if self.app.TESTFLAG is True:
                        log.debug("Attempted to establish EC2 connection, but TESTFLAG is set. Returning default EC2 connection.")
                        self.ec2_conn = EC2Connection(self.aws_access_key, self.aws_secret_key)
                        return self.ec2_conn
                    # In order to get a connection for the correct region, get instance zone and go from there
                    zone = self.get_zone()[:-1] # truncate zone and be left with region name
                    tmp_conn = EC2Connection(self.aws_access_key, self.aws_secret_key) # get conn in default region
                    try:
                        regions = tmp_conn.get_all_regions()
                    except EC2ResponseError, e:
                        log.error("Cannot validate provided AWS credentials: %s" % e)
                    # Find region that matches instance zone and then create ec2_conn
                    for r in regions:
                        if zone in r.name:
                            region = r
                            break
                    self.ec2_conn = EC2Connection(self.aws_access_key, self.aws_secret_key, region=region)
                    # Do a simple query to test if provided credentials are valid
                    try:
                        self.ec2_conn.get_all_instances()
                        log.debug("Got boto EC2 connection for region '%s'" % self.ec2_conn.region.name)
                    except EC2ResponseError, e:
                        log.error("Cannot validate provided AWS credentials (A:%s, S:%s): %s" % (self.aws_access_key, self.aws_secret_key, e))
                        self.ec2_conn = False
                except Exception, e:
                    log.error(e)
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
                try:
                    self.s3_conn = S3Connection(self.aws_access_key, self.aws_secret_key)
                    log.debug( 'Got boto S3 connection to amazon.' )
                    # try:
                    #     self.s3_conn.get_bucket('test_creds') # Any bucket name will do - just testing the call
                    #     log.debug( 'Got boto S3 connection.' )
                    # except S3ResponseError, e:
                    #     log.error("Cannot validate provided AWS credentials: %s" % e)
                    #     self.s3_conn = False
                except Exception, e:
                    log.error(e)
        return self.s3_conn

    def get_user_data(self, force=False):
        if self.user_data is None or force:
            self.user_data = misc.load_yaml_file(paths.USER_DATA_FILE)
            self.aws_access_key = self.user_data.get('access_key', None)
            self.aws_secret_key = self.user_data.get('secret_key', None)
            self.s3_url = self.user_data.get('s3_url',None)
            self.ec2_url = self.user_data.get('ec2_url',None)
        return self.user_data

    def add_tag(self, resource, key, value):
        """ Add tag as key value pair to the `resource` object. The `resource`
        object must be an instance of a cloud object and support tagging.
        """
        if not self.tags_not_supported:
            try:
                log.debug("Adding tag '%s:%s' to resource '%s'" % (key, value, resource.id if resource.id else resource))
                resource.add_tag(key, value)
            except EC2ResponseError, e:
                log.error("Exception adding tag '%s:%s' to resource '%s': %s" % (key, value, resource, e))
                self.tags_not_supported = True
        resource_tags = self.tags.get(resource.id, {})
        resource_tags[key] = value
        self.tags[resource.id] = resource_tags
    
    def get_tag(self, resource, key):
        """ Get tag on `resource` cloud object. Return None if tag does not exist.
        """
        value = None
        if not self.tags_not_supported:
            try:
                log.debug("Getting tag '%s' on resource '%s'" % (key, resource.id))
                value = resource.tags.get(key, None)
            except EC2ResponseError, e:
                log.error("Exception getting tag '%s' on resource '%s': %s" % (key, resource, e))
                self.tags_not_supported = True
        if not value:
            resource_tags = self.tags.get(resource.id,{})
            value = resource_tags.get(key)
        return value    
