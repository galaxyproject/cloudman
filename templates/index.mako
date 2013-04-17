<%inherit file="/base_panels.mako"/>
<%def name="main_body()">

<script type='text/javascript' src="//cdnjs.cloudflare.com/ajax/libs/flot/0.7/jquery.flot.min.js"></script>
<script type='text/javascript' src="//raw.github.com/flot/flot/master/jquery.flot.time.js"></script>
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
			    					<button class="btn btn-small" ng-click="share_cluster($event)" ng-disabled="getCloudmanStatus().data_status != 'green'">
					  					<i class="icon-share"></i>
					    				Share Cluster
				  					</button>
			    				</td>
			    				<td><strong>Disk status:</strong></td>
			    				<td>
			    					{{ getCloudmanStatus().disk_usage.used }} / {{ getCloudmanStatus().disk_usage.total }} ({{ getCloudmanStatus().disk_usage.pct }})
			    				</td>
			    				<td>
				    				<button class="btn btn-small" ng-click="resize_fs($event)" ng-disabled="getCloudmanStatus().data_status != 'green'">
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
            	particular cluster. <strong>Once turned on, autoscaling takes control over the size
            	of your cluster.</strong>
            	<br />
				<a href="#" ng-show="isCollapsed" ng-click="toggleOptions($event)">Read more...</a>
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


<%include file="bits/fs_resize_dialogue.htm" />


<script type="text/ng-template" id="partials/share_cluster_template.html">
    <form id="share_a_cluster_form" class="share_a_cluster" name="share_a_cluster_form" action="${h.url_for(controller='root', action='share_a_cluster')}" method="post">
    	<div class="modal-header">
    		<h3>Cluster Sharing Configuration</h3>
    	</div>
    	<div class="modal-body" >
    		<accordion close-others="true">
		    	<accordion-group is-open="true">
		    		<accordion-heading><strong>Currently shared instances</strong></accordion-heading>
		    		<div class="row-fluid">
		    			<div class="span12">
		    				<p ng-show="isRetrieving"><i class="icon-spinner icon-spin"></i>&nbsp;Retrieving your shared cluster instances...</p>
	            			
	            			<div ui-if="!isRetrieving && shared_instances">
		            			<p> These are the share string IDs that you can share
	                    			with others so they can create and instantiate their instances
	                    			of your shared cluster. Also, for reference, corresponding
	                    			snapshot ID's are provided and you have an option to delete a
	                    			given shared instance. <strong>Note</strong> that once deleted, any derived instances
	                    			that have been created and used will cease to be able to be started.</p>
	                    		<table class="table">
	                    			<thead>
		                    			<tr>
		                    				<th>Visibility</th>
		                    				<th>Share string ID</th>
		                    				<th nowrap>Snapshot ID</th>
		                    				<th></th>
		                    			</tr>
	                    			</thead>
	                    			<tbody>
	                    				<tr ng-repeat="instance in shared_instances">
	                    					<td>{{ instance.visibility }}</td>
	                    					<td>{{ instance.bucket }}</td>
	                    					<td>{{ instance.snap }}</td>
	                    					<td><button class="btn btn-link" ng-click="deleteShare($event, instance)"><i class="icon-remove"></i></button></td>
	                    				</tr>
	                    			</tbody>
	                    		</table>
	                    	</div>
                    		<span ui-if="!isRetrieving && !shared_instances">
                    			You have no shared cluster instances.
                    		</span>
		    			</div>
		    		</div>
		    	</accordion-group>
		    	<accordion-group>
		    		<accordion-heading><strong>Share-an-instance</strong></accordion-heading>
		    		<div class="row-fluid">
		    			<div class="span12">
		    				<p><strong>This form allows you to share this cluster instance, at its current state,
	                		with others.</strong> You can make the instance public or share it with specific
			                users by providing their account information below.<br/></p>
			                <a href="#" ng-show="isCollapsed" ng-click="toggleCollapsed($event)">Read more...</a>
			                <div collapse="isCollapsed">
				                <p>
				                You may also share the instance with yourself by specifying your own
				                credentials, which will have the effect of saving the instance at
				                its current state.
				                </p>
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
				                process is complete, services on your cluster will automatically resume.
				                </p>
			                </div>
			                
		    			</div>
		    		</div>
		    		<div class="row-fluid">
		    			<div class="span12">
		    				<br />
		    				Cluster share permissions:<br />
		    				<div class="form-inline">
								<label class="radio"><input type="radio" id="public_visibility" name="visibility" value="public" checked="yes" ng-model="shared_select" />Public</label>
								&nbsp;&nbsp;
							    <label class="radio"><input type="radio" id="shared_visibility" name="visibility" value="shared" ng-model="shared_select" />Shared</label>
							</div>
	                        
	                        <div ng-show="shared_select=='shared'">
	                            <h4>Specific user permissions:</h4>
	                            <p><strong>Both fields must be provided for each of the users.</strong><br/>
	                            These numbers can be obtained from the bottom of the
	                            AWS Security Credentials page, under <i>Account Identifiers</i> section.</p>
	                            
	                            <div class="row-fluid">
		    						<div class="span5"><label class="control-label" for="user_ids">AWS account numbers:</label></div>
			                        <div class="span5"><input type="text" id="user_ids" name="user_ids" value="" placeholder="CSV numbers"/></div>
			                     </div>
			                     <div class="row-fluid">
		    						<div class="span5"><label class="control-label" for="canonical_ids">AWS canonical user IDs:</label></div>
			                        <div class="span5"><input type="text" id="canonical_ids" name="canonical_ids" value="" placeholder="CSV HEX numbers" /></div>
			                     </div>
	                        </div>
		    			</div>
		    		</div>
		    	</accordion-group>
		    </accordion>
		</div>
		<div class="modal-footer">
	    	<button ng-click="confirm($event, 'confirm')" class="btn btn-primary" ng-disabled="share_a_cluster_form.$invalid">Confirm</button>
	      	<button ng-click="cancel($event, 'cancel')" class="btn">Cancel</button>  
		</div>
    </form>
</script>
    
## ****************************************************************************
## ******************************** Javascript ********************************
## ****************************************************************************

<script type="text/javascript">
		// Place URLs here so that url_for can be used to generate them
        var get_cloudman_index_update_url = "${h.url_for(controller='root',action='full_update')}";
        var get_cloudman_status_update_url = "${h.url_for(controller='root',action='instance_feed_json')}";
        var get_shared_instances_url = "${h.url_for(controller='root',action='get_shared_instances')}";
        var delete_shared_instances_url = "${h.url_for(controller='root',action='delete_shared_instance')}";
        var initial_cluster_type = '${initial_cluster_type}';
</script>

</div>
</%def>
