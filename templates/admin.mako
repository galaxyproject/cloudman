<%inherit file="/base_panels.mako"/>
<%def name="main_body()">
<div>
	<div ng-controller="cmAlertController">
		<alert ng-repeat="alert in getAlerts()" type="alert.type" close="closeAlert(alert)">{{alert.msg}}</alert>
	</div>
	<!-- 
	<div id="msg_box" class="info_msg_box" style="margin-top: -25px; min-height: 16px">
		<span id="msg" class="info_msg_box_content" style="display: none"></span>
	</div>
	 -->
	<%include file="bits/messages.html" />

	<header>
		<h2>CloudMan Admin Console</h2>
		<div id="main_text">
			<span class="lead">
				This admin panel is a convenient way to gain insight into the status
				of individual CloudMan services as well as to control those services.
			</span>
			<p class="text-warning">Services should not be manipulated unless absolutely
				necessary.
				Please keep in mind that the actions performed by these service-control
				'buttons' are basic in that they assume things will operate as
				expected.
				In other words, minimal special case handling for recovering services
				exists. Also note that clicking on a service action button will
				initiate the action; there is no additional confirmation required.
			</p>
		</div>
	</header>

	<section id="service_controls" ng-controller="ServiceController">
		<div>
			<h3>Services controls</h3>
		</div>
		<p>
			Use these controls to administer individual application services
			managed by CloudMan.
			Currently running a '<a href="http://wiki.g2.bx.psu.edu/Admin/Cloud" target='_blank'>${initial_cluster_type}</a>' type of cluster.
		</p>

<!--
	<div class="row-fluid" id="app_service_table">
		<div class="span12" id="app_service_header_row">
			<div class="row-fluid">
				<div class="span1">
				</div>
				<div class="span2">
					<strong>Service Name</strong>
				</div>
				<div class="span8">
					<strong>Status</strong>
				</div>
			</div>
		</div>
	</div>
	<div class="row-fluid" id="app_service_row">
		<div class="span12 accordion" id="app_service_item_row">
			<div class="row-fluid accordion-heading">
				<div class="span1" style="background:yellow"><a class="accordion-toggle" data-toggle="collapse" data-parent="app_service_item_row"
						href="#collapseService"><i class="icon-plus"></i></a></div>
				<div class="span2">
					<span style="display:table-cell;vertical-align:middle;height:30px">
						Service Name</span>
				</div>
				<div class="span8" style="background:blue;height:50px">
				<span style="display:table-cell;vertical-align:middle;height:30px;background:yellow">
					Status <a class="accordion-toggle" data-toggle="collapse" data-parent="app_service_item_row" href="#collapseService">
				</span>
				</div>
			</div>
			<div id="collapseService" class="row-fluid accordion-body collapse">
				<div class="span11 offset1">
					hello world! dfkdfks lksdfjklsd fsdlkfjs fkjsdlsj
				</div>
			</div>
		</div>
	</div>
		
