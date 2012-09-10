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
                // Set color for services - `Running`: green, 'Error': red; anything else is tan
                // Galaxy
                if (data.Galaxy === 'Running') {
                    $('#galaxy_status').css("color", "#639B41");
                }
                else if (data.Galaxy === 'Error') {
                    $('#galaxy_status').css("color", "#BF3030");
                }
                else {
                    $('#galaxy_status').css("color", "#BFB795");
                }
                // Postgres
                if (data.Postgres === 'Running') {
                    $('#postgres_status').css("color", "#639B41");
                }
                else if (data.Postgres === 'Error') {
                    $('#postgres_status').css("color", "#BF3030");
                }
                else {
                    $('#postgres_status').css("color", "#BFB795");
                }
                // SGE
                if (data.SGE === 'Running') {
                    $('#sge_status').css("color", "#639B41");
                }
                else if (data.SGE === 'Error') {
                    $('#sge_status').css("color", "#BF3030");
                }
                else {
                    $('#sge_status').css("color", "#BFB795");
                }

                if (data.master_is_exec_host === true) {
                    $('#master_is_exec_host').html("Switch master not to run jobs");
                } else {
                    $('#master_is_exec_host').html("Switch master to run jobs");
                }
                $('#dummy').html(data.dummy);
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
    //$('#manage_FSs_link').click(function(){
        //$('#overlay').show();
        //$('#add_fs_overlay').show();
        // get_filesystems();
    //});
    // Clicking the semi-transparent overlay clears any overlays
    $('body').on('click', 'div.overlay', function() { hidebox();});
    // Force an update of the field on click
    $('#master_is_exec_host').click(function(){
        update();
    });
    // Handle click on 'Details' of an individual file system
    // TODO: this should be translated to a backbone event
    $('table').on('click', 'a.fs-details', function() {
        // Make sure any other details boxes are closed before opening a new one
        if ($('.fs-details-box').is(':visible')) {
            $('.fs-details-box-close').trigger('click');
        }
        var elid = $(this).attr('details-box'); // Get the element ID of the clicked FS
        var tr = $(this).parents('tr'); // Keep reference to the highlighted tr
        tr.animate({backgroundColor: '#FEF1B5'}, 'slow');
        $("#"+elid).show("fold");
        // Add a hide event on the 'close' button
        // Need to use closure here to keep a reference to the highlighted tr
        var closer = function () {
            $("#"+elid).on('click', "a.fs-details-box-close", function() {
                $("#"+elid).hide();
                $(tr).animate({backgroundColor: 'transparent'}, 'slow');
            });
        }();
        return false; // prevent page autoscroll to the top
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

String.prototype.toProperCase = function () {
    // Convert a string to Title Case capitalization
    return this.replace(/\w\S*/g, function(txt){return txt.charAt(0).toUpperCase() + txt.substr(1).toLowerCase();});
};
String.prototype.toSpaced = function(){
    // Convert an underscore-connected string to a space-connected string
    // (e.g., i_am_undescored -> i am underscored)
	return this.replace(/(\_[a-z])/g, function($1){return $1.toUpperCase().replace('_',' ');});
};

// Backbone.js components
(function ($) {

    // Define the file system model
    var Filesystem = Backbone.Model.extend({
        defaults: {
            id: null,
            status: 'Unavailable'
        }
    });

    // Define the filesystems collection
    var Filesystems = Backbone.Collection.extend({
        model: Filesystem,
        url: get_all_filesystems_url
    });
    var FScollection = new Filesystems(); // A container for all Filesystems

    // Define an individual file system summary view
    var FilesystemView = Backbone.View.extend({
        // Template for rendering an indiviudal file system summary/overview
        filesystemSummaryTemplate: '<td class="fs-td1"><%= name %></td>' +
            '<td class="fs-status fs-td1"><%= status %></td>' +
            '<td class="fs-td2"><a class="fs-remove" id="fs-<%= name %>-remove" href="' + manage_service_url +
            '?service_name=<%= name %>&to_be_started=False&is_filesystem=True">'+
            'Remove</a></td>' +
            '<td class="fs-td2"><a href="#" class="fs-details" details-box="fs-<%= name %>-details">Details</a></td>' +
            '<td class="td-spacer"></td>',
        tagName: "tr",
        className: "filesystem-tr",
        attributes: function() {
            // Explicitly add file system name as a tag/row attribute
            return {fs_name: this.model.get('name')};
        },

        render: function () {
            var tmpl = _.template(this.filesystemSummaryTemplate);
            $(this.el).html(tmpl(this.model.toJSON()));
            if (this.model.attributes.status === 'Available') {
                $(this.el).find('.fs-status').addClass("td-green-txt");
            } else if (this.model.attributes.status === 'Removing' ||
                this.model.attributes.status === 'Adding') {
                $(this.el).find('.fs-status').addClass("td-tan-txt");
            } else if (this.model.attributes.status === 'Error') {
                $(this.el).find('.fs-status').addClass("td-red-txt");
            }
            return this;
        }
    });

    // Define the details popup view for an individual file system
    var FilesystemDetailsView = Backbone.View.extend({
        filesystemDetailsTemplate: '<a class="fs-details-box-close"></a>' +
            '<div class="fs-details-box-header">File system information</div>' +
            '<table>' +
            '<tr><th>Name:</th><td><%= name %></td>' +
            '<tr><th>Status:</th><td><%= status %></td>' +
            '<tr><th>Mount point:</th><td><%= mount_point %></td>' +
            '<tr><th>Kind:</th><td><%= kind %></td>' +
            '<tr><th>Size (used/total):</th><td><%= size_used %>/<%= size %> (<%= size_pct %>)</td>' +
            '<tr><th>Delete on termination:</th><td><%= DoT %></td>',
        tagName: "div",
        className: "fs-details-box",

        render: function () {
            var tmpl = _.template(this.filesystemDetailsTemplate);
            $(this.el).attr('id', "fs-"+this.model.attributes.name+"-details");
            // Build the details table using the 'standard' keys and then add any
            // additional ones that are found in the provided file system's JSON
            html = tmpl(this.model.toJSON())
            standard_keys = ['name', 'status', 'mount_point', 'kind',
                'size', 'size_used', 'size_pct', 'DoT'];
            for (key in this.model.attributes) {
                if ($.inArray(key, standard_keys) === -1) {
                    if (this.model.get(key) != null) {
                        html += '<tr><th>'+key.toSpaced().toProperCase()+':</th><td>' +
                            this.model.get(key)+'</td>';
                    }
                }
            }
            html += '</table>';
            $(this.el).html(html);
            return this;
        }
    });

    // Define the master view, i.e., list of all the file systems
    var FilesystemsView = Backbone.View.extend({
        tableHeaderTemplate: '<tr class="filesystem-tr"><th width="200px">Name</th>' +
            '<th width="100px">Status</th></tr>',
        el: $("#filesystems-table"),

        initialize: function() {
            // Bind events to actions
            this.on("click:removeFS", this.handleRemove, this);
            FScollection.on('reset', this.render, this); // Triggered on the initial page load
        },

        render: function () {
            var that = this;
            // Clear the current list; otherwise, the list just grows indefinitely
            // FIXME: I don't think this will work once FS can be added from the client side?
            //        Just add an argument from the update method?
            $(this.el).empty();
            $('#fs-details-container').empty();
            // Explicitly add the header row
            //this.$el.append(this.tableHeaderTemplate);
            // Add all of the file systems, one per row
            _.each(FScollection.models, function (fs) {
                that.renderFilesystem(fs);
            }, this);
        },

        renderFilesystem: function (fs) {
            var filesystemView = new FilesystemView({
                model: fs
            });
            this.$el.append(filesystemView.render().el);
            var filesystemDetailsView = new FilesystemDetailsView({
                model: fs
            });
            $('#fs-details-container').append(filesystemDetailsView.render().el);
        },

        // Add UI event handlers
        events: {
            "click .fs-remove": "triggerRemove"
        },

        triggerRemove: function (event) {
            // Is this trigger necessary? Why can't the click just be handled in this method?
            this.fsToRemoveID = event.currentTarget.id; // Reference to the element ID of the FS to be remvoed
            this.fsToRemoveTR = $('#'+event.currentTarget.id).parents('tr'); // Reference to tr to be removed
            event.preventDefault();
            this.trigger("click:removeFS");
        },

        handleRemove: function() {
            var el = $('#'+this.fsToRemoveID);
            var url = el.attr('href');
            $.get(url, function(data) {
                //alert("Success");
                $('#msg').html(data).fadeIn();
                clear_msg();
            });
            //.success(function() { alert("Second success"); })
            //.error(function() { alert("Error"); })
            //.complete(function() { alert("Complete"); });
            popup();
            // A rather convoluted way to instantly update the UI status to 'Removing'
            // Is there a more straighforward way?
            for (var i=0; i<FScollection.models.length; i++) {
                if (FScollection.models[i].attributes.name === this.fsToRemoveTR.attr('fs_name')) {
                    FScollection.models[i].attributes.status = 'Removing';
                }
            }
            var that = this;
            var tmp_models = FScollection.models; // .reset below clears the models so keep a reference
            FScollection.reset();
            _.each(tmp_models, function (fs) {
                that.renderFilesystem(fs);
            }, this);
        },
    });

    // Create an instance of the master view
    var filesystemList = new FilesystemsView();
    // Fetch the initial data from the server
    FScollection.fetch();
    function updateFS() {
        // Do not update file systems while a details box is visible because it
        // does not function: conceptually, a file system may dissapear so what
        // to display; also, the UI gets rendered w/ each refresh so it's would
        // have to be handled differently (maybe one day)
        if (!$('.fs-details-box').is(':visible')) {
            // Keep updating the display with the fresh data from the server
            FScollection.fetch();
        }
        window.setTimeout(function(){updateFS();}, 5000);
    }
    updateFS();
} (jQuery));
