import boto
import socket
import time
import urllib
import yaml

from boto.ec2.connection import EC2Connection
from boto.exception import BotoServerError, EC2ResponseError
from boto.s3.connection import S3Connection

from cm.clouds import CloudInterface
from cm.instance import Instance
from cm.util import misc
from cm.util.decorators import TestFlag

import logging
log = logging.getLogger('cloudman')


class EC2Interface(CloudInterface):

    def __init__(self, app=None):
        super(EC2Interface, self).__init__()
        self.app = app
        self.tags_supported = True
        self.update_frequency = 60
        self.public_hostname_updated = time.time()
        self.set_configuration()
        self._vpc_id = None
        self._security_group_ids = []
        self._security_groups = []
        self._mac_address = None
        self._subnet_id = None
        try:
            log.debug("Using boto version {0}".format(boto.__version__))
        except:
            pass

    @TestFlag('ami-l0cal1')
    def get_ami(self):
        if self.ami is None:
            for i in range(1, 6):
                try:
                    log.debug('Gathering instance ami, attempt %s' % i)
                    fp = urllib.urlopen(
                        'http://169.254.169.254/latest/meta-data/ami-id')
                    self.ami = fp.read()
                    fp.close()
                    if self.ami:
                        break
                except IOError:
                    pass
        return self.ami

    @TestFlag('something.good')
    def get_type(self):
        if self.instance_type is None:
            for i in range(1, 6):
                try:
                    url = 'http://169.254.169.254/latest/meta-data/instance-type'
                    log.debug('Gathering instance type via {0}; attempt {1}/5'
                              .format(url, i+1))
                    fp = urllib.urlopen(url)
                    if fp.code == 200:
                        self.instance_type = fp.read()
                    else:
                        log.warning("Error (code {0}) retrieving instance type "
                                    "from url {1}: {2}".format(fp.code, url,
                                                               fp.read()))
                    fp.close()
                    if self.instance_type:
                        break
                except IOError:
                    pass
        return self.instance_type

    @TestFlag('id-LOCAL')
    def get_instance_id(self):
        if self.instance_id is None:
            for i in range(1, 6):
                try:
                    log.debug('Gathering instance id, attempt %s' % i)
                    fp = urllib.urlopen(
                        'http://169.254.169.254/latest/meta-data/instance-id')
                    self.instance_id = fp.read()
                    fp.close()
                    if self.instance_id:
                        log.debug("Instance ID is '%s'" % self.instance_id)
                        break
                except IOError:
                    pass
        return self.instance_id

    @TestFlag(None)
    def get_instance_object(self):
        log.debug("Getting instance object: %s" % self.instance)
        if self.instance is None:
            log.debug("Getting instance boto object")
            i_id = self.get_instance_id()
            ec2_conn = self.get_ec2_connection()
            try:
                ir = ec2_conn.get_all_instances(i_id)
                self.instance = ir[0].instances[0]
            except EC2ResponseError, e:
                log.debug("Error getting instance object: {0}".format(e))
            except Exception, e:
                log.debug("Error retrieving instance object: {0}".format(e))
        return self.instance

    @TestFlag('us-local-1a')
    def get_zone(self):
        if self.zone is None:
            for i in range(1, 6):
                try:
                    log.debug('Gathering instance zone, attempt %s' % i)
                    fp = urllib.urlopen(
                        'http://169.254.169.254/latest/meta-data/placement/availability-zone')
                    self.zone = fp.read()
                    fp.close()
                    if self.zone:
                        log.debug("Instance zone is '%s'" % self.zone)
                        break
                except IOError:
                    pass
        return self.zone

    @TestFlag('b8:8d:12:0e:60:5a')
    def get_mac_address(self):
        if not self._mac_address:
            fp = urllib.urlopen('http://169.254.169.254/latest/meta-data/mac')
            self._mac_address = fp.read().strip()
            fp.close()
        return self._mac_address

    @property
    def running_in_vpc(self):
        """
        Try to determine if running in a VPC. Return ``True`` if so, ``False``
        otherwise.
        """
        if self.get_vpc_id():
            return True
        return False

    def get_vpc_id(self):
        if not self._vpc_id:
            fp = urllib.urlopen('http://169.254.169.254/latest/meta-data/network/'
                                'interfaces/macs/%s/vpc-id' % self.get_mac_address())
            self._vpc_id = fp.read().strip()
            fp.close()
            if "404 - Not Found" in self._vpc_id:
                self._vpc_id = None
        return self._vpc_id

    def get_subnet_id(self):
        if not self.get_vpc_id():
            return None
        if not self._subnet_id:
            fp = urllib.urlopen('http://169.254.169.254/latest/meta-data/network/'
                                'interfaces/macs/%s/subnet-id' % self.get_mac_address())
            self._subnet_id = fp.read().strip()
            fp.close()
        return self._subnet_id

    def get_security_group_ids(self):
        if not self._security_group_ids:
            self._security_group_ids = []
            fp = urllib.urlopen('http://169.254.169.254/latest/meta-data/network/'
                                'interfaces/macs/%s/security-group-ids' %
                                self.get_mac_address())
            lines = fp.readlines()
            for line in lines:
                self._security_group_ids.append(urllib.unquote_plus(line.strip()))
            fp.close()
            log.debug("Fetched security group ids for the first time: %s" %
                      self._security_group_ids)
        return self._security_group_ids

    @TestFlag(['cloudman_sg'])
    def get_security_groups(self):
        if not self._security_groups:
            for i in range(1, 6):
                try:
                    log.debug(
                        'Gathering instance security group, attempt %s' % i)
                    fp = urllib.urlopen(
                        'http://169.254.169.254/latest/meta-data/security-groups')
                    self._security_groups = []
                    for line in fp.readlines():
                        self._security_groups.append(
                            urllib.unquote_plus(line.strip()))
                    fp.close()
                    if self._security_groups:
                        break
                except IOError:
                    pass
        return self._security_groups

    @TestFlag('local_keypair')
    def get_key_pair_name(self):
        if self.key_pair_name is None:
            for i in range(1, 6):
                try:
                    log.debug(
                        'Gathering instance public keys (i.e., key pairs), attempt %s' % i)
                    fp = urllib.urlopen(
                        'http://169.254.169.254/latest/meta-data/public-keys')
                    public_keys = fp.read()
                    self.key_pair_name = public_keys.split('=')[1]
                    fp.close()
                    if self.key_pair_name:
                        log.debug("Got key pair: '%s'" % self.key_pair_name)
                        break
                except IOError:
                    pass
        return self.key_pair_name

    @TestFlag('127.0.0.1')
    def get_private_ip(self):
        if self.self_private_ip is None:
            for i in range(1, 6):
                try:
                    log.debug('Gathering instance private IP, attempt %s' % i)
                    # fp = urllib.urlopen('http://169.254.169.254/latest/meta-
                    # data/local-hostname')
                    fp = urllib.urlopen(
                        'http://169.254.169.254/latest/meta-data/local-ipv4')
                    self.self_private_ip = fp.read()
                    fp.close()
                    if self.self_private_ip:
                        break
                except IOError:
                    pass
        return self.self_private_ip

    @TestFlag('localhost')
    def get_local_hostname(self):
        if self.local_hostname is None:
            for i in range(1, 6):
                try:
                    log.debug(
                        'Gathering instance local hostname, attempt %s' % i)
                    fp = urllib.urlopen(
                        'http://169.254.169.254/latest/meta-data/local-hostname')
                    self.local_hostname = fp.read()
                    fp.close()
                    if self.local_hostname:
                        break
                except IOError:
                    pass
        return self.local_hostname

    @TestFlag('localhost')
    def get_public_hostname(self):
        """
        Return the current public hostname reported by Amazon.
        Public hostname can be changed -- check it every self.update_frequency.
        """
        if (self.public_hostname is None or
           (time.time() - self.public_hostname_updated > self.update_frequency)):
            for i in range(1, 6):
                try:
                    log.debug(
                        'Gathering instance public hostname, attempt %s' % i)
                    fp = urllib.urlopen(
                        'http://169.254.169.254/latest/meta-data/public-hostname')
                    self.public_hostname = fp.read()
                    fp.close()
                    if self.public_hostname:
                        self.public_hostname_updated = time.time()
                        break
                except Exception, e:
                    log.error("Error retrieving FQDN: %s" % e)
        return self.public_hostname

    @TestFlag('127.0.0.1')
    def get_public_ip(self):
        if self.self_public_ip is None:
            for i in range(1, 6):
                try:
                    log.debug(
                        'Gathering instance public hostname, attempt %s' % i)
                    fp = urllib.urlopen(
                        'http://169.254.169.254/latest/meta-data/public-ipv4')
                    self.self_public_ip = fp.read()
                    fp.close()
                    if self.self_public_ip:
                        # Check if we got an actual IP address or bogus response
                        try:
                            socket.inet_pton(socket.AF_INET, self.self_public_ip)
                        except socket.error:
                            self.self_public_ip = None
                        break
                except Exception, e:
                    log.error("Error retrieving FQDN: %s" % e)
        return self.self_public_ip

    def get_fqdn(self):
        log.debug("Retrieving FQDN")
        if not self.fqdn:
            try:
                self.fqdn = socket.getfqdn()
            except IOError:
                pass
        return self.fqdn

    def get_region_name(self):
        """
        Return the name of the region where currently running.
        """
        if not self.region_name:
            r = self.get_region()
            self.region_name = r.name
            log.debug("Got region name as '{0}'".format(self.region_name))
        return self.region_name

    def get_region(self):
        """
        Return a ``boto`` object representing the region where currently running.
        """
        if not self.region:
            # Get instance zone and figure out the region from there
            zone = self.get_zone()[:-1]  # truncate zone and be left with region name
            tmp_conn = EC2Connection(self.aws_access_key,
                                     self.aws_secret_key)  # get conn in the default region
            try:
                regions = tmp_conn.get_all_regions()
            except EC2ResponseError, e:
                log.error("Cannot validate provided AWS credentials: %s" % e)
            for r in regions:
                if zone in r.name:
                    self.region = r
                    log.debug("Got region as '{0}'".format(self.region))
                    break
        return self.region

    @TestFlag(None)
    def get_ec2_connection(self):
        if not self.ec2_conn:
            try:
                log.debug('Establishing boto EC2 connection')
                # Make sure we get a connection for the correct region
                region = self.get_region()
                self.ec2_conn = EC2Connection(
                    self.aws_access_key, self.aws_secret_key, region=region)
                # Do a simple query to test if provided credentials are valid
                try:
                    self.ec2_conn.get_all_instances()
                    log.debug("Got boto EC2 connection for region '%s'" %
                              self.ec2_conn.region.name)
                except EC2ResponseError, e:
                    log.error("Cannot validate provided AWS credentials (A:%s, S:%s): %s"
                              % (self.aws_access_key, self.aws_secret_key, e))
                    self.ec2_conn = False
            except Exception, e:
                log.error(e)
        return self.ec2_conn

    def get_s3_connection(self):
        # log.debug( 'Getting boto S3 connection' )
        if not self.s3_conn:
            log.debug("No S3 Connection, creating a new one.")
            try:
                self.s3_conn = S3Connection(
                    self.aws_access_key, self.aws_secret_key)
                log.debug('Got boto S3 connection.')
                # try:
                #     self.s3_conn.get_bucket('test_creds') # Any bucket name will do - just testing the call
                #     log.debug( 'Got boto S3 connection.' )
                # except S3ResponseError, e:
                #     log.error("Cannot validate provided AWS credentials: %s" % e)
                #     self.s3_conn = False
            except Exception, e:
                log.error(e)
        return self.s3_conn

    @TestFlag(None)
    def add_tag(self, resource, key, value):
        """ Add tag as key value pair to the `resource` object. The `resource`
        object must be an instance of a cloud object and support tagging.
        """
        if self.tags_supported:
            if resource:
                try:
                    resource_id = None
                    if hasattr(resource, 'id'):
                        resource_id = resource.id
                    log.debug("Adding tag '%s:%s' to resource '%s'" % (
                        key, value, resource_id if resource_id else resource))
                    resource.add_tag(key, value)
                except EC2ResponseError, e:
                    log.error("EC2ResponseError adding tag '%s:%s' to resource "
                              "'%s': %s" % (key, value, resource, e))
                    self.tags_supported = False
                except AttributeError, ae:
                    log.error("AttributeError adding tag '%s:%s' to resource "
                              "'%s': %s" % (key, value, resource, ae))
                if resource_id:
                    resource_tags = self.tags.get(resource_id, {})
                    resource_tags[key] = value
                    self.tags[resource_id] = resource_tags
            else:
                log.debug("Wanted to add a tag {0}:{1} but no resource provided."
                          .format(key, value))

    @TestFlag(None)
    def get_tag(self, resource, key):
        """ Get tag on `resource` cloud object. Return None if tag does not exist.
        """
        value = None
        if self.tags_supported:
            try:
                log.debug(
                    "Getting tag '%s' on resource '%s'" % (key, resource.id))
                value = resource.tags.get(key, None)
            except EC2ResponseError, e:
                log.error("Exception getting tag '%s' on resource '%s': %s" %
                          (key, resource, e))
                self.tags_supported = False
        if not value:
            resource_tags = self.tags.get(resource.id, {})
            value = resource_tags.get(key)
        return value

    @TestFlag(None)
    def run_instances(self, num, instance_type, spot_price=None, **kwargs):
        use_spot = False
        if spot_price is not None:
            use_spot = True
        log.info("Adding {0} {1} instance(s)".format(
            num, 'spot' if use_spot else 'on-demand'))
        worker_ud = self._compose_worker_user_data()
        # log.debug( "Worker user data: %s " % worker_ud )
        if instance_type == '':
            instance_type = self.get_type()
        if use_spot:
            self._make_spot_request(num, instance_type, spot_price, worker_ud)
        else:
            self._run_ondemand_instances(
                num, instance_type, spot_price, worker_ud)

    def _run_ondemand_instances(self, num, instance_type, spot_price, worker_ud, min_num=1):

        # log.debug("Setting boto's logger to DEBUG mode")
        # logging.getLogger('boto').setLevel(logging.DEBUG)

        worker_ud_str = yaml.dump(worker_ud)

        try:
            # log.debug( "Would be starting worker instance(s)..." )
            reservation = None
            ec2_conn = self.get_ec2_connection()
            if self.running_in_vpc:
                log.debug("Starting instance(s) in VPC with the following command : ec2_conn.run_instances( "
                          "image_id='{iid}', min_count='{min_num}', max_count='{num}', key_name='{key}', "
                          "security_group_ids={sgs}, user_data(with sensitive info filtered out)=[{ud}], "
                          "instance_type='{type}', placement='{zone}', subnet_id='{subnet_id}')"
                          .format(iid=self.get_ami(), min_num=min_num, num=num,
                                  key=self.get_key_pair_name(), sgs=self.get_security_group_ids(),
                                  ud=("\n".join(['%s: %s' % (key, value)
                                      for key, value in worker_ud.iteritems()
                                      if key not in['password', 'freenxpass', 'secret_key']])),
                                  type=instance_type, zone=self.get_zone(), subnet_id=self.get_subnet_id()))

                interface = boto.ec2.networkinterface.NetworkInterfaceSpecification(
                    subnet_id=self.get_subnet_id(),
                    groups=self.get_security_group_ids(),
                    associate_public_ip_address=True)
                interfaces = boto.ec2.networkinterface.NetworkInterfaceCollection(interface)

                reservation = ec2_conn.run_instances(image_id=self.get_ami(),
                                                     min_count=min_num,
                                                     max_count=num,
                                                     key_name=self.get_key_pair_name(),
                                                     user_data=worker_ud_str,
                                                     instance_type=instance_type,
                                                     network_interfaces=interfaces,
                                                     )
            else:
                log.debug("Starting instance(s) with the following command : ec2_conn.run_instances( "
                          "image_id='{iid}', min_count='{min_num}', max_count='{num}', key_name='{key}', "
                          "security_groups=['{sgs}'], user_data(with sensitive info filtered out)=[{ud}], "
                          "instance_type='{type}', placement='{zone}')"
                          .format(iid=self.get_ami(), min_num=min_num, num=num,
                                  key=self.get_key_pair_name(), sgs=", ".join(self.get_security_groups()),
                                  ud=("\n".join(['%s: %s' % (key, value)
                                      for key, value in worker_ud.iteritems()
                                      if key not in['password', 'freenxpass', 'secret_key']])),
                                  type=instance_type, zone=self.get_zone()))
                reservation = ec2_conn.run_instances(image_id=self.get_ami(),
                                                     min_count=min_num,
                                                     max_count=num,
                                                     key_name=self.get_key_pair_name(),
                                                     security_groups=self.get_security_groups(),
                                                     user_data=worker_ud_str,
                                                     instance_type=instance_type,
                                                     placement=self.get_zone())
            # Rarely, instances take a bit to register,
            # so wait a few seconds (although this is a very poor
            # 'solution')
            time.sleep(3)
            if reservation:
                for instance in reservation.instances:
                    # At this point in the launch, tag only amazon instances
                    if 'amazon' in self.app.config.get('cloud_name', 'amazon').lower():
                        self.add_tag(instance, 'clusterName', self.app.config['cluster_name'])
                        self.add_tag(instance, 'role', worker_ud['role'])
                        self.add_tag(instance, 'Name', "Worker: {0}".format(self.app.config['cluster_name']))
                    i = Instance(app=self.app, inst=instance, m_state=instance.state)
                    log.debug("Adding Instance %s" % instance)
                    self.app.manager.worker_instances.append(i)
        except EC2ResponseError, e:
            err = "EC2 response error when starting worker nodes: %s" % str(e)
            log.error(err)
            return False
        except BotoServerError, e:
            log.error(
                "boto server error when starting an instance: %s" % str(e))
            return False
        except Exception, ex:
            err = "Error when starting worker nodes: %s" % str(ex)
            log.error(err)
            return False
        log.debug("Started %s instance(s)" % num)
        logging.getLogger('boto').setLevel(logging.INFO)
        log.debug("Setting boto's logger to INFO mode")

    def _make_spot_request(self, num, instance_type, price, worker_ud):
        worker_ud_str = yaml.dump(worker_ud)

        reqs = None
        try:
            ec2_conn = self.get_ec2_connection()
            if self.get_subnet_id():
                log.debug("Making a spot instance request, using groups: %s, subnet=%s"
                          % (self.get_security_group_ids(), self.get_subnet_id()))
                interface = boto.ec2.networkinterface.NetworkInterfaceSpecification(
                    subnet_id=self.get_subnet_id(),
                    groups=self.get_security_group_ids(),
                    associate_public_ip_address=True)
                interfaces = boto.ec2.networkinterface.NetworkInterfaceCollection(interface)
                reqs = ec2_conn.request_spot_instances(price=price,
                                                       image_id=self.get_ami(),
                                                       count=num,
                                                       key_name=self.get_key_pair_name(),
                                                       instance_type=instance_type,
                                                       placement=self.get_zone(),
                                                       user_data=worker_ud_str,
                                                       network_interfaces=interfaces,
                                                       )
            else:
                log.debug("Making a Spot request with the following command: "
                          "ec2_conn.request_spot_instances(price='{price}', image_id='{iid}', "
                          "count='{num}', key_name='{key}', security_groups=['{sgs}'], "
                          "instance_type='{type}', placement='{zone}', user_data='{ud}')"
                          .format(price=price, iid=self.get_ami(), num=num, key=self.get_key_pair_name(),
                                  sgs=", ".join(self.get_security_groups()), type=instance_type,
                                  zone=self.get_zone(), ud=worker_ud_str))
                reqs = ec2_conn.request_spot_instances(price=price,
                                                       image_id=self.get_ami(),
                                                       count=num,
                                                       key_name=self.get_key_pair_name(),
                                                       security_groups=self.get_security_groups(),
                                                       instance_type=instance_type,
                                                       placement=self.get_zone(),
                                                       user_data=worker_ud_str)

            if reqs is not None:
                for req in reqs:
                    i = Instance(app=self.app, spot_request_id=req.id)
                    log.debug("Adding Spot request {0} as an Instance".format(req.id))
                    self.app.manager.worker_instances.append(i)
        except EC2ResponseError, e:
            log.error("Trouble issuing a spot instance request: {0}".format(e))
            return False
        except Exception, e:
            log.error("An error when making a spot request: {0}".format(e))
            return False

    @TestFlag(True)
    def terminate_instance(self, instance_id, spot_request_id=None):
        inst_terminated = request_canceled = True
        if instance_id is not None:
            inst_terminated = self._terminate_instance(instance_id)
        if spot_request_id is not None:
            request_canceled = self._cancel_spot_request(spot_request_id)
        return (inst_terminated and request_canceled)

    def _terminate_instance(self, instance_id):
        ec2_conn = self.get_ec2_connection()
        try:
            log.info("Terminating instance {0}".format(instance_id))
            ec2_conn.terminate_instances([instance_id])
            log.debug(
                "Initiated termination of instance {0}".format(instance_id))
            # Make sure the instance was terminated
            time.sleep(
                3)  # First give the middleware a chance to register the termination
            rs = ec2_conn.get_all_instances([instance_id])
            if len(rs) == 0 or rs[0].instances[0].state == 'shutting-down' or \
                    rs[0].instances[0].state == 'terminated':
                log.debug("Instance {0} terminated.".format(instance_id))
                return True
        except EC2ResponseError, e:
            if e.errors[0][0] == 'InstanceNotFound':
                return True
            else:
                log.error(
                    "EC2 exception terminating instance '%s': %s" % (instance_id, e))
        except Exception, ex:
            log.error(
                "Exception terminating instance %s: %s" % (instance_id, ex))
        return False

    def _cancel_spot_request(self, request_id):
        ec2_conn = self.get_ec2_connection()
        try:
            log.debug("Canceling spot request {0}".format(request_id))
            ec2_conn.cancel_spot_instance_requests([request_id])
            return True
        except EC2ResponseError, e:
            log.error("Trouble canceling spot request {0}: {1}".format(
                request_id, e))
            return False

    def _compose_worker_user_data(self):
        """
        Compose worker instance user data, returning a dictionary.
        """
        worker_ud = {}
        worker_ud['role'] = 'worker'
        worker_ud['master_public_ip'] = self.get_public_ip()
        worker_ud['master_ip'] = self.get_private_ip()
        worker_ud['master_hostname'] = self.get_local_hostname()
        worker_ud['master_hostname_alt'] = misc.get_hostname()
        worker_ud['cluster_type'] = self.app.manager.initial_cluster_type
        # Merge the worker's user data with the master's user data
        worker_ud = dict(self.app.config.items() + worker_ud.items())
        return worker_ud

    def create_volume(self, size, zone, snapshot=None, volume_type='gp2', iops=None):
        """
        Create a new EBS Volume.

        :type size: int
        :param size: The size of the new volume, in GiB

        :type zone: string or :class:`boto.ec2.zone.Zone`
        :param zone: The availability zone in which the Volume will be created.

        :type snapshot: string or :class:`boto.ec2.snapshot.Snapshot`
        :param snapshot: The snapshot from which the new Volume will be
                         created.

        :type volume_type: string
        :param volume_type: The type of the volume. (optional).  Valid
                            values are: standard | io1 | gp2.

        :type iops: int
        :param iops: The provisioned IOPS you want to associate with
                     this volume. (optional)

        :rtype: `None` or :class:`boto.ec2.volume.Volume`
        :return: If the volume was created successfully, return a boto instance
                 of the Volume object. Otherwise, return `None`.
        """
        try:
            return self.get_ec2_connection().create_volume(
                size=size, zone=zone, snapshot=snapshot, volume_type=volume_type,
                iops=iops)
        except EC2ResponseError as ec2e:
            log.error("EC2ResponseError creating a volume: {0}".format(ec2e))
        return None

    def delete_volume(self, volume_id):
        """
        Delete an EBS volume.

        :type volume_id: str
        :param volume_id: The ID of the volume to be deleted.

        :rtype: bool
        :return: True if successful.
        """
        try:
            if self.get_ec2_connection().delete_volume(volume_id):
                log.debug("Deleted volume {0}".format(volume_id))
        except EC2ResponseError as ec2e:
            log.error("EC2ResponseError deleting volume {0}: {1}"
                      .format(volume_id, ec2e))
        log.debug("Failed to delete volume {0}".format(volume_id))
        return False

    def get_all_volumes(self, volume_ids=None, filters=None):
        """
        Get all Volumes associated with the current credentials.

        :type volume_ids: list
        :param volume_ids: Optional list of volume IDs.  If this list
                           is present, only the volumes associated with
                           these volume IDs will be returned.

        :type filters: dict
        :param filters: Optional filters that can be used to limit
                        the results returned. Filters are provided
                        in the form of a dictionary consisting of
                        filter names as the key and filter values
                        as the value. The set of allowable filter
                        names/values is dependent on the request
                        being performed. Check the EC2 API guide
                        for details.

        :rtype: list of :class:`boto.ec2.volume.Volume`
        :return: The requested Volume objects
        """
        if volume_ids and not isinstance(volume_ids, list):
            volume_ids = [volume_ids]
        return self.get_ec2_connection().get_all_volumes(volume_ids=volume_ids,
                                                         filters=filters)

    def delete_snapshot(self, snapshot_id):
        """
        Delete a volume snapshot.

        :type snapshot_id: str
        :param snapshot_id: The ID of the snapshot to be deleted.

        :rtype: bool
        :return: True if successful.
        """
        try:
            if self.get_ec2_connection().delete_snapshot(snapshot_id):
                log.debug("Deleted snapshot {0}".format(snapshot_id))
        except EC2ResponseError as ec2e:
            log.error("EC2ResponseError deleting snapshot {0}: {1}"
                      .format(snapshot_id, ec2e))
        log.debug("Failed to delete snapshot {0}".format(snapshot_id))
        return False

    def get_all_snapshots(self, snapshot_ids=None, filters=None):
        """
        Get all Snapshots associated with the current credentials.

        :type snapshot_ids: list
        :param snapshot_ids: Optional list of snapshot IDs.  If this list
                           is present, only the snapshots associated with
                           these snapshot IDs will be returned.

        :type filters: dict
        :param filters: Optional filters that can be used to limit
                        the results returned. Filters are provided
                        in the form of a dictionary consisting of
                        filter names as the key and filter values
                        as the value. The set of allowable filter
                        names/values is dependent on the request
                        being performed. Check the EC2 API guide
                        for details.

        :rtype: list of :class:`boto.ec2.snapshot.Snapshot` objects
        :return: The requested Snapshot objects or an empty list if encounter
                 ``EC2ResponseError``.
        """
        if snapshot_ids and not isinstance(snapshot_ids, list):
            snapshot_ids = [snapshot_ids]
        try:
            return self.get_ec2_connection().get_all_snapshots(
                snapshot_ids=snapshot_ids, filters=filters)
        except EC2ResponseError, e:
            log.error("EC2ResponseError retrieving snapshot IDs {0}: {1}"
                      .format(snapshot_ids, e))
        return []

    def get_snapshot(self, snapshot_id):
        """
        Get a Snapshot object for the ``snapshot_id``.

        :type snapshot_id: string
        :param snapshot_ids: The snapshot ID to try and retrieve

        :rtype: :class:`boto.ec2.snapshot.Snapshot` object
        :return: The Snapshot object corresponding to the provided ``snapshot_id``
                 or ``None`` if the snapshot wasn't found or in the case of
                 ``EC2ResponseError``.
        """
        snaps_list = self.get_all_snapshots([snapshot_id])
        if snaps_list:
            return snaps_list[0]
        return None

    def get_snapshot_info(self, snapshot_id):
        """
        Get updated info for the ``snapshot_id``.

        :type snapshot_id: string
        :param snapshot_ids: The snapshot ID to check on

        :rtype: dict
        :return: A dictionary with the following keys capturing the current
                 state of the snapshot: ``id``, ``progress``, ``status``,
                 ``tags``, ``region_name``, ``description``, ``volume_id``,
                 and ``volume_size``.
                 If the snapshot wasn't found or in the case of
                 ``EC2ResponseError``, return an empty dict.
        """
        snap_info = {
            'id': snapshot_id,
            'progress': None,
            'status': None,
            'tags': {},
            'region_name': None,
            'description': None,
            'volume_id': None,
            'volume_size': None,
            'is_public': None,
            'owner_id': None
        }
        snap = self.get_snapshot(snapshot_id)
        if snap:
            try:
                snap.update()
                snap_info = {
                    'id': snapshot_id,
                    'progress': snap.progress,
                    'status': snap.status,
                    'tags': snap.tags,
                    'region_name': snap.region.name,
                    'description': snap.description,
                    'volume_id': snap.volume_id,
                    'volume_size': snap.volume_size,
                    'is_public': 'all' in snap.get_permissions().get('groups', []),
                    'owner_id': snap.owner_id
                }
            except EC2ResponseError, e:
                log.error("EC2ResponseError getting snapshot {0} info: {1}"
                          .format(snapshot_id, e))
        return snap_info

    def get_all_instances(self, instance_ids=None, filters=None):
        """
        Retrieve all the instances associated with current credentials.

        :type instance_ids: list
        :param instance_ids: Optional list of strings of instance IDs.
                             If this list if present, only the instances
                             associated instance IDs will be returned.

        :type filters: dict
        :param filters: Optional filters that can be used to limit the
                        results returned. Filters are provided in the form of a
                        dictionary consisting of filter names as the key and
                        filter values as the value. The set of allowable filter
                        names/values is dependent on the request being performed.
                        Check the EC2 API guide for details.

        :rtype: list
        :return: A list of  :class:`boto.ec2.instance.Reservation`
        """
        if instance_ids and not isinstance(instance_ids, list):
            instance_ids = [instance_ids]
        return self.get_ec2_connection().get_all_instances(instance_ids=instance_ids, filters=filters)

    def account_id(self):
        """
        Figure out what the current user's account ID is.

        AWS does not make this readily available so we need to deduce it.
        """
        try:
            sg = self.get_ec2_connection().get_all_security_groups()[0]
            return sg.owner_id
        except EC2ResponseError as e:
            log.debug("Trouble getting account ID: %s" % e)
            return None
