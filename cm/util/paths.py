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
LOGIN_SHELL_SCRIPT = "/etc/profile"

# Paths
P_BASE_INSTALL_DIR = '/opt/galaxy/pkg'
P_SGE_ROOT = "/opt/sge"
P_SGE_TARS = "/opt/galaxy/pkg/ge6.2u5"
P_SGE_CELL = "/opt/sge/default/spool/qmaster"
P_PSQL_DIR  = "/mnt/galaxyData/pgsql/data"
P_PG_HOME = "/usr/lib/postgresql/8.4/bin"
try:
    default_galaxy_home = "/mnt/galaxyTools/galaxy-central"
    # See if custom galaxy_home was specified as part of user data
    P_GALAXY_HOME = misc.load_yaml_file(USER_DATA_FILE).get('galaxy_home', None)
    # See if custom galaxy_home has been set on earlier invocations of the cluster
    # pd.yaml is the persistend_data.yaml file initially downloaded from cluster's
    # bucket. Also see app.py
    if P_GALAXY_HOME is None:
        downloaded_pd_file = 'pd.yaml'
        if os.path.exists(downloaded_pd_file):
            P_GALAXY_HOME = misc.load_yaml_file(downloaded_pd_file).get('galaxy_home', \
                default_galaxy_home)
        else:
            print "'{0}' not found at paths.py load!".format(downloaded_pd_file)
            P_GALAXY_HOME = default_galaxy_home
    print "Set paths.P_GALAXY_HOME as '{0}'".format(P_GALAXY_HOME)
except Exception, e:
    P_GALAXY_HOME = default_galaxy_home
    print "(paths.py) Issue checking for custom galaxy_home in user data: {0}".format(e)

P_GALAXY_DATA = "/mnt/galaxyData"
P_GALAXY_TOOLS = "/mnt/galaxyTools"
P_GALAXY_INDICES = "/mnt/galaxyIndices"

IMAGE_CONF_SUPPORT_FILE = os.path.join(P_BASE_INSTALL_DIR, 'imageConfig.yaml')