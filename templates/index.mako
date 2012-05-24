<%inherit file="/base_panels.mako"/>
<%def name="main_body()">
<style type="text/css">
td, th {
vertical-align: top;
}
</style>
<div class="body" style="max-width: 720px; margin: 0 auto;">
    <h2>CloudMan Console</h2>
    <div id="storage_warning" style="display:none;" class="warning"><strong>Warning:</strong> You are running out of disk space.  Use the disk icon below to increase your volume size.</div>
    <div id="messages" class="messages">
        <div class="msgs_header">
            <span class="msgs_title">Messages</span>
            <span class="help_text">(CRITICAL messages cannot be dismissed.)</span>
            <a id="msgs_dismiss"></a>
        </div>
        <div id="messages_list"></div>
    </div>
    <div id="main_text">
        %if initial_cluster_type is None:
            Welcome to <a href="http://usecloudman.org/" target="_blank">CloudMan</a>.
            This application allows you to manage this cloud cluster and the services provided within. 
            If this is your first time running this cluster, you will need to select an initial data volume 
            size. Once the data store is configured, default services will start and you will be able to add 
            and remove additional services as well as 'worker' nodes on which jobs are run.
        %else:
            Welcome to <a href="http://usecloudman.org/" target="_blank">CloudMan</a>.
            This application allows you to manage this instance cloud cluster and the services 
            provided within. Your previous data store has been reconnected.  Once the cluster has initialized, 
            use the controls below to manage services provided by the application.
        %endif
    </div>
    <div style="clear: both;"></div><br/>
    <div style='position:relative;text-align:center;'>
        <ul style='display:inline;padding:0;'>
            <li style='display:inline;width:150px;'>
                <a id="stop-button" original-title="Terminate Cluster" class="action-button left-button">Terminate cluster</a>
            </li>
            <li style='display:inline;width:150px;'>
                <a class="action-button" original-title="Add Nodes..." id="scale_up_button">Add nodes <img src="/cloud/static/images/downarrow.png"></a>
            </li>
            <li style='display:inline;width:150px;'>
                <a class="action-button" original-title="Remove Nodes..." id="scale_down_button">Remove nodes <img src="/cloud/static/images/downarrow.png"></a>
            </li>
            <li style='display:inline;width:150px;'>
                <a id='dns' href='' original-title="Access Galaxy" class="action-button right-button">Access Galaxy</a>
            </li>
        </ul>

    <div id='cluster_scale_up_popup' class='cluster_scale_popup'>
        <h4>Add nodes</h4>
        <form id="add_instances_form" class="generic_form" name="node_management_form" action="${h.url_for(controller='root',action='add_instances')}" method="post">
        <div class="form-row">
            <label>Number of nodes to start:</label>
            <div id="num_nodes" class="form-row-input">
                <input type="text" name="number_nodes" class="LV_field" id="number_nodes" value="1" size="10">
                <div class="LV_msgbox"><span id="number_nodes_vtag"></span></div>
            </div>
            <br/>
            <label><a href="http://aws.amazon.com/ec2/#instance" target="_blank">Type</a> of node(s):</label>
            <div style="color:#9D9E9E">(master node type: ${master_instance_type})</div>
            <div id="instance_type" class="form-row-input">
                ## Select available instance types based on cloud name
                <%include file="clouds/${cloud_name}/instance_types.mako" />
            </div>
            ## Spot instaces work only for the AWS cloud
            %if cloud_type == 'ec2':
                <div class="form-row">
                    <input type="checkbox" id="use_spot" />
                    Use <a href="http://aws.amazon.com/ec2/spot-instances/" target="_blank">
                        Spot instances
                    </a><br/>
                    Your max <a href="http://aws.amazon.com/ec2/spot-instances/#6" targte="_blank">
                        spot price</a>:
                    <input type="text" name="spot_price" id="spot_price" size="5" disabled="disabled" />
                    <div class="LV_msgbox"><span id="spot_price_vtag"></span></div>
                </div>
            %endif
            <div class="form-row"><input type="submit" value="Start Additional Nodes" onClick="return add_pending_node()"></div>
        </div>
        </form>
    </div>
    <div id='cluster_scale_down_popup' class='cluster_scale_popup'>
        <h4>Remove nodes</h4>
        <form id="remove_instances_form" class="generic_form" name="node_management_form" action="${h.url_for(controller='root',action='remove_instances')}" method="post">
            <div class="form-row">
                <div id="num_nodes" class="form-row-input">
                    <label>Number of nodes to remove:</label><input type="text" name="number_nodes" id="number_nodes" value="0" size="10">
                </div>
                <div id="num_nodes" class="form-row-input">
                    &nbsp;
                </div>
                <div id="force_termination" class="form-row-input">
                    <label>Force Termination of non-idle nodes?</label>
                    Yes<input type="radio" name="force_termination" id="force_termination" value="True">
                    No<input type="radio" name="force_termination" id="force_termination" value="False"  checked="True">
                </div>
                <div id="num_nodes" class="form-row-input">
                    &nbsp;
                </div>
                <div class="form-row"><input type="submit" value="Remove Existing Nodes"></div>
            </div>
        </form>
    </div>
