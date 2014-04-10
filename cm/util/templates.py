HTCONDOR_MASTER_CONF_TEMPLATE = """
## USER defined bits
FLOCK_TO=$flock_host
HIGHPORT=9700
LOWPORT=9600
START=true
SUSPEND=false
"""
HTCONDOR_WOORKER_CONF_TEMPLATE = """
## USER defined bits
CONDOR_HOST=$host
HIGHPORT=9700
LOWPORT=9600
DAEMON_LIST=MASTER, STARTD, SCHEDD
"""


SGE_INSTALL_TEMPLATE = \
    """SGE_ROOT="/opt/sge"
SGE_QMASTER_PORT="6444"
SGE_EXECD_PORT="6445"
SGE_ENABLE_SMF="false"
SGE_CLUSTER_NAME="$cluster_name"
SGE_JMX_PORT=""
SGE_JMX_SSL="false"
SGE_JMX_SSL_CLIENT="false"
SGE_JMX_SSL_KEYSTORE=""
SGE_JMX_SSL_KEYSTORE_PW=""
SGE_JVM_LIB_PATH=""
SGE_ADDITIONAL_JVM_ARGS=""
CELL_NAME="default"
ADMIN_USER=""
QMASTER_SPOOL_DIR="/opt/sge/default/spool/qmaster"
EXECD_SPOOL_DIR="/opt/sge/default/execd/spool"
GID_RANGE="20000-20100"
SPOOLING_METHOD="classic"
DB_SPOOLING_SERVER="none"
DB_SPOOLING_DIR="/opt/sge/default/spooldb"
PAR_EXECD_INST_COUNT="20"
ADMIN_HOST_LIST="$admin_host_list"
SUBMIT_HOST_LIST="$submit_host_list"
EXEC_HOST_LIST="$exec_host_list"
EXECD_SPOOL_DIR_LOCAL=""
HOSTNAME_RESOLVING="$hostname_resolving"
SHELL_NAME="ssh"
COPY_COMMAND="scp"
DEFAULT_DOMAIN="none"
ADMIN_MAIL="none"
ADD_TO_RC="false"
SET_FILE_PERMS="true"
RESCHEDULE_JOBS="wait"
SCHEDD_CONF="1"
SHADOW_HOST=""
EXEC_HOST_LIST_RM=""
REMOVE_RC="false"
WINDOWS_SUPPORT="false"
WIN_ADMIN_NAME="Administrator"
WIN_DOMAIN_ACCESS="false"
CSP_RECREATE="true"
CSP_COPY_CERTS="false"
CSP_COUNTRY_CODE="DE"
CSP_STATE="Germany"
CSP_LOCATION="Building"
CSP_ORGA="Organisation"
CSP_ORGA_UNIT="Organisation_unit"
CSP_MAIL_ADDRESS="name@yourdomain.com"
"""

SGE_HOST_CONF_TEMPLATE = """
hostname %s
load_scaling NONE
complex_values NONE
user_lists NONE
xuser_lists NONE
projects NONE
xprojects NONE
usage_scaling NONE
report_variables NONE

"""

ALL_Q_TEMPLATE = """
qname                 all.q
hostlist              @allhosts
seq_no                0
load_thresholds       np_load_avg=1.75
suspend_thresholds    NONE
nsuspend              1
suspend_interval      00:05:00
priority              0
min_cpu_interval      00:05:00
processors            UNDEFINED
qtype                 BATCH INTERACTIVE
ckpt_list             NONE
pe_list               make smp mpi
rerun                 FALSE
slots                 $slots
tmpdir                /mnt/galaxy/tmp
shell                 /bin/bash
prolog                $prolog_path
epilog                $epilog_path
shell_start_mode      posix_compliant
starter_method        NONE
suspend_method        NONE
resume_method         NONE
terminate_method      NONE
notify                00:00:60
owner_list            NONE
user_lists            NONE
xuser_lists           NONE
subordinate_list      NONE
complex_values        NONE
projects              NONE
xprojects             NONE
calendar              NONE
initial_state         default
s_rt                  INFINITY
h_rt                  INFINITY
s_cpu                 INFINITY
h_cpu                 INFINITY
s_fsize               INFINITY
h_fsize               INFINITY
s_data                INFINITY
h_data                INFINITY
s_stack               INFINITY
h_stack               INFINITY
s_core                INFINITY
h_core                INFINITY
s_rss                 INFINITY
h_rss                 INFINITY
s_vmem                INFINITY
h_vmem                INFINITY
"""

