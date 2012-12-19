"""
introspect.py - used as an introspection module for Galaxy CloudMan to
enable status reporting for individual services running on a machine.

All of the methods in this class set or return appropriate service's
status as True or False, based on assumed functionality of given service.
No action is taken to correct operation of a failed service.
"""
import logging, logging.config, commands

from cm.util import misc

import logging
log = logging.getLogger( 'cloudman' )

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
        # self.app.manager.postgres_running = self.check_postgres()
        # self.app.manager.sge_running = self.check_sge()
        # self.app.manager.galaxy_running = self.check_galaxy()
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


    def check_for_existing_volumes(self):
        """Check if there are any data volumes attached to the running
        instance. If yes, based on their
        """
        if self.app.TESTFLAG is True:
            return True
        s3_conn = self.app.cloud_interface.get_s3_connection()
        created_vols = ''
        attached_vols = ''
        idd_volumes = {}

        # Get existing volumes from respective files in current cluster's bucket
        # Check for attached volumes first becauce in the process we discover
        # created ones as well. If no record of attached volumes exists, check
        # for created ones.
        c_vols_file = 'created_volumes.txt'
        a_vols_file = 'attached_volumes.txt'
        if misc.get_file_from_bucket(s3_conn, self.app.ud['bucket_cluster'], a_vols_file, a_vols_file):
            f = open(a_vols_file, 'r')
            attached_vols = f.readlines()
            f.close()
            log.debug("Retrieved following volumes potentially attached to current instance: %s" % attached_vols)
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
                        idd_volumes[vol_name] = [vol_id, dev_id, vol_status, fs_status]
                except Exception, e:
                    log.error("Wrong format of line (%s) from attached volumes file. Exception: %s" % (attached_vol, e))
            return idd_volumes

        if misc.get_file_from_bucket(s3_conn, self.app.ud['bucket_cluster'], c_vols_file, c_vols_file):
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

