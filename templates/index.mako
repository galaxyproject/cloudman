<%inherit file="/base_panels.mako"/>
<%def name="main_body()">

<script type='text/javascript' src="//cdnjs.cloudflare.com/ajax/libs/flot/0.7/jquery.flot.min.js"></script>
<script type='text/javascript' src="//raw.github.com/flot/flot/master/jquery.flot.time.js"></script>
<script type='text/javascript' src="${h.url_for('/static/scripts/jquery.form.js')}"></script>
<script type='text/javascript' src="${h.url_for('/static/scripts/index.js')}"></script>


<div ng-app="cloudman.index">
    <%include file="bits/alerts.htm" />
    <div id="storage_warning" style="display:none;" class="warning"><strong>Warning:</strong> You are running out of disk space.  Use the disk icon below to increase your volume size.</div>
    
    <header>
    	<h2>CloudMan Console</h2>
	    <div>
		    <span class="lead">
		    		Welcome to <a href="http://usecloudman.org/" target="_blank">CloudMan</a>.
				%if initial_cluster_type is None:
		            This application allows you to manage this cloud cluster and the services provided within.
				%else:
		            This application allows you to manage this instance cloud cluster and the services
		            provided within.
				%endif
		    </span>
		    <p>
		        %if initial_cluster_type is None:	            
		            If this is your first time running this cluster, you will need to select an initial data volume
		            size. Once the data store is configured, default services will start and you will be able to add
		            and remove additional services as well as 'worker' nodes on which jobs are run.
		        %else:
		            Your previous data store has been reconnected.  Once the cluster has initialized,
		            use the controls below to manage services provided by the application.
		        %endif
		     </p>
	    </div>
	    <div style="clear: both;"></div><br/>
	</header>

	<section id="main_actions">
	    <div class="row-fluid" ng-controller="cmIndexMainActionsController" data-ng-init="showInitialConfig('${initial_cluster_type}')">
	    	<div class="span12">
	    	<div class="row-fluid">
	    	<div class="span11 offset1">
	    
	    
	    	<div class="span2">
		  		<a class="btn btn-block btn-small" href="{{ getGalaxyPath() }}" ng-class="{'btn-success': isGalaxyAccessible(), '': !isGalaxyAccessible()}" href="#" ng-disabled="!isGalaxyAccessible()">
		  		<i class="icon-road"></i>
		    	Access Galaxy
		  		</a>
			</div>
			
			<div class="span2 offset1">
				<div class="btn-group btn-block">
			  		<button class="btn dropdown-toggle btn-block btn-small" data-toggle="dropdown" href="#" ng-disabled="!isAddNodeEnabled()">
			  		<i class="icon-plus"></i>
			    	Add Nodes <span class="caret"></span>
			  		</button>
			  		<ul class="dropdown-menu">
			  			<!-- dropdown menu links -->
			  			<li>
			  				<div class="text-center" style='margin:20px;'>
						        <form id="add_instances_form" name="node_management_form" action="${h.url_for(controller='root',action='add_instances')}" method="POST" ng-click="handleFormClick($event)">
						        	<fieldset>
							        	<legend>Add Nodes</legend>
							            <label>Number of nodes to start:</label>
							            <input type="number" name="number_nodes" value="1" min="1" step="1" required="true"/>
							            <label><a href="http://aws.amazon.com/ec2/#instance" target="_blank">Type</a> of node(s):</label>
							            <select name="instance_type" id="instance_type">
							            	<%include file="clouds/${cloud_name}/instance_types.mako" />
							            </select>
							            ## Spot instances work only for the AWS cloud
							            <br /><br />
							            %if cloud_type == 'ec2':
							            	<fieldset class="form-inline">
												<label class="checkbox">
													<input type="checkbox" id="use_spot" ng-model="add_nodes.use_spot"/>
													Use <a href="http://aws.amazon.com/ec2/spot-instances/" target="_blank">
								                    Spot instances</a>
												</label>
											</fieldset>
							                <br/>
							                <label>
							                	Your max <a href="http://aws.amazon.com/ec2/spot-instances/#6" targte="_blank">
							                    spot price</a>:
							                    <br />
							                    <input type="number" name="spot_price" min="0" required="{{add_nodes.use_spot}}" ng-disabled="!add_nodes.use_spot" />
											</label>
							            %endif
							            <br />
							            <input type="submit" class="btn btn-small btn-primary" value="Start Additional Nodes" ng-click="addNodes($event)" ng-disabled="add_instances_form.$invalid" />
						            </fieldset>
						        </form>
							</div>
						</li>
			  		</ul>
				</div>
			</div>
			<div class="span2 offset1">
				<div class="btn-group btn-block">
			  		<button class="btn dropdown-toggle btn-block btn-small" data-toggle="dropdown" href="#" ng-disabled="!isRemoveNodeEnabled()">
			  		<i class="icon-minus"></i>
			    	Remove Nodes <span class="caret"></span>
			  		</button>
			  		<ul class="dropdown-menu">
			    	<!-- dropdown menu links -->
			    		<li>
			    			<div class="text-center" style='margin:20px'>
						        <form id="remove_instances_form" name="node_management_form" action="${h.url_for(controller='root',action='remove_instances')}" method="POST" ng-click="handleFormClick($event)">
						        	<fieldset>
							        	<legend>Remove Nodes</legend>
							            <label>Number of nodes to remove:</label>
							            <input type="number" name="number_nodes" value="0" min="1" step="1" required="true"/>
							            <label>Force Termination of non-idle nodes?</label>
							            <div class="form-inline">
										      <label class="radio"><input type="radio" name="force_termination" value="True" />Yes</label>
										      &nbsp;&nbsp;
							            	  <label class="radio"><input type="radio" name="force_termination" value="False" checked="True"/>No</label>
										</div>
										<br /><br />
										<input type="submit" class="btn btn-small btn-primary" value="Remove Existing Nodes" ng-click="removeNodes($event)" ng-disabled="remove_instances_form.$invalid" />
							        </fieldset>
						        </form>
						    </div>		    		
			    		</li>
			  		</ul>
				</div>
			</div>
			
			<div class="span2 offset1">
		  		<button type="button" class="btn btn-danger btn-block btn-small" ng-click="confirm_terminate($event)">
			  		<i class="icon-off"></i>
			    	Terminate
		  		</button>
			</div>
			
			</div>
			</div>
			</div>
		</div>
	</section>
	
	<!--  Status section -->
	<section id="cluster_status" ng-controller="cmIndexMainActionsController">
		<div>
			<br />
		    <div class="row-fluid">
		    	<div class="span12">
					<fieldset>
						<h3>Cluster Status <span ng-show="isRefreshInProgress()"><i class="icon-spinner icon-spin"></i></span></h3>
					</fieldset>
				</div>
			</div>
			<div class="row-fluid">
		    	<div class="span12">
			    	<table class="table">
			    		<tbody>
			    			<tr>
			    				<td><strong>Cluster Name:</strong></td>
			    				<td>${cluster_name}</td>
			    				<td colspan="3">
			    					<button class="btn btn-small">
					  					<i class="icon-share"></i>
					    				Share Cluster
				  					</button>
			    				</td>
			    				<td><strong>Disk status:</strong></td>
			    				<td>
			    					{{ getCloudmanStatus().disk_usage.used }} / {{ getCloudmanStatus().disk_usage.total }} ({{ getCloudmanStatus().disk_usage.pct }})
			    				</td>
			    				<td>
				    				<button class="btn btn-small">
						  				<i class="icon-resize-vertical"></i>
						    			Expand disk size
				  					</button>
			  					</td>
			    			</tr>
			    			<tr>
								<td><strong>Worker status:</strong></td>
			    				<td>Idle: {{ getCloudmanStatus().instance_status.idle }}</td>
	            				<td>Available: {{ getCloudmanStatus().instance_status.available }}</td>
	            				<td colspan="2">Requested: {{ getCloudmanStatus().instance_status.requested }}</td>
	            				
			    				<td><strong>Service status:</strong></td>
			    				<td>Applications <span ng-class="{'text-success': getCloudmanStatus().app_status == 'green', 'text-warning': getCloudmanStatus().app_status == 'yellow', 'text-error': getCloudmanStatus().app_status == 'red', 'muted' : getCloudmanStatus().app_status == 'nodata' }"><i class="icon-circle"></i></span></td>
	            				<td>Data <span ng-class="{'text-success': getCloudmanStatus().data_status == 'green', 'text-warning': getCloudmanStatus().data_status == 'yellow', 'text-error': getCloudmanStatus().data_status == 'red', 'muted' : getCloudmanStatus().data_status == 'nodata'}"><i class="icon-circle"></i></span></td>
			    			</tr>
			    			<!--  Autoscaling -->
			    			<tr>
								<td><strong>Autoscaling:</strong></td>
			    				<td ng-show="!getCloudmanStatus().autoscaling.use_autoscaling"><p class="text-warning">Off</p></td>
			    				<td ng-show="getCloudmanStatus().autoscaling.use_autoscaling"><span class="text-success form-inline">On</span></td>
			    				<td ng-show="getCloudmanStatus().autoscaling.use_autoscaling">Min: {{ getCloudmanStatus().autoscaling.as_min }}</td>
			    				<td ng-show="getCloudmanStatus().autoscaling.use_autoscaling">Max: {{ getCloudmanStatus().autoscaling.as_max }}</td>
								<td colspan="{{ getCloudmanStatus().autoscaling.use_autoscaling && '1' || '3' }}">
				    				<button class="btn btn-small" ng-click="configureAutoScaling()">
						  				<i class="icon-th-large"></i>
						    			Configure
					  				</button>
				  				</td>
								<td colspan="3"><!--  Empty for now --></td>
			    			</tr>
			    		</tbody>
			    	</table>	
		    	</div>
		    </div>
			
		</div>
	</section>
	
	<section id="stauts_details">
		 <accordion close-others="true">
		    <accordion-group is-open="true">
		    	<accordion-heading><strong>System Load</strong> <div class="pull-right"><span id="chart_legend"></span></div></accordion-heading>
		    	<div class="row-fluid">
			    	<div class="span12">
						 <div class="row-fluid" ng-controller="cmLoadGraphController">
							<div ng-repeat="node in nodes">
								<div class="cluster_node"">
									<table>
										<tr>
											<td>
						  						<chart ng-model='node.system_load' legend-location="#chart_legend" ng-click="test" />
						  					</td>
						  				</tr>
						  				<tr>
						  					<td align="center">
						  						<a class="btn btn-link" ng-click="node.isVisible=!node.isVisible">
						  							<i ng-class="{'icon-caret-right': !node.isVisible, 'icon-caret-down': node.isVisible}"></i>
						  							<span ng-show="$index == 0">Master:</span>
						  							<span ng-show="$index != 0">Worker:</span>
						  							{{ node.instance.public_ip }}
						  						</a>
						  						
						  						<span ng-show="$index != 0">
							  						<span ng-class="{'text-success': get_node_fs_status(node) == 'allgood', 'text-warning': get_node_fs_status(node) == 'warning', 'text-error': get_node_fs_status(node) == 'error', 'muted' : get_node_fs_status(node) == 'unknown'}">
							  							<i class="icon-circle" title="Filesystems"></i>
							  						</span>
							  						
							  						<span ng-class="{'text-success': get_permission_status(node) == 'allgood', 'text-warning': get_permission_status(node) == 'warning', 'text-error': get_permission_status(node) == 'error', 'muted' : get_permission_status(node) == 'unknown'}">
							  							<i class="icon-circle" title="Permissions"></i>
							  						</span>
							  						
							  						<span ng-class="{'text-success': get_scheduler_status(node) == 'allgood', 'text-warning': get_scheduler_status(node) == 'warning', 'text-error': get_scheduler_status(node) == 'error', 'muted' : get_scheduler_status(node) == 'unknown'}">
							  							<i class="icon-circle" title="Scheduler"></i>
							  						</span>
							  					</span>
						  						
						  						<div collapse="!node.isVisible">
						  							
						  							<i class="icon-repeat text-warning" title="Reboot instance" alt="Reboot instance" ng-click="rebootInstance(node, '/cloud/root/reboot_instance')"></i>
						  							<i class="icon-off text-error" title="Terminate instance" alt="Terminate instance" ng-click="terminateInstance(node, '/cloud/root/remove_instance')"></i>
						  						</div>
						  					</td>
						  				</tr>
						  			</table>
					  			</div>
							</div>
						</div>
					</div>
				</div>
		    </accordion-group>
		    <accordion-group>
		    	<accordion-heading><strong>Cluster Log</strong></accordion-heading>
		    	<ul ng-controller="cmClusterLogController">
		    		<li ng-repeat="msg in getLogData()" ng-bind-html-unsafe="msg">
		    		</li>
		    	</ul>
		    </accordion-group>
		 </accordion>
	</section>