SMP_PE = """pe_name            smp
slots              999
user_lists         NONE
xuser_lists        NONE
start_proc_args    NONE
stop_proc_args     NONE
allocation_rule    $pe_slots
control_slaves     TRUE
job_is_first_task  FALSE
urgency_slots      min
accounting_summary FALSE
"""

MPI_PE = """pe_name           mpi
slots             999
user_lists        NONE
xuser_lists       NONE
start_proc_args   /opt/sge/mpi/startmpi.sh $pe_hostfile
stop_proc_args    /opt/sge/mpi/stopmpi.sh
allocation_rule   $round_robin
control_slaves    TRUE
job_is_first_task FALSE
urgency_slots     min
accounting_summary FALSE
"""

SGE_REQUEST_TEMPLATE = """
-b no
-shell yes
-v PATH=/opt/sge/bin/lx24-amd64:$psql_home:/usr/nginx/sbin:$galaxy_tools_dir/tools/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
-v DISPLAY=:42
"""

NGINX_CONF_TEMPLATE = """worker_processes  2;

events {
    worker_connections  1024;
}

http {
    include       mime.types;
    default_type  application/octet-stream;
    sendfile      on;
    keepalive_timeout  65;

    gzip  on;
    gzip_http_version 1.1;
    gzip_vary on;
    gzip_comp_level 4;
    gzip_proxied any;
    gzip_types text/plain text/css application/x-javascript text/xml application/xml text/javascript application/json;
    gzip_buffers 16 8k;
    gzip_disable "MSIE [1-6].(?!.*SV1)";

    upstream galaxy_app {
        $galaxy_server
    }

    upstream cm_app {
        server localhost:42284;
    }

    upstream galaxy_reports_app {
        server localhost:9001;
    }

    server {
        listen                  80;
        client_max_body_size    2048m;
        server_name             localhost;
        proxy_read_timeout      600;

        include commandline_utilities_http.conf;
        include galaxy_locations.conf

        location /cloud {
            proxy_pass  http://cm_app;
            proxy_set_header   X-Forwarded-Host $$host;
            proxy_set_header   X-Forwarded-For  $$proxy_add_x_forwarded_for;
            error_page   502    /errdoc/cm_502.html;
        }

        location /cloud/static {
            alias /mnt/cm/static;
            expires 24h;
        }

        location /cloud/static/style {
            alias /mnt/cm/static/style;
            expires 24h;
        }

        location /cloud/static/scripts {
            alias /mnt/cm/static/scripts;
            expires 24h;
        }
    }
}
"""

NGINX_GALAXY_CONF_TEMPLATE = """

        location /reports/ {
            rewrite ^/reports/(.*)$$ /reports/$$1/ break;
            proxy_pass http://galaxy_reports_app;
            proxy_set_header   X-Forwarded-Host $$host;
            proxy_set_header   X-Forwarded-For  $$proxy_add_x_forwarded_for;
        }

        location / {
            proxy_pass  http://galaxy_app;
            proxy_set_header   X-Forwarded-Host $$host;
            proxy_set_header   X-Forwarded-For  $$proxy_add_x_forwarded_for;
        }

        location /static {
            alias $galaxy_home/static;
            expires 24h;
        }

        location /static/style {
            alias $galaxy_home/static/june_2007_style/blue;
            expires 24h;
        }

        location /static/scripts {
            alias $galaxy_home/static/scripts/packed;
            expires 24h;
        }

        location /robots.txt {
            alias $galaxy_home/static/robots.txt;
        }

        location /favicon.ico {
            alias $galaxy_home/static/favicon.ico;
        }

        location /admin/jobs {
            proxy_pass  http://localhost:8079;
        }

        location /_x_accel_redirect/ {
            internal;
            alias /;
        }

        location /_upload {
            upload_store $galaxy_data/upload_store;
            upload_pass_form_field "";
            upload_set_form_field "__$${upload_field_name}__is_composite" "true";
            upload_set_form_field "__$${upload_field_name}__keys" "name path";
            upload_set_form_field "$${upload_field_name}_name" "$$upload_file_name";
            upload_set_form_field "$${upload_field_name}_path" "$$upload_tmp_path";
            upload_pass_args on;
            upload_pass /_upload_done;
        }

        location /_upload_done {
            set $$dst /tool_runner/index;
            if ($$args ~ nginx_redir=([^&]+)) {
                set $$dst $$1;
            }
            rewrite "" $$dst;
        }

        error_page   502    /errdoc/502.html;
        location /errdoc {
            root   html;
        }
"""
