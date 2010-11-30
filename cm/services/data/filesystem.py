import commands, os, time, shutil, threading

from cm.services.data import DataService
from cm.util.misc import run
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
    def __init__(self, app, vol_id=None, device=None, size=0, from_snapshot_id=None, static=False):
        self.app = app
        self.volume = None # boto instance object representing the current volume
        self.volume_id = vol_id
        self.device = device
        self.size = size
        self.from_snapshot_id = from_snapshot_id
        self.device = None
        self.static = static # Indicates if a volume is created from a snapshot AND can be deleted upon cluster termination
        self.snapshot_progress = None
        self.snapshot_status = None
        
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
    
    def get_device(self):
        if self.device is None:
            # Get list of Galaxy-specific devices already attached to 
            # the instance and set current volume as the next one in line
            # TODO: make device root an app config option vs. hard coding here
            dev_list = commands.getstatusoutput('ls /dev/sdg*')
            if dev_list[0]==0:
                self.device = '/dev/sdg%s' % str(max([int(d[8:]) for d in dev_list[1].split()])+1)
            else:
                log.debug("No devices found attached to /dev/sdg#, defaulting current volume device to /dev/sdg1")
                self.device = '/dev/sdg1'
        return self.device
    
    def create(self, filesystem=None):
        if self.status() == volume_status.NONE:
            try:
                self.volume = self.app.cloud_interface.get_ec2_connection().create_volume(self.size, self.app.cloud_interface.get_zone(), snapshot=self.from_snapshot_id)
                self.volume_id = str(self.volume.id)
                self.size = int(self.volume.size)
                log.debug("Created new volume of size '%s' from snapshot '%s' with ID '%s'" % (self.size, self.from_snapshot_id, self.volume_id))
                self.volume.add_tag('clusterName', self.app.ud['cluster_name'])
                if filesystem:
                    self.volume.add_tag('filesystem', filesystem)
                # Mark a volume as 'static' if created from a snapshot
                # Note that if a volume is marked as 'static', it is assumed it can be deleted
                # upon cluster termination! This will need some attention once data volumes can 
                # be snapshotted.
                if self.from_snapshot_id is not None:
                    self.static = True
            except EC2ResponseError, e:
                log.error("Error creating volume: %s" % e)
    
    def delete(self):
        try:
            self.app.cloud_interface.get_ec2_connection().delete_volume(self.volume_id)
            log.debug("Deleted volume '%s'" % self.volume_id)
            self.volume_id = None
            self.volume = None
        except EC2ResponseError, e:
            log.error("Error deleting volume '%s': %s" % (self.volume_id, e))
    
    def attach(self):
        """
        Attach EBS volume to the given device.
        Try it for some time.
        """
        for counter in range( 30 ):
            if self.status() == volume_status.AVAILABLE:
                self.get_device() # Ensure device ID is assigned to current volume
                try:
                    log.debug("Attaching volume '%s' to instance '%s' as device '%s'" % ( self.volume_id,  self.app.cloud_interface.get_instance_id(), self.get_device() ))
                    volumestatus = self.app.cloud_interface.get_ec2_connection().attach_volume( self.volume_id, self.app.cloud_interface.get_instance_id(), self.get_device() )
                except EC2ResponseError, e:
                    log.error("Attaching volume '%s' to instance '%s' as device '%s' failed. Exception: %s" % ( self.volume_id,  self.app.cloud_interface.get_instance_id(), self.get_device(), e ))
                    return False
                for counter in range( 30 ):
                    log.debug("Attach attempt %s, volume status: %s" % ( counter, volumestatus ))
                    if volumestatus == 'attached':
                        log.debug("Volume '%s' attached to instance '%s' as device '%s'" % (  self.volume_id,  self.app.cloud_interface.get_instance_id(), self.get_device()))
                        break
                    if counter == 29:
                        log.debug("Volume '%s' FAILED to attach to instance '%s' as device '%s'. Aborting." % (  self.volume_id,  self.app.cloud_interface.get_instance_id(), self.get_device() ))
                        return False
                    volumes = (self.app.cloud_interface.get_ec2_connection()).get_all_volumes( [self.volume_id] )
                    volumestatus = volumes[0].attachment_state()
                    time.sleep( 3 )
                return True
            elif self.status() == volume_status.IN_USE or self.status() == volume_status.ATTACHED:
                # Check if the volume is already attached to current instance (can happen following a reboot/crash)
                if self.volume.attach_data.instance_id == self.app.self.app.cloud_interface.get_instance_id():
                    self.device = self.volume.attach_data.device
                    return True
            if counter == 29:
                log.warning("Cannot attach volume '%s' in state '%s'" % (self.volume_id, self.status()))
                return False
            log.debug("Wanting to attach volume '%s' but it's not 'available' yet (current state: '%s'). Waiting (%s/30)." % (self.volume_id, self.status(), counter))
            time.sleep( 2 )
    
    def detach(self):
        """
        Detach EBS volume from the given instance (using boto).
        Try it for some time.
        """
        if self.status() == volume_status.ATTACHED:
            try:
                volumestatus = self.app.cloud_interface.get_ec2_connection().detach_volume( self.volume_id, self.app.cloud_interface.get_instance_id(), force=True )
            except EC2ResponseError, ( e ):
                print "Detaching volume '%s' from instance '%s' failed. Exception: %s" % ( self.volume_id, self.app.cloud_interface.get_instance_id(), e )
                return False
                
            for counter in range( 30 ):
                log.debug( "Volume '%s' status '%s'" % ( self.volume_id, volumestatus ))
                if volumestatus == 'available':
                    log.debug("Volume '%s' successfully detached from instance '%s'." % ( self.volume_id, self.app.cloud_interface.get_instance_id() ))
                    self.volume = None
                    break
                if counter == 29:
                    log.debug("Volume '%s' FAILED to detach to instance '%s'." % ( self.volume_id, self.app.cloud_interface.get_instance_id() ))
                time.sleep( 3 )
                volumes = self.app.cloud_interface.get_ec2_connection().get_all_volumes( [self.volume_id] )
                volumestatus = volumes[0].status
        else:
            log.warning("Cannot detach volume '%s' in state '%s'" % (self.volume_id, self.status()))
            return False
        return True
    
    def snapshot(self, snap_description=None):
        log.info("Initiating creation of a snapshot for the volume '%s')" % self.volume_id)
        ec2_conn = self.app.cloud_interface.get_ec2_connection()
        snapshot = ec2_conn.create_snapshot(self.volume_id, description="galaxyData: %s" % snap_description)
        if snapshot: 
            while snapshot.status != 'completed':
                log.debug("Snapshot '%s' progress: '%s'; status: '%s'" % (snapshot.id, snapshot.progress, snapshot.status))
                self.snapshot_progress = snapshot.progress
                self.snapshot_status = snapshot.status
                time.sleep(6)
                snapshot.update()
            log.info("Creation of a snapshot for the volume '%s' completed: '%s'" % (self.volume_id, snapshot))
            self.snapshot_progress = None # Reset because of the UI
            self.snapshot_status = None # Reset because of the UI
            return str(snapshot.id)
        else:
            log.error("Could not create snapshot from volume '%s'" % self.volume_id)
            return False
    

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
            self.state = service_states.STARTING
            for vol in self.volumes:
                vol.create(self.name)
                vol.attach()
                self.mount(vol)
                self.status()
        except Exception, e:
            log.error("Error adding service '%s-%s': %s" % (self.svc_type, self.name, e))
            self.status()
    
    def remove(self):
        """ Sequential removal of volumes has issues so thread it"""
        log.info("Removing '%s-%s' data service" % (self.svc_type, self.name))
        self.state = service_states.SHUTTING_DOWN
        r_thread = threading.Thread( target=self.__remove() )
        r_thread.start()
        
    def __remove(self):
        log.debug("Thread-removing '%s-%s' data service" % (self.svc_type, self.name))
        self.state = service_states.SHUTTING_DOWN
        self.unmount()
        log.debug("Unmounted %s" % self.get_full_name())
        for vol in self.volumes:
            log.debug("Detaching %s" % self.get_full_name())
            if vol.detach():
                log.debug("Detached %s" % self.get_full_name())
                if vol.static and self.name != 'galaxyData':
                    log.debug("Deleting %s" % self.get_full_name())
                    vol.delete()
            log.debug("Setting state of %s to %s" % (self.get_full_name(), service_states.SHUT_DOWN))
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
            smaller_vols = []
            # Create a snapshot of detached volume
            for vol in self.volumes:
                smaller_vols.append(vol)
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
            for smaller_vol in smaller_vols:
                smaller_vol.delete()
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
                        break
                    else:
                        time.sleep(4)
                if not run('/bin/mount %s %s' % (volume.get_device(), self.mount_point), "Error mounting file system '%s' from '%s'" % (self.mount_point, volume.get_device()), "Successfully mounted file system '%s' from '%s'" % (self.mount_point, volume.get_device())):
                    # FIXME: Assume if a file system cannot be mounted that it's because there is not a file system on the device so create one
                    if run('/sbin/mkfs.xfs %s' % volume.get_device(), "Failed to create filesystem on device '%s'" % volume.get_device(), "Created filesystem on device '%s'" % volume.get_device()):
                        if run('/bin/mount %s %s' % (volume.get_device(), self.mount_point), "Error mounting file system '%s' from '%s'" % (self.mount_point, volume.get_device()), "Successfully mounted file system '%s' from '%s'" % (self.mount_point, volume.get_device())):
                            try:
                                if self.name == 'galaxyData':
                                    if not os.path.exists('/mnt/galaxyData/files'):
                                        os.mkdir('/mnt/galaxyData/files')
                                    if not os.path.exists('/mnt/galaxyData/tmp'):
                                        os.mkdir('/mnt/galaxyData/tmp')
                                    if not os.path.exists('/mnt/galaxyData/upload_store'):
                                        os.mkdir('/mnt/galaxyData/upload_store')
                            except OSError, e:
                                log.debug("Tried making a galaxyData sub-dir but failed: %s" % e)
                    else:
                        log.error("Failed to mount device '%s' to mount point '%s'" % (volume.get_device(), self.mount_point))
                        return False
                # if self.name == 'galaxyIndices':
                #     run("ln -s %s /mnt/biodata" % self.mount_point, "Failed to create a symlink for galaxyIndices to biodata", "Successfully  created a symlink for galaxyIndices to biodata")
                run('/bin/chown -R galaxy:galaxy %s' % self.mount_point, "Failed to change owner of '%s' to 'galaxy:galaxy'" % self.mount_point, "Changed owner of '%s' to 'galaxy'" % self.mount_point)
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
        for counter in range(10):
            if run('/bin/umount -f %s' % self.mount_point, "Error unmounting file system '%s'" % self.mount_point, "Successfully unmounted file system '%s'" % self.mount_point):
                break
            if counter == 9:
                log.warning("Could not unmount file system at '%s'" % self.mount_point)
                return False
            counter += 1
            time.sleep(3)
        return True
    
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
            mnt_location = commands.getstatusoutput("cat /proc/mounts | grep %s | cut -d' ' -f2" % self.mount_point)
            if mnt_location[0] == 0:
                if mnt_location[1] == self.mount_point:
                    self.state = service_states.RUNNING
                else:
                    log.error("Retrieved mount path '%s' does not match expected path '%s'" % (mnt_location[1], self.mount_point))
                    self.state = service_states.ERROR
            else:
                log.error("File system named '%s' is not mounted. Error code %s" % (self.name, mnt_location[0]))
                self.state = service_states.ERROR
        else:
            log.debug("Did not check status of filesystem '%s' with mount point '%s' in state '%s'" % (self.name, self.mount_point, self.state))
    
    def add_volume(self, vol_id=None, size=None, from_snapshot_id=None):
        self.volumes.append(Volume(self.app, vol_id=vol_id, size=size, from_snapshot_id=from_snapshot_id))
    