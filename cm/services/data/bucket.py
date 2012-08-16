"""
Methods for managing S3 Buckets and making them available as local file systems.
"""
import os
import urllib2

from cm.util import misc
from cm.util import paths
from cm.util.misc import _if_not_installed
from cm.util.decorators import TestFlag

import logging
log = logging.getLogger('cloudman')

class Bucket(object):
    def __init__(self, filesystem, bucket_name, a_key=None, s_key=None):
        """
        Define the properties for the a given bucket and how it maps to the
        local file system.

        Currently, S3 buckets are the only supported data source, even if the
        current cluster is not running on AWS. If the source bucket is private,
        for the AWS case, credentials used by the current CloudMan cluster are
        used. Alternatively, if running on a non-AWS cloud, explicit credentials
        need to be passed and will be used when interacting with this bucket.

        Note that this method uses ``s3fs`` for mounting S3 buckets and, if ``s3fs``
        command is not available on the system, it will automatically install it.
        """
        self.fs = filesystem # Filesystem that the bucket represents
        self.app = self.fs.app # A local reference to app (used by @TestFlag)
        self.bucket_name = bucket_name
        self.mount_point = os.path.join(paths.P_MOUNT_ROOT, bucket_name)
        if a_key is None:
            self.a_key = self.app.ud.get('access_key', None)
            self.s_key = self.app.ud.get('secret_key', None)
        else:
            self.a_key = a_key
            self.s_key = s_key
        log.debug("If needed, when mounting bucket {0} will use the following credentials: '{1}' & '{2}'"\
            .format(self.bucket_name, self.a_key, self.s_key))
        self._install_s3fs()

    @TestFlag(True)
    @_if_not_installed("s3fs")
    def _install_s3fs(self):
        msg = "s3fs is not installed; will install it now (this typically takes 2-5 minutes)."
        log.info(msg)
        self.app.msgs.info(msg)
        misc.run("cd /tmp;wget --output-document=s3fs.sh http://s3.amazonaws.com/cloudman/pss/s3fs.sh")
        misc.run("cd /tmp;sh s3fs.sh")
        msg = "Done installing s3fs"
        log.debug(msg)
        self.app.msgs.info(msg)

    def __str__(self):
        return str(self.bucket_name)

    def __repr__(self):
        return str(self.bucket_name)

    def _compose_mount_cmd(self):
        """
        Compose the command line used to mount the current bucket as a file system.
        This method checks if a given bucket is public or private and composes
        the appropriate command line.
        """
        bucket_url = 'http://{0}.s3.amazonaws.com/'.format(self.bucket_name)
        cl = None
        is_public = False
        try:
            u = urllib2.urlopen(bucket_url)
            if u.msg == 'OK':
                is_public = True
                log.debug("Bucket {0} is public".format(self.bucket_name))
        except urllib2.HTTPError:
            log.debug("Bucket {0} is NOT public".format(self.bucket_name))
        if is_public:
            cl = "s3fs -oallow_other -opublic_bucket=1 {0} {1}".format(self.bucket_name, self.mount_point)
        else:
            # Create a file containing user creds - we'll create one such file
            # per bucket for maximum flexibility
            creds_file = os.path.join('/tmp', self.bucket_name)
            with open(creds_file, 'w') as cf:
                cf.write("{0}:{1}".format(self.a_key, self.s_key))
            os.chmod(creds_file, 0600) # Required by s3fs
            cl = "s3fs -oallow_other -opasswd_file={0} {1} {2}"\
                .format(creds_file, self.bucket_name, self.mount_point)
        return cl

    @TestFlag(True)
    def mount(self):
        """
        Mount the bucket as a local file system, making it available at
        ``/mnt/<bucket_name>``
        """
        try:
            if os.path.exists(self.mount_point):
                if len(os.listdir(self.mount_point)) != 0:
                    log.warning("Filesystem at %s already exists and is not empty." % self.mount_point)
                    return False
            else:
                os.mkdir(self.mount_point)
            mount_cmd = None
            mount_cmd = self._compose_mount_cmd()
            if mount_cmd is not None:
                ok = misc.run(mount_cmd)
                if ok is True:
                    msg = "Done adding bucket {0} as a local file system. The bucket can now be "\
                        "accessed at /mnt/{0}".format(self.bucket_name)
                else:
                    msg = "Seems to have run into a problem adding bucket {0} as a local file "\
                            "system.".format(self.bucket_name)
                log.debug(msg)
                self.app.msgs.info(msg)
                return ok
            else:
                log.error("Cannot compose command line for mounting bucket {0}".format(self.bucket_name))
        except Exception, e:
            log.error("Trouble mounting bucket {0} as file system to {1}: {2}"\
                .format(self.bucket_name, self.mount_point, e))
        return False

    @TestFlag(True)
    def unmount(self):
        """
        Unmount the local file system mounted from the current bucket
        """
        log.debug("Unmounting bucket {0} from {1}".format(self.bucket_name, self.mount_point))
        return misc.run("/bin/umount {0}".format(self.mount_point))

    def status(self):
        """
        Check on the status of this bucket as a mounted file system
        """
        # TODO
        pass
