<%inherit file="/base_panels.mako"/>
<%def name="main_body()">
<style type="text/css">
td, th {
vertical-align: top;
}
</style>
<div class="body" style="max-width: 720px; margin: 0 auto;">
    <h2>Galaxy CloudMan Console</h2>
<div>
%if initial_cluster_type is None:
	Welcome to the Galaxy Cloud Manager.  This application will allow you to manage this cloud and the services provided within. If this is your first time running this cluster, you will need to select an initial data volume size.  Once the data store is configured, default services will start and you will be add and remove additional services as well as 'worker' nodes on which jobs are run.
%else:
	Welcome to the Galaxy Cloud Console.  This application allows you to manage this instance of Galaxy.  Your previous data store has been reconnected.  Once Galaxy has initialized, use the controls below to add and remove 'worker' nodes for running jobs.
%endif


<div>
</div>
</div>
<div style="clear: both;"></div>
<br/>
		<div style='position:relative;text-align:center;'>
		<ul style='display:inline;padding:0;'>
			<li style='display:inline;width:150px;'>
				<a id="stop-button" original-title="Terminate Cluster" class="action-button left-button">Terminate cluster</a>
			</li>
			<li style='display:inline;width:150px;'>
	        	<a class="action-button" original-title="Add Instances..." id="scale_up_button">Add instances <img src="/cloud/static/images/downarrow.png"></a>
			</li>
			<li style='display:inline;width:150px;'>
	        	<a class="action-button" original-title="Remove Instances..." id="scale_down_button">Remove instances <img src="/cloud/static/images/downarrow.png"></a>
			</li>
			<li style='display:inline;width:150px;'>
				<a id='dns' href='' original-title="Access Galaxy" class="action-button right-button">Access Galaxy</a>
			</li>
		</ul>

		<div id='cluster_scale_up_popup' class='cluster_scale_popup'>
		<h4>Add Instances</h4>
		<form id="add_instances_form" name="node_management_form" action="${h.url_for(controller='root',action='add_instances')}" method="post">
	        <div class="form-row">
	        <label>Number of instances to start:</label>
	        <div id="num_nodes" class="form-row-input">
	            <input type="text" name="number_nodes" id="number_nodes" value="0" size="10">
	        </div>
	        <label>Type of Instance(s):</label>
				<div id="instance_type" class="form-row-input">
		    	<select name="instance_type" id="instance_type">
					<option value=''>Same as Master</option>
					<option value='t1.micro'>Micro</option>
					<option value='m1.large'>Large</option>
					<option value='m1.xlarge'>Extra Large</option>
					<option value='m2.xlarge'>High-Memory Extra Large Instance</option>
					<option value='m2.2xlarge'>High-Memory Double Extra Large Instance</option>
					<option value='m2.4xlarge'>High-Memory Quadruple Extra Large Instance</option>
##					<option value='c1.medium'>High-CPU Medium Instance</option>
					<option value='c1.xlarge'>High-CPU Extra Large Instance</option>
				</select>
			</div>
	        <div class="form-row"><input type="submit" value="Start Additional Instances"></div>
	        </div>
	    </form>
		</div>
		<div id='cluster_scale_down_popup' class='cluster_scale_popup'>
	    <h4>Remove Instances</h4>
	    <form id="remove_instances_form" name="node_management_form" action="${h.url_for(controller='root',action='remove_instances')}" method="post">
	        <div class="form-row">
	        <div id="num_nodes" class="form-row-input">
	            <label>Number of instances to remove:</label><input type="text" name="number_nodes" id="number_nodes" value="0" size="10">
	        </div>
	        <div id="num_nodes" class="form-row-input">
				&nbsp;
	        </div>
	        <div id="force_termination" class="form-row-input">
	            <label>Force Termination of non-idle instances?</label>
				Yes<input type="radio" name="force_termination" id="force_termination" value="True">
				No<input type="radio" name="force_termination" id="force_termination" value="False"  checked="True">
	        </div>
	        <div id="num_nodes" class="form-row-input">
				&nbsp;
	        </div>
	        <div class="form-row"><input type="submit" value="Remove Existing Instances"></div>
	        </div>
	    </form>
		</div>
		</div>
