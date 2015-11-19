import commands
import os
import random
import string
from cm.util import misc
from cm.services import ServiceRole

import logging
log = logging.getLogger('cloudman')

# Commands
P_MKDIR = "/bin/mkdir"
P_RM = "/bin/rm"
P_CHOWN = "/bin/chown"
P_SU = "/bin/su"
P_MV = "/bin/mv"
P_LN = "/bin/ln"

# Configs
C_PSQL_PORT = "5930"
USER_DATA_FILE = "userData.yaml"
SYSTEM_MESSAGES_FILE = '/mnt/cm/sysmsg.txt'
LOGIN_SHELL_SCRIPT = "/etc/bash.bashrc"
GALAXY_USER_NAME = 'galaxy'

# Paths
P_BASE_INSTALL_DIR = '/opt/galaxy/pkg'
P_SGE_ROOT = "/opt/sge"
P_SGE_TARS = "/opt/galaxy/pkg/ge6.2u5"
P_SGE_CELL = "/opt/sge/default/spool/qmaster"
P_DRMAA_LIBRARY_PATH = "/opt/sge/lib/lx24-amd64/libdrmaa.so.1.0"

# Slurm paths
SLURM_CONF_FILE = "slurm.conf"
P_SLURM_ROOT_LOCAL = "/etc/slurm-llnl/"
P_SLURM_ROOT_NFS = "/mnt/transient_nfs/slurm/"
P_SLURM_ROOT_TMP = "/tmp/slurm"

# the value for P_HADOOP_HOME must be equal to the directory
# in the file hdfs-start.sh from sge_integration
P_HADOOP_HOME = "/opt/hadoop"
P_HADOOP_TARS_PATH = "/opt/hadoop"
# # P_HADOOP_TAR is a regex format file name to find the latest hadoop from the site or directory
# # the standard for the versioning here is "hadoop.<hadoop release number>__<release numbere.build number>.tar.gz"
# if no version is set it is assumed 0.0 and would be replaced if any
# newer is found
P_HADOOP_TAR = "hadoop\.((([|0-9])*\.)*[0-9]*__([0-9]*\.)*[0-9]+){0,1}\.{0,1}tar\.gz"
# P_HADOOP_INTEGRATION_TAR is a regex format file name to find the latest
# hadoop_sge_integration from the site or directory
P_HADOOP_INTEGRATION_TAR = "sge_integration\.(([0-9]*\.)*[0-9]+){0,1}\.{0,1}tar\.gz"
P_HADOOP_TAR_URL = "https://s3.amazonaws.com/cloudman/"
P_HADOOP_INTEGRATION_TAR_URL = "https://s3.amazonaws.com/cloudman/"

P_HADOOP_INTEGRATION_FOLDER = "sge_integration"

P_ETC_TRANSIENT_PATH = "/mnt/transient_nfs/hosts"

# # Condor
P_HTCONDOR_CONFIG_PATH = "/etc/condor/condor_config"
P_HTCONDOR_HOME = "/etc/init.d"

try:
    # Get only the first 3 chars of the version since that's all that's used
    # for dir name
    pg_ver = load = (commands.getoutput(
        "dpkg -s postgresql | grep Version | cut -f2 -d':'")).strip()[:3]
    P_PG_HOME = "/usr/lib/postgresql/{0}/bin".format(pg_ver)
except Exception, e:
    P_PG_HOME = "/usr/lib/postgresql/9.3/bin"
    print "[paths.py] Exception setting PostgreSQL path: {0}\nSet paths.P_PG_HOME to '{1}'"\
        .format(e, P_PG_HOME)

try:
    # Get only the first 3 chars of the version since that's all that's used
    # for dir name
    pg_ver = load = (commands.getoutput(
        "dpkg -s postgresql | grep Version | cut -f2 -d':'")).strip()[:3]
    P_PG_CONF = "/etc/postgresql/{0}/main/postgresql.conf".format(pg_ver)
except Exception, e:
    P_PG_CONF = "/etc/postgresql/9.3/main/postgresql.conf"
    print "[paths.py] Exception setting PostgreSQL path: {0}\nSet paths.P_PG_CONF to '{1}'"\
        .format(e, P_PG_CONF)


