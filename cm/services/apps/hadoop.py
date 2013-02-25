import os
import re
import glob
import shutil
import tarfile
import urllib2
import urlparse
import threading
from distutils.version import StrictVersion

from cm.util import misc
from cm.util import paths
from cm.services import ServiceRole
from cm.services import service_states
from cm.services import ServiceDependency
from cm.services.apps import ApplicationService

import logging
log = logging.getLogger('cloudman')


class HadoopService(ApplicationService):
    def __init__(self, app):
        super(HadoopService, self).__init__(app)
        self.svc_roles = [ServiceRole.HADOOP]
        self.name = ServiceRole.to_string(ServiceRole.HADOOP)
        self.reqs = [ServiceDependency(self, ServiceRole.SGE)]
        self.id_rsa_path = os.path.join(paths.P_HADOOP_HOME, "id_rsa")
        self.id_rsa_pub_key_path = os.path.join(
            paths.P_HADOOP_HOME, "id_rsa.pub")

    def start(self):
        """
        Start Hadoop. This entails downloading and extracting Hadoop
        binaries into its folders and setting up the environment
        so Hadoop jobs can be submitted.
        """
        log.debug("Configuring Hadoop")
        self.state = service_states.STARTING
        threading.Thread(target=self.__start).start()

    def __start(self):
        """
        Do the actual unpacking and configuring for Hadoop.
        This method is intended to be called in a separate thread
        and this is because the file download may take a while.
        """
        if self.unpack_hadoop():
            self.configure_hadoop()
            self.state = service_states.RUNNING
            log.info("Done adding Hadoop service; service running.")
        else:
            log.error("Error adding service '%s'" % self.svc_type)
            self.state = service_states.ERROR

    def remove(self):
        """
        Remove Hadoop related files from the system.
        """
        log.info("Removing Hadoop service")
        self.state = service_states.SHUTTING_DOWN
        self._clean()
        self.state = service_states.SHUT_DOWN

    def _clean(self):
        """
        Clean up the system as if Hadoop was never installed.
        """
        if self.state == service_states.SHUT_DOWN:
            misc.run('rm -rf %s/*' % paths.P_HADOOP_HOME)

    def unpack_hadoop(self):
        """
        Download and extract Hadoop into the ``paths.P_HADOOP_HOME`` folder.

        This function first looks for Hadoop in that folder and, if not found,
        downloads the tar ball from the ``cloudman`` bucket.
        """
        all_done = False
        log.debug("Unpacking Hadoop")
        hadoop_path = os.path.join(
            paths.P_HADOOP_TARS_PATH, paths.P_HADOOP_TAR)
        log.debug("Hadoop path is " + hadoop_path)
        hadoop_intg_path = os.path.join(
            paths.P_HADOOP_TARS_PATH, paths.P_HADOOP_INTEGRATION_TAR)
        log.debug("Hadoop SGE integration path is " + hadoop_intg_path)
        try:
            if not os.path.exists(paths.P_HADOOP_HOME):
                os.makedirs(paths.P_HADOOP_HOME)
            if not os.path.exists(self.id_rsa_path):
                shutil.copy("/mnt/cm/id_rsa", self.id_rsa_path)
            if not os.path.exists(self.id_rsa_pub_key_path):
                shutil.copy("/mnt/cm/id_rsa.pub", self.id_rsa_pub_key_path)
            hdp = glob.glob(paths.P_HADOOP_TARS_PATH + "/hadoop.*")
            img_hdp_ver = "0.0"
            img_intg_ver = "0.0"
            if len(hdp) > 0:
                hdp_file = os.path.basename(hdp[0])
                img_hdp_ver, img_intg_ver = self.get_file_version(hdp_file)

            u = urllib2.urlopen(paths.P_HADOOP_TAR_URL)
            s = u.read()
            m = re.search(paths.P_HADOOP_TAR, s)
            srv_hdp = m.group(0)
            srv_hdp_intg = paths.P_HADOOP_INTEGRATION_TAR

            serv_hdp_ver = "0.0"
            serv_intg_ver = "0.0"

            if m != None:
                serv_hdp_ver, serv_intg_ver = self.get_file_version(srv_hdp)
                m = re.search(paths.P_HADOOP_INTEGRATION_TAR, s)
                srv_hdp_intg = m.group(0)
            # log.debug(srv_hdp)
            # log.debug(img_hdp_ver)
            # log.debug(serv_hdp_ver)
            # log.debug(img_intg_ver)
            # log.debug(serv_intg_ver)
            if StrictVersion(serv_hdp_ver) > StrictVersion(img_hdp_ver) or StrictVersion(serv_intg_ver) > StrictVersion(img_intg_ver):
                u = urllib2.urlopen(
                    urlparse.urljoin(paths.P_HADOOP_TAR_URL, srv_hdp))
                log.debug("Downloading Hadoop from {0}".format(u))
                localFile = open(paths.P_HADOOP_TARS_PATH + "/" + srv_hdp, 'w')
                localFile.write(u.read())
                localFile.close()
                log.debug("Downloaded Hadoop")
            if not os.path.exists(paths.P_HADOOP_TARS_PATH + "/" + srv_hdp_intg):
                u = urllib2.urlopen(
                    urlparse.urljoin(paths.P_HADOOP_TAR_URL, srv_hdp_intg))
                log.debug(
                    "Downloading Hadoop SGE integration from {0}".format(u))
                localFile = open(
                    paths.P_HADOOP_TARS_PATH + "/" + srv_hdp_intg, 'w')
                localFile.write(u.read())
                localFile.close()
                log.debug("Hadoop SGE integration downloaded")
            tar = tarfile.open(paths.P_HADOOP_TARS_PATH + "/" + srv_hdp)
            tar.extractall(paths.P_HADOOP_HOME)
            tar.close()
            log.debug("Hadoop extracted to {0}".format(paths.P_HADOOP_HOME))
            tar = tarfile.open(paths.P_HADOOP_TARS_PATH + "/" + srv_hdp_intg)
            tar.extractall(paths.P_HADOOP_HOME)
            tar.close()
            log.debug("Hadoop SGE integration extracted to {0}".format(
                paths.P_HADOOP_HOME))
            misc.run("chown -R -c ubuntu " +
                     paths.P_HADOOP_TARS_PATH + "/" + srv_hdp_intg)
            misc.run("chown -R -c ubuntu " +
                     paths.P_HADOOP_TARS_PATH + "/" + srv_hdp)
            all_done = True
        except Exception, e:
            log.debug("Error downloading Hadoop: {0}".format(e))
            all_done = False
        return all_done

    def get_file_version(self, file_name):
        """
        Extract and return the file version from the file name passed into
        the method, namely, Hadoop and program version.

        Our standard for versioning Hadoop and SGE integration is as follows:
        ``hadoop.<hadoop version>.__.<release version>.<builde versio>.tar.gz``

        If no version is found from the file name, version ``0.0`` will be returned.
        The returned values should be compatible with from StrictVersion
        ``distutils.version`` module.
        """
        hdp_file_ver = file_name.lstrip('hadoop.').rstrip('tar.gz').rstrip('.')
        versions = hdp_file_ver.split('__')
        hadoop_version = "0.0"
        build_version = "0.0"
        try:
            hadoop_version = versions[0]
            build_version = versions[1]
        except Exception, e:
            log.debug("Error extracting Hadoop's file version: {0}".format(e))
            hadoop_version = "0.0"
            build_version = "0.0"
        log.debug("Extracted Hadoop version: {0}".format(hadoop_version))
        log.debug("Extracted Hadoop build version: {0}".format(build_version))
        return hadoop_version, build_version

    def configure_hadoop(self):
        """
        Configure environment for running Hadoop on demand.
        """
        all_done = False
        try:
            log.debug("Setting up Hadoop environment")
            etcFile = open("/etc/environment", "a")
            etcFile.write("JAVA_HOME=\"/usr\"\n")
            etcFile.flush()
            etcFile.close()
            log.debug("Hadoop id_rsa set from::" + self.id_rsa_path)
            hadoop_id_rsa = "/home/ubuntu/.ssh/id_rsa"
            shutil.copy(self.id_rsa_path, hadoop_id_rsa)
            misc.run("chown -c ubuntu {0}".format(hadoop_id_rsa))
            log.debug("Hadoop authFile saved to {0}".format(hadoop_id_rsa))
            authFile = open("/home/ubuntu/.ssh/authorized_keys", "a")
            pubKeyFile = open(self.id_rsa_pub_key_path)
            authFile.write(pubKeyFile.read())
            authFile.flush()
            authFile.close()
            pubKeyFile.close()
            misc.run("chown -c ubuntu /home/ubuntu/.ssh/authorized_keys")
            all_done = True
        except Exception, e:
            log.debug("Error while configuring HADOOP: {0}".format(e))
            all_done = False
        return all_done

    def status(self):
        """
        Check and update the status of HADOOP service. If the service state is
        ``SHUTTING_DOWN``, ``SHUT_DOWN``, ``UNSTARTED``, or ``WAITING_FOR_USER_ACTION``,
        the method doesn't do anything. Otherwise, it updates service status (see
        ``check_sge``) by setting ``self.state``, whose value is always the method's
        return value.
        """
        # # TODO: Add actual logic to make sure  Hadoop jobs run
        if self.state == service_states.RUNNING:
            return service_states.RUNNING
        else:
            pass
