"""
introspect.py - used as an introspection module for Galaxy Cloud to 
enable status reporting for individal services running on a machine.

All of the methods in this class set or return approapriate service's
status as True or False, based on assumed functinality of given service. 
No action is taken to correct operation of a failed service.

Created by Enis on 2010-04-22.
"""

import logging, logging.config, commands, sys, os, os.path, time, subprocess, string
import tempfile, re, traceback, shutil, Queue, pwd, grp, shutil, random, urllib2

from boto.s3.connection import S3Connection
from boto.ec2.connection import EC2Connection
from boto.ec2.volume import Volume
from boto.exception import EC2ResponseError, S3ResponseError, BotoServerError

from cm.util.bunch import Bunch
from cm.util import misc, comm
from cm.util.paths import *

log = logging.getLogger(__name__)


try:
    DRMAA = __import__("DRMAA")
    log.debug("Loaded DRMAA.")
except:
    log.debug("Could not load DRMAA.")
    DRMAA = None


if DRMAA is not None:
    DRMAA_state = {
        DRMAA.Session.UNDETERMINED: 'process status cannot be determined',
        DRMAA.Session.QUEUED_ACTIVE: 'job is queued and waiting to be scheduled',
        DRMAA.Session.SYSTEM_ON_HOLD: 'job is queued and in system hold',
        DRMAA.Session.USER_ON_HOLD: 'job is queued and in user hold',
        DRMAA.Session.USER_SYSTEM_ON_HOLD: 'job is queued and in user and system hold',
        DRMAA.Session.RUNNING: 'job is running',
        DRMAA.Session.SYSTEM_SUSPENDED: 'job is system suspended',
        DRMAA.Session.USER_SUSPENDED: 'job is user suspended',
        DRMAA.Session.DONE: 'job finished normally',
        DRMAA.Session.FAILED: 'job finished, but failed',
    }

sge_template = """#!/bin/sh
    #$ -N TestJob
    #$ -S /bin/bash
    #$ -o TestJob.out
    #$ -e TestJob.err
    # print date and time
    date
    # Sleep for 5 seconds
    sleep 5
    # print date and time again
    date
    """    


