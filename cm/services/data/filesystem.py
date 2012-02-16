import commands, os, time, shutil, threading, pwd, grp, re

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

class Volume(object):
    def __init__(self, app, vol_id=None, device=None, attach_device=None, size=0, from_snapshot_id=None, static=False):
        self.app = app
        self.volume = None # boto instance object representing the current volume
        self.volume_id = vol_id
        self.device = device # Device ID visible by the operating system
        self.attach_device = attach_device # Device ID visible/reported by cloud provider as the device attach point
        self.size = size
        self.from_snapshot_id = from_snapshot_id
        self.device = None
        self.static = static # Indicates if a volume is created from a snapshot AND can be deleted upon cluster termination
        self.snapshot_progress = None
        self.snapshot_status = None
    
    def update(self, vol):
        """ Update reference to the 'self' to point to argument 'vol' """
        log.debug("Updating current volume reference '%s' to a new one '%s'" % (self.volume_id, vol.id))
        self.volume = vol
        self.volume_id = vol.id
        self.device = vol.attach_data.device
        self.size = vol.size
        self.from_snapshot_id = vol.snapshot_id
    
    def status(self):
        if self.volume_id is None:
            return volume_status.NONE
        else:
            ec2_conn = self.app.cloud_interface.get_ec2_connection()
            if ec2_conn:
                try:
                    self.volume = ec2_conn.get_all_volumes([self.volume_id])[0]
                except EC2ResponseError, e:
                    log.error("Cannot retrieve reference to volume '%s'; setting volume id to None. Error: %s" % (self.volume_id, e))
                    self.volume_id = None
                    return volume_status.NONE
                self.from_snapshot_id = self.volume.snapshot_id
                if self.from_snapshot_id is '': # ensure consistency
                    self.from_snapshot_id = None
                if self.volume.status == 'creating':
                    return volume_status.CREATING
                elif self.volume.status == 'available':
                    return volume_status.AVAILABLE
                elif self.volume.status == 'in-use':
                    if self.volume.attach_data.status == 'attached':
                        return volume_status.ATTACHED
                    else:
                        return volume_status.IN_USE
                elif self.volume.status == 'deleting':
                    return volume_status.DELETING
                else:
                    log.debug("Unrecognized volume '%s' status: '%s'" % (self.volume_id, self.volume.status))
                    return self.volume.status
            # Connection failed
            return volume_status.NONE
    
    def get_attach_device(self, offset=0):
        # Need to ensure both of the variables are in sync
        if offset or (not self.device or not self.attach_device):
            if not self._set_devices(offset):
                return None
        return self.attach_device
    
    def get_device(self, offset=0):
        # Need to ensure both of the variables are in sync
        if offset or (not self.device or not self.attach_device):
            if not self._set_devices(offset):
                return None
        return self.device
    
    def _set_devices(self, offset=0):
        """ Use this method to figure out which as device this volume should get
        attached and how is it visible to the system once attached.
        Offset forces creation of a new device ID"""
        # Get list of Galaxy-specific devices already attached to 
        # the instance and set current volume as the next one in line
        # TODO: make device root an app config option vs. hard coding here
        
        # As of Ubuntu 11.04 (kernel 2.6.38), EBS volumes attached to /dev/sd*
        # get attached as device /dev/xvd*. So, look at the current version
        # of kernel running and set volume's device accordingly
        kernel_out = commands.getstatusoutput('uname -r')
        if kernel_out[0] == 0:
            # Extract significant kernel version numbers and test against
            # lowest kernel version that changes device mappings
            if map(int, kernel_out[1].split('-')[0].split('.')) >= [2, 6, 38]:
                mount_base = '/dev/xvdg'
            else:
                mount_base = '/dev/sdg'
        else:
            log.error("Could not discover kernel version required for to obtain volume's device.")
            return False
        attach_base = '/dev/sdg'
        # In case the system was rebooted and the volume is already attached, match
        # the device ID with the attach device ID
        # If offset is set, force creation of new IDs
        if self.attach_device and offset == 0:
            self.device = re.sub(attach_base, mount_base, self.attach_device)
            return True
        dev_list = commands.getstatusoutput('ls %s*' % mount_base)
        if dev_list[0] == 0:
            device_number = str(max([int(d[len(mount_base):]) for d in dev_list[1].split()])+1+offset)
            self.device = '%s%s' % (mount_base, device_number)
            self.attach_device = '%s%s' % (attach_base, device_number)
        else:
            log.debug("No devices found attached to %s#, defaulting current volume device to %s1 and attach device to %s1" % (mount_base, mount_base, attach_base))
            self.device = '%s1' % mount_base
            self.attach_device = '%s1' % attach_base
        log.debug("Running on kernel version %s; set volume device as '%s' and attach device as '%s'" % (kernel_out[1], self.device, self.attach_device))
        return True
    
    def create(self, filesystem=None):
        if self.status() == volume_status.NONE:
            try:
                log.debug("Creating a new volume of size '%s' in zone '%s' from snapshot '%s'" % (self.size, self.app.cloud_interface.get_zone(), self.from_snapshot_id))
                self.volume = self.app.cloud_interface.get_ec2_connection().create_volume(self.size, self.app.cloud_interface.get_zone(), snapshot=self.from_snapshot_id)
                self.volume_id = str(self.volume.id)
                self.size = int(self.volume.size)
                log.debug("Created new volume of size '%s' from snapshot '%s' with ID '%s' in zone '%s'" % (self.size, self.from_snapshot_id, self.volume_id, self.app.cloud_interface.get_zone()))
            except EC2ResponseError, e:
                log.error("Error creating volume: %s" % e)
        else:
            log.debug("Tried to create a volume but it is in state '%s' (volume ID: %s)" % (self.status(), self.volume_id))
        
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
            self.app.cloud_interface.get_ec2_connection().delete_volume(self.volume_id)
            log.debug("Deleted volume '%s'" % self.volume_id)
            self.volume_id = None
            self.volume = None
        except EC2ResponseError, e:
            log.error("Error deleting volume '%s' - you should delete it manually after the cluster has shut down: %s" % (self.volume_id, e))
    
    def do_attach(self, attach_device):
        try:
            if attach_device is not None:
                log.debug("Attaching volume '%s' to instance '%s' as device '%s'" 
                    % (self.volume_id,  self.app.cloud_interface.get_instance_id(), attach_device))
                volumestatus = self.app.cloud_interface.get_ec2_connection() \
                    .attach_volume(self.volume_id, self.app.cloud_interface.get_instance_id(), attach_device)
            else:
                log.error("Attaching volume '%s' to instance '%s' failed because could not determine device." 
                    % (self.volume_id,  self.app.cloud_interface.get_instance_id()))
                return False
        except EC2ResponseError, e:
            for er in e.errors:
                if er[0] == 'InvalidVolume.ZoneMismatch':
                    log.error("Volume '{0}' is in the wrong zone for this instance. IT IS REQUIRED TO START A NEW INSTANCE IN ZONE '{1}'."\
                        .format(self.volume_id, self.app.cloud_interface.get_zone()))
                else:
                    log.error("Attaching volume '%s' to instance '%s' as device '%s' failed. Exception: %s (%s)" 
                        % (self.volume_id,  self.app.cloud_interface.get_instance_id(), attach_device, er[0], er[1]))
            return False
        return volumestatus
    
    def attach(self):
        """
        Attach EBS volume to the given device.
        Try it for some time.
        """
        for counter in range( 30 ):
            if self.status() == volume_status.AVAILABLE:
                attach_device = self.get_attach_device() # Ensure device ID is assigned to current volume
                volumestatus = self.do_attach(attach_device)
                # Wait until the volume is 'attached'
                ctn = 0
                attempts = 30
                while ctn < attempts:
                    log.debug("Attaching volume '%s'; status: %s (check %s/%s)" % (self.volume_id, volumestatus, ctn, attempts))
                    if volumestatus == 'attached':
                        log.debug("Volume '%s' attached to instance '%s' as device '%s'" % (self.volume_id, self.app.cloud_interface.get_instance_id(), self.get_attach_device()))
                        break
                    if ctn == attempts-1:
                        log.debug("Volume '%s' FAILED to attach to instance '%s' as device '%s'." % (self.volume_id, self.app.cloud_interface.get_instance_id(), self.get_attach_device()))
                        if attempts < 90:
                            log.debug("Will try another device")
                            attempts += 30 # Increment attempts for another try
                            if self.detach():
                                attach_device = self.get_attach_device(offset=attempts/30-1) # Offset device num by number of attempts
                                volumestatus = self.do_attach(attach_device)
                        else:
                            log.debug("Will not try again. Aborting attaching of volume")
                            return False
                    volumes = (self.app.cloud_interface.get_ec2_connection()).get_all_volumes([self.volume_id])
                    volumestatus = volumes[0].attachment_state()
                    time.sleep(2)
                    ctn += 1
                return True
            elif self.status() == volume_status.IN_USE or self.status() == volume_status.ATTACHED:
                # Check if the volume is already attached to current instance (can happen following a reboot/crash)
                if self.volume.attach_data.instance_id == self.app.cloud_interface.get_instance_id():
                    self.attach_device = self.volume.attach_data.device
                    log.debug("Tried to attach a volume but the volume '%s' is already attached (as device %s)" % (self.volume_id, self.get_attach_device()))
                    return True
            elif self.volume_id is None:
                log.error("Wanted to attach a volume but missing volume ID; cannot attach")
                return False
            if counter == 29:
                log.warning("Cannot attach volume '%s' in state '%s'" % (self.volume_id, self.status()))
                return False
            log.debug("Wanting to attach volume '%s' but it's not 'available' yet (current state: '%s'). Waiting (%s/30)." % (self.volume_id, self.status(), counter))
            time.sleep( 2 )
    
    def detach(self):
        """
        Detach EBS volume from an instance.
        Try it for some time.
        """
        if self.status() == volume_status.ATTACHED or self.status() == volume_status.IN_USE:
            try:
                volumestatus = self.app.cloud_interface.get_ec2_connection().detach_volume( self.volume_id, self.app.cloud_interface.get_instance_id())
            except EC2ResponseError, e:
                log.error("Detaching volume '%s' from instance '%s' failed. Exception: %s" % (self.volume_id, self.app.cloud_interface.get_instance_id(), e))
                return False
                
            for counter in range(30):
                log.debug("Detaching volume '%s'; status '%s' (check %s/30)" % (self.volume_id, volumestatus, counter))
                if volumestatus == 'available':
                    log.debug("Volume '%s' successfully detached from instance '%s'." % ( self.volume_id, self.app.cloud_interface.get_instance_id() ))
                    self.volume = None
                    break
                if counter == 28:
                    try:
                        volumestatus = self.app.cloud_interface.get_ec2_connection().detach_volume(self.volume_id, self.app.cloud_interface.get_instance_id(), force=True)
                    except EC2ResponseError, e:
                        log.error("Second attempt at detaching volume '%s' from instance '%s' failed. Exception: %s" % (self.volume_id, self.app.cloud_interface.get_instance_id(), e))
                        return False
                if counter == 29:
                    log.debug("Volume '%s' FAILED to detach from instance '%s'" % ( self.volume_id, self.app.cloud_interface.get_instance_id() ))
                    return False
                time.sleep(6)
                volumes = self.app.cloud_interface.get_ec2_connection().get_all_volumes( [self.volume_id] )
                volumestatus = volumes[0].status
        else:
            log.warning("Cannot detach volume '%s' in state '%s'" % (self.volume_id, self.status()))
            return False
        return True
    
    def snapshot(self, snap_description=None):
        log.info("Initiating creation of a snapshot for the volume '%s'" % self.volume_id)
        ec2_conn = self.app.cloud_interface.get_ec2_connection()
        try:
            snapshot = ec2_conn.create_snapshot(self.volume_id, description=snap_description)
        except Exception, ex:
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
        self.status()
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
        except Exception, e:
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
        # If the service was successfuly removed, remove the mount point
        if self.state == service_states.SHUT_DOWN:
            try:
                if len(os.listdir(self.mount_point)) > 0:
                    shutil.rmtree(self.mount_point)
            except OSError, e:
                log.error("Trouble cleaning directory '%s': %s" % (self.mount_point, e))
        else:
            log.warning("Wanted to clean file system {0} but the service is not in state '{1}'; it in state '{2}'") \
                .format(self.name, service_states.SHUT_DOWN, self.state)
    
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
                vol.volume_id = None
            
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
                    ec2_conn = self.app.cloud_interface.get_ec2_connection()
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
            if volume.status() == volume_status.ATTACHED:
                if os.path.exists(self.mount_point):
                    if len(os.listdir(self.mount_point)) != 0:
                        log.warning("Filesystem at %s already exists and is not empty." % self.mount_point)
                        return False
                else:
                    os.mkdir( self.mount_point )
                
                # Potentially wait for the device to actually become available in the system
                # TODO: Do something if the device is not available in given time period
                for i in range(10):
                    if os.path.exists(volume.get_device()):
                        log.debug("Path '%s' checked and exists." % volume.get_device())
                        break
                    else:
                        log.debug("Path '%s' does not yet exists." % volume.get_device())
                        time.sleep(4)
                if not run('/bin/mount %s %s' % (volume.get_device(), self.mount_point), "Error mounting file system '%s' from '%s'" % (self.mount_point, volume.get_device()), "Successfully mounted file system '%s' from '%s'" % (self.mount_point, volume.get_device())):
                    # FIXME: Assume if a file system cannot be mounted that it's because there is not a file system on the device so create one
                    if run('/sbin/mkfs.xfs %s' % volume.get_device(), "Failed to create filesystem on device '%s'" % volume.get_device(), "Created filesystem on device '%s'" % volume.get_device()):
                        if not run('/bin/mount %s %s' % (volume.get_device(), self.mount_point), "Error mounting file system '%s' from '%s'" % (self.mount_point, volume.get_device()), "Successfully mounted file system '%s' from '%s'" % (self.mount_point, volume.get_device())):
                            log.error("Failed to mount device '%s' to mount point '%s'" % (volume.get_device(), self.mount_point))
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
            log.warning("Cannot mount volume '%s' in state '%s'. Waiting (%s/30)." % (volume.volume_id, volume.status(), counter))
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
        vols = self.app.cloud_interface.get_ec2_connection().get_all_volumes(filters=f)
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
    
