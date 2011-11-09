import os
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

# Paths
P_BASE_INSTALL_DIR = '/opt/galaxy/pkg'
P_SGE_ROOT = "/opt/sge"
P_SGE_TARS = "/opt/galaxy/pkg/ge6.2u5"
P_SGE_CELL = "/opt/sge/default/spool/qmaster"
P_PSQL_DIR  = "/mnt/galaxyData/pgsql/data"
P_PG_HOME = "/usr/lib/postgresql/8.4/bin"
try:
    P_GALAXY_HOME = misc.load_yaml_file(USER_DATA_FILE).get('galaxy_home', \
        "/mnt/galaxyTools/galaxy-central")
except Exception, e:
    P_GALAXY_HOME = "/mnt/galaxyTools/galaxy-central"
    print "(paths.py) Issue checking for custom galaxy_home in user data: {0}".format(e)

P_GALAXY_DATA = "/mnt/galaxyData"
P_GALAXY_TOOLS = "/mnt/galaxyTools"
P_GALAXY_INDICES = "/mnt/galaxyIndices"

IMAGE_CONF_SUPPORT_FILE = os.path.join(P_BASE_INSTALL_DIR, 'imageConfig.yaml')