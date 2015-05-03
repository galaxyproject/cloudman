"""
A wrapper class around instance's transient storage. This class exposes that
storage over NFS to the rest of the cluster.

.. important::
    The file system behind this device is transient, meaning that it will
    dissapear at instance termination and it cannot be recovered.
"""
import logging
import os

from cm.services import ServiceRole, service_states
from cm.services.data import BlockStorage
from cm.util import misc
from cm.util import ExtractArchive
from cm.util.nfs_export import NFSExport

log = logging.getLogger('cloudman')


class TransientStorage(BlockStorage):
    def __init__(self, filesystem, from_archive=None):
        """
        Instance's transient storage exposed over NFS.
        """
        super(TransientStorage, self).__init__(filesystem.app)
        self.fs = filesystem
        self.app = self.fs.app
        self.device = None
        self.from_archive = from_archive
        self.svc_roles = [ServiceRole.TRANSIENT_NFS]
        self.name = ServiceRole.to_string(ServiceRole.TRANSIENT_NFS)

    def __repr__(self):
        return self.get_full_name()

    def get_full_name(self):
        return "Transient storage @ {0}".format(self.fs.mount_point)

    def _get_details(self, details):
        """
        Transient storage-specific file system details
        """
        details['DoT'] = "Yes"
        details['device'] = self.device
        # TODO: keep track of any errors
        details['err_msg'] = None if details.get(
            'err_msg', '') == '' else details['err_msg']
        return details

    def add(self):
        """
        Add this file system by creating a dedicated path (i.e., self.fs.mount_point)
        and exporting it over NFS. Set the owner of the repo as ``ubuntu`` user.
        """
        log.debug("Adding a transient FS at {0}".format(self.fs.mount_point))
        misc.make_dir(self.fs.mount_point, owner='ubuntu')
        # Set the device ID
        cmd = "df %s | grep -v Filesystem | awk '{print $1}'" % self.fs.mount_point
        self.device = misc.getoutput(cmd)
        # If based on an archive, extract archive contents to the mount point
        if self.from_archive:
            self.fs.persistent = True
            # Extract the FS archive in a separate thread
            ExtractArchive(self.from_archive['url'], self.fs.mount_point,
                           self.from_archive['md5_sum'],
                           callback=self.fs.nfs_share_and_set_state).start()
        else:
            self.fs.nfs_share_and_set_state()

    def remove(self):
        """
        Initiate removal of this file system from the system.

        Because the backend storage will be gone after an instance is
        terminated, here we just need to remove the NFS share point.
        """
        log.debug("Removing transient file system {0}".format(self.fs.mount_point))
        self.fs.remove_nfs_share()
        self.fs.state = service_states.SHUT_DOWN

    def status(self):
        """
        Update the status of this data service: ake sure the mount point exists
        and that it is in /etc/exports for NFS
        """
        # log.debug("Checking the status of {0}".format(self.fs.mount_point))
        if self.fs._service_transitioning():
            # log.debug("Data service {0}
            # transitioning".format(self.fs.get_full_name()))
            pass
        elif self.fs._service_starting():
            # log.debug("Data service {0}
            # starting".format(self.fs.get_full_name()))
            pass
        elif not os.path.exists(self.fs.mount_point):
            # log.debug("Data service {0} dir {1} not there?".format(
            #           self.fs.get_full_name(), self.fs.mount_point))
            self.fs.state = service_states.UNSTARTED
        else:
            try:
                if NFSExport.find_mount_point_entry(self.fs.mount_point) > -1:
                    self.fs.state = service_states.RUNNING
                    # Transient storage needs to be special-cased because
                    # it's not a mounted disk per se but a disk on an
                    # otherwise default device for an instance (i.e., /mnt)
                    update_size_cmd = ("df --block-size 1 | grep /mnt$ | "
                                       "awk '{print $2, $3, $5}'")
                    self.fs._update_size(cmd=update_size_cmd)
                else:
                    # Or should this set it to UNSTARTED? Because this FS is just an
                    # NFS-exported file path...
                    log.warning("Data service {0} not found in /etc/exports; error!"
                                .format(self.fs.get_full_name()))
                    self.fs.state = service_states.ERROR
            except Exception, e:
                log.error("Error checking the status of {0} service: {1}".format(
                    self.fs.get_full_name(), e))
                self.fs.state = service_states.ERROR
