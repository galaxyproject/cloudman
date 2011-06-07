<%inherit file="/base_panels.mako"/>
<%def name="main_body()">
    <div class="body" style="max-width: 720px; margin: 0 auto;">
        <h2>Galaxy Cloudman Admin Console</h2>
        <div id="main_text">
            This admin panel is a convenient way to gain insight into the status
            of individual Cloudman services as well as to control those services.<br/>
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
			<li><span id='galaxy_dns'>&nbsp;</span></li>
            <li>Current Galaxy admins: <span id="galaxy_admins">N/A</span></li>
            <li>Add Galaxy admin users:
                <span class="help_info">
                    <span class="help_link">What will this do?</span>
                    <div class="help_content" style="display: none">
                        Add Galaxy admin users to Galaxy. This action simply
                        adds users' emails to Galaxy's universe_wsgi.ini file
                        and does not check of the users exist or register new
                        users. Note that this action implies restarting Galaxy. 
                    </div>
                </span>
                <form action="add_galaxy_admin_users" method="get">
                    <input type="text" value="CSV list of emails to be added as admins" class="form_el" name="admin_users" size="45">
                    <input type="submit" value="Add admin users">
                </form>
            </li>
            <li>Current Galaxy revision: <span id="galaxy_rev">N/A</span></li>
            <li>Update Galaxy from a provided repository:
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
                <form action="update_galaxy" method="get">
                    <input type="text" value="http://bitbucket.org/galaxy/galaxy-central" class="form_el" name="repository" size="45">
                    <input type="submit" value="Update Galaxy">
                </form>
            </li>
        </ul>
        <h3>Services controls</h3>
        <div class="help_text">
            Use these controls to administer individual application services managed by Cloudman.
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
        </table>
        <h3>System controls</h3>
        <div class="help_text">
            Use these controls to administer Cloudman itself as well as the underlying system.
        </div>
        <ul class='services_list'>
			<li>Command used to connect to the instance: <div class="code">ssh -i <i>[path to ${key_pair_name} file]</i> ubuntu@${ip}</div></li>
            <li><a id='show_user_data' href="${h.url_for(controller='root', action='get_user_data')}">Show current user data</a></li>
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
                        Try to (re)start Cloudman service monitor thread, which is 
                        responsible for monitoring the status of all of the other
                        services. This should only be used if the Cloudman user
                        interface becomes unresponsive or during debugging.
                    </div>
                </span>
            </li>
            <li>
                <a class='action' href="${h.url_for(controller='root', action='recover_monitor')}?force=True">Recover monitor *with Force*</a>
                <span class="help_info">
                    <span class="help_link">What will this do?</span>
                    <div class="help_content" style="display: none">
                        Start a new Cloudman service monitor thread regardless
                        of if one already exists.
                    </div>
                </span>
            </li>
        </ul>

		## Overlays
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
    <script type="text/javascript">
        function update(repeat_update){
            $.getJSON("${h.url_for(controller='root',action='get_all_services_status')}",
                function(data){
                    if (data){
                        if (data.galaxy_rev != 'N/A') {
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
                    }
            });
            // Update service status every 5 seconds
            window.setTimeout(function(){update(true)}, 5000);
        }
        function handle_clicks() {
            $(".action").click(function(event) {
				event.preventDefault();
				var url = $(this).attr('href');
				$.get(url);
				popup();
            });
			$('#show_user_data').click(function(event) {
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