## ****************************************************************************
## ***************************** Angular templates ****************************
## ****************************************************************************

<script type="text/ng-template" id="partials/terminate-confirm.html">
	<form id="form_terminate_confirm" action="${h.url_for(controller='root',action='kill_all')}" method="POST">
    	<div class="modal-header">
			<h3>Power Off Cluster?</h3>
		</div>
	    <div class="modal-body" >
	        <p>This action will shut down all services on the cluster and terminate
	            any worker nodes (instances) associated with this cluster. Unless you
	            choose to have the cluster deleted, all of your data will be preserved
	            beyond the life of this instance. Next time you wish to start this same
	            cluster, simply use the same user data (i.e., cluster name and credentials)
	            and CloudMan will reactivate your cluster with your data.
	        </p>
	        <fieldset>
	        	<label class="checkbox"><input type="checkbox" name="terminate_master_instance" id="terminate_master_instance" checked>
	        		<strong>Automatically terminate the master instance?</strong>
	        		<br />
					If checked, this master instance will automatically terminate after all services have been shut down.
	        		If not checked, you should maually terminate this instance after all services have been shut down.
	        	</label>
	        	<label class="checkbox"><input type="checkbox" name="delete_cluster" id="delete_cluster"><strong>Also delete this cluster?</strong>
	        		<br />
	        		If checked, this cluster will be deleted. <span class="text-warning">This action is irreversible!</span> All your data will be deleted.
	        	</label>
	        </fieldset>
		</div>    
	    <div class="modal-footer">
	    	<button ng-click="confirm($event, 'confirm')" class="btn btn-danger">Confirm</button>
	      	<button ng-click="cancel($event, 'cancel')" class="btn btn-primary">Cancel</button>  
		</div>
	</form>
