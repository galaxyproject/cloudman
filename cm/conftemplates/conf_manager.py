import os
from string import Template

CONF_TEMPLATE_DEFAULT_PATH = "/mnt/cm/cm/conftemplates/"
CONF_TEMPLATE_OVERRIDE_PATH = "/opt/cloudman/config/conftemplates/"

HTCONDOR_MASTER_CONF_TEMPLATE = "condor_master_config"
HTCONDOR_WOORKER_CONF_TEMPLATE = "condor_worker_config"

NGINX_CONF_TEMPLATE = "nginx.conf"
NGINX_14_CONF_TEMPLATE = "nginx1.4.conf"
NGINX_SERVER = "nginx_server"
NGINX_SERVER_SSL = "nginx_server_ssl"
NGINX_DEFAULT = "nginx_default_locations"
NGINX_SERVER_PULSAR = "nginx_server_pulsar"
NGINX_GALAXY_REPORTS = "nginx_galaxy_reports_locations"
NGINX_GALAXY = "nginx_galaxy_locations"
NGINX_CLOUDERA_MANAGER = "nginx_cloudera_manager_locations"
NGINX_CLOUDGENE = "nginx_cloudgene_locations"

PROFTPD_CONF_TEMPLATE = "proftpd.conf"
SGE_INSTALL_TEMPLATE = "sge_install_template"
SGE_HOST_CONF_TEMPLATE = "sge_host_conf_template"
SGE_ALL_Q_TEMPLATE = "sge_all.q.conf"
SGE_SMP_PE = "sge_smp_pe"
SGE_MPI_PE = "sge_mpi_pe"
SGE_REQUEST_TEMPLATE = "sge_request_template"
SLURM_CONF_TEMPLATE = "slurm.conf"

SUPERVISOR_TEMPLATE = "supervisord.conf"


def find_conf_template(conf_file_name):
    """
    Checks whether an overridden template exists, or falls back to the default template if not
    """
    filepath = os.path.join(CONF_TEMPLATE_OVERRIDE_PATH, conf_file_name)
    if not os.path.exists(filepath):
        return os.path.join(CONF_TEMPLATE_DEFAULT_PATH, conf_file_name + ".default")
    else:
        return filepath

def load_conf_template(conf_file_name):
    """Loads and returns the given text file as a string Template.
    The file will be loaded from CONF_TEMPLATE_OVERRIDE_PATH first, but if it does
    not exist, it will append the .default extension and load that file from
    the CONF_TEMPLATE_DEFAULT_PATH instead.

    Positional arguments:
    conf_file_name -- The name of the conf template
    """
    filepath = find_conf_template(conf_file_name)
    return Template(open(filepath, 'r').read())