</div>
<h2>Status</h2>
<div id="status_container">
    <div id="cluster_view">
        <div id="cluster_view_tooltip" style="text-align: center;"></div>
        <canvas id="cluster_canvas" width="150" height="120"></canvas>
    </div>
    <table cellpadding="0" cellspacing="10">
            %if cluster_name:
                <tr><td><h4>Cluster name: </h4></td><td><span id="cluster_name">${cluster_name}</span>&nbsp;
                <span><a id="share_a_cluster" title="Share this cluster instance">&nbsp;</a></span></td></tr>
            %endif
        <tr><td><h4>Disk status: </h4></td><td>
            <span id="du-used">0</span> / <span id="du-total">0</span> (<span id="du-pct">0</span>) <span id='expand_vol' title="Expand disk size">&nbsp;</span>
            ##<span id="snap-status"></span><span id="snap-progress"></span>
        </td></tr>
        <tr><td><h4>Worker status: </h4></td><td>
            <b>Idle</b>: <span id="status-idle">0</span>
            <b>Available</b>: <span id="status-available">0</span>
            <b>Requested</b>: <span id="status-total">0</span>
        </td></tr>
        <tr><td><h4>Service status: </h4></td><td>
            Applications <div id="app-status" style="width:16px;display:inline-block" class="status_green">&nbsp;</div>
            Data <div id="data-status" style="width:16px;display:inline-block" class="status_green">&nbsp;</div>
        </td></tr>
##      <tr><td colspan=2>
##      </td></tr>
    </table>
</div>

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
            <label>Automatically terminate the master instance?</label>
            <input type="checkbox" name="terminate_master_instance" id="terminate_master_instance" checked>
            If checked, this master instance will automatically terminate after all services have been shut down.
            If not checked, you should maually terminate this instance after all services have been shut down.
            <p></p><label>Also delete this cluster?</label>
            <input type="checkbox" name="delete_cluster" id="delete_cluster">
            If checked, this cluster will be deleted. <b>This action is irreversible!</b> All your data will be deleted.
            <div class="form-row"><input type="submit" value="Yes, power off"></div>
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
                    <select name="as_instance_type" id="as_instance_type">
                        <option value=''>Same as Master</option>
                        <option value='t1.micro'>Micro</option>
                        <option value='m1.large'>Large</option>
                        <option value='m1.xlarge'>Extra Large</option>
                        <option value='m2.xlarge'>High-Memory Extra Large</option>
                        <option value='m2.2xlarge'>High-Memory Double Extra Large</option>
                        <option value='m2.4xlarge'>High-Memory Quadruple Extra Large</option>
                        ## <option value='c1.medium'>High-CPU Medium</option>
                        <option value='c1.xlarge'>High-CPU Extra Large</option>
                    </select>
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
                                <input type="text" id="cannonical_ids" name="cannonical_ids" size="40" value="" />
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
    <h2>Initial Cluster Configuration</h2>
    <div class="form-row">
        <p>Welcome to CloudMan. This application will allow you to manage this cluster and
        the services provided within. To get started, choose the type of cluster you'd like to work
        with and provide the associated value, if any.</p>
    </div>
    <form id="initial_volume_config_form" name="power_cluster_form" action="${h.url_for(controller='root',action='initialize_cluster')}" method="post">
        <div class="form-row">
            ## Allow Galaxy-cluster only if the underlying image/system supports it
            % if 'galaxy' in image_config_support.apps:
                <p><input id="galaxy-cluster" type="radio" name="startup_opt" value="Galaxy" checked='true'>
                    <b>Galaxy Cluster</b>: Galaxy application, available tools, reference datasets, SGE job manager, and a data volume.
                    Specify the initial storage size (in Gigabytes):
                </p>
                <input style="margin-left:20px" type="text" name="g_pss" class="LV_field" id="g_pss" value="" size="3">GB<span id="g_pss_vtag"></span>
            % else:
                <p class='disabled'>
                    <input id="galaxy-cluster" type="radio" name="startup_opt" value="Galaxy" disabled='true'>
                    <b>Galaxy Cluster</b>: Galaxy application, available tools, reference datasets,
                    SGE job manager, and a data volume. <u>NOTE</u>: The current machine image
                    does not support this cluster type option; click on 'Show more startup options'
                    so see the available cluster configuration options.
                    <br/>Specify the initial storage size (in Gigabytes):
                </p>
                <input disabled='true' style="margin-left:20px" type="text" name="g_pss" class="LV_field" id="g_pss" value="" size="3">GB<span id="g_pss_vtag"></span>
            % endif             
        </div>
        <div id='extra_startup_options'>
            <div class="form-row">
                <p><input id="share-cluster" type="radio" name="startup_opt" value="Shared_cluster">
                    <b>Share-an-Instance Cluster</b>: derive your cluster form someone else's cluster.
                    Specify the provided cluster share-string (for example,
                    <span style="white-space:nowrap">cm-0011923649e9271f17c4f83ba6846db0/shared/2011-08-19--21-00</span>):
                </p>
                <input style="margin-left:20px"  type="text" name="shared_bucket" class="LV_field" id="shared_bucket" value="" size="50">
                    Cluster share-string
            </div>

            <div class="form-row">
                <p><input id="data-cluster" type="radio" name="startup_opt" value="Data">
                    <b>Data Cluster</b>: a persistent data volume and SGE. 
                    Specify the initial storage size (in Gigabytes):
                </p>
                <input style="margin-left:20px"  type="text" name="d_pss" class="LV_field" id="d_pss" value="" size="3">GB<span id="d_pss_vtag"></span>
            </div>
            
            <div class="form-row">
                <p><input type="radio" name="startup_opt" value="SGE">
                <b>Test Cluster</b>: SGE only. No persistent storage is created.</p>
            </div>
        </div>
        <div id="toggle_extra_startup_options_cont" class="form-row"><a id='toggle_extra_startup_options' href="#">Show more startup options</a></div>
        <br/>
        <div class="form-row" style="text-align:center;">
            <input type="submit" value="Start CloudMan Cluster" id="start_cluster_submit_btn"/>
        </div>
        </form>
    </div>