</script>

<script type="text/ng-template" id="partials/initial-config.html">
	 <form id="init_cluster_form" name="init_cluster_form" action="${h.url_for(controller='root',action='initialize_cluster')}" method="POST">
		<div class="modal-header">
			<h3>Initial CloudMan Platform Configuration</h3>
		</div>
	    <div class="modal-body" >
	        <p>Welcome to CloudMan. This application will allow you to manage this cluster platform and
	        the services provided within. To get started, choose the type of platform you'd like to work
	        with and provide the associated value, if any.</p>
	        <div class="row-fluid">
	        	<div class="span1">
					<label class="radio"><input id="galaxy-cluster" type="radio" name="startup_opt" value="Galaxy" checked="true" /></label>
				</div>
				<div class="span11">
					<div class="row-fluid">
						<div class="span12">
							<strong>Galaxy Cluster</strong>: Galaxy application, available tools, reference datasets, SGE job manager, and a data volume.
							% if 'galaxy' not in image_config_support.apps:
		                        <u>NOTE</u>: The current machine image
		                        does not support this cluster type option; click on 'Show more startup options'
		                        so see the available cluster configuration options.
		                    % endif
		                        Specify the initial storage size (in Gigabytes):
	                    </div>
	                </div>
	                <div class="row-fluid">
						<div class="span12">
							<fieldset class="form-inline">
								<label class="radio"><input id="galaxy-default-size" type="radio" name="galaxy_data_option" value="default-size" checked='true' />&nbsp;Default size (${default_data_size} GB)</label>
								&nbsp;&nbsp;&nbsp;
								<label class="radio"><input id="galaxy-custom-size" type="radio" name="galaxy_data_option" value="custom-size" />&nbsp;Custom size:</label>
		                		<label><input type="number" class="input-mini" type="text" name="pss" id="g_pss" value="" min="1" />&nbsp;GB</label>
		            		</fieldset>
						</div>
					</div>
	            </div>
	        </div>
	        <div class="row-fluid" ng-show="isCollapsed">
	        	<div class="span11 offset1">
					<a ng-click="toggleOptions($event)" href="#">Show more startup options</a>
				</div>
			</div>
	        <div collapse="isCollapsed">
	        	<br />
	        	<div class="row-fluid">
		            <div class="span1">
		            	<label class="radio"><input type="radio" name="startup_opt" value="Shared_cluster" /></label>
		            </div> 
		            <div class="span11">
						<div class="row-fluid">
							<div class="span12">
								<strong>Share-an-Instance Cluster</strong>:
			            			derive your cluster form someone else's cluster. Specify the provided cluster share-string (for example,
			                    <span style="white-space:nowrap">cm-0011923649e9271f17c4f83ba6846db0/shared/2011-08-19--21-00</span>):
							</div>
						</div>
						<div class="row-fluid">
							<div class="span12">
								<fieldset class="form-inline">
		            				<label>Cluster share-string <input type="text" name="shared_bucket" id="shared_bucket" value="" class="input-xlarge" /></label>
		            			</fieldset>
		                	</div>	
		                </div>
		            </div>
				</div>
				<br />
	            <div class="row-fluid">
		            <div class="span1">
		            	<label class="radio"><input id="data-cluster" type="radio" name="startup_opt" value="Data" /></label>
		            </div>
		            <div class="span11">
						<div class="row-fluid">
							<div class="span12">
								<strong>Data Cluster</strong>: a persistent data volume and SGE.
								<br />
	                        	Specify the initial storage size (in Gigabytes):
	                    	</div>
	                    </div>
	                    <div class="row-fluid">
							<div class="span12">
								<fieldset class="form-inline">
									<label class="text"><input type="number" name="pss" id="d_pss" class="input-mini" min="1" />&nbsp;GB</label>
								</fieldset>
							</div>
						</div>
					</div>
	            </div>
	            <br />
	            <div class="row-fluid">
		            <div class="span1">
		            	<label class="radio"><input type="radio" name="startup_opt" value="SGE"></label>
		            </div>
		            <div class="span11">
						<div class="row-fluid">
							<div class="span12">
								<strong>Test Cluster</strong>: SGE only. No persistent storage is created.</p>
	                    	</div>
	                    </div>
					</div>
	            </div>
	        </div>
		</div>
		<div class="modal-footer">
	    	<button ng-click="confirm($event, 'confirm')" class="btn btn-primary" ng-disabled="init_cluster_form.$invalid">Confirm</button>
	      	<button ng-click="cancel($event, 'cancel')" class="btn">Cancel</button>  
		</div>
	</form>
</script>

<script type="text/ng-template" id="partials/autoscaling-config.html">
	<form id="form_autoscaling_config" name="turn_autoscaling_on_form" action="${h.url_for(controller='root', action='toggle_autoscaling')}" method="POST">
    	<div class="modal-header">
			<h3>Autoscaling Configuration</h3>
		</div>
	    <div class="modal-body" >
            <p> Autoscaling attempts to automate the elasticity offered by cloud computing for this
            	particular cluster. <strong>Once turned on, autoscaling takes over the control over the size
            	of your cluster.</strong>
            	<br />
				<a ng-show="isCollapsed" ng-click="toggleOptions($event)">Read more...</a>
			</p>
			<p>
	        <div collapse="isCollapsed">
	            <p>
	            Autoscaling is simple, just specify the cluster size limits you want to want to work within
	            and use your cluster as you normally do.  The cluster will not automatically shrink to less
	            than the minimum number of worker nodes you specify and it will never grow larger than the
	            maximum number of worker nodes you specify.
	            </p>
	            <p>
	            While respecting the set limits, if there are more jobs than the cluster can comfortably process at
	            a given time autoscaling will automatically add compute nodes; if there are cluster nodes
	            sitting idle at the end of an hour autoscaling will terminate those nodes reducing the size
	            of the cluster and  your cost.
	            </p>
	            <p>Once turned on, the cluster size limits respected by autoscaling can be adjusted or
	            autoscaling can be turned off.</p>
	            <p>NOTE: <strong>If there are no idle nodes to remove</strong>, although the maximum
	            limit may be higher than the number of available nodes, autoscaling will wait
	            until the nodes become idle to terminate them.
	         	</p>
	        </div>
	        </p>
            <div>
                <label>Minimum number of nodes to maintain:</label>
                <div>
                    <input type="number" min="0" step="1" name="as_min" id="as_min" size="10" ng-model="getAutoscalingSettings().as_min">
                </div>
                <label>Maximum number of nodes to maintain:</label>
                <div>
                    <input type="number" min="1" step="1" name="as_max" id="as_max" size="10" ng-model="getAutoscalingSettings().as_max">
                </div>
                <label>Type of Nodes(s):</label>
                <select name="instance_type" id="instance_type">
					<%include file="clouds/${cloud_name}/instance_types.mako" />
				</select>
            </div>
        </div>
		<div class="modal-footer">
	    	<button ng-click="toggleAutoscaling($event, 'activate')" class="btn btn-primary" ng-show="!isAutoScalingEnabled()">Turn autoscaling on</button>
	    	<button ng-click="confirm($event, 'reconfigure')" class="btn btn-primary" ng-show="isAutoScalingEnabled()">Adjust autoscaling</button>
	    	<button ng-click="toggleAutoscaling($event, 'deactivate')" class="btn btn-warning" ng-show="isAutoScalingEnabled()">Turn autoscaling off</button>
	      	<button ng-click="cancel($event, 'cancel')" class="btn">Cancel</button>  
		</div>
    </form>
