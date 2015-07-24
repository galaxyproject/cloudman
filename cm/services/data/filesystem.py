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

from cm.util import misc
from cm.util import Time
from cm.util.misc import run
from cm.util.misc import nice_size
from cm.services import service_states
from cm.services import ServiceRole
from cm.services.data import DataService
from cm.services.data.mountablefs import MountableFS
from cm.services.data.volume import Volume
from cm.services.data.bucket import Bucket
from cm.services.data.transient_storage import TransientStorage
from cm.util.nfs_export import NFSExport

import logging
log = logging.getLogger('cloudman')


class Filesystem(DataService):
    def __init__(self, app, name, svc_roles=[ServiceRole.GENERIC_FS], mount_point=None, persistent=True):
        super(Filesystem, self).__init__(app)
        log.debug("Instantiating Filesystem object {0} with service roles: '{1}'"
                  .format(name, ServiceRole.to_string(svc_roles)))
        self.svc_roles = svc_roles
        # TODO: Introduce a new file system layer that abstracts/consolidates
        # potentially multiple devices under a single file system interface
        # Maybe a class above this class should be introduced, e.g., DataService,
        # that provides the common interface???
        self.volumes = []  # A list of cm.services.data.volume.Volume objects
        self.buckets = []  # A list of cm.services.data.bucket.Bucket objects
        self.transient_storage = []  # Instance's transient storage
        self.nfs_fs = None  # NFS file system object implementing this file system's device
        self.gluster_fs = None  # GlusterFs based file system object implementing this file system's device
        self.name = name  # File system name
        self.persistent = persistent  # Whether it should be part of the cluster config
        self.size = None  # Total size of this file system
        self.size_used = None  # Used size of the this file system
        self.size_pct = None  # Used percentage of this file system
        self.kind = None  # Choice of 'snapshot', 'volume', 'bucket', 'transient', or 'nfs'
        self.mount_point = mount_point if mount_point is not None else os.path.join(
            self.app.path_resolver.mount_root, self.name)
        # Used to indicate a need to grow/expand the file system;
        # This is a composite dict and the implementatin logic depends on the
        # keys so look around carefully (i.e., this should probably be turned
        # into a helper class)
        self.grow = {}
        # A time stamp when the state changed to STARTING; it is used to
        # avoid brief ERROR states during system configuration.
        self.started_starting = datetime.utcnow()

    def __repr__(self):
        return self.get_full_name()

    def get_full_name(self):
        """
        Return a descriptive name of this file system
        """
        return "FS object for {0}".format(self.name)

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
        if self.kind == 'nfs':
            details = self.nfs_fs._get_details(details)
        if self.kind == 'gluster':
            details = self.gluster_fs._get_details(details)
        return details

    def _get_details(self, details):
        """
        Get the general details about this file system, excluding any
        device-specific details. Returns a dictionary.
        """
        details['name'] = self.name
        details['kind'] = str(self.kind).title()
        details['size'] = nice_size(self.size)
        details['size_used'] = nice_size(self.size_used)
        details['size_pct'] = self.size_pct
        details['status'] = self.state
        details['err_msg'] = ""
        details['mount_point'] = self.mount_point
        details['persistent'] = "Yes" if self.persistent else "No"
        return details

    def add(self):
        """
        Add this file system service by adding any devices that compose it
        """
        if self.state == service_states.UNSTARTED or self.state == service_states.SHUT_DOWN:
            try:
                log.debug("Trying to add file system service named '{0}'"
                          .format(self.get_full_name()))
                self.state = service_states.STARTING
                self.last_state_change_time = Time.now()
                self.started_starting = datetime.utcnow()
                if not self.activated:
                    self.activated = True
                    log.debug("Service {0} self-activated".format(self.get_full_name()))
                # TODO: devices must be added to a file system before one can
                # be `added` and thus we know what `kind` a FS is. So, instead of
                # iterating over all devices, just use `self.kind`-based if/else, right?
                # See `nfs` case as an example
                for vol in self.volumes:
                    # Threading has some issues w/ race conditions over device IDs
                    # threading.Thread(target=vol.add).start()
                    vol.add()
                for b in self.buckets:
                    self.kind = 'bucket'
                    threading.Thread(target=b.mount).start()
                    log.debug("Initiated addition of FS from bucket {0}".format(
                        b.bucket_name))
                for ts in self.transient_storage:
                    self.kind = 'transient'
                    ts.add()
                if self.kind == 'nfs':
                    self.nfs_fs.start()
                elif self.kind == 'gluster':
                    self.gluster_fs.start()
            except Exception, e:
                log.error("Error adding file system service {0}: {1}".format(
                    self.get_full_name(), e))
                return False
            self.status()
            log.debug("Done adding devices to {0}. Vols: {1}; buckets: {2}; "
                      "transient: {3}; NFS device: {4}; Gluster devices: {5})"
                      .format(self.get_full_name(), self.volumes, self.buckets,
                              self.transient_storage,
                              self.nfs_fs.device if self.nfs_fs else '-',
                              self.gluster_fs.device if self.gluster_fs else '-'))
            return True
        else:
            log.debug("Data service {0} in {2} state instead of {1} state; cannot add it"
                      .format(self.get_full_name(), service_states.UNSTARTED, self.state))
        return False

    def remove(self, synchronous=False, delete_devices=False):
        """
        Initiate removal of this file system from the system; do it in a
        separate thread and return without waiting for the process to complete.
        If ``delete_devices`` is set, ensure all devices composing this file
        system are deleted in the process of service removal.

        .. warning::

            Setting ``delete_devices`` is irreversible. All data will be
            permanently deleted.

        """
        log.info("Initiating removal of '{0}' data service with: volumes {1}, buckets {2}, "
                 "transient storage {3}, nfs server {4} and gluster fs {5}"
                 .format(self.get_full_name(), self.volumes, self.buckets,
                         self.transient_storage, self.nfs_fs, self.gluster_fs))
        self.state = service_states.SHUTTING_DOWN
        self.last_state_change_time = Time.now()
        r_thread = threading.Thread(target=self.__remove, kwargs={'delete_devices':
                                                                  delete_devices})
        r_thread.start()
        if synchronous:
            r_thread.join()

    def __remove(self, delete_devices=False, remove_from_master=True, detach=True):
        """
        Do the actual removal of devices used to compose this file system.

        Setting ``delete_devices`` will instruct the underlying service to delete
        any of its devices. **Warning**: all data on those devices will be
        permanently deleted. *Note* that for the time being, ``delete_devices`` is
        only propagated to the ``volume`` service/devices.

        After the service is successfully stopped, if ``remove_from_master``
        is set to ``True``, the service is automatically removed
        from the list of services monitored by the master.

        ``detach`` applies to volume-based file systems only and, if set, the
        given volume will be detached in the process of removing the file system.
        Otherwise, it will be left attached (this is useful during snapshot creation).
        """
        super(Filesystem, self).remove(synchronous=True)
        log.debug("Removing all devices from {0}".format(self.get_full_name()))
        self.state = service_states.SHUTTING_DOWN
        self.last_state_change_time = Time.now()
        for vol in self.volumes[:]:
            vol.remove(self.mount_point, delete_vols=delete_devices, detach=detach)
            # Remove the element from the list after the device has been removed
            # This is done so multiple threads do not potentially try removing
            # the same volume twice
            self.volumes.remove(vol)
        for b in self.buckets:
            b.unmount()
        for t in self.transient_storage:
            t.remove()
        if self.nfs_fs:
            self.nfs_fs.stop()
        elif self.gluster_fs:
            self.gluster_fs.stop()
        log.debug("Setting state of %s to '%s'" % (
            self.get_full_name(), service_states.SHUT_DOWN))
        self.state = service_states.SHUT_DOWN
        # Remove self from the list of master's services
        if self.state == service_states.SHUT_DOWN and remove_from_master:
            self.app.manager.deactivate_master_service(self)

    def clean(self):
        """
        Remove this file system and clean up the system as if the file system was
        never there. Useful for CloudMan restarts.
        """
        self.__remove(delete_devices=True)
        # If the service was successfuly removed, remove the mount point
        if self.state == service_states.SHUT_DOWN:
            try:
                if len(os.listdir(self.mount_point)) > 0:
                    shutil.rmtree(self.mount_point)
            except OSError, e:
                log.error("Trouble cleaning directory '%s': %s" %
                          (self.mount_point, e))
        else:
            log.warning("Wanted to clean file system {0} but the service is not in state '{1}'; "
                        "it in state '{2}'").format(self.name, service_states.SHUT_DOWN, self.state)

    def expand(self):
        """
        Expand the size of this file system.

        This process requires the file system to be unmounted during
        the operation, hence all services using the file system must be stopped
        prior to calling this method. Depending on the size of the file system,
        it may take many hours for the expansion process to complete. However,
        this method will only initiate the expandion process by creating a
        snapshot of the underlying file system. A separate process should keep
        checking on the status of the created snapshot. After the snapshot
        reached 'completed' status, the file system the snapshot will need to be
        grown - see ``self.growfs`` method.

        Also note that this method applies only to Volume-based file systems.
        """
        if self.grow:
            log.debug("Starting expansion of {0} file system."
                      .format(self.get_full_name()))
            self.grow['status'] = 'in_progress'
            # Keep track of the Volume objects before removing them
            self.grow['smaller_vol_ids'] = self.volumes[:]
            self.__remove(delete_devices=False, remove_from_master=False)
            self.grow['snap_ids'] = []
            # Create a snapshots of the original volumes
            for vol in self.grow['smaller_vol_ids']:
                snap_id = vol.create_snapshot(self.grow['snap_description'])
                if snap_id:
                    self.grow['snap_ids'].append(snap_id)
                else:
                    log.warning("Did not create a snapshot of vol {0}?!"
                                .format(vol.volume_id))
        else:
            log.debug("Tried to grow '%s' but `self.grow` field is not set." %
                      self.get_full_name())

    def probe_expansion(self):
        """
        Probe the status of the file system expansion process.
        """
        # log.debug("Checking on the expansion status of file system {0}"
        #           .format(self.get_full_name()))
        snap_ids = self.grow.get('snap_ids', [])
        for snap_id in snap_ids:
            ss = self.app.cloud_interface.get_snapshot_status(snap_id)
            if ss == 'completed':
                log.debug("File system {0} snapshot {1} completed."
                          .format(self.get_full_name(), snap_id))
                self.grow['status'] = 'snaps_completed'

    def growfs(self):
        """
        Reinstate this file system and the ``growfs`` command.

        This method should only be called after the ``self.expand`` method
        and after the created snapshots have reached ``completed`` state.
        """
        log.debug("Growing file system {0}".format(self.get_full_name()))
        self.grow['status'] = 'growing'
        # Add new volume objects into this file system based on the created snaps
        for snap_id in self.grow.get('snap_ids', []):
            self.add_volume(size=self.grow.get('new_size', None),
                            from_snapshot_id=snap_id)
        self.add()
        # Grow the file system
        if not run('/usr/sbin/xfs_growfs %s' % self.mount_point, "Error growing file system '%s'"
                   % self.mount_point, "Successfully grew file system '%s'" % self.mount_point):
            return False
        # Delete old, smaller volumes since everything seems to have gone ok
        ec2_conn = self.app.cloud_interface.get_ec2_connection()
        for vol in self.grow.get('smaller_vol_ids', []):
            try:
                ec2_conn.delete_volume(vol.volume_id)
                log.debug("Deleted smaller volume {0} after resizing".format(
                    vol.volume_id))
            except EC2ResponseError, e:
                log.error("Error deleting smaller volume '%s' after resizing: %s"
                          % (vol.volume_id, e))
        # If specified by user, delete the snapshot used during the
        # resizing process
        if self.grow['delete_snap'] is True:
            try:
                for snap_id in self.grow.get('snap_ids', []):
                    ec2_conn.delete_snapshot(snap_id)
                    log.debug("Deleted temporary snapshot {0} created and used during resizing"
                              .format(snap_id))
            except EC2ResponseError, e:
                log.error("Error deleting a snapshot after resizing '%s': %s"
                          % (self.get_full_name(), e))
        self.grow = {}  # Reset the grow flag

    def create_snapshot(self, snap_description=None):
        """
        Create a snapshot of this file system.

        .. note::
            This functionality applies only to file systems based on volumes.
        """
        detach = True
        if self.app.cloud_type == "ec2":
            # On AWS it is possible to snapshot a volume while it's still
            # attached so do that because it's faster
            detach = False
        self.__remove(delete_devices=False, detach=detach)
        snap_ids = []
        # Create a snapshot of the detached volumes
        for vol in self.volumes:
            snap_ids.append(vol.create_snapshot(snap_description=snap_description))
        # After the snapshot has begun, add the file system back as a cluster
        # service
        log.debug("{0} snapshot created; adding self to the list of master "
                  "services.".format(self.get_full_name()))
        self.state = service_states.UNSTARTED  # Need to reset state so it gets picked up by monitor
        self.app.manager.activate_master_service(self)
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
        """
        Run an update on the volume, making sure it exists, it is attached to this
        instance to ``device``. If not, try to update the reference to self.
        """
        # TODO: Abstract filtering into the cloud interface classes
        # log.debug("Checking if a volume is attached to instance {0} on device {1}"
        #           .format(self.app.cloud_interface.get_instance_id(), device))
        if self.app.cloud_type == "ec2":
            # filtering w/ boto is supported only with ec2
            f = {'attachment.device': device, 'attachment.instance-id':
                 self.app.cloud_interface.get_instance_id()}
            vols = self.app.cloud_interface.get_ec2_connection().get_all_volumes(filters=f)
        else:
            vols = []
            all_vols = self.app.cloud_interface.get_ec2_connection().get_all_volumes()
            for vol in all_vols:
                if vol.attach_data.instance_id == self.app.cloud_interface.get_instance_id() and \
                        vol.attach_data.device == device:
                    vols.append(vol)
        # log.debug("Found these volume(s) during a check: '{0}'".format(vols))
        if len(vols) == 1:
            att_vol = vols[0]
            for vol in self.volumes:  # Currently, bc. only 1 vol can be assoc w/ FS, we'll only deal w/ 1 vol
                if (vol is None and att_vol) or (vol and att_vol and vol.volume_id != att_vol.id):
                    log.debug("Discovered a change of vol %s to '%s', attached as device '%s', for FS '%s'"
                              % ([vol.volume_id for vol in self.volumes], att_vol.id, device, self.name))
                    vol.update(att_vol)
                    # If the new volume does not have tags (clusterName &
                    # filesystem), add those
                    if not self.app.cloud_interface.get_tag(att_vol, 'clusterName'):
                        self.app.cloud_interface.add_tag(
                            att_vol, 'clusterName', self.app.config['cluster_name'])
                    if not self.app.cloud_interface.get_tag(att_vol, 'filesystem'):
                        self.app.cloud_interface.add_tag(att_vol, 'filesystem', self.name)
                    self.app.cloud_interface.add_tag(att_vol, 'Name', self.name)
                    # Update cluster configuration (i.e., persistent_data.yaml)
                    # in cluster's bucket
                    self.app.manager.console_monitor.store_cluster_config()
        else:
            log.warning("Did not find a volume attached to instance '%s' as device '%s', file system "
                        "'%s' (vols=%s)" % (self.app.cloud_interface.get_instance_id(),
                                            device, self.name, vols))

    def nfs_share_and_set_state(self, ok_state=service_states.RUNNING,
                                err_state=service_states.ERROR, mount_point=None):
        """
        Share the current file system/mount point over NFS and set the
        state of the file system to `ok_state` if the NFS sharing went OK.
        Otherwise, set the file system state to `err_state`.
        """
        previous_state = self.state
        if not mount_point:
            mount_point = self.mount_point
        log.debug("Exporting FS {0} over NFS".format(mount_point))
        if NFSExport.add_nfs_share(mount_point):
            self.state = ok_state
        else:
            self.state = err_state
        log.debug("Set state for FS {0} to: {1} (was: {2})".format(mount_point,
                  self.state, previous_state))

    def remove_nfs_share(self):
        NFSExport.remove_nfs_share(self.mount_point)

    def _service_transitioning(self):
        """
        A convenience method indicating if the service is in a transitioning state
        (i.e., ``SHUTTING_DOWN, SHUT_DOWN, UNSTARTED, WAITING_FOR_USER_ACTION``).
        If so, return ``True``, else return ``False``.
        """
        if self.state == service_states.SHUTTING_DOWN or \
           self.state == service_states.SHUT_DOWN or \
           self.state == service_states.UNSTARTED or \
           self.state == service_states.WAITING_FOR_USER_ACTION or \
           self.state == service_states.CONFIGURING:
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
        if self.state == service_states.STARTING and \
                (datetime.utcnow() - self.started_starting).seconds < wait_period:
            log.debug("{0} in '{2}' state for {1} seconds"
                      .format(self.get_full_name(),
                              (datetime.utcnow() - self.started_starting).seconds,
                              service_states.STARTING))
            return True
        return False

    def _update_size(self, cmd=None):
        """
        Update local size fields to reflect the current file system usage.
        The optional ``cmd`` can be specified if the process of obtaining the
        file system size differs from the *standard* one. If provided, the output
        from this command must have the following format: *total used percentage*,
        in bytes. For example: ``11524096   2314808   21%``
        """
        if not cmd:
            # Get the size and usage status for this file system in bytes
            cmd = "df --block-size 1 | grep %s$  | awk '{print $2, $3, $5}'" % self.name
        # Extract size & usage
        try:
            disk_usage = commands.getoutput(cmd)
            if disk_usage:
                disk_usage = disk_usage.split(' ')
                if len(disk_usage) == 3:
                    self.size = disk_usage[0]
                    self.size_used = disk_usage[1]
                    self.size_pct = disk_usage[2]
            else:
                log.warning("Empty disk usage for FS '{0}'".format(self.name))
        except Exception, e:
            log.debug("Error updating file system {0} size and usage: {1}".format(
                self.get_full_name(), e))

    def _is_mounted(self, mount_point=None):
        """
        Check if the `mount_point` (or `self.mount_point` if the argument is not
        provided) is mounted. Do so by inspecting `/proc/mounts`.
        """
        if not mount_point:
            mount_point = self.mount_point
        cmd = ("cat /proc/mounts | grep {0}[[:space:]] | cut -d' ' -f2"
               .format(mount_point))
        mnt_location = misc.getoutput(cmd)
        if mnt_location:
            try:
                if mount_point == mnt_location:
                    return True
            except Exception, e:
                log.error("Exception checking if FS {0} is mounted at {1}: {2}"
                          .format(self.name, mount_point, e))
        return False

    def status(self):
        """
        Do a status update for the current file system, checking
        if the file system is mounted to a location based on its name.
        Set state to RUNNING if the file system is accessible, otherwise
        set state to ERROR.
        """
        # log.debug("Updating service '%s-%s' status; current state: %s" \
        #   % (self.name, self.name, self.state))
        NFSExport.reload_nfs_exports()
        # Transient storage file system has its own process for checking status
        if len(self.transient_storage) > 0:
            for ts in self.transient_storage:
                ts.status()
            return
        # Wait for s3fs to install before checking status
        if len(self.buckets) > 0:
            for b in self.buckets:
                if not b.s3fs_installed:
                    return
        # TODO: Move volume-specific checks into volume.py
        if self._service_transitioning():
            pass
        elif self._service_starting():
            pass
        elif self.mount_point is not None:
            mnt_location = commands.getstatusoutput("cat /proc/mounts | grep %s[[:space:]] "
                                                    "| cut -d' ' -f1,2" % self.mount_point)
            if mnt_location[0] == 0 and mnt_location[1] != '':
                try:
                    device, mnt_path = mnt_location[1].split(' ')
                    # Check volume(s) if part of the file system
                    if len(self.volumes) > 0:
                        self.check_and_update_volume(
                            self._get_attach_device_from_device(device))
                    # Check mount point
                    if mnt_path == self.mount_point:
                        self.state = service_states.RUNNING
                        self._update_size()
                    else:
                        log.error("STATUS CHECK [FS %s]: Retrieved mount path '%s' "
                                  "does not match expected path '%s'" %
                                  (self.get_full_name(), mnt_location[1], self.mount_point))
                        self.state = service_states.ERROR
                except Exception, e:
                    log.error("STATUS CHECK: Exception checking status of FS "
                              "'{0}': {1}".format(self.name, e))
                    self.state = service_states.ERROR
                    log.debug(mnt_location)
            else:
                log.error("STATUS CHECK: File system {0} is not mounted at {1}"
                          .format(self.name, self.mount_point))
                self.state = service_states.ERROR
        else:
            log.debug("Did not check status of filesystem '%s' with mount point '%s' in state '%s'"
                      % (self.name, self.mount_point, self.state))

    def add_volume(self, vol_id=None, size=0, from_snapshot_id=None, dot=False, from_archive=None):
        """
        Add a volume device to this file system.

        Each file system is composed of actual devices; otherwise, it's just an
        empty shell/wrapper for what CloudMan considers a file system.
        """
        log.debug("Adding Volume (id={id}, size={size}, snap={snap}) into Filesystem {fs}"
                  .format(id=vol_id, size=size, snap=from_snapshot_id, fs=self.get_full_name()))
        self.volumes.append(Volume(self, vol_id=vol_id, size=size,
                            from_snapshot_id=from_snapshot_id, static=dot, from_archive=from_archive))

    def add_bucket(self, bucket_name, bucket_a_key=None, bucket_s_key=None):
        """
        Add a bucket to this file system.

        Each file system is composed of actual devices; otherwise, it's just an
        empty shell/wrapper for what CloudMan considers a file system.
        """
        log.debug("Adding Bucket (name={name}) into Filesystem {fs}"
                  .format(name=bucket_name, fs=self.get_full_name()))
        self.buckets.append(
            Bucket(self, bucket_name, bucket_a_key, bucket_s_key))

    def add_transient_storage(self, from_archive=None, persistent=False):
        """
        Add instance's transient storage and make it available over NFS to the
        cluster. All this really does is makes a directory under ``/mnt`` and
        exports it over NFS.
        """
        log.debug("Configuring instance transient storage at {0} with NFS.".format(
            self.mount_point))
        self.kind = 'transient'
        self.persistent = True if from_archive else persistent
        self.transient_storage.append(TransientStorage(self, from_archive=from_archive))

    def add_glusterfs(self, gluster_server, mount_options=None):
        """
        Add a Gluster server (e.g., ``172.22.169.17:/gluster_dir``) to mount the file system from
        """
        log.debug("Adding Gluster server {0} to file system {1}".format(gluster_server, self.name))
        self.kind = 'gluster'
        self.gluster_fs = MountableFS(self, 'glusterfs', gluster_server, mount_options=mount_options)

    def add_nfs(self, nfs_server, username=None, pwd=None, mount_options=None):
        """
        Add a NFS server (e.g., ``172.22.169.17:/nfs_dir``) to mount the file system from
        """
        log.debug("Adding NFS server {0} to file system {1}".format(nfs_server, self.name))
        self.kind = 'nfs'
        self.nfs_fs = MountableFS(self, 'nfs', nfs_server, mount_options=mount_options)
