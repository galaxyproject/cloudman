import commands, os, time, shutil, threading, pwd, grp
from glob import glob

from cm.services.data import DataService
from cm.util.misc import run
from cm.util import paths
from cm.services import service_states
from boto.exception import EC2ResponseError
from cm.util.bunch import Bunch

import logging
log = logging.getLogger( 'cloudman' )

volume_status = Bunch(
    NONE="does not exist",
    CREATING="creating",
    AVAILABLE="available",
    IN_USE="in use",
    ATTACHED="attached",
    DELETING="deleting"
)

volume_status_map = {
                     'creating'    : volume_status.CREATING,
                     'available'   : volume_status.AVAILABLE,
                     'in-use'      : volume_status.IN_USE,
                     'attached'    : volume_status.ATTACHED,
                     'deleting'    : volume_status.DELETING,
                     }

class Volume(object):
    def __init__(self, app, vol_id=None, device=None, attach_device=None, size=0, from_snapshot_id=None, static=False):
        self.app = app
        self.volume = None # boto instance object representing the current volume
        self.device = device # Device ID visible by the operating system
        self.size = size
        self.from_snapshot_id = from_snapshot_id
        self.device = None
        self.static = static # Indicates if a volume is created from a snapshot AND can be deleted upon cluster termination
        self.snapshot_progress = None
        self.snapshot_status = None

        if (vol_id): # get the volume object immediately, if id is passed
            volumes = self.app.cloud_interface.get_all_volumes( volume_ids=(vol_id,))
            if volumes:
                self.update(volumes[0])
            else:
                log.error('Attempt to create Volume object with non-existent volume ID {0}'.format(vol_id))

    def update(self, vol):
        """ switch to a different boto.ec2.volume.Volume """
        log.debug("Updating current volume reference '%s' to a new one '%s'" % (self.volume_id, vol.id))
        vol.update()
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
        else:
            try:
                self.volume.update()
                status = volume_status_map.get(self.volume.status,None)
                if status == volume_status.IN_USE and self.volume.attachment_state() == 'attached':
                    status = volume_status.ATTACHED
                if not status:
                    log.error('Unknown volume status {0}. Assuming volume_status.NONE'.format(self.volume.status))
                    status = volume_status.NONE
            except EC2ResponseError as e:
                log.error('Cannot retrieve status of current volume. {0}'.format(e))
                status = volume_status.NONE
        return status

    def wait_for_status(self,status,timeout=120):
        """Wait for timeout seconds, or until the volume reaches a desired status
        Returns false if it never hit the request status before timeout"""
        if self.status == volume_status.NONE:
            log.debug('Attemped to wait for a status ({0} ) on a non-existent volume'.format(status))
            return False # no volume means not worth waiting
        else:
            start_time=time.time()
            checks = 30
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
        if self.status == volume_status.NONE:
            try:
                log.debug("Creating a new volume of size '%s' in zone '%s' from snapshot '%s'" % (self.size, self.app.cloud_interface.get_zone(), self.from_snapshot_id))
                self.volume = self.app.cloud_interface.get_ec2_connection().create_volume(self.size, self.app.cloud_interface.get_zone(), snapshot=self.from_snapshot_id)
                self.size = int(self.volume.size)
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
            return ( self._increment_device_id( sds[-1] ), '/dev/xvda', '/dev/vda' ) 
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
            log.error("Attaching volume '%s' to instance '%s' as device '%s' failed. Exception: %s" % (self.volume_id,  self.app.cloud_interface.get_instance_id(), attach_device, e))
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
        if self.status != volume_status.AVAILABLE:
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
                log.debug("Snapshot '%s' progress: '%s'; status: '%s'" % (snapshot.id, snapshot.progress, snapshot.status))
                self.snapshot_progress = snapshot.progress
                self.snapshot_status = snapshot.status
                time.sleep(6)
                snapshot.update()
            log.info("Completed creation of a snapshot for the volume '%s', snap id: '%s'" % (self.volume_id, snapshot.id))
            self.snapshot_progress = None # Reset because of the UI
            self.snapshot_status = None # Reset because of the UI
            return str(snapshot.id)
        else:
            log.error("Could not create snapshot from volume '%s'" % self.volume_id)
            return None

    def get_from_snap_id(self):
        return self.from_snapshot_id


