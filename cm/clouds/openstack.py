from cm.clouds.ec2 import EC2Interface

import boto
from boto.s3.connection import OrdinaryCallingFormat
from boto.ec2.regioninfo import RegionInfo
from boto.exception import EC2ResponseError

import logging
log = logging.getLogger('cloudman')


class OSInterface(EC2Interface):
    
    def __init__(self, app=None):
        super(OSInterface, self).__init__()
        self.app = app
        self.set_configuration()
    
    def set_configuration(self):
        super(OSInterface, self).set_configuration()
        # Cloud details gotten from the user data
        self.region_name = self.user_data.get('region_name', None)
        self.region_endpoint = self.user_data.get('region_endpoint', None)
        self.ec2_port = self.user_data.get('ec2_port', None)
        self.ec2_conn_path = self.user_data.get('ec2_conn_path', None)
        self.is_secure = self.user_data.get('is_secure', False)
        self.s3_host = self.user_data.get('s3_host', None)
        self.s3_port = self.user_data.get('s3_port', None)
        self.s3_conn_path = self.user_data.get('s3_conn_path', None)
        self.calling_format = OrdinaryCallingFormat()
    
    def get_ec2_connection( self ):
        if self.ec2_conn == None:
            try:
                if self.app.TESTFLAG is True:
                    log.debug("Attempted to establish Nova connection, but TESTFLAG is set. " \
                              "Returning a default connection.")
                    self.ec2_conn = self._get_default_ec2_conn()
                    return self.ec2_conn
                log.debug('Establishing a boto Nova connection')
                self.ec2_conn = self._get_default_ec2_conn()
                # Do a simple query to test if provided credentials are valid
                try:
                    self.ec2_conn.get_all_instances()
                    log.debug("Got boto Nova connection for region {0}".format(self.ec2_conn.region.name))
                except EC2ResponseError, e:
                    log.error("Cannot validate provided OpenStack credentials or configuration " \
                              "(AK:{0}, SK:{1}): {2}".format(self.aws_access_key, self.aws_secret_key, e))
                    self.ec2_conn = False
            except Exception, e:
                log.error(e)
        return self.ec2_conn
    
    def _get_default_ec2_conn(self, region=None):
        ec2_conn = None
        try:
            if region is None:
                region = RegionInfo(name=self.region_name, endpoint=self.region_endpoint)
            ec2_conn = boto.connect_ec2(aws_access_key_id=self.aws_access_key,
                                        aws_secret_access_key=self.aws_secret_key,
                                        is_secure=self.is_secure,
                                        region=region,
                                        port=self.ec2_port,
                                        path=self.ec2_conn_path)
        except EC2ResponseError, e:
            log.error("Trouble creating a Nova connection: {0}".format(e))
        return ec2_conn
    
    def get_s3_connection(self):
        log.debug('Getting boto Swift connection')
        if self.s3_conn == None:
            log.debug("Establishing a boto Swift connection.")
            try:
                self.s3_conn = boto.connect_s3(aws_access_key_id=self.aws_access_key,
                                               aws_secret_access_key=self.aws_secret_key,
                                               is_secure=self.is_secure,
                                               host=self.s3_host,
                                               port=self.s3_port,
                                               path=self.s3_conn_path,
                                               calling_format=self.calling_format)
                log.debug('Got boto Swift connection.')
                # try:
                #     self.s3_conn.get_bucket('cloudman') # Any bucket name will do - just testing the call
                #     log.debug('Got boto Swift connection.')
                # except S3ResponseError, e:
                #     log.error("Cannot validate provided OpenStack credentials: %s" % e)
                #     self.s3_conn = None
            except Exception, e:
                log.error("Trouble creating a Swift connection: {0}".format(e))
        return self.s3_conn
    
    def add_tag(self, resource, key, value):
        log.debug("Tried adding tag {key}:{value} to resource {resource} but OpenStack does not support tags" \
            .format(key=key, value=value, resource=resource))
        pass
    
    def get_tag(self, resource, key):
        log.debug("Tried getting tag {key} from resource {resource} but OpenStack does not support tags" \
            .format(key=key, resource=resource))
        pass
    
