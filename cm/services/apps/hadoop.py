import shutil
import tarfile
import os

from cm.services.apps import ApplicationService
from cm.util import paths
from cm.services import service_states
from cm.services import ServiceRole
from cm.services import ServiceDependency
from cm.util import misc
from distutils.version import StrictVersion

import sys
import urlparse
import urllib2
import re
import glob

import logging
log = logging.getLogger('cloudman')


class HadoopService(ApplicationService):
    def __init__(self, app):
        super(HadoopService, self).__init__(app)
        self.svc_roles = [ServiceRole.HADOOP]
        self.name = ServiceRole.to_string(ServiceRole.HADOOP)
        self.reqs = [ServiceDependency(self, ServiceRole.SGE)]
        self.id_rsa_path = os.path.join(paths.P_HADOOP_HOME, "id_rsa")
        self.id_rsa_pub_key_path = os.path.join(paths.P_HADOOP_HOME, "id_rsa.pub")

    def start(self):
        """
        Starting hadoop. Starting hadoop is nothing but downloading
        and extracting hadoop into its folders and set up the environment        for furthur use by hadoop.
        """
        log.debug("configuring hadoop")
        self.state = service_states.STARTING
        if self.unpack_hadoop():
            self.configure_hadoop()
            self.state = service_states.RUNNING
        else:
            log.error("Error adding service '%s'" % self.svc_type)
            self.state = service_states.ERROR

    def remove(self):
        "Removing Hadoop related files."
        log.info("Removing Hadoop service")
        self.state = service_states.SHUTTING_DOWN
        self._clean()
        self.state = service_states.SHUT_DOWN

    def _clean(self):
        """ Clean up the system as if Hadoop was never installed. """
        if self.state == service_states.SHUT_DOWN:
            misc.run('rm -rf %s/*' % paths.P_HADOOP_HOME)

    def unpack_hadoop(self):
        """
        Download and extract hadoop into the specified folders. This function look for
        hadoop both in predefined folder and the cloud and the one with the latest version
        will be always extracted to be used in the system.
        """
        all_done = False
        log.debug("unpack hadoop")

        hadoop_path = os.path.join(paths.P_HADOOP_TARS_PATH, paths.P_HADOOP_TAR)
        log.debug("hadoop path is " + hadoop_path)
        hadoop_intg_path = os.path.join(paths.P_HADOOP_TARS_PATH, paths.P_HADOOP_INTEGRATION_TAR)
        log.debug("hadoop integ path is " + hadoop_intg_path)
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
                img_hdp_ver, img_intg_ver = self.get_fileversion(hdp_file)

            u = urllib2.urlopen(paths.P_HADOOP_TAR_URL)
            s = u.read()
            m = re.search(paths.P_HADOOP_TAR, s)
            srv_hdp = m.group(0)
            srv_hdp_intg = paths.P_HADOOP_INTEGRATION_TAR

            serv_hdp_ver = "0.0"
            serv_intg_ver = "0.0"

            if m != None:
                serv_hdp_ver, serv_intg_ver = self.get_fileversion(srv_hdp)
                m = re.search(paths.P_HADOOP_INTEGRATION_TAR, s)
                srv_hdp_intg = m.group(0)
            log.debug(srv_hdp)
            log.debug(img_hdp_ver)
            log.debug(serv_hdp_ver)
            log.debug(img_intg_ver)
            log.debug(serv_intg_ver)
            if StrictVersion(serv_hdp_ver) > StrictVersion(img_hdp_ver) or StrictVersion(serv_intg_ver) > StrictVersion(img_intg_ver):
                log.debug("downloading hadoop")
                u = urllib2.urlopen(urlparse.urljoin(paths.P_HADOOP_TAR_URL, srv_hdp))
                #log.debug("downloading hadoop URL:;")
                localFile = open(paths.P_HADOOP_TARS_PATH + "/" + srv_hdp, 'w')
                localFile.write(u.read())
                localFile.close()
                log.debug("downloaded hadoop")
            if not os.path.exists(paths.P_HADOOP_TARS_PATH + "/" + srv_hdp_intg):
                log.debug("downloading hadoop integ")
                u = urllib2.urlopen(urlparse.urljoin(paths.P_HADOOP_TAR_URL, srv_hdp_intg))
                #log.debug("downloading hadoop integ URL::")
                localFile = open(paths.P_HADOOP_TARS_PATH + "/" + srv_hdp_intg, 'w')
                localFile.write(u.read())
                localFile.close()
                log.debug("integr downloaded")
            tar = tarfile.open(paths.P_HADOOP_TARS_PATH + "/" + srv_hdp)
            tar.extractall(paths.P_HADOOP_HOME)
            tar.close()
            log.debug("hadoop extracted")
            tar = tarfile.open(paths.P_HADOOP_TARS_PATH + "/" + srv_hdp_intg)
            tar.extractall(paths.P_HADOOP_HOME)
            tar.close()
            log.debug("hadoop integ extracted")
            misc.run("chown -R -c ubuntu " + paths.P_HADOOP_TARS_PATH + "/" + srv_hdp_intg)
            misc.run("chown -R -c ubuntu " + paths.P_HADOOP_TARS_PATH + "/" + srv_hdp)
            all_done = True
        except:
            log.debug("Error in downloading HADOOP")
            log.debug(str(sys.exc_info()[:2]))
            all_done = False
        return all_done

    def get_fileversion(self, file_name):
        """
        Extract and return the file version from the file name passed into it i.e.
        Hadoop version , Program version. Our standard for vesrioning hadoo integration
        versioning is hadoop.<hadoop version>.__.<release version>.<builde versio>.tar.gz.
        If no version has found from the file name the version 0.0,0.0 will be returned.
        The returned values should be compatible with from StrictVersion distutils.version
        module.
        """
        log.debug(file_name)
        hdp_file_ver = file_name.lstrip('hadoop.').rstrip('tar.gz').rstrip('.')
        versions = hdp_file_ver.split('__')
        hadoop_version = "0.0"
        build_version = "0.0"
        try:
            hadoop_version = versions[0]
            build_version = versions[1]
        except:
            log.debug("Error in fileversion HADOOP")
            log.debug(str(sys.exc_info()[:2]))
            hadoop_version = "0.0"
            build_version = "0.0"
        log.debug(str(hadoop_version))
        log.debug(str(build_version))
        return hadoop_version, build_version

    def configure_hadoop(self):
        """
        Configure environment for running hadoop on demand.
        """
        all_done = False
        try:
            log.debug("hadoop env set")
            etcFile = open("/etc/environment", "a")
            etcFile.write("JAVA_HOME=\"/usr\"\n")
            etcFile.flush()
            etcFile.close()
            log.debug("hadoop id_rsa set from::" + self.id_rsa_path)
            shutil.copy(self.id_rsa_path, "/home/ubuntu/.ssh/id_rsa")
            misc.run("chown -c ubuntu /home/ubuntu/.ssh/id_rsa")
            log.debug("hadoop authFile set")
            authFile = open("/home/ubuntu/.ssh/authorized_keys", "a")
            pubKeyFile = open(self.id_rsa_pub_key_path)
            authFile.write(pubKeyFile.read())
            authFile.flush()
            authFile.close()
            pubKeyFile.close()
            misc.run("chown -c ubuntu /home/ubuntu/.ssh/authorized_keys")
            all_done = True
        except:
            log.debug("Error in configuring HADOOP")
            log.debug(str(sys.exc_info()[:2]))
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
        ## TODO:: this method will be submitted every 5 sec
        ## make sure the HADOOP might run
        if self.state == service_states.RUNNING:
            return service_states.RUNNING
        else:
            pass
