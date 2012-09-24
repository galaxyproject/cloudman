"""
A core class for what CloudMan sees as a file system. This means that it is
aware of it and can thus manipulate it.
"""
import os
import shutil
import commands
import threading
from datetime import datetime

from boto.exception import EC2ResponseError

from cm.util.misc import run
from cm.util.misc import flock
from cm.services import service_states
from cm.services.data import DataService
from cm.services.data.volume import Volume
from cm.services.data.bucket import Bucket
from cm.services.data.transient_storage import TransientStorage

import logging
log = logging.getLogger('cloudman')


class Filesystem(DataService):
    def __init__(self, app, name, mount_point=None):
        super(Filesystem, self).__init__(app)
        self.svc_type = "Filesystem"
        self.nfs_lock_file = '/tmp/nfs.lockfile'
        # TODO: Introduce a new file system layer that abstracts/consolidates
        # potentially multiple devices under a single file system interface
        # Maybe a class above this class should be introduced, e.g., DataService,
        # that provides the common interface???
        self.volumes = [] # A list of cm.services.data.volume.Volume objects
        self.buckets = [] # A list of cm.services.data.bucket.Bucket objects
        self.transient_storage = [] # Instance's transient storage
        self.name = name  # File system name
        self.size = None      # Total size of this file system
        self.size_used = None # Used size of the this file system
        self.size_pct = None  # Used percentage of this file system
        self.dirty = False
        self.kind = None # Choice of 'snapshot', 'volume', 'bucket', or 'transient'
        self.mount_point = mount_point if mount_point is not None else '/mnt/%s' % self.name
        self.grow = None # Used (APPLICABLE ONLY FOR the galaxyData FS) to indicate a need to grow
                         # the file system; use following dict structure:
                         # {'new_size': <size>, 'snap_desc': <snapshot description>}
        self.started_starting = datetime.utcnow() # A time stamp when the state changed to STARTING.
                                                  # It is used to avoid brief ERROR states during
                                                  # the system configuration.

    def get_full_name(self):
        """
        Return a descriptive name of this file system
        """
        return "FS-%s" % self.name

    def get_details(self):
        """
        Return a dictionary with the details describing the details of this file system.
        """
        details = {}
        details = self._get_details(details)
        # Uff... This is not scalable and, depending on the context, questionably
        # functionally correct...
        for vol in self.volumes:
            details = vol._get_details(details)
        for b in self.buckets:
            details = b._get_details(details)
        for ts in self.transient_storage:
            details = ts._get_details(details)
        return details

    def _get_details(self, details):
        """
        Get details about this file system, excluding any device-specific details
        """
        details['name']     = self.name
        details['kind']     = str(self.kind).title()
        details['size']     = self.size
        details['size_used']= self.size_used
        details['size_pct'] = self.size_pct
        details['status']   = self.state
        details['err_msg']  = ""
        details['mount_point'] = self.mount_point
        return details

    def get_size(self):
        """
        Get the total size of this file system across all of its devices
        """
        new_size = 0
        for volume in self.volumes:
            new_size += volume.size
        # TODO: get FS size used by bucket(s)
        self.size = new_size
        return self.size

    def add(self):
        """
        Add this file system service by adding any devices that compose it
        """
        if self.state == service_states.UNSTARTED:
            try:
                log.debug("Trying to add file system service {0}".format(self.get_full_name()))
                self.state = service_states.STARTING
                self.started_starting = datetime.utcnow()
                for vol in self.volumes:
                    # Threading has some issues w/ race conditions over device IDs
                    # threading.Thread(target=vol.add).start()
                    vol.add()
                for b in self.buckets:
                    self.kind = 'bucket'
                    threading.Thread(target=b.mount).start()
                    log.debug("Initiated addition of FS from bucket {0}".format(b.bucket_name))
                for ts in self.transient_storage:
                    self.kind = 'transient'
                    ts.add()
            except Exception, e:
                log.error("Error adding file system service {0}: {1}".format(self.get_full_name(), e))
            self.status()
        else:
            log.debug("Data service {0} in {2} state instead of {1} state; cannot add it"\
                    .format(self.get_full_name(), service_states.UNSTARTED, self.state))

    def remove(self):
        """
        Initiate removal of this file system from the system
        """
        log.info("Initiating removal of '{0}' data service with: volumes {1}, buckets {2}, and "\
                "transient storage {3}".format(self.get_full_name(), self.volumes, self.buckets,
                    self.transient_storage))
        self.state = service_states.SHUTTING_DOWN
        r_thread = threading.Thread( target=self.__remove )
        r_thread.start()

    def __remove(self, delete_vols=True):
        """
        Do the actual removal of devices used to compose this file system
        """
        log.debug("Removing {0} devices".format(self.get_full_name()))
        self.state = service_states.SHUTTING_DOWN
        for vol in self.volumes:
            vol.remove(self.mount_point, delete_vols)
        for b in self.buckets:
            b.unmount()
        for t in self.transient_storage:
            t.remove()
        log.debug("Setting state of %s to '%s'" % (self.get_full_name(), service_states.SHUT_DOWN))
        self.state = service_states.SHUT_DOWN
        # Remove self from the list of master's services
        if self.state == service_states.SHUT_DOWN:
            self.app.manager.services.remove(self)

    def clean(self):
        """
        Remove this file system and clean up the system as if the file system was
        never there. Useful for CloudMan restarts.
        """
        self.__remove()
        # If the service was successfuly removed, remove the mount point
        if self.state == service_states.SHUT_DOWN:
            try:
                if len(os.listdir(self.mount_point)) > 0:
                    shutil.rmtree(self.mount_point)
            except OSError, e:
                log.error("Trouble cleaning directory '%s': %s" % (self.mount_point, e))
        else:
            log.warning("Wanted to clean file system {0} but the service is not in state '{1}'; "\
                    "it in state '{2}'").format(self.name, service_states.SHUT_DOWN, self.state)

    def expand(self):
        """
        Exapnd the size of this file system. Note that this process requires
        the file system to be unmounted during the operation and the new one
        will be automatically remounted upon completion of the process.

        Also note that this method applies only to Volume-based file systems.
        """
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
            if not run('/usr/sbin/xfs_growfs %s' % self.mount_point, "Error growing file system '%s'"
                    % self.mount_point, "Successfully grew file system '%s'" % self.mount_point):
                return False
            # Delete old, smaller volumes since everything seems to have gone ok
            ec2_conn = self.app.cloud_interface.get_ec2_connection()
            for smaller_vol_id in smaller_vol_ids:
                try:
                    ec2_conn.delete_volume(smaller_vol_id)
                except EC2ResponseError, e:
                    log.error("Error deleting old data volume '%s' during '%s' resizing: %s"
                            % (smaller_vol_id, self.get_full_name(), e))
            # If desired by user, delete snapshot used during the resizing process
            if self.grow['delete_snap'] is True:
                try:
                    ec2_conn = self.app.cloud_interface.get_ec2_connection()
                    ec2_conn.delete_snapshot(snap_id)
                except EC2ResponseError, e:
                    log.error("Error deleting snapshot '%s' during '%s' resizing: %s"
                            % (snap_id, self.get_full_name(), e))
            self.grow = None # Reset flag
            return True
        else:
            log.debug("Tried to grow '%s' but grow flag is None" % self.get_full_name())
            return False

    def snapshot(self, snap_description=None):
        """
        Create a snapshot of this file system. **Note** that this only applies to
        file systems based on volumes.
        """
        self.__remove(delete_vols=False)
        snap_ids = []
        # Create a snapshot of the detached volumes
        for vol in self.volumes:
            snap_ids.append(vol.snapshot(snap_description=snap_description))
        # After the snapshot is done, add the file system back as a cluster service
        self.add()
        return snap_ids

    def _get_attach_device_from_device(self, device):
        """
        Get the device a volume is attached as from the volume itself (i.e.,
        double check that the ``device`` we have locally is the ``device`` the
        cloud middleware sees as well).
        If the devices do not match, return ``None``.
        """
        for vol in self.volumes:
            if device == vol.device:
                # This is limited to file systems composed from 1 volume only
                return vol.attach_device
        return None

    def check_and_update_volume(self, device):
        f = {'attachment.device': device, 'attachment.instance-id': self.app.cloud_interface.get_instance_id()}
        vols = self.app.cloud_interface.get_all_volumes(filters=f)
        if len(vols) == 1:
            att_vol = vols[0]
            for vol in self.volumes: # Currently, bc. only 1 vol can be assoc w/ FS, we'll only deal w/ 1 vol
                if (vol is None and att_vol) or (vol and att_vol and vol.volume_id != att_vol.id):
                    log.debug("Discovered a change of vol %s to '%s', attached as device '%s', for FS '%s'" \
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
            log.warning("Did not find a volume attached to instance '%s' as device '%s', file system "\
                    "'%s' (vols=%s)" % (self.app.cloud_interface.get_instance_id(), device, self.name, vols))

    def add_nfs_share(self, mount_point=None, permissions='rw'):
        """
        Share the given/current file system/mount point over NFS. Note that
        if the given mount point already exists in /etc/exports, replace
        the existing line with the line composed within this method.

        :type mount_point: string
        :param mount_point: The mount point to add to the NFS share

        :type permissions: string
        :param permissions: Choose the type of permissions for the hosts
                            mounting this NFS mount point. Use: 'rw' for
                            read-write (default) or 'ro' for read-only
        """
        try:
            ee_file = '/etc/exports'
            if mount_point is None:
                mount_point = self.mount_point
            # Compose the line that will be put into /etc/exports
            # NOTE: with Spot instances, should we use 'async' vs. 'sync' option?
            # See: http://linux.die.net/man/5/exports
            ee_line = "{mp}\t*({perms},sync,no_root_squash,no_subtree_check)\n"\
                .format(mp=mount_point, perms=permissions)
            # Make sure we manipulate ee_file by a single process at a time
            with flock(self.nfs_lock_file):
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
                log.debug("Added '{0}' line to NFS file {1}".format(ee_line.strip(), ee_file))
            # Mark the NFS server as being in need of a restart
            self.dirty=True
            return True
        except Exception, e:
            log.error("Error configuring {0} file for NFS: {1}".format(ee_file, e))
            return False

    def remove_nfs_share(self, mount_point=None):
        """
        Remove the given/current file system/mount point from being shared
        over NFS. The method removes the file system's ``mount_point`` from
        ``/etc/share`` and indcates that the NFS server needs restarting.
        """
        try:
            ee_file = '/etc/exports'
            if mount_point is None:
                mount_point = self.mount_point
            mount_point = mount_point.replace('/', '\/') # Escape slashes for sed
            cmd = "sed -i '/^{0}/d' {1}".format(mount_point, ee_file)
            log.debug("Removing NSF share for mount point {0}; cmd: {1}".format(mount_point, cmd))
            # To avoid race conditions between threads, use a lock file
            with flock(self.nfs_lock_file):
                run(cmd)
            self.dirty = True
            return True
        except Exception, e:
            log.error("Error removing FS {0} share from NFS: {1}".format(mount_point, e))
            return False

    def _service_transitioning(self):
        """
        A convenience method indicating if the service is in a transitioning state
        (i.e., ``SHUTTING_DOWN, SHUT_DOWN, UNSTARTED, WAITING_FOR_USER_ACTION``).
        If so, return ``True``, else return ``False``.
        """
        if self.state==service_states.SHUTTING_DOWN or \
           self.state==service_states.SHUT_DOWN or \
           self.state==service_states.UNSTARTED or \
           self.state==service_states.WAITING_FOR_USER_ACTION:
               return True
        return False

    def _service_starting(self, wait_period=30):
        """
        A convenience method that checks if a service has been in ``STARTING``
        state too long. ``wait_period`` indicates how many seconds that period is.
        So, if a service is in ``STARTING`` state and has been there for less then
        the ``waiting_period``, the method returns ``True`` (i.e., the service IS
        starting). If the service is in not in ``STARTING`` state or it's been in
        that state for longer than the ``wait_period``, return ``False``.

        Basically, this method allows a service to remain in ``STARTING`` state
        for some time before actually checking its status - this helps avoid
        brief ``ERROR`` states due to a service not yet been configured.
        """
        if self.state==service_states.STARTING and \
               (datetime.utcnow()-self.started_starting).seconds < wait_period:
            log.debug("{0} in '{2}' state for {1} seconds".format(self.get_full_name(),
                (datetime.utcnow() - self.started_starting).seconds, service_states.STARTING))
            return True
        return False

    def _update_size(self, cmd=None):
        """
        Update local size fields to reflect the current file system usage.
        The optional ``cmd`` can be specified if the process of obtaining the
        file system size differe from the *standard* one. If provided, the output
        from this command must have the following format: *total used percentage*
        For example: ``335G 199M 1%``
        """
        if not cmd:
            cmd = "df -h | grep %s | awk '{print $2, $3, $5}'" % self.name
        # Get size & usage
        try:
            disk_usage = commands.getoutput(cmd)
            disk_usage = disk_usage.split(' ')
            if len(disk_usage) == 3:
                self.size = disk_usage[0] # or should this the device size?
                self.size_used = disk_usage[1]
                self.size_pct = disk_usage[2]
        except Exception, e:
            log.debug("Error updating file system {0} size and usage: {1}".format(self.get_full_name(), e))

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
        # Transient storage file system has its own process for checking status
        if len(self.transient_storage) > 0:
            for ts in self.transient_storage:
                ts.status()
            return
        # TODO: Move volume-specific checks into volume.py
        if self._service_transitioning():
            pass
        elif self._service_starting():
            pass
        elif self.mount_point is not None:
            mnt_location = commands.getstatusoutput("cat /proc/mounts | grep %s | cut -d' ' -f1,2" \
                % self.mount_point)
            if mnt_location[0] == 0 and mnt_location[1] != '':
                try:
                    device, mnt_path = mnt_location[1].split(' ')
                    # Check volume(s) if part of the file system (but because boto
                    # filtering works only on ec2, for now, do this check only on ec2)
                    if len(self.volumes) > 0:
                        self.check_and_update_volume(self._get_attach_device_from_device(device))
                    # Check mount point
                    if mnt_path == self.mount_point:
                        self.state = service_states.RUNNING
                        self._update_size()
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
        """
        Add a volume device to this file system.

        Each file system is composed of actual devices; otherwise, it's just an
        empty shell/wrapper for what CloudMan considers a file system.
        """
        log.debug("Adding Volume (id={id}, size={size}, snap={snap}) into Filesystem {fs}"\
            .format(id=vol_id, size=size, snap=from_snapshot_id, fs=self.get_full_name()))
        self.volumes.append(Volume(self, vol_id=vol_id, size=size, from_snapshot_id=from_snapshot_id))

    def add_bucket(self, bucket_name, bucket_a_key=None, bucket_s_key=None):
        """
        Add a bucket to this file system.

        Each file system is composed of actual devices; otherwise, it's just an
        empty shell/wrapper for what CloudMan considers a file system.
        """
        log.debug("Adding Bucket (name={name}) into Filesystem {fs}"\
            .format(name=bucket_name, fs=self.get_full_name()))
        self.buckets.append(Bucket(self, bucket_name, bucket_a_key, bucket_s_key))

    def add_transient_storage(self):
        """
        Add instance's transient storage and make it available over NFS to the
        cluster. All this really does is makes a directory under ``/mnt`` and
        exports it over NFS.
        """
        log.debug("Configuring instance transient storage at {0} with NFS.".format(self.mount_point))
        self.transient_storage.append(TransientStorage(self))

