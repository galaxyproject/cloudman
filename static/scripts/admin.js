$(function() {
    $( "#fs_accordion" ).accordion({
        autoHeight: false,
        collapsible: true,
        active: 1 // Temporary only? - until the top fold is functional
    });
});

function hidebox(){
    $('.box').hide();
    $('.overlay').hide();
    $('#overlay').hide();
}

function update(repeat_update){
    $.getJSON(get_all_services_status_url,
        function(data){
            if (data){
                // Get any message data
                update_messages(data.messages);
                if (data.galaxy_rev !== 'N/A') {
                    // This will always point to galaxy-central but better than nothing?
                    var rev_html = "<a href='http://bitbucket.org/galaxy/galaxy-central/changesets/" +
                      data.galaxy_rev.split(':')[1] + "' target='_blank'>" +
                      data.galaxy_rev + '</a>';
                } else {
                    var rev_html = "N/A";
                }
                if (data.galaxy_dns === '#') {
                    var galaxy_dns = "Galaxy is currently inaccessible";
                } else {
                    var galaxy_dns = "<a href='"+data.galaxy_dns+"' target='_blank'>Access Galaxy</a>";
                }
                $('#galaxy_dns').html(galaxy_dns);
                $('#galaxy_admins').html(data.galaxy_admins);
                $('#galaxy_rev').html(rev_html);
                $('#galaxy_status').html(data.Galaxy);
                $('#postgres_status').html(data.Postgres);
                $('#sge_status').html(data.SGE);
                $('#filesystem_status').html(data.Filesystem);
                if (data.snapshot.status !== "None"){
                    $('#snapshotoverlay').show(); // Overlay that prevents any future clicking
                    $('#update_fs_status').html(" - Wait until the process completes. Status: <i>" +
                        data.snapshot.status + "</i>");
                } else {
                    $('#update_fs_status').html("");
                    $('#snapshotoverlay').hide();
                }
                // Set color for services - `Running` is green, anything else is red
                if (data.Galaxy === 'Running') {
                    $('#galaxy_status').css("color", "green");
                }
                else {
                    $('#galaxy_status').css("color", "red");
                }
                if (data.Postgres === 'Running') {
                    $('#postgres_status').css("color", "green");
                }
                else {
                    $('#postgres_status').css("color", "red");
                }
                if (data.SGE === 'Running') {
                    $('#sge_status').css("color", "green");
                }
                else {
                    $('#sge_status').css("color", "red");
                }
                if (data.Filesystem === 'Running') {
                    $('#filesystem_status').css("color", "green");
                }
                else {
                    $('#filesystem_status').css("color", "red");
                }
                if (data.master_is_exec_host === true) {
                    $('#master_is_exec_host').html("Switch master not to run jobs");
                } else {
                    $('#master_is_exec_host').html("Switch master to run jobs");
                }
            }
    });
    if (repeat_update === true){
        // Update service status every 8 seconds
        window.setTimeout(function(){update(true);}, 8000);
    }
}
function popup() {
    $("#action_initiated").fadeIn("slow").delay(400).fadeOut("slow");
}
function clear_msg() {
    // Clear message box 1 minute after the call to this method
    // FIXME: sometimes, the box gets cleared sooner, issue w/ intermittent clicks?
    window.setTimeout(function(){$('#msg').hide();}, 60000);
}
function handle_clicks() {
    // Handle action links
    $(".action").click(function(event) {
        $('#msg').hide();
        event.preventDefault();
        var url = $(this).attr('href');
        $.get(url, function(data) {
            $('#msg').html(data).fadeIn();
            clear_msg();
        });
        popup();
    });
    // Display overlays
    $('#show_user_data').click(function(event) {
        $('#msg').hide();
        $('#overlay').show();
        event.preventDefault();
        var url = $(this).attr('href');
        $.get(url, function(user_data) {
            // Pretty-print JSON user data and display in an overlay box
            var ud_obj = JSON.parse(user_data);
            var ud_str = JSON.stringify(ud_obj, null, 2);
            $('#user_data_content').html(ud_str);
            $('#user_data').fadeIn('fast');
        });
    });
    $('#manage_FSs_link').click(function(){
        $('#overlay').show();
        $('#add_fs_overlay').show();
        // get_filesystems();
    });
    $('#overlay').click(function(){
        hidebox();
    });
    // Force an update of the field on click
    $('#master_is_exec_host').click(function(){
        update();
    });
}
function handle_forms() {
    // Handle generic forms
    $('.generic_form').ajaxForm({
        type: 'POST',
        dataType: 'json',
        beforeSubmit: function() {
            $('#msg').hide();
            popup();
        },
        complete: function(data) {
            update();
            $('#msg').html(data.responseText).fadeIn();
            clear_msg();
        }
    });
    // Handle form for adding a file system
    $('#add_fs_form').ajaxForm({
        type: 'POST',
        dataType: 'json',
        beforeSubmit: function(data){
            hidebox();
            $('#filesystem_status').html("Adding");
            popup();
        }
    });
}
$(document).ready(function() {
    // Toggle help info boxes
    $(".help_info span").click(function () {
        var content_div = $(this).parent().find(".help_content");
        var help_link = $(this).parent().find(".help_link");
        if (content_div.is(":hidden")) {
            help_link.addClass("help_link_on");
            content_div.slideDown("fast");
        } else {
            content_div.slideUp("fast");
            help_link.removeClass("help_link_on");
        }
    });
    // Initiate service status updates
    update(true);
    // Handle control click events
    handle_clicks();
    // Make clearing form fields easier by auto selecting the content
    $('.form_el').focus(function() {
        this.select();
    });
    // Add event to enable closing of an overlay box
    $('.boxclose').click(function(){
        hidebox();
    });
    // Handle forms++
    handle_forms();
});