</script>

## ****************************************************************************
## ***************************** Overlays and such ****************************
## ****************************************************************************

<div id="volume_expand_popup" class="box">
   <a class="boxclose"></a>
    <h2>Expand Disk Space</h2>
    <form id="expand_user_data_volume" name="expand_user_data_volume" class="generic_form" action="${h.url_for(controller='root',action='expand_user_data_volume')}" method="post">
        <div class="form-row">
        Through this form you may increase the disk space available to Galaxy. All of the cluster services (but not the cluster)
        <b>WILL BE STOPPED</b> until the new disk is ready, at which point they will all be restarted. This may result in Galaxy
        jobs that are currently running to fail. Note that the new disk size <b>must be larger</b> than the current disk size.
        <p>During this process, a snapshot of your data volume will be created, which can optionally be left in your account.
        If you decide to leave the snapshot for reference, you may also provide a brief note that will later be visible in
        the snapshot's description.</p>
        </div>
        <div class="form-row">
            <label>New Disk Size (minimum <span id="du-inc">0</span>GB, maximum 1000GB):</label>
            <div id="permanent_storage_size" class="form-row-input">
                <input type="text" name="new_vol_size" id="new_vol_size" value="0" size="25">
            </div>
            <label>Note (optional):</label>
            <div id="permanent_storage_size" class="form-row-input">
                <input type="text" name="vol_expand_desc" id="vol_expand_desc" value="" size="50"><br/>
            </div>
            <label>or delete the created snapshot after filesystem resizing?</label>
            <input type="checkbox" name="delete_snap" id="delete_snap"> If checked, the created snapshot will not be kept
            <div class="form-row">
                <input type="submit" value="Create Data Volume"/>
            </div>
        </div>
    </form>
</div>

## Overlay that prevents any future clicking, see CSS
<div id="snapshotoverlay" style="display:none">
    <div id="snapshotoverlay_msg_box" style="display:none"></div>
</div>
<div id="no_click_clear_overlay" style="display:none"></div>
<div id="snapshot_status_box" class="box">
    <h2>Volume Manipulation In Progress</h2>
    <div class="form-row">
        <p>Creating a snapshot of the cluster's data volume is in progress. All
        of the cluster services have been stopped for the time being and will resume
        automatically upon completion of the process.<br/>This message should go
        away after the process completes but if it does not, try refreshing the
        page then.</p>
    </div>
    <div class="form-row">
        Snapshot status: <span id="snapshot_status" style="font-style: italic;">configuring</span>
        <span id="snapshot_progress">&nbsp;</span>
    </div>
</div>
<div id="reboot_overlay" style="display:none"></div>
<div id="reboot_status_box" class="box">
    <h2>Reboot In Progress</h2>
    <div class="form-row">
        <p>This page should reload automatically when the reboot is complete.
        However, if it does not after approximately 5 minutes, reload it manually.</p>
    </div>
</div>
<div style="clear: both;"></div>
<div class="overlay" id="overlay" style="display:none"></div>
<div class="box" id="power_off">
    <a class="boxclose"></a>
    <h1>EC2 Cluster Configuration</h1>
    <form id="power_cluster_off_form" class="generic_form" name="power_cluster_form" action="${h.url_for(controller='root',action='kill_all')}" method="post">
        <div class="form-row">
            <label>Are you sure you want to power the cluster off?</label>
            <p>This action will shut down all services on the cluster and terminate
            any worker nodes (instances) associated with this cluster. Unless you
            choose to have the cluster deleted, all of your data will be preserved
            beyond the life of this instance. Next time you wish to start this same
            cluster, simply use the same user data (i.e., cluster name and credentials)
            and CloudMan will reactivate your cluster with your data.</p>
            <label for="terminate_master_instance"><b>Automatically terminate the master instance?</b></label>
            <div><input type="checkbox" name="terminate_master_instance" id="terminate_master_instance" checked>
            <label for="terminate_master_instance">If checked, this master instance will automatically terminate after all services have been shut down.
            If not checked, you should maually terminate this instance after all services have been shut down.</label></div>
            <p></p><b>Also delete this cluster?</b>
            <div><input type="checkbox" name="delete_cluster" id="delete_cluster">
            If checked, this cluster will be deleted. <b>This action is irreversible!</b> All your data will be deleted.</div>
            <div style="padding-top: 20px;"><input type="submit" value="Yes, power off"></div>
        </div>
    </form>
</div>
<div style="clear: both;"></div>
## Autoscaling link
##Autoscaling is <span id='autoscaling_status'>N/A</span>. Turn <a id="toggle_autoscaling_link" style="text-decoration: underline; cursor: pointer;">N/A</a>?
## Autoscaling configuration popup
<div class="box" id="turn_autoscaling_off">
    <a class="boxclose"></a>
    <h2>Autoscaling Configuration</h2>
    <form id="turn_autoscaling_off_form" class="autoscaling_form" name="turn_autoscaling_off_form" action="${h.url_for(controller='root', action='toggle_autoscaling')}" method="post">
        <div class="form-row">
            If autoscaling is turned off, the cluster will remain in it's current state and you will
            be able to manually add or remove nodes.
            <div class="form-row"><input type="submit" value="Turn autoscaling off"/></div>
        </div>
    </form>
</div>
<div class="box" id="turn_autoscaling_on">
    <a class="boxclose"></a>
    <h2>Autoscaling Configuration</h2>
    <form id="turn_autoscaling_on_form" class="autoscaling_form" name="turn_autoscaling_on_form" action="${h.url_for(controller='root', action='toggle_autoscaling')}" method="post">
        <div class="form-row">
            <p>Autoscaling attempts to automate the elasticity offered by cloud computing for this
            particular cluster. <b>Once turned on, autoscaling takes over the control over the size
            of your cluster.</b></p>
            <p>
            Autoscaling is simple, just specify the cluster size limits you want to want to work within
            and use your cluster as you normally do.  The cluster will not automatically shrink to less
            than the minimum number of worker nodes you specify and it will never grow larger than the
            maximum number of worker nodes you specify.
            </p>
            <p>
            While respecting the set limits, if there are more jobs than the cluster can comfortably process at
            a given time autoscaling will automatically add compute nodes; if there are cluster nodes
            sitting idle at the end of an hour autoscaling will terminate those nodes reducing the size
            of the cluster and  your cost.
            </p>
            <p>Once turned on, the cluster size limits respected by autoscaling can be adjusted or
            autoscaling can be turned off.</p>
            <div class="form-row">
                <label>Minimum number of nodes to maintain:</label>
                <div class="form-row-input">
                    <input type="text" name="as_min" id="as_min" value="" size="10">
                </div>
                <label>Maximum number of nodes to maintain:</label>
                <div class="form-row-input">
                    <input type="text" name="as_max" id="as_max" value="" size="10">
                </div>
                <label>Type of Nodes(s):</label>
                <div id="instance_type" class="form-row-input">
                    ## Select available instance types based on cloud name
                    <%include file="clouds/${cloud_name}/instance_types.mako" />
                </div>
                <br/><div class="form-row"><input type="submit" value="Turn autoscaling on"/></div>
            </div>
        </div>
    </form>
