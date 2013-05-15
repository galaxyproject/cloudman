## This needs to be on the first line, otherwise IE6 goes into quirks mode
<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN" "http://www.w3.org/TR/html4/loose.dtd">

## Default title
<%def name="title()">CM</%def>

## Default stylesheets
<%def name="stylesheets()">
  <link href="${h.url_for('/static/style/minibar.css')}" rel="stylesheet" type="text/css" />
</%def>

## Default javascripts
<%def name="javascripts()">
  <!--[if lt IE 7]>
  <script type='text/javascript' src="/static/scripts/IE7.js"></script>
  <script type='text/javascript' src="/static/scripts/IE8.js"></script>
  <script type='text/javascript' src="/static/scripts/ie7-recalc.js"></script>
  <![endif]-->
  <script type='text/javascript' src="/static/scripts/jQuery-1.4.2.js"></script>
</%def>

<html lang="en">
	<head>
		<title>${self.title()}</title>
		<meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
			${self.javascripts()}
			${self.stylesheets()}
	</head>
	<body>
		<div id="minibar">
				<a id="cmhome" href="/index"><img border='0' width='25px' height='25px' src="/static/images/cm_icon.png"></a>
				<div id="s_container">
					<h4>Cluster Name: </h4><span id="cluster_name">ClusterName</span>
					<h4>Status: </h4><span id="status">Unavailable</span>
					<h4>Node Status: </h4><span id="available_nodes">0 / 0 / 0</span>
				</div>
		</div>


<script type="text/javascript">
var cluster_status = "OFF";

function update(){
	$.get('instance_state', function(data) {
		var arr = new Array();
		arr = data.split(" : ");
		$('#status').html(arr[0]);
		$('#dns').html(arr[2]);
		$('#available_nodes').html(arr[3]);
		cluster_status = arr[1]
		if ( cluster_status == "OFF" ) {
			$('#power_button_container a').removeClass("on");
		} else {
			$('#power_button_container a').addClass("on");
		}
		window.setTimeout(update, 10000);
	});
}

$(document).ready(function() {
	update();
});

</script>

	</body>
</html>