class Introspect(object):
    
    def __init__(self, app):
        self.app = app
    
    def check_all_master_services(self):
        """Check all services running on a master instance and update 
        appropriate fields in the master itself. 
        """
        log.debug("Checking all services...")
        self.check_volumes()
        self.check_file_systems()
        self.app.manager.postgres_running = self.check_postgres()
        self.app.manager.sge_running = self.check_sge()
        self.app.manager.galaxy_running = self.check_galaxy()
        self.check_disk()

    def check_all_worker_services(self):
        log.debug("Checking all services...")
        self.check_worker_file_systems()

    def check_disk(self):
        try:
            disk_usage = commands.getoutput("df -h | grep galaxyData | awk '{print $2, $3, $5}'")
            disk_usage = disk_usage.split(' ')
            if len(disk_usage) == 3:
                self.app.manager.disk_total = disk_usage[0]
                self.app.manager.disk_used = disk_usage[1]
                self.app.manager.disk_pct = disk_usage[2]
                return True
            else:
                return False
        except Exception, e:
            log.error("Failure checking disk usage.  %s" % e)
            return False

    def check_volumes(self):
        """Check if external data volumes expected by GC exist and are 
        attached to the instance. Because multiple volumes are checked, 
        status of individual voluems is stored in master's volume description
        variable so this method does not return a value.
        """
        # log.debug("\tChecking volumes")
        for vol in self.app.manager.volumes.iterkeys():
            vol_name = vol
            vol_id = self.app.manager.volumes[vol][0]
            vol_status = self.check_volume(vol_name, vol_id)
            self.app.manager.volumes[vol][2] = vol_status
            # log.debug("\tVol ID '%s' with name '%s' status: '%s'" % 
            #     (vol_id, vol_name, vol_status))

    def check_volume(self, vol_name, vol_id):
        """Check the existence and status of given vol_id. 
        :type vol_name: str
        :param vol_name: Name of the volume being checked as assigned by GC
        :type vol_id: str
        :param vol_id: AWS ID for EBS volume being checked
        
        :rtype: bool
        :return: If vol_id status is 'attached', return True.
                 If found volume does not exist any more, return None.
                 False, otherwise.
        """
        if self.app.TESTFLAG is True:
            return True
        # log.debug("\tChecking volume ID '%s' with name '%s'" % (vol_id, vol_name)) 
        ec2_conn = self.app.get_ec2_connection()
        try: 
            vol = ec2_conn.get_all_volumes([vol_id])
        except EC2ResponseError, e:
            log.error("Volume ID '%s' with name '%s' returned an error: %s" 
                % (vol_id, vol_name, e))
            if str(e).find('does not exist') > -1:
                return None
            else:
                return False 

        if len(vol) > 0: 
            # We're only looking for the first vol bc. that's all we asked for
            if vol[0].attachment_state() == 'attached':
                return True
            else:
                return False #vol[0].status
        
    def check_file_systems(self):
        """Check if file systems expected by GC are available and mounted. 
        Following file systems are checked (as they map to their appropriate
        mount points - e.g., /mnt/<FS name>): 'galaxyData', 'galaxyTools', 
        and 'galaxyIndices'.
        Because multiple file syatems are checked, status of individual voluems
        is stored in master's volume description variable so this method does
        not return a value.
        """
        # log.debug("\tChecking file systems")
        for vol_name, lst in self.app.manager.volumes.iteritems():
            dev_id = lst[1] # get device id as stored in the volume description
            fs_status = self.check_file_system(vol_name, dev_id)
            lst[3] = fs_status # store fs_status in self.app.manager.volumes
            # log.debug("\tVol with name '%s' and device ID '%s' status: '%s'" % 
            #     (vol_name, dev_id, fs_status))
    
    def check_worker_file_systems(self):
        """Check if file systems expected by GC worker are available and mounted. 
        Following file systems are checked (as they map to their appropriate
        mount points - e.g., /mnt/<FS name>): 'galaxyData', 'galaxyTools', 
        'galaxyIndices', and '/opt/sge'.
        """
        self.app.manager.nfs_data = self.check_file_system('galaxyData', '/mnt/galaxyData')
        self.app.manager.nfs_tools = self.check_file_system('galaxyTools', '/mnt/galaxyTools')
        self.app.manager.nfs_indices = self.check_file_system('galaxyIndices', '/mnt/galaxyIndices')
        self.app.manager.nfs_sge = self.check_file_system('SGE', '/opt/sge')
        
    def check_file_system(self, vol_name, dev_id):
        """Check if file system on given device ID was mounted to the location
        based on the volume name.
        :type vol_name: str
        :param vol_name: Name of the volume being checked as assigned by GC
        :type vol_id: str
        :param vol_id: device id where given volume is attached (e.g., /dev/sdi)
    
        :rtype: bool
        :return: True if dev_id is mounted to /mnt/vol_name, 
                 False otherwise.
        """
        # log.debug("\tChecking volume with name '%s' attached to device '%s'" % 
        #             (vol_name, dev_id))
        mnt_location = ''
        mnt_location = commands.getoutput("cat /proc/mounts | grep %s | cut -d' ' -f2" % dev_id)
        if vol_name.find( ':' ) != -1: # handle multiple volumes comprising vol_name
            mnt_path = '/mnt/%s' % vol_name.split(':')[0]
        else:
            mnt_path = '/mnt/%s' % vol_name
        if mnt_location != '':
            # log.debug("\tVolume named '%s' attached to device '%s' is mounted to '%s'" %
                # (vol_name, dev_id, mnt_location))
            if mnt_location == mnt_path:
                return True
            else:
                log.warning("Retreived mount path '%s' does not match expected path '%s'" %
                    (mnt_location, mnt_path))
                return False
        else:
            log.error("Volume named '%s' is attached as device '%s' but not mounted." %
                (vol_name, dev_id))
            return False
        
    def check_postgres(self):
        """Check if PostgreSQL server is running and if 'galaxy' database exists.
        
        :rtype: bool
        :return: True if the server is running and 'galaxy' database exists,
                 False otherwise.
        """
        # log.debug("\tChecking PostgreSQL")
        if self._check_daemon('postgres'):
            # log.debug("\tPostgreSQL daemon running. Trying to connect and select tables.")
            dbs = commands.getoutput('%s - postgres -c "%s/psql -c \\\"SELECT datname FROM PG_DATABASE;\\\" "' % (P_SU, P_PG_HOME))
            if dbs.find('galaxy') > -1:
                # log.debug("\tPostgreSQL daemon OK, 'galaxy' database exists.")
                return True
            else:
                log.warning("\tPostgreSQL daemon OK, 'galaxy' database does NOT exist: %s" % dbs)
                return False
        elif not os.path.exists( P_PSQL_DIR ):
            log.warning("PostgreSQL data directory '%s' does not exist (yet?)" % P_PSQL_DIR)
            # Assume this is because user data dir has not been setup yet,
            # mark service as not-attempted yet (i.e., status: None)
            return None
        else:
            log.error("\tPostgreSQL daemon NOT running.")
            return False
        
    def _check_daemon(self, service):
        """Check if 'service' daemon process is running. 
        
        :rtype: bool
        :return: True if a process assocaited with the 'service' exists on the system,
                 False otherwise.
        """
        daemon_pid = self._get_daemon_pid(service)
        if daemon_pid == -1:
            return False
        else:
            # Check if given PID is actually still running
            alive_daemon_pid = None
            # Galaxy deamon is named 'paster' so handle this special case
            if service == 'galaxy':
                service = 'python'
            alive_daemon_pid = commands.getoutput("ps -o comm,pid -p %s | grep %s | awk '{print $2}'" % (daemon_pid, service))
            if service == 'pyhton':
                service = 'galaxy'
            if alive_daemon_pid == daemon_pid:
                # log.debug("\t'%s' daemon is running with PID: %s" % (service, daemon_pid))
                return True
            else:
                log.debug("\t'%s' daemon is NOT running any more (expected pid: '%s')." 
                    % (service, daemon_pid))
                return False
        
    def _get_daemon_pid(self, service):
        """Get PID of 'service' daemon as stored in the service.pid file 
        in respective service directory. 
        :type service: str
        :param service: Recognized values include only 'postgres', 'sge', 'galaxy' 
        
        :rtype: int
        :return: PID, -1 if the file does not exist
        """
        if service == 'postgres':
            pid_file = '%s/postmaster.pid' % P_PSQL_DIR
        elif service == 'sge':
            pid_file = '%s/qmaster.pid' % P_SGE_CELL
        elif service == 'galaxy':
            pid_file = '%s/paster.pid' % P_GALAXY_HOME
        else:
            return -1
        # log.debug("\tChecking pid file '%s' for service '%s'" % (pid_file, service))
        if os.path.isfile(pid_file):
            return commands.getoutput("head -n 1 %s" % pid_file)
        else:
            return -1
        
    def check_sge(self):
        """Check if SGE qmaster is running and a sample job can be successfully run.
        
        :rtype: bool
        :return: True if the daemon is running and a sample job can be run,
                 False otherwise.
        """
        # log.debug("\tChecking SGE")
        if self._check_daemon('sge'):
            # log.debug("\tSGE daemon running. Trying to submit a sample job as user 'galaxy'.")
            qstat_out = ''
            qstat_out = commands.getoutput('%s - galaxy -c "export SGE_ROOT=%s;\
                . %s/default/common/settings.sh; \
                %s/bin/lx24-amd64/qstat -f | grep all.q"' 
                % (P_SU, P_SGE_ROOT, P_SGE_ROOT, P_SGE_ROOT))
            qstat_out = qstat_out.split('\n')
            cleaned_qstat_out = []
            for line in qstat_out:
                if line.startswith('all.q'):
                    cleaned_qstat_out.append(line)
            log.debug("cleaned_qstat_out: %s" % cleaned_qstat_out)
            if len(cleaned_qstat_out) > 0: #i.e., at least 1 exec host exists
                # At least 1 exec host exists, assume it will accept jobs
                return True
                # if DRMAA is not None: 
                #     try:
                #         ds = DRMAA.Session()
                #         ds.init()
                #         # log.debug('\tDRMAA session was started successfully')
                # 
                #         # Create a simple script
                #         jt = ds.createJobTemplate()
                #         jt.remoteCommand = '%s/sge_script.sh' % P_SGE_ROOT
                #         f = open(jt.remoteCommand, 'w')
                #         f.write(sge_template)
                #         f.close()
                #         os.chmod(jt.remoteCommand, 0750)
                #     
                #         job_id = ds.runJob( jt )
                #         log.debug('\tSample job (%s) has been submitted with id %s' % (jt.remoteCommand, job_id))
                #     
                #         state = None
                #         for i in range(10):
                #             state = ds.getJobProgramStatus( job_id )
                #             log.debug("\tSample %s (job id: '%s')." % (DRMAA_state[state], job_id))
                #             if state == DRMAA.Session.DONE:
                #                 ds.deleteJobTemplate( jt )
                #                 ds.exit()
                #                 return True
                #             elif state == DRMAA.Session.RUNNING:
                #                 pass
                #             elif state == DRMAA.Session.QUEUED_ACTIVE:
                #                 pass
                #             elif state == DRMAA.Session.FAILED:
                #                 ds.exit()
                #                 return False
                #             time.sleep(6)
                # 
                #         log.warning("\tSample job did not complete in time; last state: %s." 
                #             % DRMAA_state[state])
                #         # Clean up
                #         ds.deleteJobTemplate( jt )
                #         ds.exit()
                #     except Exception, e:
                #         # Trying not to kill the app here while testing
                #         log.error("Problems submitting a sample SGE job: %s" % e)
                #     return False
                # else:
                #                     # Hack until can import DRMAA and submit a real test job 
                #                     # because if qstat shows available nodes, will assume
                #                     # those can accept jobs too.
                #                     return True
            elif self.app.manager.get_num_available_workers() == 0:
                # Deamon running but no ready worker instances yet so assume all OK
                return True
            else:
                log.warning("\tNo machines available to test SGE (qstat: %s)." % cleaned_qstat_out)
                return False
        else:
            log.error("\tSGE qmaster daemon not running.")
            return False

    def check_qmaster(self):
        # log.debug("Checking SGE qmaster")
        if self._check_daemon('sge'):
            log.debug("SGE qmaster is running.")
            return True
        else:
            log.debug("SGE qmaster is not running.")
            return False

    def check_galaxy(self):
        """Check if Galaxy daemon is running and the UI is accessible.
        
        :rtype: bool
        :return: True if the daemon is running and the UI is accessible,
                 False otherwise.
        """
        # log.debug("\tChecking Galaxy")
        if self._check_daemon('galaxy'):
            # log.debug("\tGalaxy daemon running. Checking if UI is accessible.")
            dns = "http://127.0.0.1:8080"
            try:
                urllib2.urlopen(dns)
                # log.debug("\tGalaxy daemon running and the UI is accessible.")
                return True
            except urllib2.URLError:
                log.debug("\tGalaxy UI does not seem to be accessible.")
                return False
            except Exception, e:
                log.debug("\tGalaxy UI does not seem to be accessible.")
                return False
                
        elif self.app.manager.galaxy_running is None:
            # Assume it was never attempted if the flag is still unset.  This is reasonably safe, and more reliable than checking the path.
            return None
        # elif not os.path.exists( P_GALAXY_DATA ):
        #     log.warning("Galaxy directory '%s' does not exist (yet?)" % P_GALAXY_DATA)
        #     # Assume this is because user data dir has not been setup yet,
        #     # mark service as not-attempted yet (i.e., status: None)
        #     return None
        else:
            log.error("\tGalaxy daemon not running.")
            return False
            
    def check_for_existing_volumes(self):
        """Check if there are any data volumes attached to the running
        instance. If yes, based on their 
        """
        if self.app.TESTFLAG is True:
            return True
        ec2_conn = self.app.get_ec2_connection()
        s3_conn = self.app.get_s3_connection()
        created_vols = ''
        attached_vols = ''
        idd_volumes = {}

        # Get existing volumes from respective files in current cluster's bucket
        # Check for attached volumes first becauce in the process we discover
        # created ones as well. If no record of attached volumes exists, check
        # for created ones. 
        c_vols_file = 'created_volumes.txt'
        a_vols_file = 'attached_volumes.txt'
        if misc.get_file_from_bucket(s3_conn, self.app.shell_vars['BUCKET_NAME'], a_vols_file, a_vols_file):
            f = open(a_vols_file, 'r')
            attached_vols = f.readlines()
            f.close()
            log.debug("Retrieved following volumes pottentially attached to current instance: %s" % attached_vols)
            for attached_vol in attached_vols:
                try:
                    # Each line of attached_vol must be formatted as follows:
                    # <file system name>@<volume ID>@<attached device ID>
                    vol_name = attached_vol.split('@')[0].strip()
                    vol_id = attached_vol.split('@')[1].strip()
                    dev_id = attached_vol.split('@')[2].strip()
                    vol_status = self.check_volume(vol_name, vol_id)
                    # If found vol does not exist, don't create reference to it
                    if vol_status is not None:
                        fs_status = self.check_file_system(vol_name, dev_id)
                        # vol_size = misc.get_volume_size(ec2_conn, vol_id)
                        idd_volumes[vol_name] = [vol_id, dev_id, vol_status, fs_status]
                except Exception, e:
                    log.error("Wrong format of line (%s) from attached volumes file. Exception: %s" % (attached_vol, e))
            return idd_volumes
        
        if misc.get_file_from_bucket(s3_conn, self.app.shell_vars['BUCKET_NAME'], c_vols_file, c_vols_file):
            f = open(c_vols_file, 'r')
            created_vols = f.readlines()
            f.close()
            log.debug("Retrieved following volumes potentially created by/for current instance: %s" % created_vols)
            for created_vol in created_vols:
                try:
                    # Each line of created_vol must be formatted as follows:
                    # <file system name>@<volume ID>
                    vol_name = attached_vol.split('@')[0].strip()
                    vol_id = attached_vol.split('@')[1].strip()
                    vol_status = self.check_volume(vol_name, vol_id)
                    # If found vol does not exist, don't create reference to it
                    if vol_status is not None:
                        idd_volumes[vol_name] = [vol_id, dev_id, vol_status, None]
                except Exception, e:
                    log.error("Wrong format of line (%s) from created volumes file. Exception: %s" % (created_vol, e))
            return idd_volumes
            
        log.debug("No already existing volumes found.")
        return {}

        # all_user_volumes = ec2_conn.get_all_volumes()
        # for vol in all_user_volumes:
        #     if vol.instance_id == self.app.get_instance_id():
        #         log.debug("vol '%s' attached to instance '%s' (from instance '%s')" % (vol.id, vol.instance_id, self.app.get_instance_id()))
        #         attached_vols.append(vol)
        # if len(attached_vols) == 0:
        #     log.debug("No volumes are attached to the instance.")
        # 
        # for attached_vol in attached_vols:
        #     if attached_vol.device == P_GALAXY_TOOLS_MNT:
        #         log.debug("Found attached data volume '%s' attached to device '%s' as 'galaxyTools' volume."
        #             % (attached_vol.id, attached_vol.device))
        #         idd_volumes['galaxyTools'] = [attached_vol.id, attached_vol.device, None, None]
        #     elif attached_vol.device == P_GALAXY_INDICES_MNT:
        #         log.debug("Found attached data volume '%s' attached to device '%s' as 'galaxyIndices' volume."
        #             % (attached_vol.id, attached_vol.device))
        #         idd_volumes['galaxyIndices'] = [attached_vol.id, attached_vol.device, None, None]
        #     elif attached_vol.device == P_GALAXY_DATA_MNT:
        #         log.debug("Found attached data volume '%s' attached to device '%s' as 'galaxyData' volume."
        #             % (attached_vol.id, attached_vol.device))
        #         idd_volumes['galaxyData:0'] = [attached_vol.id, attached_vol.device, None, None]
        #     else:
        #         log.error("Found attached data volume '%s' that does not match any expected mount points: '%s'" %
        #             (attached_vol.id, attached_vol.device))