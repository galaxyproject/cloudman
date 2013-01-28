## This needs to be on the first line, otherwise IE6 goes into quirks mode
<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN" "http://www.w3.org/TR/html4/loose.dtd">
<html lang="en">
	<head>
		<title>Galaxy on the Cloud!</title>
		<meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
		<script type='text/javascript' src="/static/scripts/jQuery-1.4.2.js"></script>
	</head>
	<body style='margin:0px; padding:0px;'>
	<iframe id="cm_mini_controller" src="${h.url_for( '/root/minibar' )}" width="100%" height="30px" frameborder="0" scrolling="no" style="margin: 0; border: 0 none; width: 100%; overflow: hidden;"> </iframe>
	<iframe id="galaxy_frame" src="http://127.0.0.1:8080" width="100%" onload="resize_iframe()" frameborder="0" > </iframe>
	<script type='text/javascript'>
	function check_iframe_size(){
		var w_height = $(window).height() - 30;
		$('#galaxy_frame').height(w_height);
	}
	$(window).resize(function() {
	  	check_iframe_size();
	});
	$(document).ready(function() {
		check_iframe_size();
	});
	</script>
	</body>
	<!-- <frameset id='fset' frameborder='0px' border='0px' framespacing='0px' rows="25px,*">
        <frame src="${h.url_for( '/root/minibar' )}" marginwidth='0px' marginheight=0 frameborder=0 scrolling='no' noresize>
        <frame src="${h.url_for( '/root/index' )}" marginwidth='0px' marginheight='0px' frameborder='0px'>
        <frame src="http://localhost:8080/" marginwidth='0px' marginheight='0px' frameborder='0px'>
    </frameset> -->
</html>
