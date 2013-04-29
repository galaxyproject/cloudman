"""
A simple static path based file system service.
"""
import os
import time
import subprocess

from cm.util.misc import run
from cm.services import service_states

import logging
log = logging.getLogger('cloudman')


class StaticPathFS(object):
    def __init__(self, filesystem, path):
        self.fs = filesystem  # File system encapsulating this implementation
        self.app = self.fs.app  # A local reference to app (used by @TestFlag)
        self.static_path = path
        assert(self.fs.mount_point == self.static_path)

    def __str__(self):
        return str(self.static_path)

    def __repr__(self):
        return str(self.static_path)

    def _get_details(self, details):
        details['static_path'] = self.static_path
        details['DoT'] = "No"
        details['kind'] = 'Static Path'
        return details

    def start(self):
        """
        Start static_path_fs service.
        """
        if not os.path.exists(self.fs.mount_point):
            os.makedirs(self.fs.mount_point)

    def stop(self):
        """
        Stop static_path_fs service and cleanup the ``self.fs.mount_point`` directory.
        """
        pass
