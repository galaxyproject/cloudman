<%inherit file="/base_panels.mako"/>
<%def name="main_body()">
    <div id='msg_warning'>
        %if not full:
            Only up to the most recent ${num_lines} lines of the file (${log_file})
            are shown. 
            <a href="?service_name=${service_name}&show=all">Show all</a>
            %if num_lines > 100:
                | <a href="?service_name=${service_name}&show=less&num_lines=${num_lines}">Show less</a>
            %endif
            | <a href="?service_name=${service_name}&show=more&num_lines=${num_lines}">Show more</a>
        %else:
            The entire log file (${log_file}) is shown.
            <a href="?service_name=${service_name}&show=latest">Show latest</a>
        %endif
        | <a href="${h.url_for(controller='root', action='admin')}">Back to admin view</a>
    </div>
    <div class="srvc_log">
        <pre>${log_contents}</pre>
    </div>
</%def>
