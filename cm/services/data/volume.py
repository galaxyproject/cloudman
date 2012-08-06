import re
import time
import commands

from boto.exception import EC2ResponseError

from cm.framework import messages
from cm.services.data import BlockStorage
from cm.services.data import volume_status

import logging
log = logging.getLogger('cloudman')


class Volume(BlockStorage):
    
    def __init__(self, filesystem, vol_id=None, device=None, attach_device=None,
                 size=0, from_snapshot_id=None, static=False):
        super(Volume, self).__init__(filesystem.app)
        self.fs = filesystem
        self.app = self.fs.app
        self.volume = None # boto instance object representing the current volume
        self.volume_id = vol_id
        self.device = device # Device ID visible by the operating system
        self.attach_device = attach_device # Device ID visible/reported by cloud
                                           # provider as the device attach point
        self.size = size
        self.from_snapshot_id = from_snapshot_id
        self.device = None
        self.static = static # Indicates if a volume is created from a snapshot
                             # AND can be deleted upon cluster termination
        self.snapshot_progress = None
        self.snapshot_status = None
    
    def __str__(self):
        return str(self.volume_id)
    
    def __repr__(self):
        if self.volume_id is not None:
            return self.get_full_name()
        else:
            return "No volume ID yet; {0} ({1})".format(self.from_snapshot_id, self.fs.get_full_name())
    
    def get_full_name(self):
        return "{vol} ({fs})".format(vol=self.volume_id, fs=self.fs.get_full_name())
    
    def update(self, bsd):
        """ Update reference to the 'self' to point to argument 'bsd' """
        log.debug("Updating current volume reference '%s' to a new one '%s'" % (self.volume_id, bsd.id))
        self.volume = bsd
        self.volume_id = bsd.id
        self.device = bsd.attach_data.device
        self.size = bsd.size
        self.from_snapshot_id = bsd.snapshot_id
    
    def status(self):
        if self.volume_id is None:
            return volume_status.NONE
        else:
            ec2_conn = self.app.cloud_interface.get_ec2_connection()
            if ec2_conn:
                try:
                    self.volume = ec2_conn.get_all_volumes([self.volume_id])[0]
                except EC2ResponseError, e:
                    log.error("Cannot retrieve reference to volume '%s'; "
                        "setting volume id to None. Error: %s" % (self.volume_id, e))
                    self.volume_id = None
                    return volume_status.NONE
                self.from_snapshot_id = self.volume.snapshot_id
                self.size = self.volume.size
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
            log.debug("No devices found attached to %s#, defaulting current volume device "
                "to %s1 and attach device to %s1" % (mount_base, mount_base, attach_base))
            self.device = '%s1' % mount_base
            self.attach_device = '%s1' % attach_base
        log.debug("Running on kernel version %s; set volume device as '%s' and attach "
            "device as '%s'" % (kernel_out[1], self.device, self.attach_device))
        return True
    
    def create(self, filesystem=None):
        if self.status() == volume_status.NONE:
            try:
                log.debug("Creating a new volume of size '%s' in zone '%s' from snapshot '%s'" \
                    % (self.size, self.app.cloud_interface.get_zone(), self.from_snapshot_id))
                if self.size > 0:
                    self.volume = self.app.cloud_interface.get_ec2_connection().create_volume(self.size,
                        self.app.cloud_interface.get_zone(), snapshot=self.from_snapshot_id)
                    self.volume_id = str(self.volume.id)
                    self.size = int(self.volume.size)
                    log.debug("Created new volume of size '%s' from snapshot '%s' with ID '%s' in zone '%s'" \
                        % (self.size, self.from_snapshot_id, self.get_full_name(), \
                        self.app.cloud_interface.get_zone()))
                else:
                    log.warning("Cannot create volume of size 0! Volume not created.")
            except EC2ResponseError, e:
                log.error("Error creating volume: %s" % e)
        else:
            log.debug("Tried to create a volume but it is in state '%s' (volume ID: %s)" \
                % (self.status(), self.get_full_name()))
        
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
            self.app.cloud_interface.get_ec2_connection().delete_volume(self.volume_id)
            log.debug("Deleted volume '%s'" % self.volume_id)
            self.volume_id = None
            self.volume = None
        except EC2ResponseError, e:
            log.error("Error deleting volume '%s' - you should delete it manually after "
                "the cluster has shut down: %s" % (self.volume_id, e))
    
    def do_attach(self, attach_device):
        try:
            if attach_device is not None:
                log.debug("Attaching volume '%s' to instance '%s' as device '%s'" 
                    % (self.get_full_name(),  self.app.cloud_interface.get_instance_id(), attach_device))
                volumestatus = self.app.cloud_interface.get_ec2_connection() \
                    .attach_volume(self.volume_id, self.app.cloud_interface.get_instance_id(), attach_device)
            else:
                log.error("Attaching volume '%s' to instance '%s' failed because could not determine device."
                    % (self.get_full_name(),  self.app.cloud_interface.get_instance_id()))
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
                    log.debug("Attaching volume '%s'; status: %s (check %s/%s)" \
                        % (self.get_full_name(), volumestatus, ctn, attempts))
                    if volumestatus == 'attached':
                        log.debug("Volume '%s' attached to instance '%s' as device '%s'" \
                            % (self.volume_id, self.app.cloud_interface.get_instance_id(), 
                            self.get_attach_device()))
                        break
                    if ctn == attempts-1:
                        log.debug("Volume '%s' FAILED to attach to instance '%s' as device '%s'." \
                            % (self.get_full_name(), self.app.cloud_interface.get_instance_id(), 
                            self.get_attach_device()))
                        if attempts < 90:
                            log.debug("Will try another device")
                            attempts += 30 # Increment attempts for another try
                            if self.detach():
                                # Offset device num by number of attempts
                                attach_device = self.get_attach_device(offset=attempts/30-1)
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
                # Check if the volume is already attached to current instance
                # (this can happen following a reboot/crash)
                if self.volume.attach_data.instance_id == self.app.cloud_interface.get_instance_id():
                    self.attach_device = self.volume.attach_data.device
                    log.debug("Tried to attach a volume but the volume '%s' is already "
                        "attached (as device %s)" % (self.get_full_name(), self.get_attach_device()))
                    return True
            elif self.volume_id is None:
                log.error("Wanted to attach a volume but missing volume ID; cannot attach")
                return False
            if counter == 29:
                log.warning("Cannot attach volume '%s' in state '%s'" % (self.volume_id, self.status()))
                return False
            log.debug("Wanting to attach volume '%s' but it's not 'available' yet (current state: '%s'). "
                "Waiting (%s/30)." % (self.volume_id, self.status(), counter))
            time.sleep( 2 )
    
    def detach(self):
        """
        Detach EBS volume from an instance.
        Try it for some time.
        """
        if self.status() == volume_status.ATTACHED or self.status() == volume_status.IN_USE:
            try:
                volumestatus = self.app.cloud_interface.get_ec2_connection()\
                    .detach_volume( self.volume_id, self.app.cloud_interface.get_instance_id())
            except EC2ResponseError, e:
                log.error("Detaching volume '%s' from instance '%s' failed. Exception: %s" \
                    % (self.get_full_name(), self.app.cloud_interface.get_instance_id(), e))
                return False
                
            for counter in range(30):
                log.debug("Detaching volume '%s'; status '%s' (check %s/30)" \
                    % (self.get_full_name(), volumestatus, counter))
                if volumestatus == 'available':
                    log.debug("Volume '%s' successfully detached from instance '%s'." \
                        % ( self.get_full_name(), self.app.cloud_interface.get_instance_id() ))
                    self.volume = None
                    break
                if counter == 28:
                    try:
                        volumestatus = self.app.cloud_interface.get_ec2_connection()\
                            .detach_volume(self.volume_id, self.app.cloud_interface.get_instance_id(), 
                            force=True)
                    except EC2ResponseError, e:
                        log.error("Second attempt at detaching volume '%s' from instance '%s' failed. "
                            "Exception: %s" % (self.get_full_name(), self.app.cloud_interface.get_instance_id(), e))
                        return False
                if counter == 29:
                    log.debug("Volume '%s' FAILED to detach from instance '%s'" \
                        % ( self.get_full_name(), self.app.cloud_interface.get_instance_id() ))
                    return False
                time.sleep(6)
                volumes = self.app.cloud_interface.get_ec2_connection().get_all_volumes( [self.volume_id] )
                volumestatus = volumes[0].status
        else:
            log.warning("Cannot detach volume '%s' in state '%s'" % (self.get_full_name(), self.status()))
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
        self.status()
        return self.from_snapshot_id
    

