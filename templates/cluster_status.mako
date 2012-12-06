<!DOCTYPE html>

%if instances is not None:
<div style="padding:100px;">
<div style="width:400px;">
	<div style="float:right; width:170px; height:150px; background:orange; border:1px solid grey"><h4 style="margin:0px">Node Status:</h4><p id="inst_display"></p></div>
	<canvas id="cluster_canvas" width="200" height="200"></canvas>
	</div>
</div>
	<hr/>

	<p id="status">Status:<br/></p>
	<hr/>
	<script type='text/javascript' src="${h.url_for('/static/scripts/jQuery-1.4.2.js')}"></script>
	<script type='text/javascript' src="${h.url_for('/static/scripts/cluster_canvas.js')}">	</script>
	<!-- Number of Instances: ${len(instances)}
	<table cellspacing='5'>
	<%
	import random
	rows = 4
	cols = 5
	colors = ['orange','green', 'red', 'gray']
	for i in range(rows):
		context.write("<tr>")
		for j in range(cols):
			if i * cols + j < len(instances):
				context.write("<td style='width:20px; height:20px;background-color:%s'></td>" % random.choice(colors))				
			else:
				context.write("<td style='width:20px; height:20px;background-color:#EEEEEE'></td>")
		context.write("</tr>")
	%>
	</table>
	<div>
	%for i in instances:
		<div class='inst_display' style='margin:2px;padding:2px;border:1px solid;background:green;float:left;display:block; width:200px'>
		<ul style='list-style:none;padding:0px;'>
		<li><em>${i.id}</em></li>
		<li>${i.m_state}</li>
		<li>${i.last_comm}</li>
		</ul>
		</div>
	%endfor
	</div> -->
%else:
	<h4>Cluster status is unknown.</h4>
%endif