<div style="clear: both;"></div>
<h2>Status</h2>
<div id="status_container">
    <div id="cluster_view">
    <div id="cluster_view_tooltip">
    </div>
    <canvas id="cluster_canvas" width="150" height="120"></canvas>
    </div>
    <table cellpadding="0" cellspacing="10">
            %if cluster_name:
                <tr><td><h4>Cluster name: </h4></td><td><span id="cluster_name">${cluster_name}</span></td></tr>
            %endif
    <tr><td><h4>Disk status: </h4></td><td>
        <span id="du-used">0</span> / <span id="du-total">0</span> (<span id="du-pct">0</span>) <span id='expand_vol' style='cursor: pointer;background-image:url(/cloud/static/images/disc_plus.png); background-repeat:no-repeat; display:inline-block; width:20px;'>&nbsp;</span>
    	##<span id="snap-status"></span><span id="snap-progress"></span>
	</td></tr>
    <tr><td><h4>Worker status: </h4></td><td>
        <b>Idle</b>: <span id="status-idle">0</span>
        <b>Available</b>: <span id="status-available">0</span>
        <b>Requested</b>: <span id="status-total">0</span>
    </td></tr>
    <tr><td><h4>Service status: </h4></td><td>
		Applications <div style="width:16px;display:inline-block" class="status_green">&nbsp;</div>
		Data <div style="width:16px;display:inline-block" class="status_green">&nbsp;</div>
    </td></tr>

    <tr><td colspan=2></td></tr>
    </table>

	<div class="box" id="volume_expand_popup">
    <a class="boxclose"></a>
		<h2>Expand Disk Space</h2>
		<form id="expand_user_data_volume" name="expand_user_data_volume" action="${h.url_for(controller='root',action='expand_user_data_volume')}" method="post">
			<div class="form-row">
			Through this form you may increase the disk space available to Galaxy. All of the cluster services (but not the cluster)
			<b>WILL BE SHUT DOWN</b> until the new disk is ready, at which point they will all be restarted. This may result in Galaxy 
			jobs that are currently running to fail. Note that the new disk size <b>must be larger</b> than the current disk size.
			<br/>During this process, a snapshot of your data volume will be created and left in you account. For reference, you may 
			provide a brief note that will later be visible in the snapshot description.
			</div>
			<div class="form-row">
				<label>New Disk Size (max 1000GB):</label>
				<div id="permanent_storage_size" class="form-row-input">
					<input type="text" name="new_vol_size" id="new_vol_size" value="0" size="10">
				</div>
				<label>Note (optional):</label>
				<div id="permanent_storage_size" class="form-row-input">
					<input type="text" name="vol_expand_desc" id="vol_expand_desc" value="" size="10">
				</div>
				<div class="form-row">
					<input type="submit" value="Create Data Volume"/>
				</div>
			</div>
		</form>
	</div>
	
	

</div>
<div style="clear: both;"></div>
<div class="overlay" id="overlay" style="display:none"></div>
<div class="box" id="power_off">
    <a class="boxclose"></a>
    <h1>EC2 Cluster Configuration</h1>
    <form id="power_cluster_off_form" name="power_cluster_form" action="${h.url_for(controller='root',action='kill_all')}" method="post">
        <div class="form-row">
            <label>Are you sure you want to power the cluster off?</label>
            <div class="form-row"><input type="submit" value="Yes, power off"></div>
        </div>
    </form>
</div>

<div id="voloverlay" class="overlay" style="display:none"></div>
<div id="popupoverlay" class="overlay" style="display:none"></div>
<div class="box" id="volume_config">
	<h2>Initial Server Configuration</h2>


