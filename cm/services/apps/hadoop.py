import shutil, tarfile, os, time, subprocess, pwd, grp, datetime, commands

from string import Template

from cm.services.apps import ApplicationService
from cm.util import paths, templates
from cm.services import service_states
from cm.services import ServiceRole
from cm.services import ServiceDependency
from cm.util import misc
from distutils.version import StrictVersion


from os import path
import sys
import urlparse
import urllib2
import shutil
import tarfile
import re
import glob

import logging
log = logging.getLogger( 'cloudman' )


class HadoopService( ApplicationService ):
    def __init__(self, app):
        super(HadoopService, self).__init__(app)
        self.svc_roles = [ServiceRole.HADOOP]
        self.name = ServiceRole.to_string(ServiceRole.HADOOP)
        self.reqs = [ ServiceDependency(self, ServiceRole.SGE)] 
        self.id_rsa_path = os.path.join(paths.P_HADOOP_HOME,"id_rsa")
        self.id_rsa_pub_key_path = os.path.join(paths.P_HADOOP_HOME,"id_rsa.pub")

    def start(self):
        log.debug("configuring hadoop")
        self.state = service_states.STARTING
        if self.unpack_hadoop():
            
            self.configure_hadoop()
            self.state = service_states.RUNNING
        else:
            log.error("Error adding service '%s'" % self.svc_type)
            self.state = service_states.ERROR

    def remove(self):
        log.info("Removing Hadoop service")
        self.state = service_states.SHUTTING_DOWN
        self._clean()
        self.state = service_states.SHUT_DOWN

    def _clean(self):
        """ Stop Hadoop and clean up the system as if Hadoop was never installed. """
        
        if self.state == service_states.SHUT_DOWN:
            misc.run('rm -rf %s/*' % paths.P_HADOOP_HOME)
            
    def unpack_hadoop( self ):
        # TODOD: <KWS> implement the psudo
        # download HADOOP
        # download HADOOP_INTEGRATION
        # Extract both to paths.P_HADOOP_HOME
        # if somthing goes wrong return false
        allDone=False
        log.debug("unpack hadoop")

        hadoop_path = os.path.join(paths.P_HADOOP_TARS_PATH,paths.P_HADOOP_TAR)
        log.debug("hadoop path is "+hadoop_path)
        hadoop_intg_path = os.path.join(paths.P_HADOOP_TARS_PATH,paths.P_HADOOP_INTEGRATION_TAR)
        log.debug("hadoop integ path is "+hadoop_intg_path)
        try:
            if not os.path.exists(paths.P_HADOOP_HOME):
                os.makedirs(paths.P_HADOOP_HOME)
            
            if not os.path.exists(self.id_rsa_path):
                shutil.copy("/mnt/cm/id_rsa",self.id_rsa_path)
                
            if not os.path.exists(self.id_rsa_pub_key_path):
                shutil.copy("/mnt/cm/id_rsa.pub",self.id_rsa_pub_key_path)
            hdp = glob.glob(paths.P_HADOOP_TARS_PATH +"/hadoop.*")
            img_hdp_ver="0.0"
            img_intg_ver = "0.0"
            if len(hdp) > 0:
                hdp_file = os.path.basename(hdp[0])
                img_hdp_ver,img_intg_ver = self.get_fileversion(hdp_file)

            u = urllib2.urlopen(paths.P_HADOOP_TAR_URL)
            s = u.read()
            m = re.search(paths.P_HADOOP_TAR,s)
            srv_hdp=m.group(0)
            srv_hdp_intg = paths.P_HADOOP_INTEGRATION_TAR

            serv_hdp_ver="0.0"
            serv_intg_ver="0.0"

            if m!=None:
                serv_hdp_ver,serv_intg_ver = self.get_fileversion(srv_hdp)
                m = re.search(paths.P_HADOOP_INTEGRATION_TAR,s)
                srv_hdp_intg=m.group(0)
            log.debug(srv_hdp)
            log.debug(img_hdp_ver)
            log.debug(serv_hdp_ver)
            log.debug(img_intg_ver)
            log.debug(serv_intg_ver)
            if StrictVersion(serv_hdp_ver) > StrictVersion(img_hdp_ver) or  StrictVersion(serv_intg_ver) > StrictVersion(img_intg_ver):
                log.debug("downloading hadoop")
                u = urllib2.urlopen(urlparse.urljoin(paths.P_HADOOP_TAR_URL, srv_hdp))
                #log.debug("downloading hadoop URL:;")
                localFile = open(paths.P_HADOOP_TARS_PATH+"/"+srv_hdp, 'w')
                localFile.write(u.read())
                localFile.close()
                log.debug("downloaded hadoop")
            if not os.path.exists(paths.P_HADOOP_TARS_PATH+"/"+srv_hdp_intg):
                log.debug("downloading hadoop integ")
                u = urllib2.urlopen(urlparse.urljoin(paths.P_HADOOP_TAR_URL, srv_hdp_intg))
                #log.debug("downloading hadoop integ URL::")
                localFile = open(paths.P_HADOOP_TARS_PATH+"/"+srv_hdp_intg, 'w')
                localFile.write(u.read())
                localFile.close()
                log.debug("integr downloaded")
            tar = tarfile.open(paths.P_HADOOP_TARS_PATH+"/"+srv_hdp)
            tar.extractall(paths.P_HADOOP_HOME)
            tar.close()
            log.debug("hadoop extracted")
            tar = tarfile.open(paths.P_HADOOP_TARS_PATH+"/"+srv_hdp_intg)
            tar.extractall(paths.P_HADOOP_HOME)
            tar.close()
            log.debug("hadoop integ extracted")
            misc.run("chown -R -c ubuntu "+paths.P_HADOOP_TARS_PATH+"/"+srv_hdp_intg)
            misc.run("chown -R -c ubuntu "+paths.P_HADOOP_TARS_PATH+"/"+srv_hdp)
            allDone=True
        except:
            log.debug("Error in downloading HADOOP")
            log.debug(str(sys.exc_info()[:2]))
            allDone=False
        return allDone

    def get_fileversion(self, file_name):
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
        return hadoop_version,build_version

    def configure_hadoop( self ):
        #TODO:: <KWS> configure user environment
        ## if config goes well 
        ##  set self.state=service_states.RUNNING
        allDone=False
        try:
            log.debug("hadoop env set")
            etcFile=open("/etc/environment","a")
            
            etcFile.write("JAVA_HOME=\"/usr\"\n")
            etcFile.flush()
            etcFile.close()
            log.debug("hadoop id_rsa set from::"+self.id_rsa_path)
            shutil.copy(self.id_rsa_path,"/home/ubuntu/.ssh/id_rsa")
            misc.run("chown -c ubuntu /home/ubuntu/.ssh/id_rsa")
            
            log.debug("hadoop authFile set")
            authFile=open("/home/ubuntu/.ssh/authorized_keys","a")
            pubKeyFile=open(self.id_rsa_pub_key_path)
            authFile.write(pubKeyFile.read())
            authFile.flush()
            authFile.close()
            pubKeyFile.close()
            misc.run("chown -c ubuntu /home/ubuntu/.ssh/authorized_keys")
            allDone=True
        except:
            log.debug("Error in configuring HADOOP")
            log.debug(str(sys.exc_info()[:2]))
            allDone=False
        return allDone

    def check_sge(self):
        """
        Check if SGE qmaster is running and qstat returns at least one node
        (assuming one should be available based on the current state of the
        cluster). If so, return ``True``, ``False`` otherwise.
        """
        qstat_out = commands.getoutput('%s - galaxy -c "export SGE_ROOT=%s;\
            . %s/default/common/settings.sh; \
            %s/bin/lx24-amd64/qstat -f | grep all.q"'
            % (paths.P_SU, paths.P_SGE_ROOT, paths.P_SGE_ROOT, paths.P_SGE_ROOT))
        qstat_out = qstat_out.split('\n')
        cleaned_qstat_out = []
        for line in qstat_out:
            if line.startswith('all.q'):
                cleaned_qstat_out.append(line)
        log.debug("qstat: %s" % cleaned_qstat_out)
        if len(cleaned_qstat_out) > 0: #i.e., at least 1 exec host exists
            # At least 1 exec host exists, assume it will accept jobs
            return True
        elif self.app.manager.get_num_available_workers() == 0:
            # Daemon running but no ready worker instances yet so assume all OK
            return True
        else:
            log.warning("\tNo machines available to test SGE (qstat: %s)." % cleaned_qstat_out)
            return False

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