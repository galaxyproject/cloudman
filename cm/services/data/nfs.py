"""
An implementation of the NFS-based file system service capable of managing
interactions with a remote NFS server and making it available locally as a
file system.
"""
import os
import time
import subprocess

from cm.util.misc import run
from cm.services import service_states

import logging
log = logging.getLogger('cloudman')


class NfsFS(object):
    def __init__(self, filesystem, nfs_server, username=None, pwd=None):
        self.fs = filesystem  # File system encapsulating this implementation
        self.app = self.fs.app  # A local reference to app (used by @TestFlag)
        self.nfs_server = nfs_server
        self.server_username = username
        self.server_pwd = pwd

    def __str__(self):
        return str(self.nfs_server)

    def __repr__(self):
        return str(self.nfs_server)

    def _get_details(self, details):
        details['nfs_server'] = self.nfs_server
        details['DoT'] = "No"
        details['kind'] = 'External NFS'
        return details

    def start(self):
        """
        Start NfsFS service.
        Satisfy any preconditions and try to mount ``self.nfs_server`` locally at
        ``self.fs.mount_point``
        """
        if not os.path.exists(self.fs.mount_point):
            os.makedirs(self.fs.mount_point)
        self.mount()

    def stop(self):
        """
        Stop NfsFS service and cleanup the ``self.fs.mount_point`` directory.
        """
        if self.unmount():
            # Clean up the system path now that the file system is unmounted
            try:
                os.rmdir(self.fs.mount_point)
            except OSError, e:
                log.error("Error removing unmounted path {0}: {1}".format(
                    self.fs.mount_point, e))

    def mount(self):
        """
        Do the actual mounting of the remote NFS file system locally.
        """
        log.debug("Mounting NFS FS {0} from {1}".format(self.fs.mount_point, self.nfs_server))
        cmd = '/bin/mount -t nfs {0} {1}'.format(self.nfs_server, self.fs.mount_point)
        process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        _, _ = process.communicate()
        if process.returncode != 0:
            log.error("Trouble mounting file system at {0} from NFS server {1}"
                .format(self.fs.mount_point, self.nfs_server))
        else:
            log.info("Successfully mounted file system at {0} from {1}"
                .format(self.fs.mount_point, self.nfs_server))

    def unmount(self):
        """
        Do the actual unmounting of this file system.
        """
        log.debug("Unmounting NFS-based FS from {0}".format(self.fs.mount_point))
        for counter in range(10):
            if (self.fs.state == service_states.RUNNING and
                run('/bin/umount %s' % self.fs.mount_point)):
                break
            if counter == 9:
                log.warning("Could not unmount file system at '%s'" % self.fs.mount_point)
                return False
            counter += 1
            time.sleep(3)
        return True
