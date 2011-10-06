import os

# Commands
P_MKDIR = "/bin/mkdir"
P_RM = "/bin/rm"
P_CHOWN = "/bin/chown"
P_SU = "/bin/su"
P_MV = "/bin/mv"
P_LN = "/bin/ln"

# Paths
P_BASE_INSTALL_DIR = '/opt/galaxy/pkg'
P_SGE_ROOT = "/opt/sge"
P_SGE_TARS = "/opt/galaxy/pkg/ge6.2u5"
P_SGE_CELL = "/opt/sge/default/spool/qmaster"
P_PSQL_DIR  = "/mnt/galaxyData/pgsql/data"
P_PG_HOME = "/usr/lib/postgresql/8.4/bin"
P_GALAXY_HOME = "/mnt/galaxyTools/galaxy-central"

P_GALAXY_DATA = "/mnt/galaxyData"
P_GALAXY_TOOLS = "/mnt/galaxyTools"
P_GALAXY_INDICES = "/mnt/galaxyIndices"

# Configs
C_PSQL_PORT = "5840"
USER_DATA_FILE = "userData.yaml"
IMAGE_CONF_SUPPORT_FILE = os.path.join(P_BASE_INSTALL_DIR, 'imageConfig.yaml')