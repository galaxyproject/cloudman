from cm.util.misc import run
from cm.util.misc import flock
import shlex
import logging
log = logging.getLogger('cloudman')


class NFSExport:

    nfs_lock_file = '/tmp/nfs.lockfile'
    nfs_dirty = False

    @staticmethod
    def add_nfs_share(mount_point, permissions='rw'):
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
            if not mount_point:
                raise Exception("add_nfs_share: No mount point provided")
            # Compose the line that will be put into /etc/exports
            # NOTE: with Spot instances, should we use 'async' vs. 'sync' option?
            # See: http://linux.die.net/man/5/exports
            ee_line = "{mp}\t*({perms},sync,no_root_squash,no_subtree_check)\n"\
                .format(mp=mount_point, perms=permissions)
            # Make sure we manipulate ee_file by a single process at a time
            with flock(NFSExport.nfs_lock_file):
                # Determine if the given mount point is already shared
                with open(ee_file) as f:
                    shared_paths = f.readlines()
                in_ee = -1
                for i, sp in enumerate(shared_paths):
                    tokens = shlex.split(sp)
                    if tokens and mount_point in tokens[0]:
                        in_ee = i

                # If the mount point is already in /etc/exports, replace the existing
                # entry with the newly composed ee_line (thus supporting change of
                # permissions). Otherwise, append ee_line to the end of the
                # file.
                if in_ee > -1:
                    shared_paths[in_ee] = ee_line
                else:
                    shared_paths.append(ee_line)
                # Write out the newly composed file
                with open(ee_file, 'w') as f:
                    f.writelines(shared_paths)
                log.debug("Added '{0}' line to NFS file {1}".format(
                    ee_line.strip(), ee_file))
            # Mark the NFS server as being in need of a restart
            NFSExport.nfs_dirty = True
            return True
        except Exception, e:
            log.error(
                "Error configuring {0} file for NFS: {1}".format(ee_file, e))
            return False

    @staticmethod
    def remove_nfs_share(mount_point):
        """
        Remove the given/current file system/mount point from being shared
        over NFS. The method removes the file system's ``mount_point`` from
        ``/etc/share`` and indicates that the NFS server needs restarting.
        """
        try:
            ee_file = '/etc/exports'
            if not mount_point:
                raise Exception("remove_nfs_share: No mount point provided")
            mount_point = mount_point.replace(
                '/', '\/')  # Escape slashes for sed
            cmd = "sed -i '/^{0}/d' {1}".format(mount_point, ee_file)
            log.debug("Removing NSF share for mount point {0}; cmd: {1}".format(
                mount_point, cmd))
            # To avoid race conditions between threads, use a lock file
            with flock(NFSExport.nfs_lock_file):
                run(cmd)
            NFSExport.nfs_dirty = True
            return True
        except Exception, e:
            log.error("Error removing FS {0} share from NFS: {1}".format(
                mount_point, e))
            return False

    @staticmethod
    def reload_nfs_exports():
        with flock(NFSExport.nfs_lock_file):
            if run("/etc/init.d/nfs-kernel-server restart", "Error restarting NFS server",
                    "Successfully restarted NFS server"):
                NFSExport.nfs_dirty = False

    @staticmethod
    def reload_exports_if_required():
        if NFSExport.nfs_dirty:
            NFSExport.reload_nfs_exports()