def get_path(name, default_path):
    """
    Get a file system path where a service with the given ``name`` resides/runs
    as defined in the user data. For example, to use a custom path for Galaxy,
    set ``galaxy_home: /my/custom/path/to/galaxy`` in the user data. If the custom
    path is not provided, just return the ``default_path``.
    """
    path = None
    try:
        path = misc.load_yaml_file(USER_DATA_FILE).get(name, None)
        if path is None:
            downloaded_pd_file = 'pd.yaml'
            if os.path.exists(downloaded_pd_file):
                path = misc.load_yaml_file(
                    downloaded_pd_file).get(name, default_path)
    except:
        pass
    if not path:
        path = default_path
    return path

P_MOUNT_ROOT = "/mnt"
P_GALAXY_TOOLS = get_path(
    "galaxy_tools", os.path.join(P_MOUNT_ROOT, "galaxy"))
P_GALAXY_HOME = get_path(
    "galaxy_home", os.path.join(P_GALAXY_TOOLS, "galaxy-app"))
P_PULSAR_HOME = get_path(
    "pulsar_home", os.path.join('/mnt', "pulsar"))
P_GALAXY_DATA = get_path(
    "galaxy_data", os.path.join(P_MOUNT_ROOT, 'galaxy'))
P_GALAXY_INDICES = get_path(
    "galaxy_indices", os.path.join(P_MOUNT_ROOT, "galaxyIndices"))

IMAGE_CONF_SUPPORT_FILE = os.path.join(P_BASE_INSTALL_DIR, 'imageConfig.yaml')