</div>
<div id="log_container">
    <div id="status_svcs" style="display:none;">
        <ul><li class='fs_det_clicker'><div class='status_nodata'>&nbsp;</div>Filesystems</li>
        <li><div class='status_nodata'>&nbsp;</div>Scheduler</li>
        <li><div class='status_nodata'>&nbsp;</div>Database</li>
        <li><div class='status_nodata'>&nbsp;</div>Galaxy</li></ul>
    </div>
    <div id="volume_detail"></div>
    <div id="fs_detail"></div>
    <div id="log_container_header">
        <h3>Cluster status log</h3>
        <div id="log_container_header_img"></div>
    </div>
    <div id="log_container_body">
    <ul>
    </ul>
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
 
function scrollLog(){
    if ($("#log_container_body").attr("scrollHeight") <= ($("#log_container_body").scrollTop() + $("#log_container_body").height() + 100)){
        $('#log_container_body').animate({
            scrollTop: $("#log_container_body").attr("scrollHeight") + 100
        }, 1000);
    }
}

function toggleVolDialog(){
    if ($('#volume_config').is(":visible")){
        $('#volume_config').hide();
        $('#voloverlay').hide();
    }else{
        $('#voloverlay').show();
        $('#volume_config').show();
    }
}

function update_ui(data){
    if (data){
        $('#status').html(data.instance_state);
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
        $('#status-idle').text( data.instance_status.idle );
        $('#status-available').text( data.instance_status.available );
        $('#status-total').text( data.instance_status.requested );
        $('#du-total').text(data.disk_usage.total);
        $('#du-inc').text(data.disk_usage.total.slice(0,-1));
        $('#du-used').text(data.disk_usage.used);
        $('#du-pct').text(data.disk_usage.pct);
        if($('#new_vol_size').val() == '0'){
            $('#new_vol_size').val(data.disk_usage.total.slice(0,-1));
        }
        if (parseInt(data.disk_usage.pct) > 80){
            $('#storage_warning').show();
        }else{
            $('#storage_warning').hide();
        }
        $('#snap-progress').text(data.snapshot.progress);
        $('#snap-status').text(data.snapshot.status);
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
        for (i = 0; i < data.all_fs.length; i++){
            fsdet += "<li><div class='status_" + data.all_fs[i][1] + "'>&nbsp;</div>" + data.all_fs[i][0] + "</li>";
        }
        fsdet += "</ul>";
        $('#fs_detail').html(fsdet);
        cluster_status = data.cluster_status;
        if (cluster_status === "SHUTTING_DOWN"){
            shutting_down();
            return true; // Must return here because the remaining code clears the UI
        }
        else if (cluster_status === "SHUT_DOWN"){
            $('.action-button').addClass('ab_disabled');
            $('#snapshotoverlay').show(); // Overlay that prevents any future clicking
            $('#snapshotoverlay_msg_box').html("<div id='snapshotoverlay_msg_box_important'> \
                <h4>Important:</h4><p>This cluster has terminated. If not done automatically, \
                please terminate the master instance from the cloud console.</p></div>");
            $('#snapshotoverlay_msg_box').show();
            return true; // Must return here because the remaining code clears the UI
        }
        if (data.autoscaling.use_autoscaling === true) {
            use_autoscaling = true;
            as_min = data.autoscaling.as_min;
            as_max = data.autoscaling.as_max;
            $('#scale_up_button').addClass('ab_disabled');
            $('#scale_up_button > img').hide();
            $('#scale_down_button').addClass('ab_disabled');
            $('#scale_down_button > img').hide();
        } else if (data.autoscaling.use_autoscaling === false) {
            use_autoscaling = false;
            as_min = 0;
            as_max = 0;
            $('#scale_up_button').removeClass('ab_disabled');
            $('#scale_up_button > img').show();
            if (data.instance_status.requested == '0'){
                $('#scale_down_button').addClass('ab_disabled');
                $('#scale_down_button > img').hide();
            }else{
                $('#scale_down_button').removeClass('ab_disabled');
                $('#scale_down_button > img').show();
            }
        }
        if (data.snapshot.status !== "None"){
            if(!$('#snapshotoverlay').is(':visible')) {
                $('#snapshotoverlay').show();
            }
            $('#snapshot_status_box').show();
            $('#snapshot_status').text(data.snapshot.status);
            if (data.snapshot.progress !== "None"){
                $('#snapshot_progress').html("; progress: <i>"+data.snapshot.progress+"</i>");
            } else {
                $('#snapshot_progress').html("");
            }
        }else{
            $('#snapshot_status_box').hide();
            $('#snapshotoverlay').hide();
        }
    }
}
function update_log(data){
    if (data){
        if(data.log_messages.length > 0){
            // Check to make sure the log isn't huge (1000? 5000?) and truncate it first if it is.
            var loglen = $('#log_container_body>ul>li').size();
            if (loglen > 200){
                $('#log_container_body>ul>li:lt(' +(loglen - 100)+')').remove();
                $('#log_container_body>ul').prepend('<li>The log has been truncated to keep up performance.  The <a href="/cloud/log/">full log is available here</a>. </li>');
            }
            last_log = data.log_cursor;
            var to_add = "";
            for (i = 0; i < data.log_messages.length; i++){
                to_add += "<li>"+data.log_messages[i]+"</li>";
            }
            $('#log_container_body>ul').append(to_add);
            scrollLog();
        }
    }
}

