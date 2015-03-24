"""
A wrapper class around instance's transient storage. This class exposes that
storage over NFS to the rest of the cluster.

.. important::
    The file system behind this device is transient, meaning that it will
    dissapear at instance termination and it cannot be recovered.
"""
import commands
import grp
import logging
import os
import pwd

from cm.services import ServiceRole, service_states
from cm.services.data import BlockStorage
from cm.util import misc

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
        try:
            log.debug("Adding transient file system at {0}".format(self.fs.mount_point))
            if not os.path.exists(self.fs.mount_point):
                os.mkdir(self.fs.mount_point)
            os.chown(self.fs.mount_point, pwd.getpwnam("ubuntu")[2],
                     grp.getgrnam("ubuntu")[2])
            self.device = commands.getoutput("df -h %s | grep -v Filesystem | awk "
                                             "'{print $1}'" % self.fs.mount_point)
            # If based on an archive, extract archive contents to the mount point
            try:
                if self.from_archive:
                    log.info("Extracting archive url {0} to mount point {1}. This"
                             "could take a while...".format(self.from_archive['url'],
                             self.fs.mount_point))
                    self.state = service_states.CONFIGURING
                    misc.extract_archive_content_to_path(self.from_archive['url'],
                                                         self.fs.mount_point,
                                                         self.from_archive['md5_sum'])
                    self.fs.persistent = True
            except Exception, e:
                log.error("Error while extracting archive: {0}".format(e))
                return False

            if self.fs.add_nfs_share(self.fs.mount_point):
                self.fs.state = service_states.RUNNING
            else:
                log.warning('Trouble sharing {0} over NFS?'.format(
                    self.fs.mount_point))
        except OSError, e:
            log.debug("Trouble adding transient file system: {0}".format(e))

    def remove(self):
        """
        Initiate removal of this file system from the system.
        Because the backend storage will be gone after an instance is terminated,
        here we just need to remove the NFS share point.
        """
        log.debug("Removing transient instance storage from {0}".format(
            self.fs.mount_point))
        self.fs.remove_nfs_share()
        self.state = service_states.SHUT_DOWN

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
            ee_file = '/etc/exports'
            try:
                # This does read the file every time the service status is
                # updated. Is this really necessary?
                with open(ee_file, 'r') as f:
                    shared_paths = f.readlines()
                for shared_path in shared_paths:
                    if self.fs.mount_point in shared_path:
                        self.fs.state = service_states.RUNNING
                        # Transient storage needs to be special-cased because
                        # it's not a mounted disk per se but a disk on an
                        # otherwise default device for an instance (i.e., /mnt)
                        update_size_cmd = ("df --block-size 1 | grep /mnt$ | "
                                           "awk '{print $2, $3, $5}'")
                        self.fs._update_size(cmd=update_size_cmd)
                        return
                # Or should this set it to UNSTARTED? Because this FS is just an
                # NFS-exported file path...
                log.warning("Data service {0} not found in {1}; error!"
                            .format(self.fs.get_full_name(), ee_file))
                self.fs.state = service_states.ERROR
            except Exception, e:
                log.error("Error checking the status of {0} service: {1}".format(
                    self.fs.get_full_name(), e))
                self.fs.state = service_states.ERROR
