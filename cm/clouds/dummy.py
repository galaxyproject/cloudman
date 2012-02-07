import urllib, socket
from cm.clouds import CloudInterface
from cm.services.data.filesystem import Volume

from oca import Client, VirtualMachine, VirtualMachinePool, CONNECTED
from oca.exceptions import OpenNebulaException

import new

# Obtaining IP and MAC addresses
import socket
import fcntl
import struct

import subprocess

import logging
log = logging.getLogger( 'cloudman' )

class DummyInterface(CloudInterface):
    
    def __init__(self, aws_access_key, aws_secret_key, app=None, on_username=None, on_password=None, on_host=None):
        super(DummyInterface, self).__init__()
        self.aws_access_key = aws_access_key
        self.aws_secret_key = aws_secret_key
        self.app = app
        self.on_username = on_username
        self.on_password = on_password
        self.on_host = on_host
        self.bridge = 72

    def _getIpAddress(self, ifname):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            ip = socket.inet_ntoa(fcntl.ioctl(
                                            s.fileno(),
                                            0x8915,  # SIOCGIFADDR
                                            struct.pack('256s', ifname[:15])
                                            )[20:24])
        except IOError:
            return None
        return ip

    def _getMacAddress(self, ifname):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        info = fcntl.ioctl(s.fileno(), 0x8927,  struct.pack('256s', ifname[:15]))
        return ''.join(['%02x:' % ord(char) for char in info[18:24]])[:-1]

    def get_ami( self ):
        pass
    
    def get_type( self ):
        #return 'worker'
        pass
    
    def get_instance_id( self ):
        pass
    
    def get_zone( self ):
        pass
    
    def get_security_groups( self ):
        pass
    
    def get_key_pair_name( self ):
        pass
    
    def get_self_private_ip( self ):
        return self._getIpAddress('eth0')
    
    def get_self_public_ip( self ):
        pass
    
    def get_fqdn(self):
        # Return the hostname
        return socket.getfqdn()
    
    def get_ec2_connection( self ):
        pass
    
    def get_s3_connection( self ):
       pass
    
    def run_instances(self, image_id, min_count, max_count, key_name, security_groups, user_data, instance_type, placement):
        pass

# Emulate EC2 objects

    def get_all_instances(self, filters={}, *args, **kwargs):
        pass

    def get_all_volumes(self, *args, **kwargs):
        pass
    
    def terminate_instances(self, instances):
        log.debug("Terminate instances")
        
        return True

    def reboot_instances(self, instances, *args, **kwargs):
        pass
    


        
class Reservations(object):
    def __init__(self):
        self.instances = []

# A EC2 instance object has a add_tag method
# which is lacking in the OpenNebula object
def add_tag(self, key, value, *args, **kwargs):
    self.tags[key] = value

def update(self):
    """Should update instance"""
    log.debug("Trying to update")
    log.debug("Instance currently in %s state" % self.state)
    log.debug("Instance id: %s" % self.id)



#def get_m_state(self):
#    print "GET M STATE"
#    print self.state

#TODO: Work on Bucket System!!
# A EC2 connection object has lookup method
# which is lacking in the oca Client object
def lookup(self, *args, **kwargs):
    pass

def create_bucket(self, *args, **kwargs):
    pass