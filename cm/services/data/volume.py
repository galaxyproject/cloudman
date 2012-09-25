"""
A wrapper class around volume block storage devices. For the purposes of this
class, a single object/volume maps to a complete file system.
"""
import os
import grp
import pwd
import time
import string
import commands
import subprocess
from glob import glob

from boto.exception import EC2ResponseError

from cm.util import paths
from cm.util.misc import run
from cm.util.misc import flock
from cm.services import service_states
from cm.services.data import BlockStorage
from cm.services.data import volume_status

import logging
log = logging.getLogger('cloudman')


MIN_TIME_BETWEEN_STATUS_CHECKS = 2 # seconds to wait before updating volume status
volume_status_map = {
                     'creating'    : volume_status.CREATING,
                     'available'   : volume_status.AVAILABLE,
                     'in-use'      : volume_status.IN_USE,
                     'attached'    : volume_status.ATTACHED,
                     'deleting'    : volume_status.DELETING,
                     }

class Volume(BlockStorage):

    def __init__(self, filesystem, vol_id=None, device=None, attach_device=None,
                 size=0, from_snapshot_id=None, static=False):
        super(Volume, self).__init__(filesystem.app)
        self.fs = filesystem
        self.app = self.fs.app
        self.volume = None # boto instance object representing the current volume
        self.device = device # Device ID visible by the operating system
        self.size = size
        self.from_snapshot_id = from_snapshot_id
        self.device = None
        self.static = static # Indicates if a volume is created from a snapshot
                             # AND can be deleted upon cluster termination
        self.snapshot_progress = None
        self.snapshot_status = None
        self._status = volume_status.NONE
        self._last_status_check = None

        if (vol_id): # get the volume object immediately, if id is passed
            self.update(vol_id)
        elif from_snapshot_id:
            self.create()

    def __str__(self):
        return str(self.volume_id)

    def __repr__(self):
        if self.volume_id is not None:
            return self.get_full_name()
        else:
            return "No volume ID yet; {0} ({1})".format(self.from_snapshot_id, self.fs.get_full_name())

    def get_full_name(self):
        return "{vol} ({fs})".format(vol=self.volume_id, fs=self.fs.get_full_name())

    def _get_details(self, details):
        """
        Volume-specific details for this file system
        """
        details['DoT']      = "Yes" if self.static else "No"
        details['device']   = self.device
        details['volume_id']= self.volume_id
        details['from_snap'] = self.from_snapshot_id
        details['snapshot_progress'] = self.snapshot_progress
        details['snapshot_status'] = self.snapshot_status
        # TODO: keep track of any errors
        details['err_msg']  = None if details.get('err_msg', '') == '' else details['err_msg']
        return details

    def update(self, vol_id):
        """ switch to a different boto.ec2.volume.Volume """
        log.debug('vol_id = {0} ({1})'.format(vol_id, type(vol_id)))
        if isinstance(vol_id,basestring):
            vols = self.app.cloud_interface.get_all_volumes( volume_ids=(vol_id, ))
            if not vols:
                log.error('Attempting to connect to a non-existent volume {0}'.format(vol_id))
            vol = vols[0]
        else:
            vol = vol_id
        log.debug("Updating current volume reference '%s' to a new one '%s'" % (self.volume_id, vol.id))
        if vol.attachment_state() == 'attached' and vol.attach_data.instance_id != self.app.cloud_interface.get_instance_id():
            log.error('Attempting to connect to a volume ({0} that is already attached to a different instance ({1}'.format(vol.volume_id, vol.attach_data.instance_id))
            self.volume = None
            self.device = None
        else:
            self.volume = vol
            self.device = vol.attach_data.device
            self.size = vol.size
            self.from_snapshot_id = vol.snapshot_id
            if self.from_snapshot_id == '':
                self.from_snapshot_id = None

    @property
    def volume_id(self):
        if self.volume:
            return self.volume.id
        else:
            return None
    
    @property
    def attach_device(self):
        if self.volume:
            return self.volume.attach_data.device
        else:
            return None
    
    @property
    def status(self):
        if not self.volume:
            # no volume active
            status = volume_status.NONE
        elif self._status and self._last_status_check >= time.time() - MIN_TIME_BETWEEN_STATUS_CHECKS:
            status = self._status
        else:
            try:
                self.volume.update()
                status = volume_status_map.get(self.volume.status,None)
                if status == volume_status.IN_USE and self.volume.attachment_state() == 'attached':
                    status = volume_status.ATTACHED
                if not status:
                    log.error('Unknown volume status {0}. Assuming volume_status.NONE'.format(self.volume.status))
                    status = volume_status.NONE
                self._status = status
                self._last_status_check = time.time()
            except EC2ResponseError as e:
                log.error('Cannot retrieve status of current volume. {0}'.format(e))
                status = volume_status.NONE
        return status

    def wait_for_status(self,status,timeout=120):
        """Wait for timeout seconds, or until the volume reaches a desired status
        Returns false if it never hit the request status before timeout"""
        if self.status == volume_status.NONE:
            log.debug('Attempted to wait for a status ({0} ) on a non-existent volume'.format(status))
            return False # no volume means not worth waiting
        else:
            start_time=time.time()
            checks = 10
            end_time = start_time + timeout
            wait_time = float(timeout)/checks
            while time.time() <= end_time:
                if self.status == status:
                    log.debug('Volume {0} has reached status {1}'.format(self.volume_id,status))
                    return True
                else:
                    log.debug('Waiting for volume {0} (status {1}) to reach status {2}. Remaining checks: {3}'.format(self.volume_id,self.status,status,checks))
                    checks -= 1
                    time.sleep(wait_time)
            log.debug('Wait for volume {0} to reach status {1} timed out. Current status {2}'.format(self.volume_id,status,self.status))
            return False


    def create(self, filesystem=None):
        if not self.size and not self.from_snapshot_id:
            log.error('Cannot add a volume without a size or snapshot ID')
            return None
        
        if self.status == volume_status.NONE:
            try:
                log.debug("Creating a new volume of size '%s' in zone '%s' from snapshot '%s'" % (self.size, self.app.cloud_interface.get_zone(), self.from_snapshot_id))
                self.volume = self.app.cloud_interface.get_ec2_connection().create_volume(self.size, self.app.cloud_interface.get_zone(), snapshot=self.from_snapshot_id)
                self.size = int(self.volume.size or 0) # when creating from a snapshot in Euca, volume.size may be None
                log.debug("Created new volume of size '%s' from snapshot '%s' with ID '%s' in zone '%s'" % (self.size, self.from_snapshot_id, self.volume_id, self.app.cloud_interface.get_zone()))
            except EC2ResponseError, e:
                log.error("Error creating volume: %s" % e)
        else:
            log.debug("Tried to create a volume but it is in state '%s' (volume ID: %s)" % (self.status, self.volume_id))

        # Add tags to newly created volumes (do this outside the inital if/else
        # to ensure the tags get assigned even if using an existing volume vs.
        # creating a new one)
        try:
            self.app.cloud_interface.add_tag(self.volume, 'clusterName', self.app.ud['cluster_name'])
            self.app.cloud_interface.add_tag(self.volume, 'bucketName', self.app.ud['bucket_cluster'])
            if filesystem:
                self.app.cloud_interface.add_tag(self.volume, 'filesystem', filesystem)
        except EC2ResponseError, e:
            log.error("Error adding tags to volume: %s" % e)

    def delete(self):
        try:
            volume_id = self.volume_id
            self.volume.delete()
            log.debug("Deleted volume '%s'" % volume_id)
            self.volume = None
        except EC2ResponseError, e:
            log.error("Error deleting volume '%s' - you should delete it manually after the cluster has shut down: %s" % (self.volume_id, e))

    # attachment helper methods

    def _get_device_list(self):
        return frozenset(glob('/dev/*d[a-z]'))

    def _increment_device_id(self,device_id):
        new_id = device_id[0:-1] + chr(ord(device_id[-1])+1)
        return new_id

    def _get_likely_next_devices(self,devices=None):
        """Returns a list of possible devices to attempt to attempt to connect to.
        If using virtio, then the devices get attached as /dev/vd?.
        Newer ubuntu kernels might get devices attached as /dev/xvd?.
        Otherwise, it'll probably get attached as /dev/sd?
        If either /dev/vd? or /dev/xvd? devices exist, then we know to use the next of those.
        Otherwise, test /dev/sd?, /dev/xvd?, then /dev/vd?
        This is so totally not thread-safe. If other devices get attached externally, the device id may already be in use when we get there."""
        if not devices:
            devices = self._get_device_list()
        device_map = map(lambda x:(x.split('/')[-1], x), devices)  # create a dict of id:/dev/id from devices
        # in order, we want vd?, xvd?, or sd?
        vds = sorted( (d[1] for d in device_map if d[0][0] == 'v' ) )
        xvds = sorted( ( d[1] for d in device_map if d[0][0:2] == 'xv' ) )
        sds = sorted( ( d[1] for d in device_map if d[0][0] == 's'  ) )
        if vds:
            return ( self._increment_device_id(vds[-1] ), )
        elif xvds:
            return ( self._increment_device_id(xvds[-1] ), )
        elif sds:
            return ( self._increment_device_id( sds[-1] ), '/dev/vda', '/dev/xvda' ) 
        else:
            log.error("Could not determine next available device from {0}".format(devices))
            return None

    def _do_attach(self, attach_device):
        try:
            if attach_device is not None:
                log.debug("Attaching volume '%s' to instance '%s' as device '%s'" % (self.volume_id,  self.app.cloud_interface.get_instance_id(), attach_device))
                self.volume.attach(self.app.cloud_interface.get_instance_id(),attach_device)
            else:
                log.error("Attaching volume '%s' to instance '%s' failed because could not determine device." % (self.volume_id,  self.app.cloud_interface.get_instance_id()))
                return False
        except EC2ResponseError, e:
            for er in e.errors:
                if er[0] == 'InvalidVolume.ZoneMismatch':
                    msg = "Volume '{0}' is located in the wrong availability zone for this instance. "\
                        "You MUST terminate this instance and start a new one in zone '{1}'."\
                        .format(self.volume_id, self.app.cloud_interface.get_zone())
                    self.app.msgs.critical(msg)
                    log.error(msg)
                else:
                    log.error("Attaching volume '%s' to instance '%s' as device '%s' failed. "
                        "Exception: %s (%s)" % (self.volume_id,
                        self.app.cloud_interface.get_instance_id(), attach_device, er[0], er[1]))
            return False
        return self.status

    def attach(self):
        """
        Attach EBS volume to the given device.
        Try it for some time.
        Returns the attached device path, or None if it can't attach
        """
        log.debug('Starting Volume.attach. volume {0}'.format(self.volume_id,self.app.cloud_interface.get_instance_id()))
        # bail if the volume is doesn't exist, or is already attached
        if self.status == volume_status.NONE or self.status == volume_status.DELETING:
            log.error('Attempt to attach non-existent volume {0}'.format(self.volume_id))
            return None
        elif self.status == volume_status.ATTACHED or self.status == volume_status.IN_USE:
            log.debug('Volume {0} already attached')
            return self.device

        # wait for the volume to become available
        if self.from_snapshot_id and  self.status == volume_status.CREATING:
            # Eucalyptus can take an inordinate amount of time to create a volume from a snapshot
            log.warning("Waiting for volume to be created from a snapshot...") 
            if not self.wait_for_status(volume_status.AVAILABLE,timeout=600): 
                log.error('Volume never reached available from creating status. Status is {0}'.format(self.status))
        elif self.status != volume_status.AVAILABLE:
            if not self.wait_for_status(volume_status.AVAILABLE, timeout=60):
                log.error('Volume never became available to attach. Status is {0}'.format(self.status))
                return None

        # attempt to attach
        for attempted_device in self._get_likely_next_devices():
            pre_devices = self._get_device_list()
            log.debug('Before attach, devices = {0}'.format(' '.join(pre_devices)))
            if self._do_attach(attempted_device):
                if self.wait_for_status(volume_status.ATTACHED):
                    time.sleep(30) # give a few seconds for the device to show up in the OS
                    post_devices = self._get_device_list()
                    log.debug('After attach, devices = {0}'.format(' '.join(post_devices)))
                    new_devices = post_devices - pre_devices
                    log.debug('New devices = {0}'.format(' '.join(new_devices)))
                    if len(new_devices) == 0:
                        log.debug('Could not find attached device for volume {0}. Attempted device = {1}'.format(self.volume_id, attempted_device))
                    elif attempted_device in new_devices:
                        self.device = attempted_device
                        return attempted_device
                    elif len(new_devices) > 1:
                        log.error("Multiple devices (%s) added to OS during process, and none are the requested device. Can't determine new device. Aborting"
                              % ', '.join(new_devices))
                        return None
                    else:
                        device = tuple(new_devices)[0]
                        self.device= device
                        return device
                # requested device didn't attach, for whatever reason
                if self.status != volume_status.AVAILABLE and attempted_device[-3:-1] != 'vd':
                    self.detach() # in case it attached invisibly
                self.wait_for_status(volume_status.AVAILABLE, 60)
        return None # no device properly attached

    def detach(self):
        """
        Detach EBS volume from an instance.
        Try it for some time.
        """
        if self.status == volume_status.ATTACHED or self.status == volume_status.IN_USE:
            try:
                self.volume.detach()
            except EC2ResponseError, e:
                log.error("Detaching volume '%s' from instance '%s' failed. Exception: %s" % (self.volume_id, self.app.cloud_interface.get_instance_id(), e))
                return False
            self.wait_for_status(volume_status.AVAILABLE,240)
            if self.status != volume_status.AVAILABLE:
                log.debug('Attempting to detach again.')
                try:
                    self.volume.detach()
                except EC2ResponseError, e:
                    log.error("Detaching volume '%s' from instance '%s' failed. Exception: %s" % (self.volume_id, self.app.cloud_interface.get_instance_id(), e))
                    return False
                if not self.wait_for_status(volume_status.AVAILABLE,60):
                    log.warning('Volume {0} did not detach properly. Left in state {1}'.format(self.volume_id,self.status))
                    return False
        else:
            log.warning("Cannot detach volume '%s' in state '%s'" % (self.volume_id, self.status))
            return False
        return True

    def snapshot(self, snap_description=None):
        log.info("Initiating creation of a snapshot for the volume '%s'" % self.volume_id)
        try:
            snapshot = self.volume.create_snapshot(description=snap_description)
        except EC2ResponseError as ex:
            log.error("Error creating a snapshot from volume '%s': %s" % (self.volume_id, ex))
            raise
        if snapshot:
            while snapshot.status != 'completed':
                log.debug("Snapshot '%s' progress: '%s'; status: '%s'" \
                    % (snapshot.id, snapshot.progress, snapshot.status))
                self.snapshot_progress = snapshot.progress
                self.snapshot_status = snapshot.status
                time.sleep(6)
                snapshot.update()
            log.info("Completed creation of a snapshot for the volume '%s', snap id: '%s'" \
                % (self.volume_id, snapshot.id))
            self.snapshot_progress = None # Reset because of the UI
            self.snapshot_status = None # Reset because of the UI
            return str(snapshot.id)
        else:
            log.error("Could not create snapshot from volume '%s'" % self.volume_id)
            return None

    def get_from_snap_id(self):
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
        if self.fs.name != 'galaxyData' and self.from_snapshot_id is not None:
            log.debug("Marked volume '%s' from file system '%s' as 'static'" % (self.volume_id, self.fs.name))
            self.static = True
            self.fs.kind= 'snapshot'
        else:
            self.fs.kind = 'volume'
        if self.attach():
            self.mount(self.fs.mount_point)

    def remove(self, mount_point, delete_vols=True):
        """
        Remove this volume from the system. This implies unmounting the associated
        file system, detaching the volume, and, optionally, deleting the volume.
        """
        self.unmount(mount_point)
        log.debug("Detaching volume {0} as {1}".format(self.volume_id, self.fs.get_full_name()))
        if self.detach():
            log.debug("Detached volume {0} as {1}".format(self.volume_id, self.fs.get_full_name()))
            if self.static and self.fs.name != 'galaxyData' and delete_vols:
                log.debug("Deleting volume {0} as part of {1}".format(self.volume_id, self.fs.get_full_name()))
                self.delete()

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
                        log.warning("A file system at {0} already exists and is not empty; cannot "
                        "mount volume {1}".format(mount_point, self.volume_id))
                        return False
                else:
                    os.mkdir(mount_point)
                # Potentially wait for the device to actually become available in the system
                # TODO: Do something if the device is not available in the given time period
                for i in range(10):
                    if os.path.exists(self.device):
                        log.debug("Device path {0} checked and it exists.".format(self.device))
                        break
                    else:
                        log.debug("Device path {0} does not yet exists; waiting...".format(self.device))
                        time.sleep(4)
                # Until the underlying issue is fixed (see FIXME below), mask this
                # even more by custom-handling the run command and thus not printing the err
                cmd = '/bin/mount %s %s' % (self.device, mount_point)
                process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                _, _ = process.communicate()
                if process.returncode != 0:
                    # FIXME: Assume if a file system cannot be mounted that it's because
                    # there is not a file system on the device so try creating one
                    if run('/sbin/mkfs.xfs %s' % self.device,
                        "Failed to create a files ystem on device %s" % self.device,
                        "Created a file system on device %s" % self.device):
                        if not run('/bin/mount %s %s' % (self.device, mount_point),
                            "Error mounting file system %s from %s" % (mount_point, self.device),
                            "Successfully mounted file system %s from %s" % (mount_point, self.device)):
                            log.error("Failed to mount device '%s' to mount point '%s'"
                                % (self.device, mount_point))
                            return False
                else:
                    log.info("Successfully mounted file system {0} from {1}".format(mount_point,
                        self.device))
                try:
                    # Default owner of all mounted file systems to `galaxy` user
                    os.chown(mount_point, pwd.getpwnam("galaxy")[2], grp.getgrnam("galaxy")[2])
                    # Add Galaxy- and CloudBioLinux-required files under the 'data' dir
                    if self.fs.name == 'galaxyData':
                        for sd in ['files', 'tmp', 'upload_store', 'export']:
                            path = os.path.join(paths.P_GALAXY_DATA, sd)
                            if not os.path.exists(path):
                                os.mkdir(path)
                            # Make 'export' dir that's shared over NFS be
                            # owned by `ubuntu` user so it's accesible
                            # for use to the rest of the cluster
                            if sd == 'export':
                                os.chown(path, pwd.getpwnam("ubuntu")[2], grp.getgrnam("ubuntu")[2])
                            else:
                                os.chown(path, pwd.getpwnam("galaxy")[2], grp.getgrnam("galaxy")[2])
                except OSError, e:
                    log.debug("Tried making 'galaxyData' sub-dirs but failed: %s" % e)
                # Lastly, share the newly mounted file system over NFS
                if self.fs.add_nfs_share(mount_point):
                    return True
            log.warning("Cannot mount volume '%s' in state '%s'. Waiting (%s/30)." % (self.volume_id,
                self.status, counter))
            time.sleep(2)

    def unmount(self, mount_point):
        """
        Unmount the file system from the specified mount point, removing it from
        NFS in the process.
        """
        try:
            mp = mount_point.replace('/', '\/') # Escape slashes for sed
            # Because we're unmounting the file systems in separate threads, use a lock file
            with flock(self.fs.nfs_lock_file):
                if run("/bin/sed -i 's/^%s/#%s/' /etc/exports" % (mp, mp),
                        "Error removing '%s' from '/etc/exports'" % mount_point,
                        "Successfully removed '%s' from '/etc/exports'" % mount_point):
                    self.fs.dirty = True
        except Exception, e:
            log.debug("Problems configuring NFS or /etc/exports: '%s'" % e)
            return False
        self.fs.status()
        if self.fs.state == service_states.RUNNING or self.fs.state == service_states.SHUTTING_DOWN:
            log.debug("Unmounting volume-based FS from {0}".format(mount_point))
            for counter in range(10):
                if run('/bin/umount %s' % mount_point,
                        "Error unmounting file system '%s'" % mount_point,
                        "Successfully unmounted file system '%s'" % mount_point):
                    # Clean up the system path now that the file system is unmounted
                    try:
                        os.rmdir(mount_point)
                    except OSError, e:
                        log.error("Error removing unmounted path {0}: {1}".format(mount_point, e))
                    break
                if counter == 9:
                    log.warning("Could not unmount file system at '%s'" % mount_point)
                    return False
                counter += 1
                time.sleep(3)
            return True
        else:
            log.debug("Did not unmount file system '%s' because it is not in state "\
                "'running' or 'shutting-down'" % self.fs.get_full_name())
            return False

