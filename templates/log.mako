<%
if logger:
	context.write("<ul>")
	for entry in logger.logmessages[-100:]:
		context.write( '<li>%s</li>' % entry)
	context.write('</ul>')
	context.write("<div id='logfooter'> </div>")
else:
	context.write('<p>Log error!</p>')
%>