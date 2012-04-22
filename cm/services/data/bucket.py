import os

from cm.util import misc
from cm.util import paths
from cm.util.misc import _if_not_installed

import logging
log = logging.getLogger('cloudman')

class Bucket(object):
    def __init__(self, filesystem, bucket_name):
        self.fs = filesystem # Filesystem that the bucket represents
        self.bucket_name = bucket_name
        self.mount_point = os.path.join(paths.P_MOUNT_ROOT, bucket_name)
        self._install_s3fs()
    
    @_if_not_installed("s3fs")
    def _install_s3fs(self):
        log.info("s3fs is not available; installing it now.")
        misc.run("cd /tmp; wget --output-document=s3fs.sh http://s3.amazonaws.com/cloudman-os/s3fs.sh")
        misc.run("cd /tmp;sh s3fs.sh")
        log.debug("Done installing s3fs")
    
    def mount(self):
        try:
            if os.path.exists(self.mount_point):
                if len(os.listdir(self.mount_point)) != 0:
                    log.warning("Filesystem at %s already exists and is not empty." % self.mount_point)
                    return False
            else:
                os.mkdir(self.mount_point)
            misc.run("s3fs -oallow_other -opublic_bucket=1 {0} {1}"\
                .format(self.bucket_name, self.mount_point))
            return True
        except Exception, e:
            log.error("Trouble mounting bucket {0} as file system to {1}: {2}"\
                .format(self.bucket_name, self.mount_point, e))
        return False
    
    def unmount(self):
        log.debug("Unmounting bucket {0} from {1}".format(self.bucket_name, self.mount_point))
        misc.run("/bin/umount {0}".format(self.mount_point))
    
