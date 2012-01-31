<%inherit file="/base_panels.mako"/>
<%def name="main_body()">
    <div class="body" style="max-width: 720px; margin: 0 auto;">
        <div id="msg_box" class="info_msg_box" style="margin-top: -25px; min-height: 16px">
            <span id="msg" class="info_msg_box_content" style="display: none"></span>
        </div>        
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
                    <input type="text" value="http://bitbucket.org/galaxy/galaxy-central" class="form_el" name="repository" size="45">
                    <input type="submit" value="Update Galaxy">
                </form>
            </li>
        </ul>
        <h3>Services controls</h3>
        <div class="help_text">
            Use these controls to administer individual application services managed by CloudMan.
        </div>
        <table width="600px" style="margin:10px 0;">
            <tr style="text-align:left">
                <th width="15%">Name</th>
                <th width="30%">Status</th>
                <th colspan="4"></th>
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
                <td>File systems</td>
                <td><span id="filesystem_status">&nbsp;</span></td>
                <td>No logs</td>
            </tr>
        </table>
        <h3>System controls</h3>
        <div class="help_text">
            Use these controls to administer CloudMan itself as well as the underlying system.
        </div>
        <ul class='services_list'>
            <li>Command used to connect to the instance: <div class="code">ssh -i <i>[path to ${key_pair_name} file]</i> ubuntu@${ip}</div></li>
            <li><a id='show_user_data' href="${h.url_for(controller='root', action='get_user_data')}">Show current user data</a></li>
            <li><a id='cloudman_log' href="${h.url_for(controller='root', action='service_log')}?service_name=CloudMan">Show CloudMan log</a></li>
            <li>Name of the cluster's bucket: ${bucket_cluster}
                (<a id='cloudman_bucket' href="https://console.aws.amazon.com/s3/home?#" target="_blank">access via AWS console</a>)
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
            </li>
            %if filesystems:
                <li>Persist changes to file system:
                    %for fs in filesystems:
                        %if fs != 'galaxyData':
                            <a class='action' id="update_fs" href="${h.url_for(controller='root', action='update_file_system')}?fs_name=${fs}">
                                ${fs}</a>,
                        %endif
                    %endfor
                    <span class="help_info">
                        <span class="help_link">What will this do?</span>
                        <div class="help_content" style="display: none">
                            If you have made changes to any of the available 
                            file systems and would like to persist the changes
                            across cluster invocations, click on the name of the
                            desired file system and the cluster configuration
                            will be updated (all of the file systems are 
                            mounted on the system unter /mnt/[file system name]).
                            Note that depending on the amount of changes made to 
                            the underlying file system, this process may take a
                            long time. Also note that the user data file system cannot
                            be persistent through this method (it makes no logical
                            sense - use Share-an-instance functionality instead).
                        </div>
                    </span>
                    <span id='update_fs_status' style='color: #5CBBFF'>&nbsp;</span>
                </li>
            %endif
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

        ## Overlays
        ## Overlay that prevents any future clicking, see CSS
        <div id="snapshotoverlay" style="display:none"></div>
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

    ## Javascript
    <script type='text/javascript' src="${h.url_for('/static/scripts/jquery.form.js')}"></script>
    <script type="text/javascript">
        function update(repeat_update){
            $.getJSON("${h.url_for(controller='root',action='get_all_services_status')}",
                function(data){
                    if (data){
                        if (data.galaxy_rev != 'N/A') {
                            // This will always point to galaxy-central but better than nothing?
                            var rev_html = "<a href='http://bitbucket.org/galaxy/galaxy-central/changesets/"
                            + data.galaxy_rev.split(':')[1] + "' target='_blank'>"
                            + data.galaxy_rev + '</a>';
                        } else {
                            var rev_html = "N/A";
                        }
                        if (data.galaxy_dns == '#') {
                            var galaxy_dns = "Galaxy is currently inaccessible"
                        } else {
                            var galaxy_dns = "<a href='"+data.galaxy_dns+"' target='_blank'>Access Galaxy</a>"
                        }
                        $('#galaxy_dns').html(galaxy_dns);
                        $('#galaxy_admins').html(data.galaxy_admins);
                        $('#galaxy_rev').html(rev_html);
                        $('#galaxy_status').html(data.Galaxy);
                        $('#postgres_status').html(data.Postgres);
                        $('#sge_status').html(data.SGE);
                        $('#filesystem_status').html(data.Filesystem);
                        if (data.snapshot.status !== "None"){
                            $('#snapshotoverlay').show(); // Overlay that prevents any future clicking
                            $('#update_fs_status').html(" - Wait until the process completes. Status: <i>" +
                                data.snapshot.status + "</i>");
                        } else {
                            $('#update_fs_status').html("");
                            $('#snapshotoverlay').hide();
                        }
                        // Set color for services - `Running` is green, anything else is red
                        if (data.Galaxy == 'Running') {
                            $('#galaxy_status').css("color", "green");
                        }
                        else {
                            $('#galaxy_status').css("color", "red");
                        }
                        if (data.Postgres == 'Running') {
                            $('#postgres_status').css("color", "green");
                        }
                        else {
                            $('#postgres_status').css("color", "red");
                        }
                        if (data.SGE == 'Running') {
                            $('#sge_status').css("color", "green");
                        }
                        else {
                            $('#sge_status').css("color", "red");
                        }
                        if (data.Filesystem == 'Running') {
                            $('#filesystem_status').css("color", "green");
                        }
                        else {
                            $('#filesystem_status').css("color", "red");
                        }
                    }
            });
            // Update service status every 5 seconds
            window.setTimeout(function(){update(true)}, 5000);
        }
        function handle_clicks() {
            // Handle action links
            $(".action").click(function(event) {
                $('#msg').hide();
                event.preventDefault();
                var url = $(this).attr('href');
                $.get(url, function(data) {
                    $('#msg').html(data).fadeIn();
                    clear_msg();
                });
                popup();
            });
            // Handle forms
            $('.generic_form').ajaxForm({
                type: 'POST',
                dataType: 'json',
                beforeSubmit: function() {
                    $('#msg').hide();
                    popup();
                },
                complete: function(data) {
                    update();
                    $('#msg').html(data.responseText).fadeIn();
                    clear_msg();
                }
            });
            // Display overlays
            $('#show_user_data').click(function(event) {
                $('#msg').hide();
                event.preventDefault();
                var url = $(this).attr('href');
                $.get(url, function(user_data) {
                    // Pretty-print JSON user data and display in an overlay box
                    var ud_obj = JSON.parse(user_data)
                    var ud_str = JSON.stringify(ud_obj, null, 2);
                    $('#user_data_content').html(ud_str);
                    $('#user_data').fadeIn('fast');
                });
            });
        }
        function popup() {
            $("#action_initiated").fadeIn("slow").delay(400).fadeOut("slow");
        }
        function clear_msg() {
            // Clear message box 1 minute after the call to this method
            // FIXME: sometimes, the box gets cleared sooner, issue w/ intermittent clicks?
            window.setTimeout(function(){$('#msg').hide();}, 60000);
        }
        $(document).ready(function() {
            // Toggle help info boxes
            $(".help_info span").click(function () {
                var content_div = $(this).parent().find(".help_content");
                var help_link = $(this).parent().find(".help_link");
                if (content_div.is(":hidden")) {
                    help_link.addClass("help_link_on");
                    content_div.slideDown("fast");
                } else {
                    content_div.slideUp("fast");
                    help_link.removeClass("help_link_on");
                }
            });
            // Get services status
            update();
            // Handle control click events
            handle_clicks();
            // Make clearing form fields easier by auto selecting the content
            $('.form_el').focus(function() {
                this.select();
            });
            // Add event to enable closing of an overlay box
            $('.boxclose').click(function(){
                $('.box').hide();
            });
        });
    </script>
</%def>