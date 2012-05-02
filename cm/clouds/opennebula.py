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

class ONInterface(CloudInterface):
    
    def __init__(self, aws_access_key=None, aws_secret_key=None, app=None, on_username=None, on_password=None, on_host=None, on_proxy=None):
        super(ONInterface, self).__init__()
        self.app = app
        self.bridge = 72
        self.tags = {}
    
    def set_configuration(self):
        if self.user_data is None:
            self.get_user_data()
        self.aws_access_key = self.user_data.get('aws_access_key', None)
        self.aws_secret_key = self.user_data.get('aws_secret_key', None)
        self.on_username = self.user_data.get('on_username', None)
        self.on_password = self.user_data.get('on_password', None)
        self.on_host = self.user_data.get('on_host', None)
        self.on_proxy = self.user_data.get('on_proxy', None)
    
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
        # There does not exist a method (yet) to get the instance
        # of a running virtual machine
        # The instance is now identified by its MAC address
        # All connected instances are checked if they
        # match with the current mac address and that VM ID 
        # is returned
        mac = self._getMacAddress('eth0')
        #log.debug(mac)
        vmpool = VirtualMachinePool(self.s3_conn)
        vmpool.info(CONNECTED)
        for vm in list(vmpool):
            vm_info = self.s3_conn.call("vm.info", vm.id)
            if mac in vm_info:
                return str(vm.id)
        return None
    
    def get_zone( self ):
        pass
    
    def get_security_groups( self ):
        pass
    
    def get_key_pair_name( self ):
        pass
    
    def get_self_private_ip( self ):
        # TODO: Change this to the masters IP
        log.debug("Asking for private IP")
        return self._getIpAddress('eth1')
    
    def get_self_public_ip( self ):
        # TODO: Change this to the masters IP
        log.debug("Asking for public IP")
        return self._getIpAddress('eth0')
    
    def get_fqdn(self):
        # Return the hostname
        return socket.getfqdn()
    
    def get_ec2_connection( self ):
        log.debug( 'Getting OpenNebula connection' )
        if self.ec2_conn == None:
            log.debug("No OpenNebula Connection, creating a new one.")
            try:
                self.ec2_conn = Client("%s:%s" % (self.on_username, self.on_password), self.on_host, self.on_proxy)
                self.ec2_conn.lookup = new.instancemethod(lookup, self.ec2_conn, self.ec2_conn.__class__)
                self.ec2_conn.create_bucket = new.instancemethod(create_bucket, self.ec2_conn, self.ec2_conn.__class__)

                try:
                     vmpool = VirtualMachinePool(self.ec2_conn)
                     vmpool.info(CONNECTED)
                     list(vmpool)
                     log.debug( 'Got OpenNebula connection.' )
                except OpenNebulaException, e:
                     log.error("Cannot validate provided credentials: %s" % e)
                     self.ec2_conn = False
            except Exception, e:
                log.error(e)
        return self
    
    def get_s3_connection( self ):
        #Note: S3 = storage (bucket)
        #Opennebula cloud has no storage
        log.debug( 'Getting OpenNebula connection' )
        if self.s3_conn == None:
            log.debug("No OpenNebula Connection, creating a new one.")
            try:
                self.s3_conn = Client("%s:%s" % (self.on_username, self.on_password), self.on_host, self.on_proxy)
                self.s3_conn.lookup = new.instancemethod(lookup, self.s3_conn, self.s3_conn.__class__)
                self.s3_conn.create_bucket = new.instancemethod(create_bucket, self.s3_conn, self.s3_conn.__class__)
 
                           
                try:
                     vmpool = VirtualMachinePool(self.s3_conn)
                     vmpool.info(CONNECTED)
                     list(vmpool)
                     log.debug( 'Got OpenNebula connection.' )
                except OpenNebulaException, e:
                     log.error("Cannot validate provided credentials: %s" % e)
                     self.s3_conn = False
            except socket.error, e:
                log.debug( "Socket error: %s:" % e )
                log.debug("Trying to reboot the machine")
                # It should be prevented that its reboot on a local machine (kvm)
                # local machine hwaddr = 00:22:64:ae:3d:fd
                # TODO
                if self._getMacAddress('eth0') != '00:22:64:ae:3d:fd':
                #if int(self.get_self_private_ip().split('.')[2]) == int(self.bridge):
                    ret_code = subprocess.call( 'sudo telinit 6', shell=True )

                
            except Exception, e:
                log.error(e)
        return self.s3_conn
        #return None
    
    def run_instances(self, num, instance_type, **kwargs):

        #TODO: Change this!!
        username = 'mdhollander'
        diskimage = 'vm-lucid-amd64-serial-galaxy-worker.img'
        vmname = "Cloudman_Node"
        
        log.debug("Adding {0} OpenNebula Worker nodes".format(num))
        # TODO: Remove public NIC? Save disk?