##	<form id="initial_volume_config_form" name="power_cluster_form" action="${h.url_for(controller='root',action='create_initial_data_vol')}" method="post">
##		<div class="form-row">
##		Please choose an initial sever configuration. Appropriate services will created for this cluster based on the role selected.
##		</div>
##		<div class="form-row">
##			<label>Permanent storage size (1-1000GB):</label>
##			<div id="permanent_storage_size" class="form-row-input">
##				<input type="text" name="pss" id="pss" value="" size="10">
##			</div>
##			<div class="form-row">
##				<input type="submit" value="Create Data Volume"/>
##			</div>
##		</div>
##	</form>

	<div class="form-row">
	Please choose an initial sever configuration. Appropriate services will created for this cluster based on the role selected.
	</div>
	<div class="form-row">
		<form id="initial_volume_config_form" name="power_cluster_form" action="${h.url_for(controller='root',action='initialize_cluster')}" method="post">
		<table><tr>
		<td>
			<div id="permanent_storage_size" class="form-row-input" style="text-align:center;width:150px">
				<input type="radio" name="startup_opt" value="Galaxy" checked='true'>
				<p>Full Galaxy Cluster. Choose initial storage size</p>
				<input type="text" name="g_pss" id="g_pss" value="" size="10">
				</div>
			</div>
		</td>
		<td>
			<div id="permanent_storage_size" class="form-row-input" style="text-align:center;width:150px">
				<input type="radio" name="startup_opt" value="Data">
				<p>Data volume + SGE. Choose initial storage size</p>
				<input type="text" name="d_pss" id="d_pss" value="" size="10">
			</div>
			</td>
		<td>
			<div id="permanent_storage_size" class="form-row-input" style="text-align:center;width:150px">
				<input type="radio" name="startup_opt" value="SGE">
				<p>SGE Only. No persistent storage created.</p>
			</div>
		</td>
		<tr/></table>
		<br/>
		<div class="form-row" style="text-align:center;">
			<input type="submit" value="Start Cluster"/>
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
<script type='text/javascript' src="${h.url_for('/static/scripts/jquery.tipsy.js')}"></script>
<script type='text/javascript' src="${h.url_for('/static/scripts/cluster_canvas.js')}"> </script>
<script type="text/javascript">

var instances = {};
var cluster_status = "OFF";
var fs_det_vis = false;
var last_log = 0;
var click_timeout = null;

function fixForms(){
    $('form').submit( function(event){
        $.post($(this).attr('action'), $(this).serialize());
        event.preventDefault();
        hidebox();
        update();
    });
	$('#volume_config')
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

function update(){
    $.getJSON('/cloud/instance_state_json', 
		function(data) {
			if (data){
		        $('#status').html(data.instance_state);
		        $('#dns').attr("href", data.dns);
				if (data.dns == '#'){
					$('#dns').addClass('ab_disabled');
			        $('#dns').attr("target", '');
				}else{
					$('#dns').removeClass('ab_disabled');
			        $('#dns').attr("target", '_blank');
				}
				if (data.instance_status.requested == '0'){
					$('#scale_down_button').addClass('ab_disabled');
					$('#scale_down_button > img').hide();
				}else{
					$('#scale_down_button').removeClass('ab_disabled');
					$('#scale_down_button > img').show();
				}
				$('#status-idle').text( data.instance_status.idle );
		        $('#status-available').text( data.instance_status.available );
		        $('#status-total').text( data.instance_status.requested );
				$('#du-total').text(data.disk_usage.total);
				$('#du-used').text(data.disk_usage.used);
				$('#du-pct').text(data.disk_usage.pct);
				$('#snap-progress').text(data.snapshot.progress);
				$('#snap-status').text(data.snapshot.status);
				// DBTODO write generic services display
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
			}
        });
    $.getJSON('/cloud/log_json',
		{l_log : last_log},
		function(data) {
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
				}
			}
	});
    scrollLog();
	window.setTimeout(update, 5000);
}

