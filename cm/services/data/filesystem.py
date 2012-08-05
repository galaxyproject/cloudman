import commands, os, time, shutil, threading, pwd, grp, subprocess
from datetime import datetime

from boto.exception import EC2ResponseError

from cm.util import paths
from cm.util.misc import run
from cm.util.misc import flock
from cm.services import service_states
from cm.services.data import DataService
from cm.services.data import volume_status
from cm.services.data.volume import Volume
from cm.services.data.bucket import Bucket

import logging
log = logging.getLogger( 'cloudman' )


class Filesystem(DataService):
    def __init__(self, app, name, mount_point=None):
        super(Filesystem, self).__init__(app)
        self.svc_type = "Filesystem"
        self.nfs_lock_file = '/tmp/nfs.lockfile'
        self.volumes = []
        self.buckets = []
        self.name = name
        self.size = None
        self.dirty = False
        self.kind = None # Choice of 'snapshot', 'volume', or 'bucket'
        self.mount_point = mount_point if mount_point is not None else '/mnt/%s' % self.name
        self.grow = None # Used (APPLICABLE ONLY FOR the galaxyData FS) to indicate a need to grow
                         # the file system; use following dict structure:
                         # {'new_size': <size>, 'snap_desc': <snapshot description>}
        self.started_starting = datetime.utcnow() # A time stamp when the state changed to STARTING.
                                                  # It is used to avoid brief ERROR states during
                                                  # the system configuration.
    
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
            self.starter_starting = datetime.utcnow()
            for vol in self.volumes:
                vol.create(self.name)
                # Mark a volume as 'static' if created from a snapshot
                # Note that if a volume is marked as 'static', it is assumed it
                # can be deleted upon cluster termination!
                if self.name != 'galaxyData' and vol.from_snapshot_id is not None:
                    log.debug("Marked volume '%s' from file system '%s' as 'static'" % (vol.volume_id, self.name))
                    vol.static = True
                    self.kind= 'snapshot'
                else:
                    self.kind = 'volume'
                if vol.attach():
                    self.mount(vol)
            for b in self.buckets:
                self.kind = 'bucket'
                threading.Thread(target=b.mount).start()
                log.debug("Initiated addition of FS from bucket {0}".format(b.bucket_name))
        except Exception, e:
            log.error("Error adding filesystem service '%s-%s': %s" % (self.svc_type, self.name, e))
        self.status()
    
    def remove(self):
        """ Sequential removal of volumes has issues so thread it"""
        log.info("Removing '{0}' data service with volumes {1} and buckets {2}"\
            .format(self.get_full_name(), self.volumes, self.buckets))
        self.state = service_states.SHUTTING_DOWN
        r_thread = threading.Thread( target=self.__remove )
        r_thread.start()
    
    def __remove(self, delete_vols=True):
        log.debug("Thread-removing '%s-%s' data service" % (self.svc_type, self.name))
        self.state = service_states.SHUTTING_DOWN
        for vol in self.volumes:
            self.unmount()
            log.debug("Detaching volume '%s' as %s" % (vol.volume_id, self.get_full_name()))
            if vol.detach():
                log.debug("Detached volume '%s' as %s" % (vol.volume_id, self.get_full_name()))
                if vol.static and self.name != 'galaxyData' and delete_vols:
                    log.debug("Deleting %s" % self.get_full_name())
                    vol.delete()
        for b in self.buckets:
            b.unmount()
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
                # Until the underlying issue is fixed (see FIXME below), mask this
                # even more by custom-handling the run command and thus not printing the err
                cmd = '/bin/mount %s %s' % (volume.get_device(), self.mount_point)
                process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                _, _ = process.communicate()
                if process.returncode != 0:
                    # FIXME: Assume if a file system cannot be mounted that it's because
                    # there is not a file system on the device so try creating one
                    if run('/sbin/mkfs.xfs %s' % volume.get_device(), 
                        "Failed to create filesystem on device %s" % volume.get_device(),
                        "Created filesystem on device %s" % volume.get_device()):
                        if not run('/bin/mount %s %s' % (volume.get_device(), self.mount_point),
                            "Error mounting file system %s from %s" % (self.mount_point, volume.get_device()),
                            "Successfully mounted file system %s from %s" % (self.mount_point, volume.get_device())):
                            log.error("Failed to mount device '%s' to mount point '%s'" 
                                % (volume.get_device(), self.mount_point))
                            return False
                else:
                    log.info("Successfully mounted file system {0} from {1}".format(self.mount_point, volume.get_device()))
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
        """ 
        Unmount the file system at the provided or the default mount point.
        If the file system is present in /etc/exports, this method enables
        NFS on the given mount point by uncommenting the respective line in
        this file and indicating that the NFS server should to be restarted).
        """
        if mount_point is not None:
            self.mount_point = mount_point
        try:
            mp = self.mount_point.replace('/', '\/') # Escape slashes for sed
            # Because we're unmounting the file systems in separate threads, use a lock file
            with flock(self.nfs_lock_file):
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
    
    def add_nfs_share(self, mount_point=None, permissions='rw'):
        """ Share the given/current file system/mount point over NFS. Note that
            if the given mount point already exists in /etc/exports, replace
            the existing line with the line composed within this method.
            
            :type mount_point: string
            :param mount_point: The mount point to add to the NFS share
            
            :type permissions: string
            :param permissions: Choose the type of permissions for the hosts
                                mounting this NFS mount point. Use: 'rw' for
                                read-write (default) or 'ro' for read-only
        """
        ee_file = '/etc/exports'
        if mount_point is None:
            mount_point = self.mount_point
        # Compose the line that will be put into /etc/exports
        # NOTE: with Spot instances, should we use 'async' vs. 'sync' option?
        # See: http://linux.die.net/man/5/exports
        ee_line = "{mp}\t*({perms},sync,no_root_squash,no_subtree_check)\n"\
            .format(mp=mount_point, perms=permissions)
        # Determine if the given mount point is already shared
        with open(ee_file) as f:
            shared_paths = f.readlines()
        in_ee = -1
        for i, sp in enumerate(shared_paths):
            if mount_point in sp:
                in_ee = i
        # If the mount point is already in /etc/exports, replace the existing
        # entry with the newly composed ee_line (thus supporting change of 
        # permissions). Otherwise, append ee_line to the end of the file.
        if in_ee > -1:
            shared_paths[in_ee] = ee_line
        else:
            shared_paths.append(ee_line)
        # Write out the newly composed file
        with open(ee_file, 'w') as f:
            f.writelines(shared_paths)
        # Mark the NFS server as being in need of a restart
        self.dirty=True
    
    def status(self):
        """
        Do a status update for the current file system, checking
        if the file system is mounted to a location based on its name.
        Set state to RUNNING if the file system is accessible, otherwise
        set state to ERROR.
        """
        # log.debug("Updating service '%s-%s' status; current state: %s" \
        #   % (self.svc_type, self.name, self.state))
        if self.dirty:
            # First check if the NFS server needs to be restarted but do it one thread at a time
            with flock(self.nfs_lock_file):
                if run("/etc/init.d/nfs-kernel-server restart", "Error restarting NFS server", \
                    "As part of %s filesystem update, successfully restarted NFS server" \
                    % self.name):
                    self.dirty = False
        if self.state==service_states.SHUTTING_DOWN or \
           self.state==service_states.SHUT_DOWN or \
           self.state==service_states.UNSTARTED or \
           self.state==service_states.WAITING_FOR_USER_ACTION:
            pass
        elif self.state==service_states.STARTING and \
           (datetime.utcnow() - self.started_starting).seconds < 30:
            log.debug("{0} in '{2}' state for {1} seconds".format(self.get_full_name(),
                (datetime.utcnow() - self.started_starting).seconds, service_states.STARTING))
            # Allow a service to remain in STARTING state for some time
            # before actually checking its status - this helps avoid
            # brief ERROR states due to services not yet being configured
            pass
        elif self.mount_point is not None:
            mnt_location = commands.getstatusoutput("cat /proc/mounts | grep %s | cut -d' ' -f1,2" \
                % self.mount_point)
            if mnt_location[0] == 0 and mnt_location[1] != '':
                try:
                    device, mnt_path = mnt_location[1].split(' ')
                    # Check volume(s) if part of the file system
                    if len(self.volumes) > 0:
                        self.check_and_update_volume(self._get_attach_device_from_device(device))
                    # Check mount point
                    if mnt_path == self.mount_point:
                        self.state = service_states.RUNNING
                    else:
                        log.error("STATUS CHECK: Retrieved mount path '%s' does not match "
                            "expected path '%s'" % (mnt_location[1], self.mount_point))
                        self.state = service_states.ERROR
                except Exception, e:
                    log.error("STATUS CHECK: Exception checking status of FS '%s': %s" % (self.name, e))
                    self.state = service_states.ERROR
                    log.debug(mnt_location)
            else:
                log.error("STATUS CHECK: File system named '%s' is not mounted. Error code %s" \
                    % (self.name, mnt_location[0]))
                self.state = service_states.ERROR
        else:
            log.debug("Did not check status of filesystem '%s' with mount point '%s' in state '%s'" \
                % (self.name, self.mount_point, self.state))
    
    def add_volume(self, vol_id=None, size=0, from_snapshot_id=None):
        log.debug("Adding Volume (id={id}, size={size}, snap={snap}) into Filesystem {fs}"\
            .format(id=vol_id, size=size, snap=from_snapshot_id, fs=self.get_full_name()))
        self.volumes.append(Volume(self, vol_id=vol_id, size=size, from_snapshot_id=from_snapshot_id))
    
    def add_bucket(self, bucket_name, bucket_a_key=None, bucket_s_key=None):
        log.debug("Adding Bucket (name={name}) into Filesystem {fs}"\
            .format(name=bucket_name, fs=self.get_full_name()))
        self.buckets.append(Bucket(self, bucket_name, bucket_a_key, bucket_s_key))
    
