import os
import commands
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
C_PSQL_PORT = "5910"
USER_DATA_FILE = "userData.yaml"
SYSTEM_MESSAGES_FILE = '/mnt/cm/sysmsg.txt'
LOGIN_SHELL_SCRIPT = "/etc/profile"

# Paths
P_BASE_INSTALL_DIR = '/opt/galaxy/pkg'
P_SGE_ROOT = "/opt/sge"
P_SGE_TARS = "/opt/galaxy/pkg/ge6.2u5"
P_SGE_CELL = "/opt/sge/default/spool/qmaster"
P_DRMAA_LIBRARY_PATH = "/opt/sge/lib/lx24-amd64/libdrmaa.so.1.0"

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

## Condor
P_HTCONDOR_CONFIG_PATH = "/etc/condor/condor_config"
P_HTCONDOR_HOME = "/etc/init.d"

try:
    # Get only the first 3 chars of the version since that's all that's used
    # for dir name
    pg_ver = load = (commands.getoutput(
        "dpkg -s postgresql | grep Version | cut -f2 -d':'")).strip()[:3]
    P_PG_HOME = "/usr/lib/postgresql/{0}/bin".format(pg_ver)
except Exception, e:
    P_PG_HOME = "/usr/lib/postgresql/9.1/bin"
    print "[paths.py] Exception setting PostgreSQL path: {0}\nSet paths.P_PG_HOME to '{1}'"\
        .format(e, P_PG_HOME)


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
P_LWR_HOME = get_path(
    "lwr_home", os.path.join(P_GALAXY_TOOLS, "lwr"))
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

    def _get_ud_path(self, name, default_path):
        path = None
        if self.manager.app.ud:
            path = self.manager.app.ud.get(name, None)
        if not path:
            path = get_path(name, default_path)
        return path

    @property
    def galaxy_home(self):
        # First check if galaxy_home is defined in user data to allow any
        # path to be overridden
        gh = self._get_ud_path('galaxy_home', None)
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
    def lwr_home(self):
        lwr_home = self._get_ud_path('lwr_home', None)
        if lwr_home:
            return lwr_home
        # Get the required file system where LWR should be kept
        galaxy_tools_fs_svc = self.manager.get_services(
            svc_role=ServiceRole.GALAXY_TOOLS)
        lwr_home = os.path.join(galaxy_tools_fs_svc[0].mount_point, 'lwr')
        if os.path.exists(lwr_home):
            return lwr_home
        return P_LWR_HOME

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
    def mount_root(self):
        return P_MOUNT_ROOT

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
    def nginx_dir(self):
        """
        Look around at possible nginx directory locations (from published
        images) and resort to a file system search
        """
        nginx_dir = None
        for path in ['/usr/nginx', '/opt/galaxy/pkg/nginx']:
            if os.path.exists(path):
                nginx_dir = path
            if not nginx_dir:
                cmd = 'find / -type d -name nginx'
                output = misc.run(cmd)
                if isinstance(output, str):
                    path = output.strip()
                    if os.path.exists(path):
                        nginx_dir = path
        return nginx_dir