class Filesystem(DataService):
    def __init__(self, app, name):
        super(Filesystem, self).__init__(app)
        self.svc_type = "Filesystem"
        self.volumes = []
        self.name = name
        self.size = None
        self.dirty = False
        self.mount_point = '/mnt/%s' % self.name
        self.grow = None # Used (APPLICABLE ONLY FOR galaxyData FS) to indicate need to grow the file system; use following dict structure {'new_size': <size>, 'snap_desc': <snapshot description>}

    def get_full_name(self):
        return "FS-%s" % self.name

    def get_size(self):
        new_size = 0
        for volume in self.volumes:
            new_size += volume.size
        self.size = new_size
        return self.size

    def add(self):
        try:
            log.debug("Trying to add service '%s'" % self.get_full_name())
            self.state = service_states.STARTING
            for vol in self.volumes:
                vol.create(self.name)
                # Mark a volume as 'static' if created from a snapshot
                # Note that if a volume is marked as 'static', it is assumed it
                # can be deleted upon cluster termination!
                if self.name != 'galaxyData' and vol.from_snapshot_id is not None:
                    log.debug("Marked volume '%s' from file system '%s' as 'static'" % (vol.volume_id, self.name))
                    vol.static = True
                if vol.attach():
                    self.mount(vol)
                self.status()
        except EC2ResponseError as e:
            log.error("Error adding filesystem service '%s-%s': %s" % (self.svc_type, self.name, e))
            self.status()

    def remove(self):
        """ Sequential removal of volumes has issues so thread it"""
        log.info("Removing '%s-%s' data service" % (self.svc_type, self.name))
        self.state = service_states.SHUTTING_DOWN
        r_thread = threading.Thread( target=self.__remove() )
        r_thread.start()

    def __remove(self, delete_vols=True):
        log.debug("Thread-removing '%s-%s' data service" % (self.svc_type, self.name))
        self.state = service_states.SHUTTING_DOWN
        self.unmount()
        for vol in self.volumes:
            log.debug("Detaching volume '%s' as %s" % (vol.volume_id, self.get_full_name()))
            if vol.detach():
                log.debug("Detached volume '%s' as %s" % (vol.volume_id, self.get_full_name()))
                if vol.static and self.name != 'galaxyData' and delete_vols:
                    log.debug("Deleting %s" % self.get_full_name())
                    vol.delete()
            log.debug("Setting state of %s to '%s'" % (self.get_full_name(), service_states.SHUT_DOWN))
            self.state = service_states.SHUT_DOWN

    def clean(self):
        """ Remove filesystems and clean up as if they were never there. Useful for CloudMan restarts."""
        self.remove()
        try:
            if len(os.listdir(self.mount_point)) > 0:
                shutil.rmtree(self.mount_point)
        except OSError, e:
            log.error("Trouble cleaning directory '%s': %s" % (self.mount_point, e))

    def expand(self):
        if self.grow is not None:
            self.__remove()
            smaller_vol_ids = []
            # Create a snapshot of detached volume
            for vol in self.volumes:
                smaller_vol_ids.append(vol.volume_id)
                snap_id = vol.snapshot(self.grow['snap_description'])
                vol.size = self.grow['new_size']
                vol.from_snapshot_id = snap_id

            # Create a new volume based on just created snapshot and add the file system
            self.add()

            # Grow file system
            if not run('/usr/sbin/xfs_growfs %s' % self.mount_point, "Error growing file system '%s'" % self.mount_point, "Successfully grew file system '%s'" % self.mount_point):
                return False
            # Delete old, smaller volumes since everything seems to have gone ok
            ec2_conn = self.app.cloud_interface.get_ec2_connection()
            for smaller_vol_id in smaller_vol_ids:
                try:
                    ec2_conn.delete_volume(smaller_vol_id)
                except EC2ResponseError, e:
                    log.error("Error deleting old data volume '%s' during '%s' resizing: %s" % (smaller_vol_id, self.get_full_name(), e))
            # If desired by user, delete snapshot used during the resizing process
            if self.grow['delete_snap'] is True:
                try:
                    ec2_conn.delete_snapshot(snap_id)
                except EC2ResponseError, e:
                    log.error("Error deleting snapshot '%s' during '%s' resizing: %s" % (snap_id, self.get_full_name(), e))
            self.grow = None # Reset flag
            return True
        else:
            log.debug("Tried to grow '%s' but grow flag is None" % self.get_full_name())
            return False

    def snapshot(self, snap_description=None):
        self.__remove(delete_vols=False)
        snap_ids = []
        # Create a snapshot of the detached volumes
        for vol in self.volumes:
            snap_ids.append(vol.snapshot(snap_description=snap_description))
        # After the snapshot is done, add the file system back as a cluster service
        self.add()
        return snap_ids

    def mount(self, volume, mount_point=None):
        """ Mount file system at provided mount point. If present in /etc/exports,
        this method enables NFS on given mount point (i.e., uncomments respective
        line in /etc/exports)
        """
        if mount_point is not None:
            self.mount_point = mount_point
        for counter in range(30):
            if volume.status == volume_status.ATTACHED:
                if os.path.exists(self.mount_point):
                    if len(os.listdir(self.mount_point)) != 0:
                        log.warning("Filesystem at %s already exists and is not empty." % self.mount_point)
                        return False
                else:
                    os.mkdir( self.mount_point )

                # Potentially wait for the device to actually become available in the system
                # TODO: Do something if the device is not available in given time period
                for i in range(10):
                    if os.path.exists(volume.device):
                        log.debug("Path '%s' checked and exists." % volume.device)
                        break
                    else:
                        log.debug("Path '%s' does not yet exists." % volume.device)
                        time.sleep(4)
                if not run('/bin/mount %s %s' % (volume.device, self.mount_point), "Error mounting file system '%s' from '%s'" % (self.mount_point, volume.device), "Successfully mounted file system '%s' from '%s'" % (self.mount_point, volume.device)):
                    # FIXME: Assume if a file system cannot be mounted that it's because there is not a file system on the device so create one
                    if run('/sbin/mkfs.xfs %s' % volume.device, "Failed to create filesystem on device '%s'" % volume.device, "Created filesystem on device '%s'" % volume.device):
                        if not run('/bin/mount %s %s' % (volume.device, self.mount_point), "Error mounting file system '%s' from '%s'" % (self.mount_point, volume.device), "Successfully mounted file system '%s' from '%s'" % (self.mount_point, volume.device)):
                            log.error("Failed to mount device '%s' to mount point '%s'" % (volume.device, self.mount_point))
                            return False
                try:
                    # Default owner of all mounted file systems to `galaxy` user
                    os.chown(self.mount_point, pwd.getpwnam("galaxy")[2], grp.getgrnam("galaxy")[2])
                    # Add Galaxy- and CloudBioLinux-required files under the 'data' dir
                    if self.name == 'galaxyData':
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
                    log.debug("Tried making galaxyData sub-dirs but failed: %s" % e)
                # if self.name == 'galaxyIndices':
                #     run("ln -s %s /mnt/biodata" % self.mount_point, "Failed to create a symlink for galaxyIndices to biodata", "Successfully  created a symlink for galaxyIndices to biodata")
                # run('/bin/chown -R galaxy:galaxy %s' % self.mount_point, "Failed to change owner of '%s' to 'galaxy:galaxy'" % self.mount_point, "Changed owner of '%s' to 'galaxy'" % self.mount_point)
                try:
                    mp = self.mount_point.replace('/', '\/') # Escape slashes for sed
                    if run("/bin/sed 's/^#%s/%s/' /etc/exports > /tmp/exports.tmp" % (mp, mp), "Error removing '%s' from '/etc/exports'" % self.mount_point, "Successfully edited '%s' in '/etc/exports' for NFS." % self.mount_point):
                        shutil.move( '/tmp/exports.tmp', '/etc/exports' )
                        self.dirty = True
                except Exception, e:
                    log.debug("Problems configuring NFS or /etc/exports: '%s'" % e)
                    return False
                return True
            log.warning("Cannot mount volume '%s' in state '%s'. Waiting (%s/30)." % (volume.volume_id, volume.status, counter))
            time.sleep( 2 )

    def unmount(self, mount_point=None):
        """ Unmount file system at provided mount point. If present in /etc/exports,
        this method enables NFS on given mount point (i.e., uncomments respective
        line in /etc/exports and restarts NFS)
        """
        if mount_point is not None:
            self.mount_point = mount_point
        try:
            mp = self.mount_point.replace('/', '\/') # Escape slashes for sed
            if run("/bin/sed 's/^%s/#%s/' /etc/exports > /tmp/exports.tmp" % (mp, mp), "Error removing '%s' from '/etc/exports'" % self.mount_point, "Successfully removed '%s' from '/etc/exports'" % self.mount_point):
                shutil.move( '/tmp/exports.tmp', '/etc/exports' )
                self.dirty = True
        except Exception, e:
            log.debug("Problems configuring NFS or /etc/exports: '%s'" % e)
            return False
        self.status()
        if self.state == service_states.RUNNING or self.state == service_states.SHUTTING_DOWN:
            for counter in range(10):
                if run('/bin/umount -f %s' % self.mount_point, "Error unmounting file system '%s'" % self.mount_point, "Successfully unmounted file system '%s'" % self.mount_point):
                    break
                if counter == 9:
                    log.warning("Could not unmount file system at '%s'" % self.mount_point)
                    return False
                counter += 1
                time.sleep(3)
            return True
        else:
            log.debug("Did not unmount file system '%s' because it is not in state 'running' or 'shutting-down'" % self.get_full_name())
            return False

    def _get_attach_device_from_device(self, device):
        for vol in self.volumes:
            if device == vol.device:
                return vol.attach_device

    def check_and_update_volume(self, device):
        f = {'attachment.device': device, 'attachment.instance-id': self.app.cloud_interface.get_instance_id()}
        vols = self.app.cloud_interface.get_all_volumes(filters=f)
        if len(vols) == 1:
            att_vol = vols[0]
            for vol in self.volumes: # Currently, bc. only 1 vol can be assoc. w/ FS, we'll only deal w/ 1 vol
                if (vol is None and att_vol) or (vol and att_vol and vol.volume_id != att_vol.id):
                    log.debug("Discovered change of vol %s to '%s', attached as device '%s', for FS '%s'" \
                        % ([vol.volume_id for vol in self.volumes], att_vol.id, device, self.name))
                    vol.update(att_vol)
                    # If the new volume does not have tags (clusterName & filesystem), add those
                    if not self.app.cloud_interface.get_tag(att_vol, 'clusterName'):
                        self.app.cloud_interface.add_tag(att_vol, 'clusterName', self.app.ud['cluster_name'])
                    if not self.app.cloud_interface.get_tag(att_vol, 'filesystem'):
                        self.app.cloud_interface.add_tag(att_vol, 'filesystem', self.name)
                    # Update cluster configuration (i.e., persistent_data.yaml) in cluster's bucket
                    self.app.manager.console_monitor.store_cluster_config()
        else:
            log.warning("Did not find a volume attached to instance '%s' as device '%s', file system '%s' (vols=%s)" \
                % (self.app.cloud_interface.get_instance_id(), device, self.name, vols))

    def status(self):
        """Check if file system is mounted to the location based on its name.
        Set state to RUNNING if file system is accessible.
        Set state to ERROR otherwise.
        """
        # log.debug("Updating service '%s-%s' status; current state: %s" % (self.svc_type, self.name, self.state))
        if self.dirty:
            if run("/etc/init.d/nfs-kernel-server restart", "Error restarting NFS server", "As part of filesystem '%s-%s' update, successfully restarted NFS server" % (self.svc_type, self.name)):
                self.dirty = False
        if self.state==service_states.SHUTTING_DOWN or \
           self.state==service_states.SHUT_DOWN or \
           self.state==service_states.UNSTARTED or \
           self.state==service_states.WAITING_FOR_USER_ACTION:
            pass
        elif self.mount_point is not None:
            mnt_location = commands.getstatusoutput("cat /proc/mounts | grep %s | cut -d' ' -f1,2" % self.mount_point)
            if mnt_location[0] == 0 and mnt_location[1] != '':
                try:
                    device, mnt_path = mnt_location[1].split(' ')
                    # Check volume
                    self.check_and_update_volume(self._get_attach_device_from_device(device))
                    # Check mount point
                    if mnt_path == self.mount_point:
                        self.state = service_states.RUNNING
                    else:
                        log.error("STATUS CHECK: Retrieved mount path '%s' does not match expected path '%s'" % (mnt_location[1], self.mount_point))
                        self.state = service_states.ERROR
                except Exception, e:
                    log.error("STATUS CHECK: Exception checking status of FS '%s': %s" % (self.name, e))
                    self.state = service_states.ERROR
                    log.debug(mnt_location)
            else:
                log.error("STATUS CHECK: File system named '%s' is not mounted. Error code %s" % (self.name, mnt_location[0]))
                self.state = service_states.ERROR
        else:
            log.debug("Did not check status of filesystem '%s' with mount point '%s' in state '%s'" % (self.name, self.mount_point, self.state))

    def add_volume(self, vol_id=None, size=None, from_snapshot_id=None):
        self.volumes.append(Volume(self.app, vol_id=vol_id, size=size, from_snapshot_id=from_snapshot_id))

