from __future__ import absolute_import
import time
from libcloud.compute.types import Provider as compute_provider
from libcloud.compute.providers import get_driver as compute_get_driver
from libcloud.storage.types import Provider as storage_provider
from libcloud.storage.providers import get_driver as storage_get_driver
from libcloud.compute.types import NodeState
import libcloud.security
libcloud.security.VERIFY_SSL_CERT = False

from cm.clouds import CloudInterface
from cm.util.decorators import TestFlag

import logging
log = logging.getLogger('cloudman')

import socket
import fcntl
import struct

class LibCloudInterface(CloudInterface):

    def __init__(self, app=None):
        super(LibCloudInterface, self).__init__()
        self.app = app
        self.tags_supported = True
        self.update_frequency = 60
        self.public_hostname_updated = time.time()
        self.set_configuration()
        try:
            log.debug("Using libcloud version {0}".format(libcloud.__version__))
        except:
            pass

    def get_ec2_connection(self):
        """
        Get a reference to the cloud connection object to be used for all
        communication with the cloud for the compute side of resources.
        """
        if not self.ec2_conn:
            try:
                log.debug('Establishing libcloud compute connection using {0} driver.'
                    .format(str(self.app.cloud_type).upper()))
                driver = compute_get_driver(getattr(compute_provider,
                    str(self.app.cloud_type).upper()))
                self.ec2_conn = driver(self.aws_access_key, self.aws_secret_key)
                # Do a simple query to test if provided credentials are valid
                try:
                    self.ec2_conn.list_nodes()
                    log.debug("Got libcloud EC2 connection for region '%s'" %
                              self.ec2_conn.region_name)
                except Exception, e:
                    log.error("Cannot validate provided credentials (A:%s, S:%s): %s"
                              % (self.aws_access_key, self.aws_secret_key, e))
                    self.ec2_conn = None
            except Exception, e:
                log.error("Trouble getting libcloud compute connection: %s" % e)
                self.ec2_conn = None
        return self.ec2_conn

    def get_s3_connection(self):
        """
        Get a reference to the cloud connection object to be used for all
        communication with the cloud for the storage side of resources.
        """
        if not self.s3_conn:
            log.debug('Establishing libcloud storage connection')
            try:
                provider = None
                cloud_type = self.app.cloud_type
                if cloud_type == "ec2":
                    provider = storage_provider.S3
                elif cloud_type.lower() == 'os' or cloud_type.lower() == 'openstack':
                    provider = storage_provider.OPENSTACK_SWIFT
                # elif cloud_type.lower() == 'opennebula':
                #     cloud_interface = ONInterface(app=self.app)
                elif cloud_type == 'dummy':
                    provider = storage_provider.DUMMY

                if provider:
                    log.debug('Establishing libcloud storage connection using {0} provider.'
                        .format(provider))
                    driver = storage_get_driver(provider)
                    self.s3_conn = driver(self.aws_access_key, self.aws_secret_key)
                else:
                    log.error("No storage driver - cannot establish connection "
                        "with storage infrastructure")
            except Exception, e:
                log.error("Trouble getting libcloud storage connection: %s" % e)
                self.s3_conn = None
        return self.s3_conn

    @TestFlag('us-east-1a)
    def get_zone(self):
        if self.app.cloud_type = "ec2":
            node = self.get_instance_object()
            self.zone = node.extra['availability']
        return self.zone

    @TestFlag('ami-l0ca1')
    def get_ami(self):
        """
        Get the image that is backing the instance.

        :rtype: NodeImage
        :return: The image that is backing the instance.
        """
        if self.ami is None:
            node = self.get_instance_object()
            self.ami = node.image
        return self.ami

    @TestFlag('something.good')
    def get_type(self):
        """
        Get the resource template for the compute node.

        :rtype: NodeSize
        :return: The resource template for the compute node.
        """
        if self.instance_type is None:
            node = self.get_instance_object()
            self.instance_type = node.size
        return self.instance_type

    @TestFlag('id-LOCAL')
    def get_instance_id(self):
        """
        Retrieve the instance id for the node.
        """
        if self.instance_id is None:
            driver = self.get_ec2_connection()
            my_ip = _get_ip_address("eth0")
            for node in driver.list_nodes():
                for ip in node.public_ips:
                    if my_ip == ip:
                        self.instance_id = node.id
                        break
        return self.instance_id

    @TestFlag('127.0.0.1')
    def _get_ip_address(self, ifname):
        """
        Retrieve the ip address bound to an interface.
        """
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

    @TestFlag(None)
    def get_instance_object(self):
        """
        Get the object representing the cloudman instance.
        """
        log.debug("Getting instance object: %s" % self.instance)
        if self.instance is None:
            log.debug("Getting instance libcloud object")
            i_id = self.get_instance_id()
            driver = self.get_ec2_connection()
            # Figure out which of the nodes is the cloudman instance.
            for node in driver.list_nodes():
                if node.state == NodeState.RUNNING and node.id == i_id:
                    self.instance = node
                    break
        return self.instance

    @TestFlag('local_keypair')
    def get_key_pair_name(self):
        """
        Get the name of the keypair that is used to authenticate.
        """
        if self.key_pair_name is None:
            driver = self.get_ec2_connection()
            key_pairs = driver.list_key_pairs()
            if key_pairs:
                self.key_pair_name = key_pairs()[0].name
        return self.key_pair_name

    @TestFlag('127.0.0.1')
    def get_private_ip(self):
        if self.self_private_ip is None:
            node = self.get_instance_object()
            if node.private_ips:
                self.self_private_ip = node.private_ips[0]
        return self.self_private_ip

    @TestFlag('127.0.0.1')
    def get_public_ip(self):
        if self.self_public_ip is None:
            node = self.get_instance_object()
            if node.public_ips:
                self.self_public_ip = node.public_ips[0]
        return self.self_public_ip

    @TestFlag('localhost.localdomain')
    def get_fqdn(self):
        log.debug("Retrieving FQDN")
        if not self.fqdn:
            try:
                self.fqdn = socket.getfqdn()
            except IOError:
                pass
        return self.fqdn

    @TestFlag([])
    def get_all_volumes(self, volume_ids=None, filters=None):
        """
        Get all Volumes associated with the current credentials.

        :type volume_ids: list
        :param volume_ids: Not used in the base implementation.

        :type filters: dict
        :param filters: Not used in the base implementation.

        :rtype: list
        :return: The requested Volume objects
        """
        return self.get_ec2_connection().list_volumes()

    def get_all_instances(self, instance_ids=None, filters=None):
        """
        Retrieve all the instances associated with current credentials.

        :type instance_ids: list
        :param instance_ids: Not used in the base implementation.

        :type filters: dict
        :param filters: Not used in the base implementation.

        :rtype: list
        :return: A list of instances
        """
        return self.get_ec2_connection().list_nodes()

    def _compose_worker_user_data(self):
        """
        Compose worker instance user data.
        """
        worker_ud = {}
        worker_ud['role'] = 'worker'
        worker_ud['master_public_ip'] = self.get_public_ip()
        worker_ud['master_ip'] = self.get_private_ip()
        worker_ud['master_hostname'] = self.get_local_hostname()
        worker_ud['cluster_type'] = self.app.manager.initial_cluster_type
        # Merge the worker's user data with the master's user data
        worker_ud = dict(self.app.ud.items() + worker_ud.items())
        return worker_ud

    def terminate_instance(self, instance_id, spot_request=None):
        """
        Terminate an instance.

        :type instance_id: str
        :param instance_id: The id of the instance to terminate

        :type spot_request: bool
        :param spot_request: Not used in the base implementation.

        :rtype: bool
        :return: True if the instance was terminated
        """
        node = _get_instance(instance_id)
        if not node:
            return False
        return node.destroy()

    def _get_instance(self, instance_id):
        """
        Get an instance by it's instance_id.

        :type instance_id: str
        :param instance_id: the instance_id to retrieve

        :rtype: Node
        :return: the Node for the instance, None if there's no instance with
        the given instance_id.
        """
        for node in self.get_ec2_connection().list_nodes():
            if node.id == instance_id:
                return node
        return None

    @TestFlag([])
    def run_instance(self, num, instance_type, spot_price=None, **kwargs):
        """
        Create num new instances.
        :type num: int
        :param num: the number of instances to create

        :type instance_type: NodeSize
        :param instance_type: the type of instance to create

        :type spot_price: bool
        :param spot_price: Not used in the base implementation.

        :rtype: list
        :return: a list of instance_id's for the created instances.
        """
        driver = self.get_ec2_connection()
        nodes= []
        for i in range(0, num):
            node = driver.create_node(name="",
                size=instance_type, image=self.get_ami(),
                location=self.get_zone(),auth=driver.list_key_pairs()[0])
            nodes.append(node.id)
        return nodes