</div>
<div class="box" id="adjust_autoscaling">
    <a class="boxclose"></a>
    <h2>Adjust Autoscaling Configuration</h2>
    <form id="adjust_autoscaling_form" class="autoscaling_form" name="adjust_autoscaling_form" action="${h.url_for(controller='root', action='adjust_autoscaling')}" method="post">
        <div class="form-row">
            Adjust the number of instances autoscaling should maintain for this cluster.
            <p>NOTE: <b>If there are no idle nodes to remove</b>, although the maximum
            limit may be higher than the number of available nodes, autoscaling will wait
            until the nodes become idle to terminate them.
            <div class="form-row">
                <label>Minimum number of nodes to maintain:</label>
                <div class="form-row-input">
                    <input type="text" name="as_min_adj" id="as_min_adj" value="" size="10">
                </div>
                <label>Maximum number of nodes to maintain:</label>
                <div class="form-row-input">
                    <input type="text" name="as_max_adj" id="as_max_adj" value="" size="10">
                </div>
                <div class="form-row"><input type="submit" value="Adjust autoscaling"/></div>
            </div>
        </div>
    </form>
</div>
<div class="box" id="share_a_cluster_overlay">
    <a class="boxclose"></a>
    <div id="sharing_accordion">
        <h3><a href="#">Currently shared instances</a></h3>
        <div id='shared_instances_list'>
            <p>Retrieving your shared cluster instances...</p>
            <div class="spinner">&nbsp;</div>
        </div>
        <h3><a href="#">Share-an-instance</a></h3>
        <div><form id="share_a_cluster_form" class="share_a_cluster" name="share_a_cluster_form" action="${h.url_for(controller='root', action='share_a_cluster')}" method="post">
            <div class="form-row">
                <p><b>This form allows you to share this cluster instance, at its current state,
                with others.</b> You can make the instance public or share it with specific
                users by providing their account information below.<br/>
                You may also share the instance with yourself by specifying your own
                credentials, which will have the effect of saving the instance at
                its current state.</p>
                <p><b>While setting up an instance to be shared, all currently running
                cluster services will be stopped.</b> Then, a snapshot of your data
                volume and a folder in your cluster's bucket will be created
                (under 'shared/[current date and time]); this folder will contain
                your cluster's current configuration. The created snapshot
                and the folder will be given READ permissions to the users
                you choose (or make it public). This will enable those users to instantiate
                their own instances of the given cluster instance. This implies that you will
                only be paying for the created snapshot while users deriving a cluster from
                yours will incur costs for running the actual cluster. After the sharing
                process is complete, services on your cluster will automatically resume.</p>
                <div class="form-row">
                    <div id="public_private">
                        <input type="radio" id="public_visibility" name="visibility" value="public" checked="yes">Public</input>
                        <input type="radio" id="shared_visibility" name="visibility" value="shared">Shared</input>
                    </div>
                    <div id="user_permissions" style="display: none;">
                        <div id="add_user">
                            <h4>Specific user permissions:</h4>
                            <p><strong>Both fields must be provided for each of the users.</strong><br/>
                            These numbers can be obtained from the bottom of the
                            AWS Security Credentials page, under <i>Account Identifiers</i> section.</p>
                            <div style="height: 38px;"><span style="display: inline-block; width: 150px;">AWS account numbers:</span>
                                <input type="text" id="user_ids" name="user_ids" size="40" value="" />
                                <span class="share_cluster_help_text">CSV numbers</span>
                            </div>
                            <div style="height: 38px;"><span style="display: inline-block; width: 150px;">AWS canonical user IDs:</span>
                                <input type="text" id="canonical_ids" name="canonical_ids" size="40" value="" />
                                <span class="share_cluster_help_text">CSV HEX numbers</span>
                            </div>
                        </div>
                    </div>
                    <div class="form-row"><input type="submit" value="Share-an-instance"/></div>
                </div>
            </div>
        </form></div>
    </div>
</div>
<div class="box" id="del_scf_popup">
    <h2>Delete shared cluster instance confirmation</h2>
    <div>Are you sure you want to delete shared cluster instance under
    <i><span id="scf_txt">&nbsp;</span></i>
    and the corresponding snapshot with ID <i><span id="scf_snap">&nbsp;</span></i>?<br/>
    <p>This action cannot be undone.</p></div>
    <p><span class="action-button" id="del_scf_conf">Delete this instance</span>&nbsp;
    <span class="action-button" id="del_scf_cancel">Do not delete</span></p>
</div>
<div id="voloverlay" class="overlay" style="display:none"></div>
<div id="popupoverlay" class="overlay" style="display:none"></div>
<div class="box" id="volume_config">
    <h2 style="text-align:center;">Initial CloudMan Platform Configuration</h2>
    <div class="form-row">
        <p style="text-align:justify;">Welcome to CloudMan. This application will allow you to manage this cluster platform and
        the services provided within. To get started, choose the type of platform you'd like to work
        with and provide the associated value, if any.</p>
    </div>
    <form id="initial_volume_config_form" name="power_cluster_form" action="${h.url_for(controller='root',action='initialize_cluster')}" method="post">
        <div class="form-row">
            ## Allow Galaxy-cluster only if the underlying image/system supports it
            % if 'galaxy' in image_config_support.apps:
                <p style="text-align:justify;">
            % else:
                <p style="text-align:justify;" class='disabled'>
            % endif
                <input id="galaxy-cluster" type="radio" name="startup_opt" value="Galaxy" checked='true' style="float:left">
                    <label for="galaxy-cluster">
                    <span style="display: block;margin-left: 20px;">
                        <b>Galaxy Cluster</b>: Galaxy application, available tools, reference datasets, SGE job manager, and a data volume.
            % if 'galaxy' not in image_config_support.apps:
                        <u>NOTE</u>: The current machine image
                        does not support this cluster type option; click on 'Show more startup options'
                        so see the available cluster configuration options.
            % endif
                        Specify the initial storage size (in Gigabytes):
                    </span>
                    </label>
                    <div style="text-align:left;margin-left: 18px">
                    <input id="galaxy-default-size" type="radio" name="galaxy_data_option" value="default-size" checked='true'>
                    <label for="galaxy-default-size">Default size (${default_data_size} GB)</label>
                    <input id="galaxy-custom-size" type="radio" name="galaxy_data_option" value="custom-size" style="margin-left:70px">
                    <label for="galaxy-custom-size">Custom size:</label>
                    <input type="text" name="pss" class="LV_field" id="g_pss" value="" size="2"> GB
                    </div>
                    <div style="height: 5px;">
                        <span style="margin-left: 247px;" id="g_pss_vtag"></span>
                    </div>
                </p>
        </div>
        <div id='extra_startup_options'>
            <div class="form-row">
                <p style="text-align:justify;"><input id="share-cluster" type="radio" name="startup_opt" value="Shared_cluster" style="float:left">
                    <label for="share-cluster">
                    <span style="display: block;margin-left: 20px;">
                        <b>Share-an-Instance Cluster</b>: derive your cluster form someone else's cluster.
                        Specify the provided cluster share-string (for example,
                        <span style="white-space:nowrap">cm-0011923649e9271f17c4f83ba6846db0/shared/2011-08-19--21-00</span>):
                    </span>
                    </label>
                </p>
                <input style="margin-left:20px"  type="text" name="shared_bucket" class="LV_field" id="shared_bucket" value="" size="50">
                    <label for="shared_bucket">Cluster share-string</label>
            </div>

            <div class="form-row">
                <p style="text-align:justify;"><input id="data-cluster" type="radio" name="startup_opt" value="Data" style="float:left">
                    <label for="data-cluster">
                    <span style="display: block;margin-left: 20px;">
                        <b>Data Cluster</b>: a persistent data volume and SGE.
                        Specify the initial storage size (in Gigabytes):
                    </span>
                    </label>
                </p>
                <input style="margin-left:20px"  type="text" name="pss" class="LV_field" id="d_pss" value="" size="3">GB<span id="d_pss_vtag"></span>
            </div>

            <div class="form-row">
                <p style="text-align:justify;"><input type="radio" name="startup_opt" value="SGE" style="float:left" id="sge-cluster">
                <label for="sge-cluster">
                <span style="display: block;margin-left: 20px;">
                    <b>Test Cluster</b>: SGE only. No persistent storage is created.</p>
                </span>
                </label>
            </div>
        </div>
        <div id="toggle_extra_startup_options_cont" class="form-row"><a id='toggle_extra_startup_options' href="#">Show more startup options</a></div>
        <br/>
        <div class="form-row" style="text-align:center;">
            <input type="submit" value="Choose platform type" id="start_cluster_submit_btn"/>
        </div>
        </form>
    </div>
</div>


## ****************************************************************************
## ******************************** Javascript ********************************
## ****************************************************************************

<script type="text/javascript">
var instances = Array();
var cluster_status = "OFF";
var fs_det_vis = false;
var last_log = 0;
var click_timeout = null;
var use_autoscaling = null;
var as_min = 0; //min number of instances autoscaling should maintain
var as_max = 0; //max number of instances autoscaling should maintain

$(function() {
    $( "#sharing_accordion" ).accordion({
        autoHeight: false,
        navigation: true,
    });
});
</script>

<script type='text/javascript' src="${h.url_for('/static/scripts/jquery.tipsy.js')}"></script>
<script type='text/javascript' src="${h.url_for('/static/scripts/jquery.form.js')}"></script>
<script type='text/javascript' src="${h.url_for('/static/scripts/cluster_canvas.js')}"> </script>
## <script type='text/javascript' src="${h.url_for('/static/scripts/inline_edit.js')}"> </script>
<script type='text/javascript' src="${h.url_for('/static/scripts/jquery.stopwatch.js')}"> </script>
<script type="text/javascript">

function hidebox(){
    $('.box').hide();
    $('.overlay').hide();
    $('.cluster_scale_popup').hide();
    $('.action-button.button-clicked').removeClass('button-clicked');
    $('#popupoverlay').hide();
    $('#volume_expand_popup').hide();
    $('#power_off').hide();
    $('#overlay').hide();
}


function toggleVolDialog(){
}

function update_ui(data){
    if (data){
        $('#dns').attr("href", data.dns);
        if (data.dns == '#'){
            $('#dns').addClass('ab_disabled');
            $('#dns').attr("target", '');
            $('#galaxy_log').hide()
        }else{
            $('#dns').removeClass('ab_disabled');
            $('#dns').attr("target", '_blank');
            $('#galaxy_log').show()
        };
        //$('#status-idle').text( data.instance_status.idle );
        //$('#status-available').text( data.instance_status.available );
        //$('#status-total').text( data.instance_status.requested );
        //$('#du-total').text(data.disk_usage.total);
        //$('#du-inc').text(data.disk_usage.total.slice(0,-1));
        //$('#du-used').text(data.disk_usage.used);
        //$('#du-pct').text(data.disk_usage.pct);
        if($('#new_vol_size').val() == '0'){
            $('#new_vol_size').val(data.disk_usage.total.slice(0,-1));
        }
        //if (parseInt(data.disk_usage.pct) > 80){
        //    $('#storage_warning').show();
        //}else{
        //    $('#storage_warning').hide();
        //}
        //$('#snap-progress').text(data.snapshot.progress);
        //$('#snap-status').text(data.snapshot.status);
        // DBTODO write generic services display
        $('#data-status').removeClass('status_nodata status_green status_red status_yellow').addClass('status_'+data.data_status);
        // Show volume manipulating options only after data volumes are ready
        if (data.data_status !== 'green'){
            $('#expand_vol').hide();
            $('#share_a_cluster').hide();
        }else{
            $('#expand_vol').show();
            $('#share_a_cluster').show();
        }
        $('#app-status').removeClass('status_nodata status_green status_red status_yellow').addClass('status_'+data.app_status);
        // $('#status_svcs').html(
        //     "<ul><li class='fs_det_clicker'><div class='status_" + data.services.fs + "'>&nbsp;</div>Filesystems</li>\
        //     <li><div class='status_" + data.services.pg + "'>&nbsp;</div>Database</li>\
        //     <li><div class='status_" + data.services.sge + "'>&nbsp;</div>Scheduler</li>\
        //     <li><div class='status_" + data.services.galaxy + "'>&nbsp;</div>Galaxy</li></ul>"
        //     );
        fsdet = "<ul>";
        //for (i = 0; i < data.all_fs.length; i++){
        //    fsdet += "<li><div class='status_" + data.all_fs[i][1] + "'>&nbsp;</div>" + data.all_fs[i][0] + "</li>";
        //}
        fsdet += "</ul>";
        $('#fs_detail').html(fsdet);
        cluster_status = data.cluster_status;
        if (cluster_status === "SHUTTING_DOWN"){
            shutting_down();
            return true; // Must return here because the remaining code clears the UI
        }
        else if (cluster_status === "TERMINATED"){
            $('.action-button').addClass('ab_disabled');
            $('#snapshotoverlay').show(); // Overlay that prevents any future clicking
            $('#snapshotoverlay_msg_box').html("<div id='snapshotoverlay_msg_box_important'> \
                <h4>Important:</h4><p>This cluster has terminated. If not done automatically, \
                please terminate the master instance from the cloud console.</p></div>");
            $('#snapshotoverlay_msg_box').show();
            return true; // Must return here because the remaining code clears the UI
        }
        //if (data.autoscaling.use_autoscaling === true) {
        //    use_autoscaling = true;
        //    as_min = data.autoscaling.as_min;
        //    as_max = data.autoscaling.as_max;
        //    $('#scale_up_button').addClass('ab_disabled');
        //    $('#scale_up_button > img').hide();
        //    $('#scale_down_button').addClass('ab_disabled');
        //    $('#scale_down_button > img').hide();
        //} else if (data.autoscaling.use_autoscaling === false) {
        //    use_autoscaling = false;
        //    as_min = 0;
        //    as_max = 0;
        //    $('#scale_up_button').removeClass('ab_disabled');
        //    $('#scale_up_button > img').show();
        //    if (data.instance_status.requested == '0'){
        //        $('#scale_down_button').addClass('ab_disabled');
        //        $('#scale_down_button > img').hide();
        //    }else{
        //        $('#scale_down_button').removeClass('ab_disabled');
        //        $('#scale_down_button > img').show();
        //    }
        //}
        //if (data.snapshot.status !== "None"){
        //    if(!$('#snapshotoverlay').is(':visible')) {
        //        $('#snapshotoverlay').show();
        //    }
        //    $('#snapshot_status_box').show();
        //    $('#snapshot_status').text(data.snapshot.status);
        //    if (data.snapshot.progress !== "None"){
        //        $('#snapshot_progress').html("; progress: <i>"+data.snapshot.progress+"</i>");
        //    } else {
        //        $('#snapshot_progress').html("");
        //    }
        //}else{
        //    $('#snapshot_status_box').hide();
        //    $('#snapshotoverlay').hide();
       // }
    }
}


function update(repeat_update){
    $.getJSON("${h.url_for(controller='root',action='full_update')}",
        {l_log : last_log},
        function(data){
            if (data){
                update_ui(data.ui_update_data);
                update_messages(data.messages);
            }
        });
    if (repeat_update === true){
        window.setTimeout(function(){update(true)}, 5000);
    }
}

function reboot_update(){
    $.ajax({
      url: "${h.url_for(controller='root',action='full_update')}",
      dataType: 'json',
      success: function(data){
                update_ui(data.ui_update_data);
                $('#reboot_overlay').hide();
                $('#reboot_status_box').hide();
                },
      error: function(data){window.setTimeout(function(){reboot_update()}, 10000)}
    });
}

function show_confirm(scf, snap_id){
    $('#del_scf_popup').show();
    $('#scf_txt').text(scf);
    $('#scf_snap').text(snap_id);
    // FIXME: Need to have an individual element ID for each of the shared instances
    $('#del_scf_conf').click(function(){
        $.get("${h.url_for(controller='root',action='delete_shared_instance')}",
            {'shared_instance_folder': scf, 'snap_id': snap_id},
            function(){
                $('#del_scf_popup').hide();
                get_shared_instances();
            });
    });
    $('#del_scf_cancel').click(function(){
        $('#del_scf_popup').hide();
    });
}
function get_shared_instances(){
    $.getJSON("${h.url_for(controller='root',action='get_shared_instances')}",
        {},
        function(data){
            if(data){
                var shared_list = $('#shared_instances_list').html(
                    "<p>These are the share string IDs that you can share " +
                    "with others so they can create and instantiate their instances " +
                    "of your shared cluster. Also, for reference, corresponding " +
                    "snapshot ID's are provided and you have an option to delete a " +
                    "given shared instance. <b>Note</b> that once deleted, any derived instances " +
                    "that have been created and used will cease to be able to be started.</p>");
                var table = $("<table/>");
                if (data.shared_instances.length > 0) {
                    table.addClass("shared_instances_table");
                    tr = $('<tr/>');
                    tr.append($('<th/>').text("Visibility"));
                    tr.append($('<th/>').text("Share string ID"));
                    tr.append($('<th/>').text("Snapshot ID"));
                    tr.append($('<th/>').text("Delete?"));
                    table.append(tr);
                    for (n=0; n<(data.shared_instances).length; n++) {
                        var fn = function(i) {
                            var tr = $("<tr/>");
                            tr.append($('<td/>').text(data.shared_instances[i].visibility));
                            tr.append($('<td/>').text(data.shared_instances[i].bucket));
                            tr.append($('<td/>').text(data.shared_instances[i].snap));
                            anchor = $("<a>&nbsp;</a>").click(function () {
                                show_confirm(data.shared_instances[i].bucket, data.shared_instances[i].snap);
                            }).addClass("del_scf");
                            tr.append($('<td/>').html(anchor));
                            table.append(tr);
                        };
                        fn(n);
                    }
                    shared_list.append(table);
                } else {
                    shared_list.text("You have no shared cluster instances.");
                }
            }
        });
}


// This is called when worker nodes are added by the user.
// Causes a pending instance to be drawn
function add_pending_node() {
    inst_kind = 'on-demand';
    if ($('#use_spot').length != 0 && $('#use_spot').attr("checked") == 'checked') {
        inst_kind = 'spot';
    }// increment_pending_instance_count(parseInt(document.getElementById("add_instances_form").elements["number_nodes"].value), inst_kind);
        return true;
}

function shutting_down() {
    // Do the UI updates to indicate the cluster is in the 'SHUTTING_DOWN' state
    $('#snapshotoverlay_msg_box').html("<div id='snapshotoverlay_msg_box_warning'> \
        <h4>Important:</h4><p>This cluster is terminating. Please wait for all the services \
        to stop and for all the nodes to be removed. Then, if not done automatically, \
        terminate the master instance from the cloud console. All of the buttons on the \
        console have been disabled at this point.</p></div>");
    $('#snapshotoverlay_msg_box').show();
    $('.action-button').addClass('ab_disabled');
    // Show and scroll the log
    $('#snapshotoverlay').show(); // Overlay that prevents any future clicking
}

$(document).ready(function() {
    var initial_cluster_type = '${initial_cluster_type}';
    var permanent_storage_size = ${permanent_storage_size};

    $('#shared_visibility').click(function() {
        $('#user_permissions').show();
        $('#user_ids').val("");
        $('#canonical_ids').val("");
    });
    $('#public_visibility').click(function() {$('#user_permissions').hide();});

    $('#stop-button').click(function(){
        if ($(this).hasClass('ab_disabled')){
            return;
        }else{
            $('#overlay').show();
            $('#power_off').show();
        }
    });
    $('#scale_up_button').click(function(){
        if ($(this).hasClass('ab_disabled')){
            return;
        }else{
            $('.cluster_scale_popup').hide();
            $('.action-button.button-clicked').removeClass('button-clicked');
            $('#popupoverlay').show();
            $('#scale_up_button').addClass('button-clicked');
            $('#cluster_scale_up_popup').show();
        }
    });
    $('#scale_down_button').click(function(){
        if ($(this).hasClass('ab_disabled')){
            return;
        }else{
            $('.cluster_scale_popup').hide();
            $('.action-button.button-clicked').removeClass('button-clicked');
            if (instances.length > 0) {
                $('#scale_down_button').addClass('button-clicked');
                $('#popupoverlay').show();
                $('#cluster_scale_down_popup').show();
            }
        }
    });
    $('#share_a_cluster').click(function(){
        if ($(this).hasClass('ab_disabled')){
            return;
        }else{
            $('#overlay').show();
            $('#share_a_cluster_overlay').show();
            get_shared_instances();
        }
    });
    $('#expand_vol').click(function(){
        $('#overlay').show();
        $('#volume_expand_popup').show();
    });
    $('#overlay').click(function(){
        hidebox();
    });
    $('#toggle_extra_startup_options').click(function(){
        // $('#toggle_extra_startup_options_cont').hide();
        // $('#extra_startup_options').show();
        if ($('#extra_startup_options').is(":visible")){
            $('#extra_startup_options').hide();
            $('#toggle_extra_startup_options').text('Show more startup options');
        }else{
            $('#extra_startup_options').show();
            $('#toggle_extra_startup_options').text("Hide extra options");
        }
    });
    $('#popupoverlay').click(function(){
        $('.cluster_scale_popup').hide();
        $('#volume_expand_popup').hide();
        $('.action-button.button-clicked').removeClass('button-clicked');
        $('#popupoverlay').hide();
    });
    $('.boxclose').click(function(){
        hidebox();
    });

    $('.generic_form').ajaxForm({
        type: 'POST',
        dataType: 'json',
        beforeSubmit: function(data){
            hidebox();
        },
        success: function( data ) {
            update_ui(data);
        }
    });

    $('.autoscaling_form').ajaxForm( {
        type: 'POST',
        dataType: 'json',
        beforeSubmit: function(data){
            hidebox();
        },
        success: function( data ) {
            if (data){
                use_autoscaling = data.running;
                as_min = data.as_min;
                as_max = data.as_max;
                update_ui(data.ui_update_data);
            }
            refreshTip();
        }
    });

    $('#share_a_cluster_form').ajaxForm({
        type: 'POST',
        dataType: 'json',
        beforeSubmit: function(data){
            hidebox();
            $('#snapshotoverlay').show();
            $('#snapshot_status_box').show();
        },
        success: function(data) {
            $('#snapshot_status_box').hide();
            $('#overlay').show();
            $('#share_a_cluster_overlay').show();
            get_shared_instances();
        }
    });

    $('#initial_volume_config_form').ajaxForm( {
        type: 'POST',
        dataType: 'json',
        beforeSubmit: function(data){
            cluster_status = "STARTING";
        },
        success: function( data ) {
            hidebox();
            update_ui(data);
        }
    });

    $('#power_cluster_off_form').ajaxForm( {
        type: 'POST',
        dataType: 'json',
        beforeSubmit: function(data){
            shutting_down();
            hidebox();
        },
        success: function( data ) {
            update_ui(data);
        }
    });

    $('#update_reboot_now').click(function(){
        $('#reboot_overlay').show();
        $('#reboot_status_box').show();
        $.getJSON("${h.url_for(controller='root',action='reboot')}",
            function(data){
                if (data.rebooting === true){
                    window.setTimeout(function(){reboot_update()}, 10000);
                }else{
                    update(false);
                }
            });
    });

    $('#update_cm').click(function(){
        $.getJSON("${h.url_for(controller='root',action='update_users_CM')}",
            function(data){
                if (data.updated === true){
                    $('#cm_update_message').html('<span style="color:#5CBBFF">Update Successful</span>, CloudMan update will be applied on cluster restart.&nbsp;&nbsp;&nbsp;');
                    $('#update_reboot_now').show();
                }else{
                    $('#cm_update_message').html('There was an error updating CloudMan.&nbsp;&nbsp;&nbsp;');
                }
            });
    });
    // Toggle accessibility of spot price field depending on whether spot instances should be used
    $("#use_spot").click(function() {
        if ($("#use_spot").attr("checked") == 'checked') {
            $("#spot_price").removeAttr('disabled');
            $("#spot_price").focus();
        } else {
            $("#spot_price").attr('disabled', 'disabled');
            $("#spot_price").val("");
        }
    });
    // Form validation
    //var expanded_storage_size = new LiveValidation('new_vol_size', { validMessage: "OK", wait: 300 } );
    //expanded_storage_size.add( Validate.Numericality, { minimum: 1, maximum: 1000 } );

    //var autoscaling_min_bound = new LiveValidation('as_min', { validMessage: "OK", wait: 300 } );
    //autoscaling_min_bound.add( Validate.Numericality, { minimum: 0, maximum: 19, onlyInteger: true } );
    //var autoscaling_max_bound = new LiveValidation('as_max', { validMessage: "OK", wait: 300 } );
    //autoscaling_max_bound.add( Validate.Numericality, { minimum: 0, maximum: 19, onlyInteger: true } );

    $('#as_min').change(function(){
        autoscaling_max_bound.validations[0].params.minimum = $('#as_min').val();
    });
    $('#as_max').change(function(){
        autoscaling_min_bound.validations[0].params.maximum = $('#as_max').val();
    });

    // FIXME: Is there a better way of doing this check than repeating all the code from the preceeding validation?
    //var autoscaling_min_bound_adj = new LiveValidation('as_min_adj', { validMessage: "OK", wait: 300 } );
    //autoscaling_min_bound_adj.add( Validate.Numericality, { minimum: 0, maximum: 19, onlyInteger: true } );
    //var autoscaling_max_bound_adj = new LiveValidation('as_max_adj', { validMessage: "OK", wait: 300 } );
    //autoscaling_max_bound_adj.add( Validate.Numericality, { minimum: 0, maximum: 19, onlyInteger: true } );
    $('#as_min_adj').change(function(){
        autoscaling_max_bound_adj.validations[0].params.minimum = $('#as_min_adj').val();
    });
    $('#as_max_adj').change(function(){
        autoscaling_min_bound_adj.validations[0].params.maximum = $('#as_max_adj').val();
    });


    if (initial_cluster_type === 'None') {
        toggleVolDialog();
    }
    // Add tooltips
    $('#share_a_cluster').tipsy({gravity: 'w', fade: true});
    $('#expand_vol').tipsy({gravity: 'w', fade: true});

    // Enable onclick events for the option in the initial cluster configuration box
    $('#galaxy-default-size').click(function() {
        $('#galaxy-cluster').attr('checked', 'checked');
    });
    $('#galaxy-custom-size').click(function() {
        $('#g_pss').focus();
    });
    $('#g_pss').focus(function() {
        $('#galaxy-cluster').attr('checked', 'checked');
        $('#galaxy-custom-size').attr('checked', 'checked');
    });
    $('#share-cluster').click(function() {
        $('#shared_bucket').focus();
    });
    $('#shared_bucket').focus(function() {
        $('#share-cluster').attr('checked', 'checked');
    });
    $('#data-cluster').click(function() {
        $('#d_pss').focus();
    });
    $('#d_pss').focus(function() {
        $('#data-cluster').attr('checked', 'checked');
    });

});

		// Place URLs here so that url_for can be used to generate them
        var get_cloudman_index_update_url = "${h.url_for(controller='root',action='full_update')}";
        var get_cloudman_status_update_url = "${h.url_for(controller='root',action='instance_feed_json')}";
        var initial_cluster_type = '${initial_cluster_type}';
</script>
    </div>
</%def>
