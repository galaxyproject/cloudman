<%inherit file="/base_panels.mako"/>
<%def name="main_body()">
<style type="text/css">
td, th {
vertical-align: top;
}
</style>
<div class="body" style="max-width: 720px; margin: 0 auto;">
    <h2>Galaxy Cloudman Console</h2>
	<div>
        This is a CloudMan worker node. Please use the master instance at
        <a href="http://${master_ip}/cloud">${master_ip}/cloud</a> to interact
        with the cluster.
    </div>
</div>
</%def>
