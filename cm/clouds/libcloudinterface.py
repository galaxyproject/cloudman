from __future__ import absolute_import
import time
from libcloud.compute.types import Provider as compute_provider
from libcloud.compute.providers import get_driver as compute_get_driver
from libcloud.storage.types import Provider as storage_provider
from libcloud.storage.providers import get_driver as storage_get_driver
import libcloud.security
libcloud.security.VERIFY_SSL_CERT = False

from cm.clouds import CloudInterface
from cm.util.decorators import TestFlag

import logging
log = logging.getLogger('cloudman')


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

    @TestFlag('Local_zone')
    def get_zone(self):
        log.debug("dummy getting zone")

    @TestFlag('ami-l0ca1')
    def get_ami(self):
        if self.ami is None:
            node = self.get_instance_object()
            self.ami = node.image
        return self.ami

    @TestFlag('something.good')
    def get_type(self):
        if self.instance_type is None:
            node = self.get_instance_object()
            self.instance_type = node.size
        return self.instance_type

    @TestFlag('id-LOCAL')
    def get_instance_id(self):
        """"
        Retrieve the instance id for the node.
        """"
        if self.instance_id is None:
            driver = self.get_instance_id()
            my_ip = _get_ip_address("eth0")
            for node in driver.list_nodes():
                for ip in node.public_ips:
                    if my_ip == ip:
                        self.instance_id = node.id
                        break
        return self.instance_id

    @TestFlag('127.0.0.1')
    def _getIpAddress(self, ifname):
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

    def get_instance_object(self):
        log.debug("Getting instance object: %s" % self.instance)
        if self.instance is None:
            if self.app.TESTFLAG is True:
                log.debug(
                    "Attempted to get instance object, but TESTFLAG is set. Returning 'None'")
                return self.instance
            log.debug("Getting instance libcloud object")
            i_id = self.get_instance_id()
            driver = self.get_ec2_connection()
            # Figure out which of the nodes is the cloudman instance.
            for node in driver.list_nodes():
                if node.state == NodeState.RUNNING && node.id = i_id:
                    self.instance = node
                    break
        return self.instance

    @TestFlag('local_keypair')
    def get_key_pair_name(self):
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