-->

	
		<table class="table">
			<thead>
				<tr>
					<th></th>
					<th>Service name</th>
					<th>Status</th>
					<th colspan="6"></th>
				</tr>
			</thead>
			<tbody ng-repeat="svc in getServices()">
				<tr id="service_row_{{svc.svc_name}}" style="text-align:left">
					<td>
						<a ng-click="expandServiceDetails()" ng-show="svc.requirements"><i class="icon-plus"></i></a>
					</td>
					<td ng-bind="svc.svc_name" />
					<td ng-bind="svc.status" />
					<td ng-repeat="action in svc.actions">
						<a ng-href="{{action.action_url}}" ng-bind="action.name"></a>
					</td>
					<td colspan=4 />
				</tr>
				<tr id="service_detail_row_{{svc.svc_name}}" ng-show="is_service_visible()">
					<td></td>
					<td colspan="9">
						<div>
							<br />
							Required Services:
							<table width="600px" style="margin:10px 0; text-align:left">
								<thead>
									<tr>
										<th width="30%">Requirement Name</th>
										<th width="20%">Type</th>
										<th width="20%">Assigned Service</th>
									</tr>
								</thead>
								<tr ng-repeat="req in svc.requirements">
									<td>{{req.display_name}}</td>
									<td>{{req.type}}</td>
									<td>
										<div ng-switch on="req.type">
											<div ng-switch-when="APPLICATION">{{req.assigned_service}}</div>
											<div ng-switch-when="FILE_SYSTEM">
												<select id="assigned_fs_{{svc.name}}_{{req.role}"
													ng-model="req.assigned_service"
													ng-options="fs.name as fs.name for fs in getAvailableFileSystems()" />
											</div>
										</div>
									</td>
								</tr>
							</table>
						</div>
					</td>
				</tr>
			</tbody>
		</table>
		<div>
			<button class="btn"><i class="icon-plus"></i>Add New</button>
			
			<form class="fs-add-form">
	            <div class="form-row">
	            	<a id="fs-add-form-close-btn" title="Cancel" href="#"></a>
	            	Through this form you may add a new file system and make it available
	            	to the rest of this CloudMan platform.
				</div>
				<div class="inline-radio-btns">
		            <fieldset>
		                <strong>File system source or device:</strong>
		                <input type="radio" name="fs_kind" id="fs-kind-bucket-name" class="fs-add-radio-btn" value="bucket"/>
		                <label for="fs-kind-bucket-name">Bucket</label>
		                <input disabled="disabled" type="radio" name="fs_kind" id="fs-kind-volume" class="fs-add-radio-btn" value="volume" />
		                <label for="fs-kind-volume">Volume</label>
		                <input disabled="disabled" type="radio" name="fs_kind" id="fs-kind-snapshot" class="fs-add-radio-btn" value="snapshot"/>
		                <label for="fs-kind-snapshot">Snapshot</label>
		                <input disabled="disabled" type="radio" name="fs_kind" id="fs-kind-new-volume" class="fs-add-radio-btn" value="new_volume"/>
		                <label for="fs-kind-new-volume">New volume</label>
		                <input type="radio" name="fs_kind" id="fs-kind-nfs" class="fs-add-radio-btn" value="nfs"/>
		                <label for="fs-kind-nfs">NFS</label>
		            </fieldset>
	            </div>
	            <!-- Bucket form details -->
	            <div id="add-bucket-form" class="add-fs-details-form-row">
	            	<table><tr>
	                    <td><label for="bucket_name">Bucket name: </label></td>
	                    <td><input type="text" size="20" name="bucket_name" id="bucket_name"
	                        placeholder="e.g., 1000genomes"/> (AWS S3 buckets only)</td>
	                    </tr><tr>
	                    <td><label for="bucket_fs_name">File system name: </label></td>
	                    <td><input type="text" size="20" name="bucket_fs_name" id="bucket_fs_name">
	                    (no spaces, alphanumeric characters only)</td>
	                </tr></table>
				</div>
				<div id="add-bucket-fs-creds">
	                    <p> It appears you are not running on the AWS cloud. CloudMan supports
	                    using only buckets from AWS S3. So, if the bucket you are trying to
	                    use is NOT PUBLIC, you must provide the AWS credentials that can be
	                    used to access this bucket. If the bucket you are trying to use
	                    IS PUBLIC, leave below fields empty.</p>
	                    <table><tr>
	                        <td><label for"bucket_a_key">AWS access key: </label></td>
	                        <td><input type="text" id="bucket_a_key" name="bucket_a_key" size="50" /></td>
	                    </tr><tr>
	                        <td><label for"bucket_s_key">AWS secret key: </label></td>
	                        <td><input type="text" id="bucket_s_key" name="bucket_s_key" size="50" /></td>
	                    </tr></table>
	            </div>
	            <!-- Volume form details -->
	            <div id="add-volume-form" class="add-fs-details-form-row">
	                <table><tr>
	                    <td><label for="vol_id">Volume ID: </label></td>
	                    <td><input type="text" size="20" name="vol_id" id="vol_id"
	                        placeholder="e.g., vol-456e6973"/></td>
	                    </tr><tr>
	                    <td><label for="vol_fs_name">File system name: </label></td>
	                    <td><input type="text" size="20" name="vol_fs_name" id="vol_fs_name">
	                    (no spaces, alphanumeric characters only)</td>
	                </tr></table>
	            </div>
	            <!-- Snapshot form details -->
	            <div id="add-snapshot-form" class="add-fs-details-form-row">
	                <table><tr>
	                    <td><label for="snap_id">Snapshot ID: </label></td>
	                    <td><input type="text" size="20" name="snap_id" id="snap_id"
	                        placeholder="e.g., snap-c21cdsi6"/></td>
	                    </tr><tr>
	                    <td><label for="snap_fs_name">File system name: </label></td>
	                    <td><input type="text" size="20" name="snap_fs_name" id="snap_fs_name">
	                    (no spaces, alphanumeric characters only)</td>
	                </tr></table>
				</div>
	            <!-- New volume form details -->
	            <div id="add-new-volume-form" class="add-fs-details-form-row">
	                <table><tr>
	                    <td><label for="new_disk_size">New file system size: </label></td>
	                    <td><input type="text" size="20" name="new_disk_size" id="new_disk_size"
	                        placeholder="e.g., 100"> (minimum 1GB, maximum 1000GB)</td>
	                    </tr><tr>
	                    <td><label for="new_vol_fs_name">File system name: </label></td>
	                    <td><input type="text" size="20" name="new_vol_fs_name" id="new_vol_fs_name">
	                    (no spaces, alphanumeric characters only)</td>
	                </tr></table>
				</div>
	            <!--   NFS form details -->
	            <div id="add-nfs-form" class="add-fs-details-form-row">
	                <table><tr>
	                    <td><label for="nfs-server">NFS server address: </label></td>
	                    <td><input type="text" size="20" name="nfs_server" id="nfs_server"
	                        'placeholder="e.g., 172.22.169.17:/nfs_dir"></td>
	                    </tr><tr>
	                    <td><label for="nfs_fs_name">File system name: </label></td>
	                    <td><input type="text" size="20" name="nfs_fs_name" id="nfs_fs_name">
	                    (no spaces, alphanumeric characters only)</td>
	                </tr></table>
	            </div>
	            <div id="add-fs-dot" class="add-fs-details-form-row">
	                <input type="checkbox" name="dot" id="add-fs-dot-box"><label for="add-fs-dot-box">
	                If checked, the created disk <b>will be deleted</b> upon cluster termination</label>
	            </div>
	            <div id="add-fs-persist" class="add-fs-details-form-row">
	                <input type="checkbox" name="persist" id="add-fs-persist-box">
	                <label for="add-fs-persist-box">If checked,
	                the created disk <b>will be persisted</b> as part of the cluster configuration
	                and thus automatically added the next time this cluster is started</label>
	            </div>
	            <div id="add-fs-submit-btn" class="add-fs-details-form-row">
	                <input type="submit" class="fs-form-submit-button" value="Add new file system"/>
	                or <a class="fs-add-form-close" href="#">cancel</a>
	            </div>
			</form>
		</div>
	</section>
	<!-- <table width="700px" style="margin:10px 0"> <tr style="text-align:left"> 
		<th width="2%"></th> <th width="20%">Service name</th> <th width="15%">Status</th> 
		<th width="65%" colspan="6"></th> </tr> <tr> <td><a ng-click="expandServiceDetails('galaxy')">+</a></td> 
		<td>Galaxy</td> <td><span id="galaxy_status">&nbsp;</span></td> <td><a href="${h.url_for(controller='root',action='service_log')}?service_name=Galaxy">Log</a></td> 
		<td><a class='action' href="${h.url_for(controller='root',action='manage_service')}?service_name=Galaxy&to_be_started=False" 
		target='_blank'>Stop</a></td> <td><a class='action' href="${h.url_for(controller='root',action='manage_service')}?service_name=Galaxy" 
		target="_blank">Start</a></td> <td><a class='action' href="${h.url_for(controller='root',action='restart_service')}?service_name=Galaxy" 
		target="_blank">Restart</a></td> <td><a class='action' href="${h.url_for(controller='root',action='update_galaxy')}?db_only=True" 
		target='_blank'>Update DB</a></td> <td /> </tr> <tr id="service_detail_row_galaxy" 
		ng-show="visible_flag_galaxy"> <td></td> <td colspan="8"> Assigned file system: 
		<select id="galaxy_assigned_fs" name="galaxy-assigned-fs"> <option ng-repeat="fs 
		in available_file_systems" ng-model="fs.name">{{fs.name}}</option> </select> 
		</td> </tr> <tr> <td><a href="javascript:expandServiceDetails('galaxy')">+</a></td> 
		<td>PostgreSQL</td> <td><span id="postgres_status">&nbsp;</span></td> <td><a 
		href="${h.url_for(controller='root',action='service_log')}?service_name=Postgres">Log</a></td> 
		<td><a class='action' href="${h.url_for(controller='root',action='manage_service')}?service_name=Postgres&to_be_started=False" 
		target="_blank">Stop</a></td> <td><a class='action' href="${h.url_for(controller='root',action='manage_service')}?service_name=Postgres" 
		target="_blank">Start</a></td> <td><a class='action' href="${h.url_for(controller='root',action='restart_service')}?service_name=Postgres" 
		target="_blank">Restart</a></td> </tr> <tr> <td><a href="javascript:expandServiceDetails('galaxy')">+</a></td> 
		<td>SGE</td> <td><span id="sge_status">&nbsp;</span></td> <td><a href="${h.url_for(controller='root',action='service_log')}?service_name=SGE">Log</a></td> 
		<td><a class='action' href="${h.url_for(controller='root',action='manage_service')}?service_name=SGE&to_be_started=False" 
		target="_blank">Stop</a></td> <td><a class='action' href="${h.url_for(controller='root',action='manage_service')}?service_name=SGE" 
		target="_blank">Start</a></td> <td><a class='action' href="${h.url_for(controller='root',action='restart_service')}?service_name=SGE" 
		target="_blank">Restart</a></td> <td><a href="${h.url_for(controller='root',action='service_log')}?service_name=SGE&q=conf">Q 
		conf</a></td> <td><a href="${h.url_for(controller='root',action='service_log')}?service_name=SGE&q=qstat">qstat</a></td> 
		</tr> <tr> <td><a href="javascript:expandServiceDetails('galaxy')">+</a></td> 
		<td>Galaxy Reports</td> <td><span id="galaxy_reports_status">&nbsp;</span></td> 
		<td><a href="${h.url_for(controller='root',action='service_log')}?service_name=GalaxyReports">Log</a></td> 
		<td><a class='action' href="${h.url_for(controller='root',action='manage_service')}?service_name=GalaxyReports&to_be_started=False" 
		target="_blank">Stop</a></td> <td><a class='action' href="${h.url_for(controller='root',action='manage_service')}?service_name=GalaxyReports" 
		target="_blank">Start</a></td> <td><a class='action' href="${h.url_for(controller='root',action='restart_service')}?service_name=GalaxyReports" 
		target="_blank">Restart</a></td> </tr> ##<tr> ## <td>Dummy</td> ## <td><span 
			id="dummy"></span></td> ##</tr> </table> ! -->
	
	<section id="file_systems_redone" ng-controller="FileSystemController">
		<div>
			<h3>File systems</h3>
		</div>
		<p>
			Use these controls to administer individual file systems
			managed by CloudMan.
		</p>
		<table class="table">
	        <thead>
	            <tr class="filesystem-tr">
	                <th class="fs-td-20pct">Name</th>
	                <th class="fs-td-15pct">Status</th>
	                <th class="fs-td-20pct">Usage</th>
	                <th class="fs-td-15pct">Controls</td>
	                <th colspan="2"></th>
	            </tr>
	        </thead>
	        <tbody>
	        	<tr ng-repeat="fs in getFileSystems()">
			        <td>{{fs.name}}</td>
			        <td ng-switch on="fs.status">
			        	<p ng-switch-when="Running" class="text-success">{{fs.status}}</p>
			        	<p ng-switch-when="Error" class="text-error">{{fs.status}}</p>
			        	<p ng-switch-default class="text-warning">{{fs.status}}</p>
			        </td>
			        <td>
				        <!-- // Only display usage when the file system is 'Available' -->
			            <meter id="fs-meter-{{fs.name}}" class="meter_file_system_space_usage" min="0" max="100" value="{{fs.size_pct}}" high="85" ng-show="is_ready_fs(fs)" display-value="{{fs.size_used}}/{{fs.size}} ({{fs.size_pct}}%)" />
			            <span ng-show="is_snapshot_in_progress(fs)">
			                Snapshot status: {{fs.snapshot_status}}; progress: {{fs.snapshot_progress}}
			            </span>
					</td>
			        <td>
			            <!-- // Enable removal while a file system is 'Available' or 'Error' -->
			            <a ng-show="!is_snapshot_in_progress(fs)" class="fs-remove icon-button" id="fs-{{fs.name}}-remove"
			               title="Remove this file system" ng-click="remove_fs($event, fs)"></i></a>
			            <!--// Only display additional controls when the file system is 'Available'-->
			            <!-- It only makes sense to persist DoT, snapshot-based file systems -->
						<a ng-show="is_persistable_fs(fs)" class="fs-persist icon-button" id="fs-{{fs.name}}-persist"
			                        title="Persist file system changes" ng-click="persist_fs($event, fs)"></a>
			            <!-- It only makes sense to resize volume-based file systems -->
						<a ng-show="is_resizable_fs(fs)" class="fs-resize icon-button" id="fs-{{fs.name}}-resize" href="#" ng-click="resize_fs($event, fs)" title="Increase file system size"></a>
			        </td>
			        <td>
			        	<!-- <a class="fs-details" details-box="fs-{{fs.name}}-details" data-toggle="popover" data-placement="right" ng-mouseover="prepareToolTip(fs)" title="Filesystem details">Details</a>
			        	-->
			        	
			        	<a class="fs-details" details-box="fs-{{fs.name}}-details" title="Filesystem details"><span popover-placement="right" cm-popover="{{fs.template}}" >Details</span></a>
			        </td>
			        <td></td>
				</tr>
	        </tbody>
		</table>
	</section>	
	
	<section id="file_systems">
		<h3>File systems Backbone</h3>
		## backbone-managed
		<div id='fs-details-container'></div>
		<div id="filesystems-container"></div>
		<div id='fs-resize-form-container'></div>
		<div id='fs-add-container'>
			<div id='fs-add-form'></div>
			<div id='fs-add-btn'>
				<i class="icon-plus"></i>
				Add new
			</div>
		</div>
	</section>
	
	<section id="galaxy_controls">
	
		<h3>Galaxy controls</h3>
		<div class="help_text">
			Use these controls to administer functionality of Galaxy.
		</div>
		<ul class='services_list'>
			<li>
				<span id='galaxy_dns'>Galaxy is currently inaccessible</span>
			</li>
			<li>
				Current Galaxy admins:
				<span id="galaxy_admins">N/A</span>
			</li>
			<li>
				Add Galaxy admin users
				<span class="help_info">
					<span class="help_link">What will this do?</span>
					<div class="help_content" style="display: none">
						Add Galaxy admin users to Galaxy. This action simply
						adds users' emails to Galaxy's universe_wsgi.ini file
						and does not check of the users exist or register new
						users. Note that this action implies restarting Galaxy.
					</div>
				</span>
				<form class="generic_form"
					action="${h.url_for(controller='root', action='add_galaxy_admin_users')}"
					method="post">
					<input type="text" value="CSV list of emails to be added as admins"
						class="form_el" name="admin_users" size="45">
						<input type="submit" value="Add admin users">
				</form>
			</li>
			<li>
				Running Galaxy at revision:
				<span id="galaxy_rev">N/A</span>
			</li>
			<li>
				Update Galaxy from a provided repository
				<span class="help_info">
					<span class="help_link">What will this do?</span>
					<div class="help_content" style="display: none">
						Update Galaxy source code from the repository provided
						in the form field. The repository can be the default
						<i>galaxy-central</i>
						or any other compatible branch.
						<br />
						Note that the update will be applied to the current
						instance only and upon termination of the cluster, the
						update will be reverted; the analysis results
						will be preserved. As a result, any analyses that depend
						on the updated functionality may not be preroducible
						on the new instance wihtout performing the update again.
						See
						<a
							href="https://bitbucket.org/galaxy/galaxy-central/wiki/Cloud/CustomizeGalaxyCloud"
							target="_blank">
							this page
						</a>
						about instructions on how to preserve the
						changes.
						<br />
						This action will:
						<ol>
							<li>Stop Galaxy service</li>
							<li>Pull and apply any changes from the provided repository.
								If there are conflicts during the merge, local changes
								will be preserved.
							</li>
							<li>Call Galaxy database migration script</li>
							<li>Start Galaxy service</li>
						</ol>
					</div>
				</span>
				<form class="generic_form"
					action="${h.url_for(controller='root', action='update_galaxy')}"
					method="post">
					<input type="text" value="http://bitbucket.org/galaxy/galaxy-central"
						class="form_el" name="repository" size="45">
						<input type="submit" value="Update Galaxy">
				</form>
			</li>
		</ul>
	</section>
	
	
	<section id="system_controls">
		<h3>System controls</h3>
		<div class="help_text">
			Use these controls to administer CloudMan itself as well as the
			underlying system.
		</div>
		<ul class='services_list'>
			<li>
				Command used to connect to the instance:
				<div class="code">
					ssh -i
					<i>[path to ${key_pair_name} file]</i>
					ubuntu@${ip}
				</div>
			</li>
			<li>
				Name of this cluster's bucket: ${bucket_cluster}
				%if cloud_type == 'ec2':
				(
				<a id='cloudman_bucket' href="https://console.aws.amazon.com/s3/home?#"
					target="_blank">access via AWS console</a>
				)
				%endif
				<span class="help_info">
					<span class="help_link">Bucket info</span>
					<div class="help_content" style="display: none">
						Each CloudMan cluster has its configuration saved in a persistent
						data repository. This repository is read at cluster start and it
						holds all the data required to restart this same cluster. The
						repository is stored under your cloud account and is accessible
						only with your credentials.
						<br />
						In the context of AWS, S3 acts as a persistent data repository
						where
						all the data is stored in an S3 bucket. The name of the bucket
						provided here corresponds to the current cluster and is provided
						simply as a reference.
					</div>
				</span>
				<li>
					<a id='show_user_data' href="${h.url_for(controller='root', action='get_user_data')}">Show current user data</a>
				</li>
				<li>
					<a id='cloudman_log'
						href="${h.url_for(controller='root', action='service_log')}?service_name=CloudMan">Show CloudMan log</a>
				</li>
			</li>
			<li>
				<a class="action" id="master_is_exec_host"
					href="${h.url_for(controller='root', action='toggle_master_as_exec_host')}">&nbsp;
				</a>
				<span class="help_info">
					<span class="help_link">What will this do?</span>
					<div class="help_content" style="display: none">
						By default, the master instance running all the services is also
						configured to
						execute jobs. You may toggle this functionality here. Note that if job
						execution
						on the master is disabled, at least one worker instance will be
						required to
						run any jobs.
					</div>
				</span>
			</li>
			<li>
				<a class='action'
					href="${h.url_for(controller='root', action='store_cluster_config')}">Store current cluster configuration</a>
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
				<a class='action'
					href="${h.url_for(controller='root', action='recover_monitor')}">Recover monitor</a>
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
				<a class='action'
					href="${h.url_for(controller='root', action='recover_monitor')}?force=True">Recover monitor *with Force*</a>
				<span class="help_info">
					<span class="help_link">What will this do?</span>
					<div class="help_content" style="display: none">
						Start a new CloudMan service monitor thread regardless
						of if one already exists.
					</div>
				</span>
			</li>
		</ul>
	</section>

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
        var get_application_services_url = "${h.url_for(controller='root',action='get_application_services')}";
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
        <% if (typeof(nfs_server) != "undefined") { %>
            <tr><th>NFS server:</th><td><%= nfs_server %></td>
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
    
    <script type="text/template" id="fs-details-popover-template">
        <table>
        <tr><th>Name:</th><td>{{ fs.name }}</td></tr>
        <tr><th>Bucket name:</th><td>{{ fs.bucket_name }}</td></tr>
        <tr><th>Status:</th><td>{{ fs.status }}</td></tr>
        <tr><th>Mount point:</th><td>{{ fs.mount_point }}</td></tr>
        <tr><th>Kind:</th><td>{{ fs.kind }}</td></tr>
		<tr><th>Volume:</th><td>{{ fs.volume_id }}</td></tr>
		<tr><th>Device:</th><td>{{ fs.device }}</td></tr>
		<tr><th>From snapshot:</th><td>{{ fs.from_snap }}</td></tr>
		<tr><th>NFS server:</th><td>{{ fs.nfs_server }}</td></tr>
        <tr><th>Size (used/total):</th><td>{{ fs.size_used }}/{{ fs.size }} ({{ fs.size_pct }})</td></tr>
        <tr><th>Delete on termination:</th><td>{{ fs.DoT }}</td></tr>
        <tr><th>Persistent:</th><td>{{ fs.persistent }}</td></tr>
        </table>
    </script>


    <script type="text/template" id="fs-resize-dialog-template">
    	<form id="fs_resize_form" action="${h.url_for(controller='root',action='expand_user_data_volume')}" method="POST">
    	<div class="modal-header" style="padding: 12px 12px 12px 12px">
    		<div class="modal-header">
		    	<h3>Resize File System</h3>
	    	</div>
	        <div class="modal-body" >
		        <p>
		            Through this form you may increase the disk space available to this file system.
		            Any services using this file system <strong>WILL BE STOPPED</strong>
		            until the new disk is ready, at which point they will all be restarted. Note
		            that This may result in failure of any jobs currently running. Note that the new
		            disk size <strong>must be larger</strong> than the current disk size.
		            <p>During this process, a snapshot of your data volume will be created,
		            which can optionally be left in your account. If you decide to leave the
		            snapshot for reference, you may also provide a brief note that will later
		            be visible in the snapshot's description.</p>
		        </p>    
	            <label>New disk size (minimum {{ fs.size }}B,
	            maximum 1000GB)</label>
	            <div id="permanent_storage_size">
	                <input type="text" name="new_vol_size" id="new_vol_size"
	                placeholder="Greater than {{ fs.size }}B" size="25" ng-model="resize_details.new_vol_size" />
	                {{ resize_details.new_vol_size}}
	            </div>
	            <label>Note</label>
	            <div id="permanent_storage_size">
	                <input type="text" name="vol_expand_desc" id="vol_expand_desc" value=""
	                placeholder="Optional snapshot description" size="50" ng-model="resize_details.vol_expand_desc" /><br/>
	            </div>
	            <label>or delete the created snapshot after filesystem resizing?</label>
	            <input type="checkbox" name="delete_snap" id="delete_snap" ng-model="resize_details.delete_snap" /> If checked,
	            the created snapshot will not be kept.
	        </div>
	        <div class="modal-footer">
	        	<button ng-click="resize($event)" class="btn btn-primary" >Resize {{ fs.name }} file system</button>
	      		<button ng-click="cancel($event)" class="btn btn-primary" >Cancel</button>  
	        </div>
	        <input name="fs_name" type="hidden" value="{{fs.name}}" />
        </div>
        </form>
    </script>
    
    <script type="text/template" id="fs-delete-dialog-template">
    	<form id="fs_remove_form" action="${h.url_for(controller='root',action='manage_service')}?service_name={{fs.name}}&to_be_started=False&is_filesystem=True" method="GET">
    		<div class="modal-header">
		    	<h3>Remove file system: {{ fs.name }}?</h3>
	    	</div>
	        <div class="modal-body" >
		        <p>
				Removing this file system will first stop any services that require this file system.
				Then, the file system will be unmounted and the underlying device disconnected from this instance.
		        </p>    
	        <div class="modal-footer">
	        	<button ng-click="confirm($event, 'confirm')" class="btn btn-primary" >Confirm</button>
	      		<button ng-click="cancel($event, 'cancel')" class="btn btn-primary" >Cancel</button>  
	        </div>
        </form>
    </script> 
    
    <script type="text/template" id="fs-persist-dialog-template">
    	<form id="fs_persist_form" action="${h.url_for(controller='root', action='update_file_system')}?fs_name={{fs.name}}" method="GET">
    		<div class="modal-header">
		    	<h3>Persist file system: {{ fs.name }}?</h3>
	    	</div>
	        <div class="modal-body" >
		        <p>
				If you have made changes to the <em>{{ fs.name }}</em> file system and would like to persist the changes
                across cluster invocations, it is required to persist those
                changes.
                </p>
                <p>
                <em>What will happen next?</em>
                </p>
                <p>
                Persisting file system changes requires that any services running on the
                file system be stopped and the file system unmounted. Then, a
                snapshot of the underlying volume will be created and any services
                running on the file system started back up. Note that depending
                on the amount of changes you have made to the file system, this
                process may take a while.
		        </p>    
	        <div class="modal-footer">
	        	<button ng-click="confirm($event, 'confirm')" class="btn btn-primary" >Confirm</button>
	      		<button ng-click="cancel($event, 'cancel')" class="btn btn-primary" >Cancel</button>  
	        </div>
        </form>
    </script>
    
    <script type='text/javascript' src="${h.url_for('/static/scripts/jquery.form.js')}"></script>
    <script src="//ajax.googleapis.com/ajax/libs/jqueryui/1.8.23/jquery-ui.min.js"></script>
    <script type='text/javascript' src="${h.url_for('/static/scripts/jquery.tipsy.js')}"></script>
    <script type='text/javascript' src="${h.url_for('/static/scripts/underscore-min.js')}"></script>
    <script type='text/javascript' src="${h.url_for('/static/scripts/backbone-min.js')}"></script>
    <script type='text/javascript' src="${h.url_for('/static/scripts/backbone.marionette.js')}"></script>
    <script type='text/javascript' src="${h.url_for('/static/scripts/Backbone.ModalDialog.js')}"></script>
    <script type='text/javascript' src="${h.url_for('/static/scripts/admin.js')}"></script>
</div>
</%def>