function update_messages(data) {
    if (data && data.length > 0) {
        // Clear the old list & repopulate
        var mList = $('#messages_list');
        mList.html('');
        $.each(data, function(i){
            txt = data[i].message + ' (' + data[i].added_at.split('.')[0] + ')'
            // Mark CRITICAL msgs
            if (data[i].level == '50') {
                txt = '[CRITICAL] ' + txt;
            }
            $('<li/>')
            .addClass('message')
            .text(txt)
            .appendTo(mList);
        });
        $('#messages').show();
    }
    else {
        $('#messages').hide();
    }
}

function update(repeat_update){
    $.getJSON("${h.url_for(controller='root',action='full_update')}",
        {l_log : last_log},
        function(data){
            if (data){
                update_ui(data.ui_update_data);
                update_log(data.log_update_data);
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
                update_log(data.log_update_data);
                $('#reboot_overlay').hide();
                $('#reboot_status_box').hide();
                },
      error: function(data){window.setTimeout(function(){reboot_update()}, 10000)}
    });
}

function dismiss_messages(){
    $.ajax({
        type: "POST",
        url:"${h.url_for(controller='root',action='dismiss_messages')}"
    }).done(function(){
       update();
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

function show_log_container_body() {
    // Show the containter box for CloudMan log on the main page
    $('#log_container_header_img').css('background', 'transparent url(/cloud/static/images/plus_minus.png) no-repeat top right' );
    $('#log_container_header').addClass('clicked');
    $('#log_container_body').slideDown('fast');
}

// This is called when worker nodes are added by the user.
// Causes a pending instance to be drawn
function add_pending_node() {
    inst_kind = 'on-demand';
    if ($('#use_spot').length != 0 && $('#use_spot').attr("checked") == 'checked') {
        inst_kind = 'spot';
    } increment_pending_instance_count(parseInt(document.getElementById("add_instances_form").elements["number_nodes"].value), inst_kind);
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
    show_log_container_body();
    update_log();
    $('#log_container_body').animate({
        scrollTop: $("#log_container_body").attr("scrollHeight") + 100
    }, 1000);
    $('#snapshotoverlay').show(); // Overlay that prevents any future clicking
}

$(document).ready(function() {
    var initial_cluster_type = '${initial_cluster_type}';
    var permanent_storage_size = ${permanent_storage_size};
    
    $('#shared_visibility').click(function() {
        $('#user_permissions').show();
        $('#user_ids').val("");
        $('#cannonical_ids').val("");
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
    $('#msgs_dismiss').click(function(){
        dismiss_messages();
    });
    $('#log_container_body').hide();
    $('#log_container_header').click(function() {
        if ($('#log_container_body').is(":hidden")){
            show_log_container_body();
        } else {
            $('#log_container_header_img').css('background', 'transparent url(/cloud/static/images/plus_minus.png) no-repeat top left' );
            $('#log_container_body').slideUp('fast', function(){
                $('#log_container_header').removeClass('clicked');
            });   
        }
        return false;
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
            hidebox();
        },
        success: function( data ) {
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
    var number_nodes = new LiveValidation('number_nodes', { validMessage: "OK", wait: 300, insertAfterWhatNode: 'number_nodes_vtag' } );
    number_nodes.add( Validate.Numericality, { minimum: 1, onlyInteger: true } );
    if (permanent_storage_size === 0) {
        var g_permanent_storage_size = new LiveValidation('g_pss', { validMessage: "OK", wait: 300, insertAfterWhatNode: 'g_pss_vtag' } );
        g_permanent_storage_size.add( Validate.Numericality, { minimum: 1, maximum: 1000, onlyInteger: true } );
        var d_permanent_storage_size = new LiveValidation('d_pss', { validMessage: "OK", wait: 300, insertAfterWhatNode: 'd_pss_vtag' } );
        d_permanent_storage_size.add( Validate.Numericality, { minimum: 1, maximum: 1000, onlyInteger: true } );
    }
    if ($('#spot_price').length != 0) {
        // Add LiveValidation only if the field is actually present on the page
        var spot_price = new LiveValidation('spot_price', { validMessage: "OK", wait: 300, insertAfterWhatNode: 'spot_price_vtag' } );
        spot_price.add( Validate.Numericality, { minimum: 0 } );
    }
    var expanded_storage_size = new LiveValidation('new_vol_size', { validMessage: "OK", wait: 300 } );
    expanded_storage_size.add( Validate.Numericality, { minimum: 1, maximum: 1000 } );
    
    var autoscaling_min_bound = new LiveValidation('as_min', { validMessage: "OK", wait: 300 } );
    autoscaling_min_bound.add( Validate.Numericality, { minimum: 0, maximum: 19, onlyInteger: true } );
    var autoscaling_max_bound = new LiveValidation('as_max', { validMessage: "OK", wait: 300 } );
    autoscaling_max_bound.add( Validate.Numericality, { minimum: 0, maximum: 19, onlyInteger: true } );
    
    $('#as_min').change(function(){
        autoscaling_max_bound.validations[0].params.minimum = $('#as_min').val();
    });
    $('#as_max').change(function(){
        autoscaling_min_bound.validations[0].params.maximum = $('#as_max').val();
    });
    
    // FIXME: Is there a better way of doing this check than repeating all the code from the preceeding validation?
    var autoscaling_min_bound_adj = new LiveValidation('as_min_adj', { validMessage: "OK", wait: 300 } );
    autoscaling_min_bound_adj.add( Validate.Numericality, { minimum: 0, maximum: 19, onlyInteger: true } );
    var autoscaling_max_bound_adj = new LiveValidation('as_max_adj', { validMessage: "OK", wait: 300 } );
    autoscaling_max_bound_adj.add( Validate.Numericality, { minimum: 0, maximum: 19, onlyInteger: true } );
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
    $('#g_pss').focus(function() {
        $('#galaxy-cluster').attr('checked', 'checked');
    });
    $('#shared_bucket').focus(function() {
        $('#share-cluster').attr('checked', 'checked');
    });
    $('#d_pss').focus(function() {
        $('#data-cluster').attr('checked', 'checked');
    });
    
    // Initiate the update calls
    update(true);
});

</script>
    </div>
</%def>
