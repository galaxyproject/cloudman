<%inherit file="/base_panels.mako"/>
<%def name="main_body()">
    <div class="body" style="max-width: 720px; margin: 0 auto;">
        <div id="msg_box" class="info_msg_box" style="margin-top: -25px; min-height: 16px">
            <span id="msg" class="info_msg_box_content" style="display: none"></span>
        </div>
        <%include file="bits/messages.html" />
        <h2>CloudMan Admin Console</h2>
        <div id="main_text">
            This admin panel is a convenient way to gain insight into the status
            of individual CloudMan services as well as to control those services.<br/>
            <b>Services should not be manipulated unless absolutely necessary.
            Please keep in mind that the actions performed by these service-control
            'buttons' are basic in that they assume things will operate as expected.
            In other words, minimal special case handling for recovering services
            exists. Also note that clicking on a service action button will
            initiate the action; there is no additional confirmation required.</b>
        </div>
        <h3>Galaxy controls</h3>
        <div class="help_text">
            Use these controls to administer functionality of Galaxy.
        </div>
        <ul class='services_list'>
            <li><span id='galaxy_dns'>Galaxy is currently inaccessible</span></li>
            <li>Current Galaxy admins: <span id="galaxy_admins">N/A</span></li>
            <li>Add Galaxy admin users
                <span class="help_info">
                    <span class="help_link">What will this do?</span>
                    <div class="help_content" style="display: none">
                        Add Galaxy admin users to Galaxy. This action simply
                        adds users' emails to Galaxy's universe_wsgi.ini file
                        and does not check of the users exist or register new
                        users. Note that this action implies restarting Galaxy.
                    </div>
                </span>
                <form class="generic_form" action="${h.url_for(controller='root', action='add_galaxy_admin_users')}" method="post">
                    <input type="text" value="CSV list of emails to be added as admins" class="form_el" name="admin_users" size="45">
                    <input type="submit" value="Add admin users">
                </form>
            </li>
            <li>Running Galaxy at revision: <span id="galaxy_rev">N/A</span></li>
            <li>Update Galaxy from a provided repository
                <span class="help_info">
                    <span class="help_link">What will this do?</span>
                    <div class="help_content" style="display: none">
                        Update Galaxy source code from the repository provided
                        in the form field. The repository can be the default
                        <i>galaxy-central</i> or any other compatible branch.<br />
                        Note that the update will be applied to the current
                        instance only and upon termination of the cluster, the
                        update will be reverted; the analysis results
                        will be preserved. As a result, any analyses that depend
                        on the updated functionality may not be preroducible
                        on the new instance wihtout performing the update again.
                        See <a href="https://bitbucket.org/galaxy/galaxy-central/wiki/Cloud/CustomizeGalaxyCloud" target="_blank">
                        this page</a> about instructions on how to preserve the
                        changes.<br />This action will:
                        <ol>
                            <li>Stop Galaxy service</li>
                            <li>Pull and apply any changes from the provided repository.
                            If there are conflicts during the merge, local changes
                            will be preserved.</li>
                            <li>Call Galaxy database migration script</li>
                            <li>Start Galaxy service</li>
                        </ol>
                    </div>
                </span>
                <form class="generic_form" action="${h.url_for(controller='root', action='update_galaxy')}" method="post">
                    <input type="text" value="http://bitbucket.org/galaxy/galaxy-dist" class="form_el" name="repository" size="45">
                    <input type="submit" value="Update Galaxy">
                </form>
            </li>
        </ul>
        <h3>Services controls</h3>
        <div class="help_text">
            Use these controls to administer individual application services managed by CloudMan.
            Currently running a '<a href="http://wiki.g2.bx.psu.edu/Admin/Cloud"
            target='_blank'>${initial_cluster_type}</a>' type of cluster.
        </div>
        <table width="700px" style="margin:10px 0;">
            <tr style="text-align:left">
                <th width="20%">Service name</th>
                <th width="15%">Status</th>
                <th width="65%" colspan="6"></th>
            </tr>
            <tr>
                <td>Galaxy</td>
                <td><span id="galaxy_status">&nbsp;</span></td>
                <td><a href="${h.url_for(controller='root',action='service_log')}?service_name=Galaxy">Log</a></td>
                <td><a class='action' href="${h.url_for(controller='root',action='manage_service')}?service_name=Galaxy&to_be_started=False" target='_blank'>Stop</a></td>
                <td><a class='action' href="${h.url_for(controller='root',action='manage_service')}?service_name=Galaxy" target="_blank">Start</a></td>
                <td><a class='action' href="${h.url_for(controller='root',action='restart_service')}?service_name=Galaxy" target="_blank">Restart</a></td>
                <td><a class='action' href="${h.url_for(controller='root',action='update_galaxy')}?db_only=True" target='_blank'>Update DB</a></td>
            </tr>
            <tr>
                <td>PostgreSQL</td>
                <td><span id="postgres_status">&nbsp;</span></td>
                <td><a href="${h.url_for(controller='root',action='service_log')}?service_name=Postgres">Log</a></td>
                <td><a class='action' href="${h.url_for(controller='root',action='manage_service')}?service_name=Postgres&to_be_started=False" target="_blank">Stop</a></td>
                <td><a class='action' href="${h.url_for(controller='root',action='manage_service')}?service_name=Postgres" target="_blank">Start</a></td>
                <td><a class='action' href="${h.url_for(controller='root',action='restart_service')}?service_name=Postgres" target="_blank">Restart</a></td>
            </tr>
            <tr>
                <td>SGE</td>
                <td><span id="sge_status">&nbsp;</span></td>
                <td><a href="${h.url_for(controller='root',action='service_log')}?service_name=SGE">Log</a></td>
                <td><a class='action' href="${h.url_for(controller='root',action='manage_service')}?service_name=SGE&to_be_started=False" target="_blank">Stop</a></td>
                <td><a class='action' href="${h.url_for(controller='root',action='manage_service')}?service_name=SGE" target="_blank">Start</a></td>
                <td><a class='action' href="${h.url_for(controller='root',action='restart_service')}?service_name=SGE" target="_blank">Restart</a></td>
                <td><a href="${h.url_for(controller='root',action='service_log')}?service_name=SGE&q=conf">Q conf</a></td>
                <td><a href="${h.url_for(controller='root',action='service_log')}?service_name=SGE&q=qstat">qstat</a></td>
            </tr>
            <tr>
                <td>LWR</td>
                <td><span id="lwr_status">&nbsp;</span></td>
                <td><a href="${h.url_for(controller='root',action='service_log')}?service_name=LWR">Log</a></td>
                <td><a class='action' href="${h.url_for(controller='root',action='manage_service')}?service_name=LWR&to_be_started=False" target="_blank">Stop</a></td>
                <td><a class='action' href="${h.url_for(controller='root',action='manage_service')}?service_name=LWR" target="_blank">Start</a></td>
                <td><a class='action' href="${h.url_for(controller='root',action='restart_service')}?service_name=LWR" target="_blank">Restart</a></td>
            </tr>

            <tr>
                <td>Galaxy Reports</td>
                <td><span id="galaxy_reports_status">&nbsp;</span></td>
                <td><a href="${h.url_for(controller='root',action='service_log')}?service_name=GalaxyReports">Log</a></td>
                <td><a class='action' href="${h.url_for(controller='root',action='manage_service')}?service_name=GalaxyReports&to_be_started=False" target="_blank">Stop</a></td>
                <td><a class='action' href="${h.url_for(controller='root',action='manage_service')}?service_name=GalaxyReports" target="_blank">Start</a></td>
                <td><a class='action' href="${h.url_for(controller='root',action='restart_service')}?service_name=GalaxyReports" target="_blank">Restart</a></td>
            </tr>

            ##<tr>
            ##    <td>Dummy</td>
            ##    <td><span id="dummy"></span></td>
            ##</tr>
        </table>
        <strong>File systems</strong>
        ## backbone-managed
        <div id='fs-details-container'></div>
        <div id="filesystems-container"></div>
        <div id='fs-resize-form-container'></div>
        <div id='fs-add-container'>
            <div id='fs-add-form'></div>
            <div id='fs-add-btn'><span class="plus-sign">+</span> Add new</div>
        </div>

        <h3>System controls</h3>
        <div class="help_text">
            Use these controls to administer CloudMan itself as well as the underlying system.
        </div>
        <ul class='services_list'>
            <li>Command used to connect to the instance: <div class="code">ssh -i <i>[path to ${key_pair_name} file]</i> ubuntu@${ip}</div></li>
            <li>Name of this cluster's bucket: ${bucket_cluster}
                %if cloud_type == 'ec2':
                    (<a id='cloudman_bucket' href="https://console.aws.amazon.com/s3/home?#"
                      target="_blank">access via AWS console</a>)
                %endif
                <span class="help_info">
                    <span class="help_link">Bucket info</span>
                    <div class="help_content" style="display: none">
                        Each CloudMan cluster has its configuration saved in a persistent
                        data repository. This repository is read at cluster start and it
                        holds all the data required to restart this same cluster. The
                        repository is stored under your cloud account and is accessible
                        only with your credentials. <br/>
                        In the context of AWS, S3 acts as a persistent data repository where
                        all the data is stored in an S3 bucket. The name of the bucket
                        provided here corresponds to the current cluster and is provided
                        simply as a reference.
                    </div>
                </span>
            <li><a id='show_user_data' href="${h.url_for(controller='root', action='get_user_data')}">Show current user data</a></li>
            <li><a id='cloudman_log' href="${h.url_for(controller='root', action='service_log')}?service_name=CloudMan">Show CloudMan log</a></li>
            </li>
            <li>
                <a class="action" id="master_is_exec_host" href="${h.url_for(controller='root', action='toggle_master_as_exec_host')}">&nbsp;</a>
                <span class="help_info">
                    <span class="help_link">What will this do?</span>
                    <div class="help_content" style="display: none">
                        By default, the master instance running all the services is also configured to
                        execute jobs. You may toggle this functionality here. Note that if job execution
                        on the master is disabled, at least one worker instance will be required to
                        run any jobs.
                    </div>
                </span>
            </li>
            <li>
                <a class='action' href="${h.url_for(controller='root', action='store_cluster_config')}">Store current cluster configuration</a>
                <span class="help_info">
                    <span class="help_link">What will this do?</span>
                    <div class="help_content" style="display: none">
                        Each CloudMan cluster has its own configuration. The state of
                        this cofiguration is saved as 'persistent_data.yaml'
                        file in the cluster's bucket. Saving of this file
                        happens automatically on cluster configuration change.
                        This link allows you to force the update of the cluster
                        configuration and capture its current state.
                    </div>
                </span>
            </li>
            <li>
                <a class='action' href="${h.url_for(controller='root', action='reboot')}">Reboot master instance</a>
                <span class="help_info">
                    <span class="help_link">What will this do?</span>
                    <div class="help_content" style="display: none">
                        Reboot the entire system. This will shut down all of the
                        services and reboot the machine. If there are any worker
                        nodes assciated with the cluster they will be reconnected
                        to after the system comes back up.
                    </div>
                </span>
            </li>
            <li>
                <a class='action' href="${h.url_for(controller='root', action='recover_monitor')}">Recover monitor</a>
                <span class="help_info">
                    <span class="help_link">What will this do?</span>
                    <div class="help_content" style="display: none">
                        Try to (re)start CloudMan service monitor thread, which is
                        responsible for monitoring the status of all of the other
                        services. This should only be used if the CloudMan user
                        interface becomes unresponsive or during debugging.
                    </div>
                </span>
            </li>
            <li>
                <a class='action' href="${h.url_for(controller='root', action='recover_monitor')}?force=True">Recover monitor *with Force*</a>
                <span class="help_info">
                    <span class="help_link">What will this do?</span>
                    <div class="help_content" style="display: none">
                        Start a new CloudMan service monitor thread regardless
                        of if one already exists.
                    </div>
                </span>
            </li>
        </ul>

        ## ****************************************************************************
        ## ********************************* Overlays *********************************
        ## ****************************************************************************
        ## Overlay that prevents any future clicking, see CSS
        <div id="snapshotoverlay" style="display:none"></div>
        <div class="overlay" id="overlay" style="display:none"></div>
        ## Indicate an action has been recorded
        <div class="box" id="action_initiated" style="height: 90px; text-align: center;">
            <h2>Action initiated.</h2>
        </div>
        <div class="box" id="user_data">
            <a class="boxclose"></a>
            <h2>User data</h2>
            <pre>
                <div style="font-size: 10px" id="user_data_content"></div>
            </pre>
        </div>
        ## Overlay for managing filesystems
        <div class="box" id="add_fs_overlay">
            <a class="boxclose"></a>
            <div id="fs_accordion">
                <h3><a href="#">Available file systems</a></h3>
                <div id='available_fs_list'>
                    ##<p>Retrieving the list of available file systems...</p>
                    ##<div class="spinner">&nbsp;</div>
                    <div class="warningmessage">Sorry but this functionality is not yet available.<br/>
                        Adding file systems is though.
                    </div>
                </div>
                <h3><a href="#">Add a new file system</a></h3>
                <div><form id="add_fs_form" name="add_fs_form" action="${h.url_for(controller='root', action='add_fs')}" method="post">
                    <div class="form-row">
                        <p>This form allows you to add an additional data source
                        and make it available as a local file system. Currently,
                        adding S3 buckets as a data source is the only supported
                        functionality. These buckets may be public or private (and
                        owned by the user running this cluster).
                        Once added, the file system will be available
                        on the underlying system under <span class="code">
                        /mnt/[bucket_name]</span> path.</p>
                    </div>
                    <div id="fs_bucket">
                        <div class="form-row">
                            Bucket name:
                            <input type="text" id="fs_bucket_name" name="bucket_name" value='1000genomes' size="50"/>
                        </div>
                        %if cloud_type != 'ec2':
                            <div class="form-row">
                                <p>
                                It appears you are not running on the AWS cloud. CloudMan supports
                                using only buckets from AWS S3. So, if the bucket you are trying to
                                use is NOT PUBLIC, you must provide the AWS credentials that can be
                                used to access this bucket. If the bucket you are trying to use
                                IS PUBLIC, leave below fields empty.
                                </p>
                            </div> <div class="form-row">
                                AWS access key:
                                <input type="text" id="bucket_a_key" name="bucket_a_key" size="50"/>
                            </div> <div class="form-row">
                                AWS secret key:
                                <input type="text" id="bucket_s_key" name="bucket_s_key" size="50"/>
                            </div>
                        %endif
                    </div>
                    <input type="submit" value="Add a file system"/>
                </form></div>
            </div>
        </div>

    ## ****************************************************************************
    ## ******************************** Javascript ********************************
    ## ****************************************************************************
    <script type='text/javascript'>
        // Place URLs here so that url_for can be used to generate them
        var get_all_services_status_url = "${h.url_for(controller='root',action='get_all_services_status')}";
        var get_all_filesystems_url = "${h.url_for(controller='root',action='get_all_filesystems')}";
        var manage_service_url = "${h.url_for(controller='root',action='manage_service')}";
        var update_fs_url = "${h.url_for(controller='root', action='update_file_system')}";
        var resize_fs_url = "${h.url_for(controller='root',action='expand_user_data_volume')}";
        var add_fs_url = "${h.url_for(controller='root',action='add_file_system')}";
        var cloud_type = "${cloud_type}";
    </script>
    <script type="text/template" id="fileSystems-template">
        <thead>
            <tr class="filesystem-tr">
                <th class="fs-td-20pct">Name</th>
                <th class="fs-td-15pct">Status</th>
                <th class="fs-td-20pct">Usage</th>
                <th class="fs-td-15pct">Controls</td>
                <th colspan="2"></th>
            </tr>
        </thead>
        <tbody></tbody>
    </script>
    <script type="text/template" id="fs-details-template">
    <%text filter='trim'>
        <a class="close"></a>
        <div class="fs-details-box-header">File system information</div>
        <table>
        <tr><th>Name:</th><td><%= name %></td>
        <% if (typeof(bucket_name) != "undefined" && typeof(bucket_name) != 'object') {
            // There's a bucket_name input field defined on the page so must guard from it above
        %>
            <tr><th>Bucket name:</th><td><%= bucket_name %></td>
        <% } %>
        <tr><th>Status:</th><td><%= status %></td>
        <tr><th>Mount point:</th><td><%= mount_point %></td>
        <tr><th>Kind:</th><td><%= kind %></td>
        <% if (typeof(volume_id) != "undefined") { %>
            <tr><th>Volume:</th><td><%= volume_id %></td>
        <% } %>
        <% if (typeof(device) != "undefined") { %>
            <tr><th>Device:</th><td><%= device %></td>
        <% } %>
        <% if (typeof(from_snap) != "undefined") { %>
            <tr><th>From snapshot:</th><td><%= from_snap %></td>
        <% } %>
        <tr><th>Size (used/total):</th><td><%= size_used %>/<%= size %> (<%= size_pct %>)</td>
        <tr><th>Delete on termination:</th><td><%= DoT %></td>
        <tr><th>Persistent:</th><td><%= persistent %></td>
    </%text>
    </script>
    <script type="text/template" id="fileSystem-template">
    <%text filter='trim'>
        <td class="fs-td-20pct"><%= name %></td>
        <td class="fs-status fs-td-15pct"><%= status %></td>
        <td class="fs-td-20pct" style="font-size: 9px;">
        <!-- // Only display usage when the file system is 'Available' -->
        <style type="text/css">
            /* Styling for the space usage meter element */
            .space_usage {
                text-align: center;
                padding: 2px 2px 2px 2px;
            }

            /* The percentage */
            #fs-meter-<%= name %>:after {
                content: "<%= size_used %>/<%= size %> (<%= size_pct %>%)";
            }
        </style>
        <% if (status === "Available" || status === "Running") { %>
            <meter id="fs-meter-<%= name %>" class="space_usage" min="0" max="100" value="<%= size_pct %>" high="85">
                <%= size_used %>/<%= size %> (<%= size_pct %>%)
            </meter>
        <% } else if (kind == "Volume" && status === "Configuring") { %>
            <% if (snapshot_status != "" && snapshot_status != null) { %>
                Snapshot status: <%= snapshot_status %>; progress: <%= snapshot_progress %>
            <% } %></td>
        <% } %></td>
        <td class="fs-td-15pct">
            <!-- // Enable removal while a file system is 'Available' or 'Error' -->
            <% if (status === "Available" || status === "Running" || status === 'Error') { %>
            <a class="fs-remove icon-button" id="fs-<%= name %>-remove"
                href="</%text>${h.url_for(controller='root',action='manage_service')}<%text filter='trim'>?service_name=<%= name %>&to_be_started=False&is_filesystem=True"
                title="Remove this file system"></a>
            <% } %>
            <!--// Only display additional controls when the file system is 'Available'-->
            <% if (status === "Available" || status === "Running") { %>
                <!-- // It only makes sense to persist DoT, snapshot-based file systems -->
                <% if (typeof(from_snap) !== "undefined" && typeof(DoT) !== "undefined" && DoT === "Yes") { %>
                    <a class="fs-persist icon-button" id="fs-<%= name %>-persist"
                        href="</%text>${h.url_for(controller='root', action='update_file_system')}<%text filter='trim'>?fs_name=<%= name %>" title="Persist file system changes"></a>
                <% } %>
                <!-- // It only makes sense to resize volume-based file systems -->
                <% if (typeof(kind) != "undefined" && kind === "Volume" ) { %>
                    <a class="fs-resize icon-button" id="fs-<%= name %>-resize" href="#" title="Increase file system size"></a>
                <% } %>
        <% } %></td>
        <td class="fs-td-15pct">
            <a href="#" class="fs-details" details-box="fs-<%= name %>-details">Details</a>
        </td>
        <td class="fs-td-spacer"></td>
    </%text>
    </script>
    <script type="text/template" id="fs-resize-template">
    <%text filter='trim'>
        <div class="form-row">
            Through this form you may increase the disk space available to this file system.
            Any services using this file system <b>WILL BE STOPPED</b>
            until the new disk is ready, at which point they will all be restarted. Note
            that This may result in failure of any jobs currently running. Note that the new
            disk size <b>must be larger</b> than the current disk size.
            <p>During this process, a snapshot of your data volume will be created,
            which can optionally be left in your account. If you decide to leave the
            snapshot for reference, you may also provide a brief note that will later
            be visible in the snapshot's description.</p>
        </div>
        <div class="form-row">
            <label>New disk size (minimum <span id="du-inc"><%= size %></span>B,
            maximum 1000GB)</label>
            <div id="permanent_storage_size" class="form-row-input">
                <input type="text" name="new_vol_size" id="new_vol_size"
                placeholder="Greater than <%= size %>B" size="25">
            </div>
            <label>Note</label>
            <div id="permanent_storage_size" class="form-row-input">
                <input type="text" name="vol_expand_desc" id="vol_expand_desc" value=""
                placeholder="Optional snapshot description" size="50"><br/>
            </div>
            <label>or delete the created snapshot after filesystem resizing?</label>
            <input type="checkbox" name="delete_snap" id="delete_snap"> If checked,
            the created snapshot will not be kept
            <div class="form-row">
                <input type="submit" class="fs-form-submit-button" value="Resize <%= name %> file system"/>
                or <a class="fs-resize-form-close" href="#">cancel</a>
            </div>
            <input name="fs_name" type="text" hidden="Yes" value="<%= name %>" />
        </div>
    </%text>
    </script>
    <script type='text/javascript' src="${h.url_for('/static/scripts/jquery.form.js')}"></script>
    <script src="//ajax.googleapis.com/ajax/libs/jqueryui/1.8.23/jquery-ui.min.js"></script>
    <script type='text/javascript' src="${h.url_for('/static/scripts/jquery.tipsy.js')}"></script>
    <script type='text/javascript' src="${h.url_for('/static/scripts/underscore-min.js')}"></script>
    <script type='text/javascript' src="${h.url_for('/static/scripts/backbone-min.js')}"></script>
    <script type='text/javascript' src="${h.url_for('/static/scripts/backbone.marionette.js')}"></script>
    <script type='text/javascript' src="${h.url_for('/static/scripts/Backbone.ModalDialog.js')}"></script>
    <script type='text/javascript' src="${h.url_for('/static/scripts/admin.js')}"></script>
</%def>