class PathResolver(object):
    def __init__(self, manager):
        self.manager = manager

    @property
    def galaxy_tools(self):
        galaxy_tool_fs = self.manager.get_services(
            svc_role=ServiceRole.GALAXY_TOOLS)
        if galaxy_tool_fs:
            return galaxy_tool_fs[0].mount_point
        else:  # For backward compatibility
            return P_GALAXY_TOOLS

    def _get_path_from_config(self, name, default_path):
        path = None
        if self.manager.app.config:
            path = self.manager.app.config.get(name, None)
        if not path:
            path = get_path(name, default_path)
        return path

    @property
    def galaxy_home(self):
        # First check if galaxy_home is defined in user data to allow any
        # path to be overridden
        gh = self._get_path_from_config('galaxy_home', None)
        if gh:
            return gh
        # Get the required file system where Galaxy should be kept
        galaxy_tools_fs_svc = self.manager.get_services(
            svc_role=ServiceRole.GALAXY_TOOLS)
        if galaxy_tools_fs_svc:
            # Test directories that were used in the past as potential
            # Galaxy-home directories on the required file system
            for g_dir in ['galaxy-app', 'galaxy-central', 'galaxy-dist']:
                gh = os.path.join(galaxy_tools_fs_svc[0].mount_point, g_dir)
                if os.path.exists(gh):
                    return gh
        # log.debug("Warning: Returning default path for galaxy_home")
        return P_GALAXY_HOME

    @property
    def galaxy_config_dir(self):
        """
        Get the likely dir where Galaxy's configuration files are located
        """
        # Starting with 2014-10-06 Galaxy release, config files are stored in
        # `galaxy_home/config` dir so check if that dir exists and use it
        for cfd in ['config', '']:
            config_dir_path = os.path.join(self.galaxy_home, cfd)
            if os.path.exists(config_dir_path):
                break
        return config_dir_path

    @property
    def pulsar_home(self):
        pulsar_home = self._get_path_from_config('pulsar_home', None)
        if pulsar_home:
            return pulsar_home
        return P_PULSAR_HOME

    @property
    def galaxy_data(self):
        galaxy_data_fs = self.manager.get_services(
            svc_role=ServiceRole.GALAXY_DATA)
        if galaxy_data_fs:
            return galaxy_data_fs[0].mount_point
        else:
            log.debug("Warning: Returning default path for galaxy_data")
            return P_GALAXY_DATA

    @property
    def galaxy_temp(self):
        return os.path.join(self.galaxy_data, 'tmp')

    @property
    def galaxy_indices(self):
        galaxy_index_fs = self.manager.get_services(
            svc_role=ServiceRole.GALAXY_INDICES)
        if galaxy_index_fs:
            return galaxy_index_fs[0].mount_point
        else:  # For backward compatibility
            log.debug("Warning: Returning default galaxy path for indices")
            return P_GALAXY_INDICES

    @property
    def pg_home(self):
        return P_PG_HOME

    @property
    def psql_dir(self):
        return os.path.join(self.galaxy_data, "db")

    @property
    def psql_cmd(self):
        return os.path.join(self.pg_home, 'psql')

    @property
    def mount_root(self):
        return P_MOUNT_ROOT

    @property
    def transient_nfs(self):
        transient_fs = self.manager.get_services(svc_role=ServiceRole.TRANSIENT_NFS)
        if transient_fs:
            return transient_fs[0].mount_point
        else:  # For backward compatibility
            log.debug("Warning: Returning default transient file system path")
            return "/mnt/transient_nfs"

    @property
    def sge_root(self):
        return P_SGE_ROOT

    @property
    def sge_tars(self):
        return P_SGE_TARS

    @property
    def sge_cell(self):
        return P_SGE_CELL

    @property
    def drmaa_library_path(self):
        return P_DRMAA_LIBRARY_PATH

    @property
    def slurm_conf_local(self):
        return os.path.join(P_SLURM_ROOT_LOCAL, SLURM_CONF_FILE)

    @property
    def slurm_conf_nfs(self):
        return os.path.join(self.slurm_root_nfs, SLURM_CONF_FILE)

    @property
    def slurm_root_nfs(self):
        return os.path.join(self.transient_nfs, "slurm")

    @property
    def slurm_root_tmp(self):
        return P_SLURM_ROOT_TMP

    @property
    def slurmctld_pid(self):
        return '/var/run/slurmctld.pid'

    @property
    def slurmd_pid(self):
        return '/var/run/slurmd.pid'

    @property
    def nginx_executable(self):
        """
        Get the path of the nginx executable
        """
        possible_paths = ['/usr/sbin', '/usr/nginx/sbin', '/opt/galaxy/pkg/nginx/sbin']
        return misc.which('nginx', possible_paths)

    @property
    def nginx_conf_dir(self):
        """
        Use the running nginx to provide the location of the current nginx configuration directory
        """
        conf_file = misc.run("{0} -t && {0} -t 2>&1 | head -n 1 | cut -d' ' -f5".format(self.nginx_executable))
        if os.path.exists(conf_file.strip()):
            return conf_file.rstrip("nginx.conf\n")
        return ''

    @property
    def nginx_conf_file(self):
        """
        Get the path of the nginx conf file, namely ``nginx.conf``
        """
        path = os.path.join(self.nginx_conf_dir, 'nginx.conf')
        if os.path.exists(path):
            return path
        # Resort to a full file system search
#         cmd = 'find / -name nginx.conf'
#         output = misc.run(cmd)
#         if isinstance(output, str):
#             path = output.strip()
#             if os.path.exists(path):
#                 return path
        return None

    @property
    def proftpd_conf_file(self):
        """
        Get the location of ProFTPd config file
        """
        return '/usr/proftpd/etc/proftpd.conf'

    @property
    def proftpd_galaxyftp_user_pwd(self):
        """
        Return a new random password for the `galaxyftp` user

        (From http://stackoverflow.com/questions/2257441)
        """
        return ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(10))

    @property
    def psql_db_port(self):
        """
        Return the port number on which PostgreSQL database is available.

        The scheme used here is 5MajorMinor0, where *Major* is PostgreSQL's
        major version number, *Minor* is the minor version number. For
        example, PostgreSQL v9.1.14 will be set to run on port 5910.
        """
        cmd = ("{0} --version | head -n 1 | cut -d')' -f2 | tr -d ' ' | cut -d'.' -f1,2 | tr -d '.'"
               .format(self.psql_cmd))
        try:
            ver_number = commands.getoutput(cmd)
        except Exception, e:
            log.error("Exception retrieving psql version number used for DB port; "
                      "defaulting port to 5930: {0}".format(e))
            ver_number = '93'
        return "5{0}0".format(ver_number)
