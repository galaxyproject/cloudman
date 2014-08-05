"""
An implementation of a file system service capable of managing
interactions with any filesystem that can be mounted via *nix mount
"""
import os
import time
import subprocess

from cm.util.misc import run
from cm.services import service_states

import logging
log = logging.getLogger('cloudman')


class MountableFS(object):

    def __init__(self, filesystem, fs_type, device, mount_options=None):
        self.fs = filesystem  # File system encapsulating this implementation
        self.fs_type = fs_type
        self.app = self.fs.app  # A local reference to app (used by @TestFlag)
        self.device = device
        self.mount_options = mount_options

    def __str__(self):
        return str(self.device)

    def __repr__(self):
        return str(self.device)

    def _get_details(self, details):
        details['device'] = self.device
        details['DoT'] = "No"
        details['kind'] = self.fs_type
        details['options'] = self.mount_options
        return details

    def start(self):
        """
        Start the service.
        Satisfy any preconditions and try to mount the device self.device locally at
        ``self.fs.mount_point``
        """
        if not os.path.exists(self.fs.mount_point):
            os.makedirs(self.fs.mount_point)
        self.mount()

    def stop(self):
        """
        Stop the service and cleanup the ``self.fs.mount_point`` directory.
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
        Do the actual mounting of the device locally.
        """
        log.debug("Mounting device of type {0} from location {0} to mount pount {1}".format(self.fs_type, self.device, self.fs.mount_point))
        options = "-o {0}".format(self.mount_options) if self.mount_options else ""
        cmd = '/bin/mount -t {0} {1} {2} {3}'.format(self.fs_type, options, self.device, self.fs.mount_point)
        process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        _, _ = process.communicate()
        if process.returncode != 0:
            log.error("Trouble mounting file system at {0} from server {1} of type {2} with mount options: {3}"
                .format(self.fs.mount_point, self.device, self.fs_type, self.mount_options if self.mount_options else "None"))
        else:
            log.info("Successfully mounted file system at: {0} from: {1} of type: {2} with mount options: {3}"
                .format(self.fs.mount_point, self.device, self.fs_type, self.mount_options if self.mount_options else "None"))

    def unmount(self):
        """
        Do the actual unmounting of this file system.
        """
        log.debug("Unmounting FS of type {0} from {1}".format(self.fs_type, self.fs.mount_point))
        for counter in range(10):
            if (self.fs.state == service_states.RUNNING and
                run('/bin/umount %s' % self.fs.mount_point)):
                break
            if counter == 9:
                log.warning("Could not unmount file system of type %s at '%s'" % (self.fs_type, self.fs.mount_point))
                return False
            counter += 1
            time.sleep(3)
        return True
