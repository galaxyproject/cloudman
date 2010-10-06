import urllib, socket
from cm.clouds import CloudInterface

from boto.s3.connection import S3Connection
from boto.ec2.connection import EC2Connection

import logging
log = logging.getLogger( __name__ )


class EC2Interface(CloudInterface):
    
    def __init__(self, aws_access_key, aws_secret_key):
        super(EC2Interface, self).__init__()
        self.aws_access_key = aws_access_key
        self.aws_secret_key = aws_secret_key

    def get_ami( self ):
        if self.ami is None:
            for i in range(0, 5):
                try:
                    log.debug('Gathering instance ami, attempt %s' % i)
                    fp = urllib.urlopen('http://169.254.169.254/latest/meta-data/ami-id')
                    self.ami = fp.read()
                    fp.close()
                    if self.ami:
                        break
                except IOError:
                    pass
        return self.ami
        
    def get_type( self ):
        if self.instance_type is None:
            for i in range(0, 5):
                try:
                    log.debug('Gathering instance type, attempt %s' % i)
                    fp = urllib.urlopen('http://169.254.169.254/latest/meta-data/instance-type')
                    self.instance_type = fp.read()
                    fp.close()
                    if self.instance_type:
                        break
                except IOError:
                    pass
        return self.instance_type
        
    def get_instance_id( self ):
        if self.instance_id is None:
            for i in range(0, 5):
                try:
                    log.debug('Gathering instance id, attempt %s' % i)
                    fp = urllib.urlopen('http://169.254.169.254/latest/meta-data/instance-id')
                    self.instance_id = fp.read()
                    fp.close()
                    if self.instance_id:
                        break
                except IOError:
                    pass
        return self.instance_id

    def get_zone( self ):
        if self.zone is None:
            for i in range(0, 5):
                try:
                    log.debug('Gathering instance zone, attempt %s' % i)
                    fp = urllib.urlopen('http://169.254.169.254/latest/meta-data/placement/availability-zone')
                    self.zone = fp.read()
                    fp.close()
                    if self.zone:
                        break
                except IOError:
                    pass
        return self.zone
        
    def get_security_groups( self ):
        if self.security_groups is None:
            for i in range(0, 5):
                try:
                    log.debug('Gathering instance security group, attempt %s' % i)
                    fp = urllib.urlopen('http://169.254.169.254/latest/meta-data/security-groups')
                    self.security_groups = []
                    for line in fp.readlines():
                        self.security_groups.append(line.strip())
                    fp.close()
                    if self.security_groups:
                        break
                except IOError:
                    pass
        return self.security_groups

    def get_key_pair_name( self ):
        if self.key_pair_name is None:
            for i in range(0, 5):
                try:
                    log.debug('Gathering instance public keys (i.e., key pairs), attempt %s' % i)
                    fp = urllib.urlopen('http://169.254.169.254/latest/meta-data/public-keys')
                    public_keys = fp.read()
                    self.key_pair_name = public_keys.split('=')[1]
                    fp.close()
                    if self.key_pair_name:
                        log.debug( "Got key pair: '%s'" % self.key_pair_name )
                        break
                except IOError:
                    pass
        return self.key_pair_name
        
    def get_self_private_ip( self ):
        if self.self_private_ip is None:
            for i in range(0, 5):
                try:
                    log.debug('Gathering instance private hostname, attempt %s' % i)
                    fp = urllib.urlopen('http://169.254.169.254/latest/meta-data/local-hostname')
                    self.self_private_ip = fp.read()
                    fp.close()
                    if self.self_private_ip:
                        break
                except IOError:
                    pass
        return self.self_private_ip
        
    def get_self_public_ip( self ):
        if self.self_public_ip is None:
            for i in range(0, 5):
                try:
                    log.debug('Gathering instance public hostname, attempt %s' % i)
                    fp = urllib.urlopen('http://169.254.169.254/latest/meta-data/public-hostname')
                    self.self_public_ip = fp.read()
                    fp.close()
                    if self.self_public_ip:
                        break
                except Exception, e:
                    log.error ( "Error retrieving FQDN: %s" % e )
                                
        return self.self_public_ip
    
    def get_fqdn(self):
        log.debug( "Retrieving FQDN" )
        if self.fqdn == None:
            try:
                self.fqdn = socket.getfqdn()
            except IOError:
                pass
        return self.fqdn
    
    def get_ec2_connection( self ):
        if self.ec2_conn == None:
            try:
                self.ec2_conn = EC2Connection(self.aws_access_key, self.aws_secret_key)
                log.debug( 'Got boto EC2 connection.' )
            except Exception, e:
                log.error(e)
        return self.ec2_conn
        
    def get_s3_connection( self ):
        log.debug( 'Establishing boto S3 connection' )
        if self.s3_conn == None:
            log.debug("No S3 Connection, creating a new one.")
            try:
                self.s3_conn = S3Connection(self.aws_access_key, self.aws_secret_key)
                log.debug( 'Got boto S3 connection.' )
            except Exception, e:
                log.error(e)
        return self.s3_conn