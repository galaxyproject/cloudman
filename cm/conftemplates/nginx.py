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
    }
}
"""

# Template for nginx v1.4+
NGINX_14_CONF_TEMPLATE = """worker_processes  2;

events {
    worker_connections  1024;
}

http {
    include       mime.types;
    default_type  application/octet-stream;
    sendfile        on;
    keepalive_timeout  65;
    index   index.html index.php index.htm;

    gzip  on;
    gzip_http_version 1.1;
    gzip_vary on;
    gzip_comp_level 4;
    gzip_proxied any;
    gzip_types text/plain text/css application/x-javascript text/xml application/xml text/javascript application/json;
    gzip_buffers 16 8k;
    gzip_disable "MSIE [1-6].(?!.*SV1)";

    upstream galaxy_app {
        server localhost:8080;
    }

    upstream cm_app {
        server localhost:42284;
    }

    upstream galaxy_reports_app {
        server localhost:9001;
    }

    upstream vnc_app {
        server localhost:6080;
    }

    server {
        listen 80;
        client_max_body_size 2048m;
        server_name localhost;
        proxy_read_timeout 600;

        include commandline_utilities_http.conf;

        location /cloud {
            auth_pam    "Secure Zone";
            auth_pam_service_name   "nginx";
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

        location /reports {
            auth_pam    "Secure Zone";
            auth_pam_service_name   "nginx";
            rewrite ^/reports/(.*) /$$1 break;
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

        # VNC & noVNC settings
        location ~ /vnc {
            auth_pam    "Secure Zone";
            auth_pam_service_name   "nginx";
            rewrite ^(.*[^/])$$ $$1/ permanent; # redirect if no trailing slash
            rewrite ^/vnc(.*) //$$1 break;
            proxy_pass http://vnc_app;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $$http_upgrade;
            proxy_set_header Connection "upgrade";
            proxy_set_header Host $$host;
        }
        location ~ /websockify {
            proxy_pass http://vnc_app;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $$http_upgrade;
            proxy_set_header Connection "upgrade";
        }


        location /gvl-scf {
            alias /home/ubuntu/www;
            index index.php;
            rewrite ^ /gvl-scf/index.php;

            # This is cool because no php is touched for static content
            try_files $$uri @rewrite;
            location ~* \.(jpg|jpeg|gif|png|bmp|ico|pdf|flv|swf|exe|html|htm|txt|css|js) {
                alias /home/ubuntu/www$$fastcgi_script_name;
                expires           1d;
            }
#           rewrite ^/(.*)$$ /gvl-scf/index.php?q=$$1;

            location ~ \.php$$ {
                alias /home/ubuntu/www;
                try_files $$uri =404;
                fastcgi_split_path_info ^(.+\.php)(/.+)$$;
                fastcgi_pass unix:/var/run/php5-fpm.sock;
                #fastcgi_pass localhost:9000;
                fastcgi_index index.php;
                include fastcgi_params;
                fastcgi_read_timeout 900;
                fastcgi_param  SCRIPT_FILENAME  $$document_root$$fastcgi_script_name;

           }

        }

        location @rewrite {
         # Some modules enforce no slash (/) at the end of the URL
         # Else this rewrite block wouldn't be needed (GlobalRedirect)
             #root /home/ubuntu/www;
             rewrite ^/(.*)$$ /gvl-scf/index.php?q=$$1;
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

    }

    server {
        listen                  443 ssl;
        client_max_body_size    2048m;
        server_name             localhost;
        proxy_read_timeout      600;

        include commandline_utilities_https.conf;
    }

}
"""
