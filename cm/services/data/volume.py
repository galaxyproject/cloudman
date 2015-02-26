"""
A wrapper class around volume block storage devices. For the purposes of this
class, a single object/volume maps to a complete file system.
"""
import os
import grp
import pwd
import time
import shutil
import subprocess
from glob import glob

from boto.exception import EC2ResponseError

from cm.util.misc import run
from cm.services import service_states
from cm.services import ServiceRole
from cm.services.data import BlockStorage
from cm.services.data import volume_status
from cm.util import misc

import logging
log = logging.getLogger('cloudman')


MIN_TIME_BETWEEN_STATUS_CHECKS = 2  # seconds to wait before updating volume status
volume_status_map = {
    'creating': volume_status.CREATING,
    'available': volume_status.AVAILABLE,
    'in-use': volume_status.IN_USE,
    'attaching': volume_status.ATTACHING,
    'attached': volume_status.ATTACHED,
    'deleting': volume_status.DELETING,
}


class Volume(BlockStorage):

    def __init__(
        self, filesystem, vol_id=None, device=None, attach_device=None,
            size=0, from_snapshot_id=None, static=False, from_archive=None):
        super(Volume, self).__init__(filesystem.app)
        self.fs = filesystem
        self.app = self.fs.app
        self.volume = None  # boto instance object representing the current volume
        self.device = device  # Device ID visible by the operating system
        self.size = size
        self.from_snapshot_id = from_snapshot_id
        self.from_archive = from_archive
        self.snapshot = None
        self.snapshots_created = []  # Snapshots that were created from this volume
        self.device = None
        # Static indicates if a volume is created from a snapshot AND can be
        # deleted upon cluster termination
        self.static = static
        self.snapshot_progress = None
        self.snapshot_status = None
        self._status = volume_status.NONE
        self._last_status_check = None

        if (vol_id):  # get the volume object immediately, if id is passed
            self.update(vol_id)
        elif from_snapshot_id or from_archive:
            self.create()

    def __str__(self):
        return str(self.volume_id)

    def __repr__(self):
        if self.volume_id is not None:
            return self.get_full_name()
        else:
            if self.from_archive:
                return "No volume ID yet; {0} ({1})".format(self.from_archive, self.fs.get_full_name())
            else:
                return "No volume ID yet; {0} ({1})".format(self.from_snapshot_id, self.fs.get_full_name())

    def get_full_name(self):
        """
        Returns a string specifying the volume ID and name of the file system
        this volume belongs to.
        """
        return "{vol} ({fs})".format(vol=self.volume_id, fs=self.fs.get_full_name())

    def _get_details(self, details):
        """
        Volume-specific details for this file system
        """
        details['DoT'] = "Yes" if self.static else "No"
        details['device'] = self.device
        details['volume_id'] = self.volume_id
        details['from_snap'] = "No" if not self.from_snapshot_id else self.from_snapshot_id
        details['from_archive'] = "No" if not self.from_archive else self.from_archive['url']
        details['snapshot_progress'] = self.snapshot_progress
        details['snapshot_status'] = self.snapshot_status
        # TODO: keep track of any errors
        details['err_msg'] = None if details.get('err_msg', '') == '' else details['err_msg']
        details['snapshots_created'] = self.snapshots_created
        return details

    def update(self, vol_id):
        """
        Set or switch the local ``self.volume`` to a different boto.ec2.volume.Volume

        This is primarily useful during restarts when introspecting an already
        attached volume.
        """
        log.debug('vol_id = {0} ({1})'.format(vol_id, type(vol_id)))
        if isinstance(vol_id, basestring):
            vols = None
            try:
                log.debug("Retrieving a reference to the Volume object for ID {0}".format(vol_id))
                vols = self.app.cloud_interface.get_ec2_connection().get_all_volumes(volume_ids=(vol_id,))
            except EC2ResponseError, e:
                log.error("Trouble getting volume reference for volume {0}: {1}"
                          .format(vol_id, e))
            if not vols:
                log.error('Attempting to connect to a non-existent volume {0}'.format(vol_id))
                self.volume = None
                self.device = None
            vol = vols[0]
        else:
            vol = vol_id
        log.debug("Updating current volume reference '%s' to a new one '%s'" % (
            self.volume_id, vol.id))
        if (vol.attachment_state() == 'attached' and
           vol.attach_data.instance_id != self.app.cloud_interface.get_instance_id()):
            log.error('Attempting to connect to a volume ({0} that is already attached "\
                "to a different instance ({1}'.format(vol.id, vol.attach_data.instance_id))
            self.volume = None
            self.device = None
        else:
            self.volume = vol
            attach_device = vol.attach_data.device
            if run('ls {0}'.format(attach_device), quiet=True):
                self.device = attach_device
            else:
                # Attach device is different than the system device so figure it out
                log.debug("Volume {0} (attached as {1}) is visible as something else???"
                          .format(vol.id, attach_device))
                if attach_device:
                    try:
                        device_id = attach_device[-1]  # Letter-only based device IDs (e.g., /dev/xvdc)
                        if (str(device_id).isdigit()):
                            device_id = attach_device[-2:]  # Number-based device IDs (e.g., /dev/sdg1)
                        attach_device = '/dev/xvd' + device_id
                        log.debug("Trying visible device {0}...".format(attach_device))
                    except Exception, e:
                        log.error("Attach device's ID ({0}) too short? {1}".format(
                            attach_device, e))
                    if run('ls {0}'.format(attach_device), quiet=True):
                        self.device = attach_device
                    else:
                        log.error("Problems discovering volume {0} attach device {1} vs. system device ?"
                                  .format(vol.id, attach_device))
                        self.device = None
                else:
                    log.debug("No attach_device candidate for volume {0}".format(vol.id))
            self.size = vol.size
            self.from_snapshot_id = vol.snapshot_id
            if self.from_snapshot_id == '':
                self.from_snapshot_id = None
            log.debug("For volume {0} ({1}) set from_snapshot_id to {2}"
                      .format(self.volume_id, self.fs.get_full_name(), self.from_snapshot_id))

    @property
    def volume_id(self):
        """
        Returns the cloud ID for this volume.
        """
        if self.volume:
            return self.volume.id
        else:
            return None

    @property
    def attach_device(self):
        """
        Returns the device this volume is attached as, as reported by the cloud middleware.
        """
        if self.volume:
            self.volume.update()
            return self.volume.attach_data.device
        else:
            return None

    @property
    def status(self):
        """
        Returns the current status of this volume, as reported by the cloud middleware.
        """
        if not self.volume:
            # no volume active
            status = volume_status.NONE
        elif self._status and self._last_status_check >= time.time() - MIN_TIME_BETWEEN_STATUS_CHECKS:
            status = self._status
        else:
            try:
                self.volume.update()
                # Take only the first word of the status as openstack adds some extra info after a space
                status = volume_status_map.get(self.volume.status.split(' ')[0], None)
                if status == volume_status.IN_USE and self.volume.attachment_state() == 'attached':
                    status = volume_status.ATTACHED
                if not status:
                    log.error("Unknown volume status: {0}. Setting status to volume_status.NONE"
                              .format(self.volume.status))
                    status = volume_status.NONE
                self._status = status
                self._last_status_check = time.time()
            except EC2ResponseError as e:
                log.error(
                    'Cannot retrieve status of current volume. {0}'.format(e))
                status = volume_status.NONE
        return status

    def wait_for_status(self, status, timeout=-1):
        """
        Wait for ``timeout`` seconds, or until the volume reaches a desired status
        Returns ``False`` if it never hit the request status before timeout.
        If ``timeout`` is set to ``-1``, wait until the desired status is reached.
        Note that this may potentially be forever.
        """
        if self.status == volume_status.NONE:
            log.debug('Attempted to wait for a status ({0}) on a non-existent volume'.format(status))
            return False  # no volume means not worth waiting
        else:
            start_time = time.time()
            end_time = start_time + timeout
            if timeout == -1:
                checks = "infinite"
                wait_time = 5
                wait_forever = True
            else:
                checks = 10
                wait_time = float(timeout) / checks
                wait_forever = False
            while wait_forever or time.time() <= end_time:
                if self.status == status:
                    log.debug("Volume {0} ({1}) has reached status '{2}'".format(self.volume_id, self.fs.get_full_name(), status))
                    return True
                else:
                    log.debug('Waiting for volume {0} (status "{1}"; {2}) to reach status "{3}". '
                              'Remaining checks: {4}'.format(self.volume_id, self.status,
                                                             self.fs.get_full_name(), status, checks))
                    if timeout != -1:
                        checks -= 1
                    time.sleep(wait_time)
            log.debug('Wait for volume {0} ({1}) to reach status {2} timed out. Current status {3}.'
                      .format(self.volume_id, self.fs.get_full_name(), status, self.status))
            return False

    def create(self, filesystem=None):
        """
        Create a new volume.
        """
        if not self.size and not self.from_snapshot_id and not self.from_archive:
            log.error('Cannot add a volume without a size, snapshot ID or archive url')
            return None

        if self.from_snapshot_id and not self.volume:
            self.snapshot = (self.app.cloud_interface.get_ec2_connection()
                             .get_all_snapshots([self.from_snapshot_id])[0])
            # We need a size to be able to create a volume, so if none
            # is specified, use snapshot size
            if self.size == 0:
                try:
                    self.size = self.snapshot.volume_size
                except EC2ResponseError, e:
                    log.error("Error retrieving snapshot %s size: %s" % (self.from_snapshot_id, e))

        if self.status == volume_status.NONE:
            try:
                # Temp code (Dec 2012) - required by the NeCTAR Research Cloud
                # until general volumes arrive
                if self.app.config.cloud_name == 'nectar':
                    zone = self.app.cloud_interface.get_zone()
                    if zone in ['sa']:
                        msg = ("It seems you're running on the NeCTAR cloud and in "
                               "zone 'SA'. However, volumes do not currently"
                               "work in that zone. Will attempt to continue but failure"
                               "is likely")
                        log.warning(msg)
                        self.app.msgs.warning(msg)
                log.debug("Creating a new volume of size '%s' in zone '%s' from snapshot '%s'"
                          % (self.size, self.app.cloud_interface.get_zone(), self.from_snapshot_id))
                self.volume = self.app.cloud_interface.get_ec2_connection().create_volume(self.size,
                                                                                          self.app.cloud_interface.get_zone(),
                                                                                          snapshot=self.from_snapshot_id)
                self.size = int(self.volume.size or 0)
                # when creating from a snapshot in Euca, volume.size may be None
                log.debug("Created new volume of size '%s' from snapshot '%s' with ID '%s' in zone '%s'"
                          % (self.size, self.from_snapshot_id, self.volume_id, self.app.cloud_interface.get_zone()))
            except EC2ResponseError, e:
                log.error("Error creating volume: %s" % e)
        else:
            log.debug("Tried to create a volume but it is in state '%s' (volume ID: %s)" %
                      (self.status, self.volume_id))

        # Add tags to newly created volumes (do this outside the inital if/else
        # to ensure the tags get assigned even if using an existing volume vs.
        # creating a new one)
        try:
            self.app.cloud_interface.add_tag(
                self.volume, 'clusterName', self.app.config.config['cluster_name'])
            self.app.cloud_interface.add_tag(
                self.volume, 'bucketName', self.app.config['bucket_cluster'])
            if filesystem:
                self.app.cloud_interface.add_tag(self.volume, 'filesystem', filesystem)
                self.app.cloud_interface.add_tag(self.volume, 'Name', "{0}FS".format(filesystem))
                self.app.cloud_interface.add_tag(self.volume, 'roles',
                                                 ServiceRole.to_string(self.fs.svc_roles))
        except EC2ResponseError, e:
            log.error("Error adding tags to volume: %s" % e)

    def delete(self):
        """
        Delete this volume.
        """
        try:
            volume_id = self.volume_id
            self.volume.delete()
            log.debug("Deleted volume '%s'" % volume_id)
            self.volume = None
        except EC2ResponseError, e:
            log.error("Error deleting volume '%s' - you should delete it manually "
                      "after the cluster has shut down: %s" % (self.volume_id, e))

    # attachment helper methods

    def _get_device_list(self):
        """
        Get a list of system devices as an iterable list of strings.
        """
        return frozenset(glob('/dev/*d[a-z]'))

    def _increment_device_id(self, device_id):
        """
        Increment the system ``device_id`` to the next letter in alphabet.
        For example, providing ``/dev/vdc`` as the ``device_id``,
        returns ``/dev/vdd``.

        There is an AWS-specific customization in this method; namely, AWS
        allows devices to be attached as /dev/sdf through /dev/sdp
        Subsequently, those devices are visible under /dev/xvd[f-p]. So, if
        ``/dev/xvd?`` is provided as the ``device_id``, replace the device
        base with ``/dev/sd`` and ensure the last letter of the device is
        never smaller than ``f``. For example, given ``/dev/xvdb`` as the
        ``device_id``, return ``/dev/sdf``; given ``/dev/xvdg``, return
        ``/dev/sdh``.
        """
        base = device_id[0:-1]
        letter = device_id[-1]

        # AWS-specific munging
        # Perhaps should be moved to the interface anyway does not work for openstack
        log.debug("Cloud type is: %s", self.app.config.cloud_type)
        if self.app.config.cloud_type == 'ec2':
            log.debug('Applying AWS-specific munging to next device id calculation')
            if base == '/dev/xvd':
                base = '/dev/sd'
            if letter < 'f':
                letter = 'e'

        # Get the next device in line
        new_id = base + chr(ord(letter) + 1)
        return new_id

    def _get_likely_next_devices(self, devices=None):
        """
        Returns a list of possible devices to attempt to attempt to attach to.

        If using virtio, then the devices get attached as ``/dev/vd?``.
        Newer Ubuntu kernels might get devices attached as ``/dev/xvd?``.
        Otherwise, it'll probably get attached as ``/dev/sd?``
        If either ``/dev/vd?`` or ``/dev/xvd?`` devices exist, then we know to
        use the next of those. Otherwise, test ``/dev/sd?``, ``/dev/xvd?``, then ``/dev/vd?``.

        **This is so totally not thread-safe.** If other devices get attached externally,
        the device id may already be in use when we get there.
        """
        if not devices:
            devices = self._get_device_list()
        device_map = map(lambda x: (x.split(
            '/')[-1], x), devices)  # create a dict of id:/dev/id from devices
        # in order, we want vd?, xvd?, or sd?
        vds = sorted((d[1] for d in device_map if d[0][0] == 'v'))
        xvds = sorted((d[1] for d in device_map if d[0][0:2] == 'xv'))
        sds = sorted((d[1] for d in device_map if d[0][0] == 's'))
        if vds:
            return (self._increment_device_id(vds[-1]),)
        elif xvds:
            return (self._increment_device_id(xvds[-1]),)
        elif sds:
            return (self._increment_device_id(sds[-1]), '/dev/vda', '/dev/xvda')
        else:
            log.error("Could not determine next available device from {0}".format(
                devices))
            return None

    def _do_attach(self, attach_device):
        """
        Do the actual process of attaching this volume to the current instance.
        Returns the current status of the volume.
        """
        try:
            if attach_device is not None:
                log.debug("Attaching volume '%s' to instance '%s' as device '%s'" %
                          (self.volume_id, self.app.cloud_interface.get_instance_id(), attach_device))
                self.volume.attach(
                    self.app.cloud_interface.get_instance_id(), attach_device)
            else:
                log.error("Attaching volume '%s' to instance '%s' failed because could not determine device."
                          % (self.volume_id, self.app.cloud_interface.get_instance_id()))
                return False
        except EC2ResponseError, e:
            for er in e.errors:
                if er[0] == 'InvalidVolume.ZoneMismatch':
                    msg = ("Volume '{0}' is located in the wrong availability zone "
                           "for this instance. You MUST terminate this instance "
                           "and start a new one in zone '{1}' instead of '{2}'."
                           .format(self.volume_id, self.volume.zone.name,
                                   self.app.cloud_interface.get_zone()))
                    self.app.msgs.critical(msg)
                    log.error(msg)
                else:
                    log.error("Attaching volume '%s' to instance '%s' as device '%s' failed. "
                              "Exception: %s (%s)" % (self.volume_id,
                                                      self.app.cloud_interface.get_instance_id(),
                                                      attach_device, er[0],
                                                      er[1]))
            return False
        return self.status

    def attach(self):
        """
        Attach EBS volume to the given device.
        Try it for some time.
        Returns the attached device path, or None if it can't attach
        """
        log.info('Adding volume {0} ({1})...'.format(
            self.volume_id, self.fs.get_full_name()))
        # Bail if the volume doesn't exist, or is already attached
        if self.status == volume_status.NONE or self.status == volume_status.DELETING:
            log.error('Attempt to attach non-existent volume {0}'.format(
                self.volume_id))
            return None
        elif self.status == volume_status.ATTACHED or self.status == volume_status.IN_USE:
            log.debug('Volume {0} already attached as {1}'.format(
                self.volume_id, self.device))
            return self.device

        # Wait for the volume to become available
        if self.from_snapshot_id and self.status == volume_status.CREATING:
            # Eucalyptus can take an inordinate amount of time to create a
            # volume from a snapshot
            log.debug("Waiting for volume to be created from a snapshot...")
            if not self.wait_for_status(volume_status.AVAILABLE):
                log.error('Volume never reached available from creating status. Status is {0}'.format(
                    self.status))
        elif self.status != volume_status.AVAILABLE:
            if not self.wait_for_status(volume_status.AVAILABLE):
                log.error('Volume never became available to attach. Status is {0}'.format(
                    self.status))
                return None

        # attempt to attach
        for attempted_device in self._get_likely_next_devices():
            pre_devices = self._get_device_list()
            log.debug(
                'Before attach, devices = {0}'.format(' '.join(pre_devices)))
            if self._do_attach(attempted_device):
                if self.wait_for_status(volume_status.ATTACHED):
                    time.sleep(10)  # give a few seconds for the device to show up in the OS
                    post_devices = self._get_device_list()
                    log.debug('After attach, devices = {0}'.format(
                        ' '.join(post_devices)))
                    new_devices = post_devices - pre_devices
                    log.debug('New devices = {0}'.format(' '.join(new_devices)))
                    if len(new_devices) == 0:
                        log.debug('Could not find attached device for volume {0}. Attempted device = {1}'
                                  .format(self.volume_id, attempted_device))
                    elif attempted_device in new_devices:
                        self.device = attempted_device
                        return attempted_device
                    elif len(new_devices) > 1:
                        log.error("Multiple devices (%s) added to OS during process, "
                                  "and none are the requested device. Can't determine "
                                  "new device. Aborting" % ', '.join(new_devices))
                        return None
                    else:
                        device = tuple(new_devices)[0]
                        self.device = device
                        log.debug("For {0}, set self.device to {1}".format(
                                  self.fs.get_full_name(), device))
                        return device
                # requested device didn't attach, for whatever reason
                if self.status != volume_status.AVAILABLE and attempted_device[-3:-1] != 'vd':
                    self.detach()  # in case it attached invisibly
                self.wait_for_status(volume_status.AVAILABLE, 60)
        return None  # no device properly attached

    def detach(self):
        """
        Detach EBS volume from an instance.
        Try it for some time.
        """
        if self.status == volume_status.ATTACHED or self.status == volume_status.IN_USE:
            try:
                self.volume.detach()
            except EC2ResponseError, e:
                log.error("Detaching volume '%s' from instance '%s' failed. Exception: %s"
                          % (self.volume_id, self.app.cloud_interface.get_instance_id(), e))
                return False
            self.wait_for_status(volume_status.AVAILABLE, 240)
            if self.status != volume_status.AVAILABLE:
                log.debug('Attempting to detach again.')
                try:
                    self.volume.detach()
                except EC2ResponseError, e:
                    log.error("Detaching volume '%s' from instance '%s' failed. Exception: %s" % (
                        self.volume_id, self.app.cloud_interface.get_instance_id(), e))
                    return False
                if not self.wait_for_status(volume_status.AVAILABLE, 60):
                    log.warning('Volume {0} did not detach properly. Left in state {1}'
                                .format(self.volume_id, self.status))
                    return False
        else:
            log.warning("Cannot detach volume '%s' in state '%s'" % (
                self.volume_id, self.status))
            return False
        return True

    def create_snapshot(self, snap_description=None):
        """
        Crete a point-in-time snapshot of the current volume, optionally specifying
        a description for the snapshot.
        """
        log.info("Initiating creation of a snapshot for the volume '%s'" %
                 self.volume_id)
        try:
            snapshot = self.volume.create_snapshot(
                description=snap_description)
        except EC2ResponseError as ex:
            log.error("Error creating a snapshot from volume '%s': %s" %
                      (self.volume_id, ex))
            raise
        if snapshot:
            while snapshot.status != 'completed':
                log.debug("Snapshot '%s' progress: '%s'; status: '%s'"
                          % (snapshot.id, snapshot.progress, snapshot.status))
                self.snapshot_progress = snapshot.progress
                self.snapshot_status = snapshot.status
                time.sleep(6)
                snapshot.update()
            log.info("Completed creation of a snapshot for the volume '%s', snap id: '%s'"
                     % (self.volume_id, snapshot.id))
            self.app.cloud_interface.add_tag(snapshot, 'clusterName',
                                             self.app.config['cluster_name'])
            self.app.cloud_interface.add_tag(
                self.volume, 'bucketName', self.app.config['bucket_cluster'])
            self.app.cloud_interface.add_tag(self.volume, 'filesystem', self.fs.name)
            self.snapshot_progress = None  # Reset because of the UI
            self.snapshot_status = None  # Reset because of the UI
            self.snapshots_created.append(snapshot.id)
            return str(snapshot.id)
        else:
            log.error(
                "Could not create snapshot from volume '%s'" % self.volume_id)
            return None

    def get_from_snap_id(self):
        """
        Returns the ID of the snapshot this volume was created from, ``None``
        if the volume was not created from a snapshot.
        """
        return self.from_snapshot_id

    def add(self):
        """
        Add this volume as a file system. This implies creating a volume (if
        it does not already exist), attaching it to the instance, and mounting
        the file system.
        """
        self.create(self.fs.name)
        # Mark a volume as 'static' if created from a snapshot
        # Note that if a volume is marked as 'static', it is assumed it
        # can be deleted upon cluster termination!
        if (ServiceRole.GALAXY_DATA not in self.fs.svc_roles and
            (self.from_snapshot_id is not None or self.from_archive is not
             None)):
            log.debug("Marked volume '%s' from file system '%s' as 'static'" % (self.volume_id, self.fs.name))
            # FIXME: This is a major problem - any new volumes added from a snapshot
            # will be assumed 'static'. This is OK before being able to add an
            # arbitrary volume as a file system but is no good any more. The
            # problem is in automatically detecting volumes that are supposed
            # to be static and are being added automatically at startup
            if self.from_archive:
                self.fs.kind = 'volume'  # Treated as a regular volume after initial extraction
            else:
                self.static = True
                self.fs.kind = 'snapshot'
        else:
            self.fs.kind = 'volume'
        if self.attach():
            self.mount(self.fs.mount_point)

    def remove(self, mount_point, delete_vols=False, detach=True):
        """
        Remove this volume from the system. This implies unmounting the associated
        file system, detaching the volume, and, optionally, deleting the volume.
        Note that a volume will get deleted if it is marked as ``static`` regardless
        of whether ``delete_vols`` is set. ``delete_vols`` overrides everything else.
        If ``detach`` is set, detach the current volume in the process of removing
        it. Otherwise, leave it attached (this is useful during snapshot creation
        but note that creating a snapshot for an attached volume works only on AWS).

        .. warning::

            Setting ``delete_vols`` is irreversible. All data will be
            permanently deleted.
        """
        self.unmount(mount_point)
        if detach:
            log.debug("Detaching volume {0} as {1}".format(
                self.volume_id, self.fs.get_full_name()))
            if self.detach():
                log.debug("Detached volume {0} as {1}".format(
                    self.volume_id, self.fs.get_full_name()))
                if ((self.static and (ServiceRole.GALAXY_DATA not in self.fs.svc_roles))
                   or delete_vols):
                    log.debug("Deleting volume {0} as part of {1} removal".format(
                        self.volume_id, self.fs.get_full_name()))
                    self.delete()
        else:
            log.debug("Unmounted FS {0} but instructed not to detach volume {1}"
                      .format(self.fs.get_full_name(), self.volume_id))

    def mount(self, mount_point):
        """
        Mount this volume as a locally accessible file system and make it
        available over NFS
        """
        for counter in range(30):
            if self.status == volume_status.ATTACHED:
                if os.path.exists(mount_point):
                    # Check if the mount location is empty
                    if len(os.listdir(mount_point)) != 0:
                        log.warning("Mount point {0} already exists and is not "
                                    "empty!? ({2}) Will attempt to mount volume {1}"
                                    .format(mount_point, self.volume_id,
                                    os.listdir(mount_point)))
                        # return False
                else:
                    log.debug("Creating mount point directory {0} for {1}"
                              .format(mount_point, self.fs.get_full_name()))
                    try:
                        os.mkdir(mount_point)
                    except Exception, e:
                        log.warning("Could not create {0} mount point {1}: {2}"
                                    .format(self.fs.get_full_name(), mount_point, e))
                # Potentially wait for the device to actually become available in the system
                # TODO: Do something if the device is not available in the
                # given time period
                for i in range(10):
                    if os.path.exists(self.device):
                        log.debug("Device path {0} checked and it exists.".format(
                            self.device))
                        break
                    else:
                        log.debug("Device path {0} does not yet exist; waiting...".format(
                            self.device))
                        time.sleep(4)
                # Until the underlying issue is fixed (see FIXME below), mask this
                # even more by custom-handling the run command and thus not
                # printing the err
                cmd = '/bin/mount %s %s' % (self.device, mount_point)
                try:
                    process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE,
                                               stderr=subprocess.PIPE)
                    _, _ = process.communicate()
                    if process.returncode != 0:
                        # FIXME: Assume if a file system cannot be mounted that it's because
                        # there is not a file system on the device so try creating
                        # one
                        if run('/sbin/mkfs.xfs %s' % self.device,
                               "Failed to create a files ystem on device %s" % self.device,
                               "Created a file system on device %s" % self.device):
                            if not run(
                                '/bin/mount %s %s' % (self.device, mount_point),
                                "Error mounting file system %s from %s" % (
                                    mount_point, self.device),
                                    "Successfully mounted file system %s from %s" %
                                    (mount_point, self.device)):
                                log.error("Failed to mount device '%s' to mount point '%s'"
                                          % (self.device, mount_point))
                                return False
                    # Resize the volume if it was created from a snapshot
                    else:
                        if self.snapshot and self.volume.size > self.snapshot.volume_size:
                            run('/usr/sbin/xfs_growfs %s' % mount_point)
                            log.info("Successfully grew file system {0}".format(self.fs.get_full_name()))
                    log.info("Successfully mounted file system {0} from {1}".format(mount_point, self.device))
                except Exception, e:
                    log.error("Exception mounting {0} at {1}".format(
                              self.fs.get_full_name(), mount_point))
                    return False
                try:
                    # Default owner of all mounted file systems to `galaxy`
                    # user
                    os.chown(mount_point, pwd.getpwnam(
                        "galaxy")[2], grp.getgrnam("galaxy")[2])
                    # Add Galaxy- and CloudBioLinux-required files under the
                    # 'data' dir
                    if ServiceRole.GALAXY_DATA in self.fs.svc_roles:
                        for sd in ['files', 'tmp', 'upload_store', 'export']:
                            path = os.path.join(
                                self.app.path_resolver.galaxy_data, sd)
                            if not os.path.exists(path):
                                os.mkdir(path)
                            # Make 'export' dir that's shared over NFS be
                            # owned by `ubuntu` user so it's accesible
                            # for use to the rest of the cluster
                            if sd == 'export':
                                os.chown(path, pwd.getpwnam(
                                    "ubuntu")[2], grp.getgrnam("ubuntu")[2])
                            else:
                                os.chown(path, pwd.getpwnam(
                                    "galaxy")[2], grp.getgrnam("galaxy")[2])
                except OSError, e:
                    log.debug(
                        "Tried making 'galaxyData' sub-dirs but failed: %s" % e)

                # If based on bucket, extract bucket contents onto new volume
                try:
                    if self.from_archive:
                        log.info("Extracting archive url: {0} to mount point: {1}. This could take a while...".format(self.from_archive['url'], mount_point))
                        misc.extract_archive_content_to_path(self.from_archive['url'], mount_point, self.from_archive['md5_sum'])
                except Exception, e:
                    log.error("Error while extracting archive: {0}".format(e))
                    return False

                # Lastly, share the newly mounted file system over NFS
                if self.fs.add_nfs_share(mount_point):
                    return True
            log.warning("Cannot mount volume '%s' in state '%s'. Waiting (%s/30)."
                        % (self.volume_id, self.status, counter))
            time.sleep(2)

    def unmount(self, mount_point):
        """
        Unmount the file system from the specified mount point, removing it from
        NFS in the process.
        """
        self.fs.remove_nfs_share()
        self.fs.status()
        if self.fs.state == service_states.RUNNING or self.fs.state == service_states.SHUTTING_DOWN:
            log.debug("Unmounting volume-based FS from {0}".format(mount_point))
            if self.fs._is_mounted(mount_point):
                for counter in range(10):
                    if run('/bin/umount %s' % mount_point,
                            "Error unmounting file system '%s'" % mount_point,
                            "Successfully unmounted file system '%s'" % mount_point):
                        # Clean up the system path now that the file system is
                        # unmounted
                        try:
                            # nginx upload store is sometimes left behind,
                            # so clean it up
                            usp = os.path.join(mount_point, 'upload_store')
                            if os.path.exists(usp):
                                shutil.rmtree(usp)
                            os.rmdir(mount_point)
                            break
                        except OSError, e:
                            log.error("Error removing unmounted path {0}: {1}".format(
                                mount_point, e))
                    if counter == 9:
                        log.warning("Could not unmount file system at '%s'" % mount_point)
                        return False
                    counter += 1
                    time.sleep(3)
                return True
            else:
                log.debug("Did not unmount file system {0} at {1} because it is "
                          "not mounted.".format(self.fs.get_full_name(), mount_point))
                return False
        log.debug("Did not unmount file system '%s' because it is not in state "
                  "'running' or 'shutting-down'" % self.fs.get_full_name())
        return False