$(document).ready(function() {
	var initial_cluster_type = '${initial_cluster_type}';
	var permanent_storage_size = ${permanent_storage_size};
    $('#stop-button').click(function(){
		$('#overlay').show();
		$('#power_off').show();
    });
    $('#scale_up_button').click(function(){
		$('.cluster_scale_popup').hide();
		$('.action-button.button-clicked').removeClass('button-clicked');
		$('#popupoverlay').show();
		$('#scale_up_button').addClass('button-clicked');
		$('#cluster_scale_up_popup').show();
	});
    $('#scale_down_button').click(function(){
		if ($('#scale_down_button').hasClass('ab_disabled')){
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
    $('#expand_vol').click(function(){
		$('#overlay').show();
		$('#volume_expand_popup').show();
    });
	$('#overlay').click(function(){
		hidebox();
	})
	$('#popupoverlay').click(function(){
		$('.cluster_scale_popup').hide();
		$('#volume_expand_popup').hide();
		$('.action-button.button-clicked').removeClass('button-clicked');
		$('#popupoverlay').hide();
	})
    $('.boxclose').click(function(){
        hidebox();
    });
    $('#log_container_body').hide();
    $('#log_container_header').click(function() {
        if ($('#log_container_body').is(":hidden")){
			$('#log_container_header').addClass('clicked');
            $('#log_container_body').slideDown('fast', function(){
				$('#log_container_header_img').css('background', 'transparent url(/cloud/static/images/plus_minus.png) no-repeat top right' );
			});
        } else {
            $('#log_container_body').slideUp('fast', function(){
				$('#log_container_header').removeClass('clicked');
				$('#log_container_header_img').css('background', 'transparent url(/cloud/static/images/plus_minus.png) no-repeat top left' );
			});
            
        }
        return false;
    });
	// console.log("CTC: %s" % initial_cluster_type)
    $('#initial_volume_config_form').submit( function(event) {
        cluster_status = "STARTING";
        $.post('/cloud/root/initialize_cluster', $("#initial_volume_config_form").serialize());
        event.preventDefault();
		$('#initial_volume_config_form').hide('fast');
        hidebox();
        update();
    });
    $('#power_cluster_off_form').submit( function(event) {
        cluster_status = "OFF";
        $.post('/cloud/root/kill_all', $("#power_cluster_off_form").serialize());
        event.preventDefault();
        hidebox();
        update();
    });
    $('#expand_user_data_volume').submit( function(event) {
        $.post('/cloud/root/expand_user_data_volume', $("#expand_user_data_volume").serialize());
        event.preventDefault();
		$('#volume_expand_popup').hide('fast');
        hidebox();
        update();
    });
    $('#add_instances_form').submit( function(event) {
        $.post('/cloud/root/add_instances', $("#add_instances_form").serialize());
        event.preventDefault();
        hidebox();
        update();
    });
    $('#remove_instances_form').submit( function(event) {
        $.post('/cloud/root/remove_instances', $("#remove_instances_form").serialize());
        event.preventDefault();
        hidebox();
        update();
    });
    $('.fs_det_clicker').click(function(){
        if (fs_det_vis == true){
			clearTimeout(click_timeout);
            $('#fs_detail').hide('fast');
            fs_det_vis = false;
        }
        else{
			$('#fs_detail').show('fast');
			click_timeout = setTimeout(function(){
				if (fs_det_vis == true){
					$('#fs_detail').hide('fast');
					fs_det_vis = false;
				}
				}, 5000);
			fs_det_vis = true;
        }
    });
    // Form validation
    var number_nodes = new LiveValidation('number_nodes', { validMessage: "OK", wait: 300 } );
    number_nodes.add( Validate.Numericality, { minimum: 1 } );
    if (permanent_storage_size == 0) {
        var permanent_storage_size = new LiveValidation('g_pss', { validMessage: "OK", wait: 300 } );
        permanent_storage_size.add( Validate.Numericality, { minimum: 1, maximum: 1000 } );
        var permanent_storage_size = new LiveValidation('d_pss', { validMessage: "OK", wait: 300 } );
        permanent_storage_size.add( Validate.Numericality, { minimum: 1, maximum: 1000 } );
    }
	var expanded_storage_size = new LiveValidation('new_vol_size', { validMessage: "OK", wait: 300 } );
    expanded_storage_size.add( Validate.Numericality, { minimum: 1, maximum: 1000 } );
	
    if (initial_cluster_type == 'None') {
		// Present the user with the dialog.
		toggleVolDialog();
	}
    update();
});
</script>
    </div>
</%def>
