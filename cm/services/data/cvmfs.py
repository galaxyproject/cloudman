"""A file system service for managing CVMFS-based client file systems."""
import os

from cm.services import service_states

import logging
log = logging.getLogger('cloudman')


class CVMFS(object):

    def __init__(self, filesystem, fs_type):
        self.fs = filesystem  # File system encapsulating this implementation
        self.fs_type = fs_type
        self.app = self.fs.app  # A local reference to app (used by @TestFlag)

    def __str__(self):
        return str(self.fs.mount_point)

    def __repr__(self):
        return str(self.fs.mount_point)

    def _get_details(self, details):
        details['DoT'] = "No"
        details['kind'] = self.fs_type
        return details

    def start(self):
        """
        Start the service.

        For the case of CVMFS, just list the file system path.
        """
        os.listdir(self.fs.mount_point)

    def stop(self):
        """Nothing to do for CVMFS."""
        pass

    def status(self):
        """Check if the mount point contains data and mark as running if so."""
        if os.listdir(self.fs.mount_point):
            self.fs.state = service_states.RUNNING
            update_size_cmd = ("df --block-size 1 | grep %s$ | awk "
                               "'{print $2, $3, $5}'" % self.fs.mount_point)
            self.fs._update_size(cmd=update_size_cmd)
        else:
            self.fs.state = service_states.ERROR
