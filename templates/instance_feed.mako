<%
if instances is not None:
	context.write(" : ".join([" | ".join([str(y) for y in x.get_status_array()]) for x in instances]))
	 # compresses list of instances to be a string separated by : with instance fields separated by |
%>