#        vmtemplatestring ="""
#NAME=\"%s\" MEMORY=1024 CPU=1 OS=[BOOT=\"hd\"] 
#GRAPHICS=[type=\"vnc\"] 
#DISK=[TYPE=\"disk\", SOURCE=\"/home/%s/images/%s\", TARGET=\"hda\", CLONE=\"yes\", SAVE=\"no\", READONLY=\"n\" ]
#NIC=[NETWORK=\"%s\", MODEL=\"virtio\"]
#NIC=[NETWORK=\"public\", MODEL=\"virtio\"]
#""" % (vmname, username, diskimage, username)

        vmtemplatestring = """
CPU=1
DISK=[
  BUS=ide,
  IMAGE_ID=316,
  TARGET=hda ]
GRAPHICS=[
  TYPE=vnc ]
MEMORY=8192
NAME=Cloudman_Node
NIC=[
  MODEL=virtio,
  NETWORK_FILTER_ID=62,
  NETWORK_ID=0 ]
NIC=[
  MODEL=virtio,
  NETWORK_ID=23 ]
OS=[
  ARCH=x86_64,
  BOOT=hd ]
RAW=[
  TYPE=kvm ]
TEMPLATE_ID=397
VCPU=1
"""
        r = Reservations()
        for i in range(1,num+1):
            new_vm_id = VirtualMachine.allocate(self.s3_conn, vmtemplatestring)
            
            # Get the just initiated instances
            # TODO: Is there another way to retrieve it? Using new_vm_id?
            vmpool = VirtualMachinePool(self.s3_conn)
            vmpool.info(CONNECTED)
            vm_instance = list(vmpool)[-1]
            
            vm_instance.add_tag = new.instancemethod(add_tag, vm_instance, vm_instance.__class__)
            vm_instance.update = new.instancemethod(update, vm_instance, vm_instance.__class__)

            #vm_instance.id = str(vm_instance.id)
            
            # Add tags dictionary
            vm_instance.tags = {}

            r.instances.append(vm_instance)
        
        return r

# Emulate EC2 objects

    def get_all_instances(self, filters={}, *args, **kwargs):
        client = Client("%s:%s" % (self.on_username, self.on_password), self.on_host, self.on_proxy)
        vmpool = VirtualMachinePool(client)
        vmpool.info(CONNECTED)
        reservations = []
        log.debug("Get all instances")
        
        for vm_instance in vmpool:
            # Make a distinction between worker and the master node
            # The workers nodes have a role defined as worker (dictionary)
            # The master node has a empty list as filter string
            
            # Instance ID needs to be a string
            vm_instance.id = str(vm_instance.id)
            
            # Hold tags in a dictionary
            vm_instance.tags = {}
            try:
                req_id = filters[0]
                if int(req_id) == int(vm_instance.id):
                    reservations = []
                    r = Reservations()
                    vm_instance.add_tag = new.instancemethod(add_tag, vm_instance, vm_instance.__class__)
                    vm_instance.update = new.instancemethod(update, vm_instance, vm_instance.__class__)
                    r.instances.append(vm_instance)
                    reservations.append(r)
                    return reservations
            except:
                pass
            # TODO Add tags to instance? (unsure if this it the right way to do it)
            try:
                for key, value in filters.iteritems():
                    tag = key.split(':')[1]
                    vm_instance.tags[tag] = value
            except AttributeError:
                pass
            
            try:
                role = filters['tag:role'] 
                if role == "worker" and vm_instance.name.strip() == "Cloudman_Node":
                    r = Reservations()
                    vm_instance.add_tag = new.instancemethod(add_tag, vm_instance, vm_instance.__class__)
                    vm_instance.update = new.instancemethod(update, vm_instance, vm_instance.__class__)
                    #vm_instance.get_m_state = get_m_state
                    
                    r.instances.append(vm_instance)
                    reservations.append(r)
            except TypeError :
                # TODO: don't hardcode the name of the master instance
                #if vm_instance.name.strip() == "Galaxy_Main":
                if vm_instance.name.strip() == "one-1592":
                    r = Reservations()
                    vm_instance.add_tag = new.instancemethod(add_tag, vm_instance, vm_instance.__class__)
                    vm_instance.update = new.instancemethod(update, vm_instance, vm_instance.__class__)
                    r.instances.append(vm_instance)
                    reservations.append(r)
                    
        return reservations

    def get_all_volumes(self, *args, **kwargs):
        pass
    
    def terminate_instances(self, instances):
        log.debug("Terminate instances")
        
        return True

    def reboot_instances(self, instances, *args, **kwargs):
        print "Rebooting %s" % instances
        from time import sleep
        # doing a 'slow' reboot: change state to stop and then to resume
        # faster way: sending sudo telinit 6 to worker
        while 1:
            vmpool = VirtualMachinePool(self.s3_conn)
            vmpool.info(CONNECTED)
            for vm_instance in vmpool:
                if vm_instance.id == int(instances[0]):
                    if vm_instance.state == 3:
                        log.debug("stop now!")
                        vm_instance.stop()
                        sleep(40)
                    if vm_instance.state == 4:
                        log.debug("rebooting")
                        vm_instance.resume()
                        return True
                    
    # EC2 can add volumes to a image
    # For ON we will create a filesystem
    # Call: Filesystem.add
    def create_volume(self, size, zone, snapshot):
        # Doing nothing
        v = Volume('dummyapp')
        v.id = None
        v.add_tag = new.instancemethod(add_tag, v, v.__class__)

        return v

    def add_tag(self, key, value, *args, **kwargs):
        self.tags[key] = value
        
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
