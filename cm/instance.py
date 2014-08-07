"""CloudMan worker instance class"""
import datetime as dt
import json
import logging
import logging.config
import threading
import time

from boto.exception import EC2ResponseError

from cm.services import ServiceRole
from cm.services import ServiceType
from cm.util import instance_lifecycle, instance_states, misc, spot_states, Time
from cm.util.decorators import TestFlag

log = logging.getLogger('cloudman')

# Time well in past to seend reboot, last comm times with.
TIME_IN_PAST = dt.datetime(2012, 1, 1, 0, 0, 0)


class Instance(object):
    def __init__(self, app, inst=None, m_state=None, last_m_state_change=None,
                 sw_state=None, reboot_required=False, spot_request_id=None):
        self.app = app
        self.config = app.config
        self.spot_request_id = spot_request_id
        self.lifecycle = instance_lifecycle.SPOT if self.spot_request_id else instance_lifecycle.ONDEMAND
        self.inst = inst  # boto object of the instance
        self.spot_state = None
        self.private_ip = None
        self.public_ip = None
        self.local_hostname = None
        if inst:
            try:
                self.id = str(inst.id)
            except EC2ResponseError, e:
                log.error("Error retrieving instance id: %s" % e)
        else:
            self.id = None
        # Machine state as obtained from the cloud middleware (see
        # instance_states Bunch)
        self.m_state = m_state
        self.last_m_state_change = Time.now()
        # A time stamp when the most recent update of the instance state
        # (m_state) took place
        self.last_state_update = Time.now()
        self.sw_state = sw_state  # Software state
        self.is_alive = False
        self.num_cpus = 1
        self.time_rebooted = TIME_IN_PAST  # Initialize to a date in the past
        self.reboot_count = 0
        self.terminate_attempt_count = 0
        self.last_comm = TIME_IN_PAST  # Initialize to a date in the past
        self.nfs_data = 0
        self.nfs_tools = 0
        self.nfs_indices = 0
        self.nfs_sge = 0
        self.nfs_tfs = 0  # Transient file system, NFS-mounted from the master
        self.get_cert = 0
        self.sge_started = 0
        self.slurmd_running = 0
        # NodeName by which this instance is tracked in Slurm
        self.alias = 'w{0}'.format(self.app.number_generator.next())
        self.worker_status = 'Pending'  # Pending, Wake, Startup, Ready, Stopping, Error
        self.load = 0
        self.type = 'Unknown'
        self.reboot_required = reboot_required
        self.update_spot()

    def __repr__(self):
        return self.get_desc()

    def maintain(self):
        """ Based on the state and status of this instance, try to do the right thing
            to keep the instance functional. Note that this may lead to terminating
            the instance.
        """
        def reboot_terminate_logic():
            """ Make a decision whether to terminate or reboot an instance.
                CALL THIS METHOD CAREFULLY because it defaults to terminating the
                instance!
            """
            if self.reboot_count < self.config.instance_reboot_attempts:
                self.reboot()
            elif self.terminate_attempt_count >= self.config.instance_terminate_attempts:
                log.info("Tried terminating instance {0} {1} times but was unsuccessful. Giving up."
                         .format(self.inst.id, self.config.instance_terminate_attempts))
                self._remove_instance()
            else:
                log.info("Instance {0} not responding after {1} reboots. Terminating instance."
                         .format(self.id, self.reboot_count))
                self.terminate()

        # Update state then do resolution
        state = self.get_m_state()
        if state == instance_states.PENDING or state == instance_states.SHUTTING_DOWN:
            if (Time.now() - self.last_m_state_change).seconds > self.config.instance_state_change_wait and \
               (Time.now() - self.time_rebooted).seconds > self.config.instance_reboot_timeout:
                log.debug("'Maintaining' instance {0} stuck in '{1}' state.".format(
                    self.get_desc(), state))
                reboot_terminate_logic()
        elif state == instance_states.ERROR:
            log.debug("'Maintaining' instance {0} in '{1}' state.".format(self.get_desc(), instance_states.ERROR))
            reboot_terminate_logic()
        elif state == instance_states.TERMINATED:
            log.debug("'Maintaining' instance {0} in '{1}' state.".format(self.get_desc(), instance_states.TERMINATED))
            self._remove_instance()
        elif state == instance_states.RUNNING:
            log.debug("'Maintaining' instance {0} in '{1}' state (last comm before {2} | "
                      "last m_state change before {3} | time_rebooted before {4}"
                      .format(self.get_desc(), instance_states.RUNNING,
                              dt.timedelta(seconds=(Time.now() - self.last_comm).seconds),
                              dt.timedelta(seconds=(Time.now() - self.last_m_state_change).seconds),
                              dt.timedelta(seconds=(Time.now() - self.time_rebooted).seconds)))
            if (Time.now() - self.last_comm).seconds > self.config.instance_comm_timeout and \
               (Time.now() - self.last_m_state_change).seconds > self.config.instance_state_change_wait and \
               (Time.now() - self.time_rebooted).seconds > self.config.instance_reboot_timeout:
                reboot_terminate_logic()

    @TestFlag(None)
    def get_cloud_instance_object(self, deep=False):
        """ Get the instance object for this instance from the library used to
            communicate with the cloud middleware. In the case of boto, this
            is the boto EC2 Instance object.

            :type deep: bool
            :param deep: If True, force the check with the cloud middleware; else
                         use local field by default

            :rtype: boto.ec2.instance.Instance (should really be a more generic repr
                    but we'll wait for OCCI or something)
            :return: cloud instance object for this instance
        """
        if deep is True:  # reset the current local instance field
            self.inst = None
        if self.inst is None and self.id is not None:
            try:
                rs = self.app.cloud_interface.get_all_instances(self.id)
                if len(rs) == 0:
                    log.warning("Instance {0} not found on the cloud?".format(
                        self.id))
                for r in rs:
                    # Update local fields
                    self.inst = r.instances[0]
                    self.id = r.instances[0].id
                    self.m_state = r.instances[0].state
            except EC2ResponseError, e:
                log.error("Trouble getting the cloud instance ({0}) object: {1}".format(self.id, e))
            except Exception, e:
                log.error("Error getting the cloud instance ({0}) object: {1}".format(self.id, e))
        elif not self.is_spot():
            log.debug(
                "Cannot get cloud instance object without an instance ID?")
        return self.inst

    def is_spot(self):
        """ Test is this Instance is a Spot instance.

            :rtype: bool
            :return: True if the current Instance is Spot instance, False otherwise.
        """
        return self.lifecycle == instance_lifecycle.SPOT

    def spot_was_filled(self):
        """ For Spot-based instances, test if the spot request has been
            filled (ie, an instance was started)

            :rtype: bool
            :return: True if this is a Spot instance and the Spot request
                     is in state spot_states.ACTIVE. False otherwise.
        """
        self.update_spot()
        if self.is_spot() and self.spot_state == spot_states.ACTIVE:
            return True
        return False

    def get_status_dict(self):
        toret = {'id': self.id,
                 'alias': self.alias,
                 'ld': self.load,
                 'time_in_state': misc.formatSeconds(Time.now() - self.last_m_state_change),
                 'nfs_data': self.nfs_data,
                 'nfs_tools': self.nfs_tools,
                 'nfs_indices': self.nfs_indices,
                 'nfs_sge': self.nfs_sge,
                 'nfs_tfs': self.nfs_tfs,
                 'get_cert': self.get_cert,
                 'slurmd_running': self.slurmd_running,
                 'worker_status': self.worker_status,
                 'instance_state': self.m_state,
                 'instance_type': self.type,
                 'public_ip': self.public_ip}

        if self.load:
            lds = self.load.split(' ')
            if len(lds) == 3:
                toret['ld'] = "%s %s %s" % (float(lds[0]) / self.num_cpus, float(
                    lds[1]) / self.num_cpus, float(lds[2]) / self.num_cpus)
        return toret

    def get_status_array(self):
        if self.m_state.lower() == "running":  # For extra states.
            if self.is_alive is not True:
                ld = "Starting"
            elif self.load:
                lds = self.load.split(' ')
                if len(lds) == 3:
                    try:
                        load1 = float(lds[0]) / self.num_cpus
                        load2 = float(lds[1]) / self.num_cpus
                        load3 = float(lds[2]) / self.num_cpus
                        ld = "%s %s %s" % (load1, load2, load3)
                    except Exception, e:
                        log.debug("Problems normalizing load: %s" % e)
                        ld = self.load
                else:
                    ld = self.load
            elif self.worker_status == "Ready":
                ld = "Running"
            return [self.id, ld, misc.formatSeconds(
                Time.now() - self.last_m_state_change),
                self.nfs_data, self.nfs_tools, self.nfs_indices, self.nfs_sge, self.get_cert,
                self.sge_started, self.worker_status]
        else:
            return [self.id, self.m_state,
                    misc.formatSeconds(Time.now() - self.last_m_state_change),
                    self.nfs_data, self.nfs_tools, self.nfs_indices,
                    self.nfs_sge, self.get_cert, self.sge_started,
                    self.worker_status]

    @TestFlag("TestInstanceID")
    def get_id(self):
        if self.inst is not None and self.id is None:
            try:
                self.inst.update()
                self.id = self.inst.id
            except EC2ResponseError, e:
                log.error("Error retrieving instance id: %s" % e)
            except Exception, e:
                log.error("Exception retreiving instance object: %s" % e)
        return self.id

    def get_desc(self):
        """ Get basic but descriptive info about this instance. Useful for logging.
        """
        if self.is_spot() and not self.spot_was_filled():
            return "'{sid}'".format(sid=self.spot_request_id)
        # TODO : DO NOT redefine id, etc.
        return "'{id}; {ip}; {sn}'".format(id=self.get_id(), ip=self.get_public_ip(),
                                           sn=self.alias)

    def reboot(self, count_reboot=True):
        """
        Reboot this instance. If ``count_reboot`` is set, increment the number
        of reboots for this instance (a treshold in this count leads to eventual
        instance termination, see ``self.config.instance_reboot_attempts``).
        """
        if self.inst is not None:
            # Show reboot count only if this reboot counts toward the reboot quota
            s = " (reboot #{0})".format(self.reboot_count + 1)
            log.info("Rebooting instance {0}{1}.".format(self.get_desc(),
                                                         s if count_reboot else ''))
            try:
                self.inst.reboot()
                self.time_rebooted = Time.now()
            except EC2ResponseError, e:
                log.error("Trouble rebooting instance {0}: {1}".format(self.get_desc(), e))
        else:
            log.debug("Attampted to reboot instance {0} but no instance object? "
                      "(doing nothing)".format(self.get_desc()))
        if count_reboot:
            # Increment irespective of success to allow for eventual termination
            self.reboot_count += 1
            log.debug("Incremented instance reboot count to {0} (out of {1})"
                      .format(self.reboot_count, self.config.instance_reboot_attempts))

    def terminate(self):
        self.worker_status = "Stopping"
        t_thread = threading.Thread(target=self.__terminate)
        t_thread.start()
        return t_thread

    def __terminate(self):
        inst_terminated = self.app.cloud_interface.terminate_instance(
            instance_id=self.id,
            spot_request_id=self.spot_request_id if self.is_spot() else None)
        self.terminate_attempt_count += 1
        if inst_terminated is False:
            log.error("Terminating instance %s did not go smoothly; instance state: '%s'"
                      % (self.get_desc(), self.get_m_state()))
        else:
            # Remove the reference to the instance object because with OpenStack &
            # boto the instance.update() method returns the instance as being
            # in 'running' state even though the instance does not even exist
            # any more.
            self.inst = None
            self._remove_instance()

    def _remove_instance(self, force=False):
        """ A convenience method to remove the current instance from the list
            of worker instances tracked by the master object.

            :type force: bool
            :param force: Indicate if the instance should be forcefully (ie, irrespective)
                          of other logic) removed from the list of instances maintained
                          by the master object.
        """
        try:
            if self in self.app.manager.worker_instances:
                self.app.manager.worker_instances.remove(self)
                log.info(
                    "Instance '%s' removed from the internal instance list." % self.id)
                # If this was the last worker removed, add master back as execution host.
                if len(self.app.manager.worker_instances) == 0 and not self.app.manager.master_exec_host:
                    self.app.manager.toggle_master_as_exec_host()
        except ValueError, e:
            log.warning("Instance '%s' no longer in instance list, the global monitor probably "
                        "picked it up and deleted it already: %s" % (self.id, e))

    def instance_can_be_terminated(self):
        log.debug("Checking if instance '%s' can be terminated" % self.id)
        # TODO (qstat -qs {a|c|d|o|s|u|A|C|D|E|S})
        return False

    @TestFlag("running")
    def get_m_state(self):
        """ Update the machine state of the current instance by querying the
            cloud middleware for the instance object itself (via the instance
            id) and updating self.m_state field to match the state returned by
            the cloud middleware.
            Also, update local last_state_update timestamp.

            :rtype: String
            :return: the current state of the instance as obtained from the
                     cloud middleware
        """
        self.last_state_update = Time.now()
        self.get_cloud_instance_object(deep=True)
        if self.inst:
            try:
                state = self.inst.state
                log.debug("Requested instance {0} update: old state: {1}; new state: {2}"
                          .format(self.get_desc(), self.m_state, state))
                if state != self.m_state:
                    self.m_state = state
                    self.last_m_state_change = Time.now()
            except EC2ResponseError, e:
                log.debug("Error updating instance {0} state: {1}".format(
                    self.get_id(), e))
                self.m_state = instance_states.ERROR
        else:
            if not self.is_spot() or self.spot_was_filled():
                log.debug("Instance object {0} not found during m_state update; "
                          "setting instance state to {1}".format(self.get_id(), instance_states.TERMINATED))
                self.m_state = instance_states.TERMINATED
        return self.m_state

    @TestFlag(None)
    def send_alive_request(self):
        self.app.manager.console_monitor.conn.send('ALIVE_REQUEST', self.id)

    def send_sync_etc_host(self, msg):
        # Because the hosts file is synced over the transientFS, give the FS
        # some time to become available before sending the msg
        for i in range(3):
            if int(self.nfs_tfs):
                self.app.manager.console_monitor.conn.send('SYNC_ETC_HOSTS | ' + msg, self.id)
                break
            log.debug("Transient FS on instance {0} not available (code {1}); "
                      "waiting a bit...".format(self.get_desc(), self.nfs_tfs))
            time.sleep(7)

    @TestFlag(None)
    def send_status_check(self):
        # log.debug("\tMT: Sending STATUS_CHECK message" )
        self.app.manager.console_monitor.conn.send('STATUS_CHECK', self.id)
        # log.debug( "\tMT: Message STATUS_CHECK sent; waiting on response" )

    @TestFlag(None)
    def send_worker_restart(self):
        # log.info("\tMT: Sending restart message to worker %s" % self.id)
        self.app.manager.console_monitor.conn.send('RESTART | %s' % self.app.cloud_interface.get_private_ip(), self.id)
        log.info("\tMT: Sent RESTART message to worker '%s'" % self.id)

    def update_spot(self, force=False):
        """ Get an update on the state of a Spot request. If the request has entered
            spot_states.ACTIVE or spot_states.CANCELLED states, update the Instance
            object itself otherwise just update state. The method will continue to poll
            for an update until the spot request has been filled (ie, enters state
            spot_states.ACTIVE). After that, simply return the spot state (see
            force parameter).

            :type force: bool
            :param force: If True, poll for an update on the spot request,
                          irrespective of the stored spot request state.
        """
        if self.is_spot() and (force or self.spot_state != spot_states.ACTIVE):
            old_state = self.spot_state
            try:
                ec2_conn = self.app.cloud_interface.get_ec2_connection()
                reqs = ec2_conn.get_all_spot_instance_requests(
                    request_ids=[self.spot_request_id])
                for req in reqs:
                    self.spot_state = req.state
                    # Also update the worker_status because otherwise there's no
                    # single source to distinguish between simply an instance
                    # in Pending state and a Spot request
                    self.worker_status = self.spot_state
                    # If the state has changed, do a deeper update
                    if self.spot_state != old_state:
                        if self.spot_state == spot_states.CANCELLED:
                            # The request was canceled so remove this Instance
                            # object
                            log.info("Spot request {0} was canceled; removing Instance object {1}"
                                     .format(self.spot_request_id, self.id))
                            self._remove_instance()
                        elif self.spot_state == spot_states.ACTIVE:
                            # We should have an instance now
                            self.id = req.instance_id
                            log.info("Spot request {0} filled with instance {1}"
                                     .format(self.spot_request_id, self.id))
                            # Potentially give it a few seconds so everything gets registered
                            for i in range(3):
                                instance = self.get_cloud_instance_object()
                                if instance:
                                    self.app.cloud_interface.add_tag(instance, 'clusterName', self.app.ud['cluster_name'])
                                    self.app.cloud_interface.add_tag(instance, 'role', 'worker')
                                    self.app.cloud_interface.add_tag(instance, 'Name', "Worker: {0}".format(self.app.ud['cluster_name']))
                                    break
                                time.sleep(5)
            except EC2ResponseError, e:
                log.error("Trouble retrieving spot request {0}: {1}".format(
                    self.spot_request_id, e))
        return self.spot_state

    @TestFlag("127.0.0.1")
    def get_private_ip(self):
        # log.debug("Getting instance '%s' private IP: '%s'" % ( self.id, self.private_ip ) )
        if self.private_ip is None:
            inst = self.get_cloud_instance_object()
            if inst is not None:
                try:
                    inst.update()
                    self.private_ip = inst.private_ip_address
                except EC2ResponseError:
                    log.debug("private_ip_address for instance {0} not (yet?) available."
                              .format(self.get_id()))
            else:
                log.debug("private_ip_address for instance {0} with no instance object not available."
                          .format(self.get_id()))
        return self.private_ip

    @TestFlag('127.0.0.1')
    def get_public_ip(self):
        """
        Get the public IP address of this worker instance.
        """
        if not self.public_ip:
            inst = self.get_cloud_instance_object(deep=True)
            # log.debug('Getting public IP for instance {0}'.format(inst.id))
            if inst:
                try:
                    inst.update()
                    self.public_ip = inst.ip_address
                    if self.public_ip:
                        log.debug("Got public IP for instance {0}: {1}".format(
                            self.get_id(), self.public_ip))
                    else:
                        log.debug("Still no public IP for instance {0}".format(
                            self.get_id()))
                except EC2ResponseError:
                    log.debug("ip_address for instance {0} not (yet?) available.".format(
                        self.get_id()))
            else:
                log.debug("ip_address for instance {0} with no instance object not available."
                          .format(self.get_id()))
        return self.public_ip

    def get_local_hostname(self):
        return self.local_hostname

    def send_mount_points(self):
        mount_points = []
        for fs in self.app.manager.get_services(svc_type=ServiceType.FILE_SYSTEM):
            if fs.nfs_fs:
                fs_type = "nfs"
                server = fs.nfs_fs.device
                options = fs.nfs_fs.mount_options
            elif fs.gluster_fs:
                fs_type = "glusterfs"
                server = fs.gluster_fs.device
                options = fs.gluster_fs.mount_options
            else:
                fs_type = "nfs"
                server = self.app.cloud_interface.get_private_ip()
                options = None
            mount_points.append(
                {'fs_type': fs_type,
                 'server': server,
                 'mount_options': options,
                 'shared_mount_path': fs.get_details()['mount_point'],
                 'fs_name': fs.get_details()['name']})
        jmp = json.dumps({'mount_points': mount_points})
        self.app.manager.console_monitor.conn.send('MOUNT | %s' % jmp, self.id)
        # log.debug("Sent mount points %s to worker %s" % (mount_points, self.id))

    def send_master_pubkey(self):
        # log.info("\tMT: Sending MASTER_PUBKEY message: %s" % self.app.manager.get_root_public_key() )
        self.app.manager.console_monitor.conn.send('MASTER_PUBKEY | %s' % self.app.manager.get_root_public_key(), self.id)
        log.debug("Sent master public key to worker instance '%s'." % self.id)
        log.debug("\tMT: Message MASTER_PUBKEY %s sent to '%s'" % (self.app.manager.get_root_public_key(), self.id))

    def send_start_slurmd(self):
        log.debug("\tMT: Sending START_SLURMD message to instance {0}, named {1}"
                  .format(self.get_desc(), self.alias))
        self.app.manager.console_monitor.conn.send('START_SLURMD | {0}'.format(
            self.alias), self.id)

    def send_start_sge(self):
        log.debug("\tMT: Sending START_SGE message to instance '%s'" % self.id)
        self.app.manager.console_monitor.conn.send('START_SGE', self.id)

    def send_add_s3fs(self, bucket_name, svc_roles):
        msg = 'ADDS3FS | {0} | {1}'.format(bucket_name, ServiceRole.to_string(svc_roles))
        self._send_msg(msg)

    # def send_add_nfs_fs(self, nfs_server, fs_name, svc_roles, username=None, pwd=None):
    #     """
    #     Send a message to the worker node requesting it to mount a new file system
    #     form the ``nfs_server`` at mount point /mnt/``fs_name`` with roles``svc_roles``.
    #     """
    #     nfs_server_info = {
    #         'nfs_server': nfs_server, 'fs_name': fs_name, 'username': username,
    #         'pwd': pwd, 'svc_roles': ServiceRole.to_string(svc_roles)
    #     }
    #     msg = "ADD_NFS_FS | {0}".format(json.dumps({'nfs_server_info': nfs_server_info}))
    #     self._send_msg(msg)

    def _send_msg(self, msg):
        """
        An internal convenience method to log and send a message to the current instance.
        """
        log.debug("\tMT: Sending message '{msg}' to instance {inst}".format(msg=msg, inst=self.id))
        self.app.manager.console_monitor.conn.send(msg, self.id)

    def handle_message(self, msg):
        # log.debug( "Handling message: %s from %s" % ( msg, self.id ) )
        self.is_alive = True
        self.last_comm = Time.now()
        # Transition from states to a particular response.
        if self.app.manager.console_monitor.conn:
            msg_type = msg.split(' | ')[0]
            if msg_type == "ALIVE":
                self.worker_status = "Starting"
                log.info("Instance %s reported alive" % self.get_desc())
                msp = msg.split(' | ')
                self.private_ip = msp[1]
                self.public_ip = msp[2]
                self.zone = msp[3]
                self.type = msp[4]
                self.ami = msp[5]
                try:
                    self.local_hostname = msp[6]
                    self.num_cpus = int(msp[7])
                except:
                    # Older versions of CloudMan did not pass this value so if the master
                    # and the worker are running 2 diff versions (can happen after an
                    # automatic update), don't crash here.
                    self.local_hostname = self.public_ip
                log.debug("INSTANCE_ALIVE private_ip: %s public_ip: %s zone: %s type: %s AMI: %s hostname: %s, CPUs: %s"
                          % (self.private_ip, self.public_ip, self.zone,
                             self.type, self.ami, self.local_hostname,
                             self.num_cpus))
                # Instance is alive and responding.
                self.send_mount_points()
            elif msg_type == "GET_MOUNTPOINTS":
                self.send_mount_points()
            elif msg_type == "MOUNT_DONE":
                log.debug("Got MOUNT_DONE message; setting up job manager(s)")
                slurmctld_svc = self.app.manager.get_services(svc_role=ServiceRole.SLURMCTLD)
                slurmctld_svc = slurmctld_svc[0] if len(slurmctld_svc) > 0 else None
                if slurmctld_svc:
                    slurmctld_svc.add_node(self)
                else:
                    log.warning('Could not get a handle on slurmctld service to '
                                'add node {0}'.format(self.get_desc()))
                # EA-Slurm self.send_master_pubkey()
                # Add hostname to /etc/hosts (for SGE config)
                if self.app.cloud_type in ('openstack', 'eucalyptus'):
                    hn2 = ''
                    if '.' in self.local_hostname:
                        hn2 = (self.local_hostname).split('.')[0]
                    worker_host_line = '{ip} {hn1} {hn2}\n'.format(ip=self.private_ip,
                                                                   hn1=self.local_hostname,
                                                                   hn2=hn2)
                    log.debug("worker_host_line: {0}".format(worker_host_line))
                    with open('/etc/hosts', 'r+') as f:
                        hosts = f.readlines()
                        if worker_host_line not in hosts:
                            log.debug("Adding worker {0} to /etc/hosts".format(
                                self.local_hostname))
                            f.write(worker_host_line)

                if self.app.cloud_type == 'opennebula':
                    f = open("/etc/hosts", 'a')
                    f.write("%s\tworker-%s\n" % (self.private_ip, self.id))
                    f.close()
                # log.debug("Update /etc/hosts through master")
                # self.app.manager.update_etc_host()
                self.send_start_slurmd()
            elif msg_type == "WORKER_H_CERT":
                self.is_alive = True  # This is for the case that an existing worker is added to a new master.
                self.app.manager.save_host_cert(msg.split(" | ")[1])
                log.debug("Worker '%s' host certificate received and appended to /root/.ssh/known_hosts" % self.id)
                try:
                    sge_svc = self.app.manager.get_services(
                        svc_role=ServiceRole.SGE)[0]
                    if sge_svc.add_sge_host(self.get_id(), self.local_hostname):
                        # Send a message to worker to start SGE
                        self.send_start_sge()
                        # If there are any bucket-based FSs, tell the worker to
                        # add those
                        fss = self.app.manager.get_services(
                            svc_type=ServiceType.FILE_SYSTEM)
                        for fs in fss:
                            if len(fs.buckets) > 0:
                                for b in fs.buckets:
                                    self.send_add_s3fs(b.bucket_name, fs.svc_roles)
                        log.info("Waiting on worker instance %s to configure itself." % self.get_desc())
                    else:
                        log.error("Adding host to SGE did not go smoothly, "
                                  "not instructing worker to configure SGE daemon.")
                except IndexError:
                    log.error(
                        "Could not get a handle on SGE service to add a host; host not added")
            elif msg_type == "NODE_READY":
                self.worker_status = "Ready"
                log.info("Instance %s ready" % self.get_desc())
                # msplit = msg.split(' | ')
                # try:
                #     self.num_cpus = int(msplit[2])
                # except:
                #     log.debug(
                #         "Instance '%s' num CPUs is not int? '%s'" % (self.id, msplit[2]))
                # log.debug("Instance '%s' reported as having '%s' CPUs." %
                #           (self.id, self.num_cpus))
                # Make sure the instace is tagged (this is also necessary to do
                # here for OpenStack because it does not allow tags to be added
                # until an instance is 'running')
                self.app.cloud_interface.add_tag(self.inst, 'clusterName', self.app.ud['cluster_name'])
                self.app.cloud_interface.add_tag(self.inst, 'role', 'worker')
                self.app.cloud_interface.add_tag(self.inst, 'alias', self.alias)
                self.app.cloud_interface.add_tag(self.inst, 'Name', "Worker: {0}".format(self.app.ud['cluster_name']))

                log.debug("update condor host through master")
                self.app.manager.update_condor_host(self.public_ip)
            elif msg_type == "NODE_STATUS":
                # log.debug("Node {0} status message: {1}".format(self.get_desc(), msg))
                if not self.worker_status == 'Stopping':
                    msplit = msg.split(' | ')
                    self.nfs_data = msplit[1]
                    self.nfs_tools = msplit[2]  # Workers currently do not update this field
                    self.nfs_indices = msplit[3]
                    self.nfs_sge = msplit[4]
                    self.get_cert = msplit[5]
                    self.sge_started = msplit[6]
                    self.load = msplit[7]
                    self.worker_status = msplit[8]
                    self.nfs_tfs = msplit[9]
                    self.slurmd_running = msplit[10]
                else:
                    log.debug("Worker {0} in state Stopping so not updating status"
                              .format(self.get_desc()))
            elif msg_type == 'NODE_SHUTTING_DOWN':
                msplit = msg.split(' | ')
                self.worker_status = msplit[1]
            else:  # Catch-all condition
                log.debug("Unknown Message: %s" % msg)
        else:
            log.error("Epic Failure, squeue not available?")
