import os
import commands
from cm.util import misc

# Commands
P_MKDIR = "/bin/mkdir"
P_RM = "/bin/rm"
P_CHOWN = "/bin/chown"
P_SU = "/bin/su"
P_MV = "/bin/mv"
P_LN = "/bin/ln"

# Configs
C_PSQL_PORT = "5840"
USER_DATA_FILE = "userData.yaml"
LOGIN_SHELL_SCRIPT = "/etc/profile"

# Paths
P_BASE_INSTALL_DIR = '/opt/galaxy/pkg'
P_SGE_ROOT = "/opt/sge"
P_SGE_TARS = "/opt/galaxy/pkg/ge6.2u5"
P_SGE_CELL = "/opt/sge/default/spool/qmaster"
P_PSQL_DIR = "/mnt/galaxyData/pgsql/data"

try:
    # Get only the first 3 chars of the version since that's all that's used for dir name
    pg_ver = load = (commands.getoutput("dpkg -s postgresql | grep Version | cut -f2 -d':'")).strip()[:3]
    P_PG_HOME = "/usr/lib/postgresql/{0}/bin".format(pg_ver)
except Exception, e:
    P_PG_HOME = "/usr/lib/postgresql/9.1/bin"
    print "[paths.py] Exception setting PostgreSQL path: {0}\nSet paths.P_PG_HOME to '{1}'"\
        .format(e, P_PG_HOME)


def get_path(name, default_path):
    try:
        path = misc.load_yaml_file(USER_DATA_FILE).get(name, None)
        if path is None:
            downloaded_pd_file = 'pd.yaml'
            if os.path.exists(downloaded_pd_file):
                path = misc.load_yaml_file(downloaded_pd_file).get(name, \
                  default_path)
        else:
            path = default_path
    except:
        path = default_path
    return path


P_MOUNT_ROOT = "/mnt"
P_GALAXY_TOOLS = get_path("galaxy_data", os.path.join(P_MOUNT_ROOT, "galaxyTools"))
P_GALAXY_HOME = get_path("galaxy_home", os.path.join(P_GALAXY_TOOLS, "galaxy-central"))
P_GALAXY_DATA = get_path("galaxy_data", os.path.join(P_MOUNT_ROOT, 'galaxyData'))
P_GALAXY_INDICES = get_path("galaxy_indices", os.path.join(P_MOUNT_ROOT, "galaxyIndices"))

IMAGE_CONF_SUPPORT_FILE = os.path.join(P_BASE_INSTALL_DIR, 'imageConfig.yaml')
