import os
import urllib2

from cm.util import misc
from cm.util import paths
from cm.util.misc import _if_not_installed

import logging
log = logging.getLogger('cloudman')

class Bucket(object):
    def __init__(self, filesystem, bucket_name, a_key=None, s_key=None):
        self.fs = filesystem # Filesystem that the bucket represents
        self.bucket_name = bucket_name
        self.mount_point = os.path.join(paths.P_MOUNT_ROOT, bucket_name)
        # Make sure we have creds used to access a given bucket.
        # Note that these may be different than the creds provided via user
        # data because CloudMan may be running on a cloud different from AWS
        # while, currently, mounting buckets from AWS S3 is the only supported
        # source of buckets. Thus, allows bucket-specific creds to be provided
        # but default to the user data creds.
        if a_key is None:
            self.a_key = self.fs.app.ud.get('access_key', None)
            self.s_key = self.fs.app.ud.get('secret_key', None)
        else:
            self.a_key = a_key
            self.s_key = s_key
        log.debug("If needed, when mounting bucket {0} will use the following credentials: '{1}' & '{2}'"\
            .format(self.bucket_name, self.a_key, self.s_key))
        self._install_s3fs()
    
    @_if_not_installed("s3fs")
    def _install_s3fs(self):
        log.info("s3fs is not available; installing it now.")
        misc.run("cd /tmp; wget --output-document=s3fs.sh http://s3.amazonaws.com/cloudman-os/s3fs.sh")
        misc.run("cd /tmp;sh s3fs.sh")
        log.debug("Done installing s3fs")
    
    def _compose_mount_cmd(self):
        """ Compose the command line used to mount the current bucket as a file system.
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
    
    def mount(self):
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
                return misc.run(mount_cmd)
            else:
                log.error("Cannot compose command line for mounting bucket {0}".format(self.bucket_name))
        except Exception, e:
            log.error("Trouble mounting bucket {0} as file system to {1}: {2}"\
                .format(self.bucket_name, self.mount_point, e))
        return False
    
    def unmount(self):
        log.debug("Unmounting bucket {0} from {1}".format(self.bucket_name, self.mount_point))
        misc.run("/bin/umount {0}".format(self.mount_point))
    
    def status(self):
        """ Check on the status of this bucket as a mounted file system
        """
        # TODO
        pass
