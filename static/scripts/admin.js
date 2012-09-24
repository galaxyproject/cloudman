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
        filesystemSummaryTemplate: '<td class="fs-td-20pct"><%= name %></td>' +
            '<td class="fs-status fs-td-15pct"><%= status %></td>' +
            '<td class="fs-td-20pct">' +
            // Only disply usage when the file system is 'Available'
            '<% if (status === "Available" || status === "Running") { %>' +
                '<%= size_used %>/<%= size %> (<%= size_pct %>)' +
            '<% } %></td>' +
            '<td class="fs-td-15pct">' +
            // Only disply controls when the file system is 'Available'
            '<% if (status === "Available" || status === "Running") { %>' +
                '<a class="fs-remove icon-button" id="fs-<%= name %>-remove" href="' + manage_service_url +
                '?service_name=<%= name %>&to_be_started=False&is_filesystem=True"' +
                'title="Remove this file system"></a>' +
                // It only makes sense to persist DoT, snapshot-based file systems
                '<% if (typeof(from_snap) !== "undefined" && typeof(DoT) !== "undefined" \
                    && DoT === "Yes") { %>' +
                    '<a class="fs-persist icon-button" id="fs-<%= name %>-persist" href="' +
                    update_fs_url + '?fs_name=<%= name %>" ' +
                    'title="Persist file system changes"></a>' +
                '<% } %>' +
                // It only makes sense to resize volume-based file systems
                '<% if (typeof(kind) != "undefined" && kind === "Volume" ) { %>' +
                    '<a class="fs-resize icon-button" id="fs-<%= name %>-resize" href="#"' +
                    'title="Increase file system size"></a>' +
                '<% } %>' +
            '<% } %></td>'+
            '<td class="fs-td-15pct">' +
                '<a href="#" class="fs-details" details-box="fs-<%= name %>-details">Details</a>' +
            '</td>' +
            '<td class="fs-td-spacer"></td>',
        tagName: "tr",
        className: "filesystem-tr",
        attributes: function() {
            // Explicitly add file system name as a tag/row attribute
            return {fs_name: this.model.get('name')};
        },

        render: function () {
            // Must clear tooltips; otherwise, following a rerender, the binding
            // element no longer exists and thus the tool tip stays on forever
            $(".tipsy").remove();
            var tmpl = _.template(this.filesystemSummaryTemplate);
            $(this.el).html(tmpl(this.model.toJSON()));
            if (this.model.attributes.status === 'Available' ||
                this.model.attributes.status === 'Running') {
                $(this.el).find('.fs-status').addClass("td-green-txt");
            } else if (this.model.attributes.status === 'Error') {
                $(this.el).find('.fs-status').addClass("td-red-txt");
            } else {
                $(this.el).find('.fs-status').addClass("td-tan-txt");
            }
            // Add toopltips
            this.$('a.icon-button').tipsy({gravity: 's', fade: true});
            return this;
        }
    });

    // Define the form view for resizing a file system
    var FilesystemResizeFormView = Backbone.View.extend({
        fsResizeFormTemplate:
            '<div class="form-row">' +
            'Through this form you may increase the disk space available to this file system. ' +
            'Any services using this file system <b>WILL BE STOPPED</b> ' +
            'until the new disk is ready, at which point they will all be restarted. Note ' +
            'that This may result in failure of any jobs currently running. Note that the new ' +
            'disk size <b>must be larger</b> than the current disk size.'+
            '<p>During this process, a snapshot of your data volume will be created, ' +
            'which can optionally be left in your account. If you decide to leave the ' +
            'snapshot for reference, you may also provide a brief note that will later ' +
            'be visible in the snapshot\'s description.</p>' +
            '</div>' +
            '<div class="form-row">' +
                '<label>New disk size (minimum <span id="du-inc"><%= size %></span>B, ' +
                'maximum 1000GB)</label>' +
                '<div id="permanent_storage_size" class="form-row-input">' +
                    '<input type="text" name="new_vol_size" id="new_vol_size" '+
                    'placeholder="Greater than <%= size %>B" size="25">' +
                '</div>' +
                '<label>Note</label>' +
                '<div id="permanent_storage_size" class="form-row-input">' +
                    '<input type="text" name="vol_expand_desc" id="vol_expand_desc" value="" ' +
                    'placeholder="Optional snapshot description" size="50"><br/>' +
                '</div>' +
                '<label>or delete the created snapshot after filesystem resizing?</label>' +
                '<input type="checkbox" name="delete_snap" id="delete_snap"> If checked, ' +
                'the created snapshot will not be kept' +
                '<div class="form-row">' +
                    '<input type="submit" value="Resize <%= name %> file system"/>' +
                    'or <a class="fs-resize-form-close" href="#">cancel</a>' +
                '</div>' +
                '<input name="fs_name" type="text" hidden="Yes" value="<%= name %>" />' +
            '</div>',
        tagName: "form",
        className: "fs-resize-form",

        initialize: function() {
            this.on("click:closeForm", this.closeForm, this);
        },

        events: {
            "submit": "handleResize",
            "click .fs-resize-form-close": "triggerFormClose",
        },

        render: function() {
            var tmpl = _.template(this.fsResizeFormTemplate);
            $(this.el).attr('id', "fs-"+this.model.attributes.name+"-resize-form");
            $(this.el).attr('action', resize_fs_url);
            $(this.el).attr('method', 'post');
            $(this.el).html(tmpl(this.model.toJSON()));
            return this;
        },

        handleResize: function(event) {
            // Issues the resize request to the back end
            event.preventDefault();
            var el = $('#'+event.currentTarget.id);
            var url = el.attr('action');
            $.post(url, el.serialize(),
                function(data) {
                    $('#msg').html(data).fadeIn();
                    clear_msg();
            });
            popup();
            // Hide the resize form
            this.formElToClose = el;
            this.closeForm();
            // Update status
            formId = el.attr('id');
            fsName = formId.split('-')[1]; // assumes form id is 'fs-<fs_name>-resize-form'
            updateFSStatus(fsName, "Resizing");
        },

        triggerFormClose: function(event) {
            // Capture the form element and trigger actual form closing
            event.preventDefault();
            this.formElToClose = $(event.currentTarget).parents('form');
            this.trigger("click:closeForm");
        },

        closeForm: function() {
            // Close the visible file system resize form
            if (this.formElToClose.is(':visible')) {
                // Hide resize form
                this.formElToClose.hide("blind");
                // Remove the highlight from the file system table row
                formId = this.formElToClose.attr('id');
                fsName = formId.split('-')[1]; // assumes form id is 'fs-<fs_name>-resize-form'
                var tr = $('tr[fs_name='+fsName+']');
                $(tr).animate({backgroundColor: 'transparent'}, 'slow');
            }
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
            };
            html += '</table>';
            $(this.el).html(html);
            return this;
        }
    });

    // Define the master view, i.e., list of all the file systems
    var FilesystemsView = Backbone.View.extend({
        tableHeaderTemplate: '<tr class="filesystem-tr"><th class="fs-td-20pct">Name</th>' +
            '<th class="fs-td-15pct">Status</th><th class="fs-td-20pct">Usage</th>' +
            '<th class="fs-td-15pct">Controls</td><th colspan="2"></th></tr>',
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
            if (FScollection.models.length > 0) {
                // Explicitly add the header row
                this.$el.append(this.tableHeaderTemplate);
                // Add all of the file systems, one per row
                _.each(FScollection.models, function (fs) {
                    that.renderFilesystem(fs);
                }, this);
            }
        },

        renderFilesystem: function (fs) {
            var filesystemView = new FilesystemView({
                model: fs
            });
            this.$el.append(filesystemView.render().el);
            // File system details view
            var filesystemDetailsView = new FilesystemDetailsView({
                model: fs
            });
            $('#fs-details-container').append(filesystemDetailsView.render().el);

            // File system resize form view
            var filesystemResizeFormView= new FilesystemResizeFormView({
                model: fs
            });
            $('#fs-resize-form-container').append(filesystemResizeFormView.render().el);

        },

        // Add UI event handlers
        events: {
            "click .fs-remove": "triggerRemove",
            "click .fs-persist": "triggerPersist",
            "click .fs-resize": "triggerResize",
        },

        triggerRemove: function (event) {
            // Is this trigger necessary? Why can't the click just be handled in this method?
            this.fsToRemoveID = event.currentTarget.id; // Reference to the element ID of the FS to be remvoed
            this.fsToRemoveTR = $('#'+event.currentTarget.id).parents('tr'); // Reference to tr to be removed
            event.preventDefault();
            // Clear any other forms that may be opened before removing a file system.
            // Otherwise, we run the risk of removing the element the form is bound to
            $('.fs-resize-form-close').trigger('click');
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
            updateFSStatus(this.fsToRemoveTR.attr('fs_name'), "Removing");
        },

        triggerPersist: function(event) {
            event.preventDefault();
            var el = $('#'+event.currentTarget.id);
            var url = el.attr('href');
            $.get(url, function(data) {
                $('#msg').html(data).fadeIn();
                clear_msg();
            });
            popup();
            updateFSStatus(el.parents('.filesystem-tr').attr('fs_name'), "Updating");
        },

        triggerResize: function(event) {
            event.preventDefault();
            var el = $('#'+event.currentTarget.id);
            var formId = el.attr('id') + '-form';
            // Close any other 'resize' forms
            if ($('.fs-resize-form').is(':visible')) {
                $('.fs-resize-form-close').trigger('click');
                // Don't 'reopen' the same form, just close it
                var reopen = false;
                $('.fs-resize-form').each(function() {
                    if ($(this).is(':visible') && $(this)[0] === $('#'+formId)[0]) {
                        reopen = true;
                    }
                });
                if (reopen === true) {
                    return false;
                }
            }
            // Highlight the fs table row
            var tr = el.parents('tr');
            tr.animate({backgroundColor: '#FEF1B5'}, 'slow');
            // Show the new file system resize form
            $('#'+formId).show("blind");
        },

    });

    // --- Views for adding a new file system service ---

    // Define the view for a form used to add a new file system
    var AddFilesystemFormView = Backbone.View.extend({
        fsAddFormTemplate:
            '<div class="form-row">' +
            '<a id="fs-add-form-close-btn" title="Cancel" href="#"></a>' +
            'Through this form you may add a new file system and make it available ' +
            'to the rest of this CloudMan platform. ' +
            '</div><div class="inline-radio-btns">' +
            '<fieldset>' +
                '<b>File system source or device:</b> ' +
                '<input type="radio" name="fs_kind" id="fs-kind-bucket-name" class="fs-add-radio-btn" value="bucket"/>' +
                '<label for="fs-kind-bucket-name">Bucket</label>' +
                '<input type="radio" name="fs_kind" id="fs-kind-volume" class="fs-add-radio-btn" value="volume" />' +
                '<label for="fs-kind-volume">Volume</label>' +
                '<input type="radio" name="fs_kind" id="fs-kind-snapshot" class="fs-add-radio-btn" value="snapshot"/>' +
                '<label for="fs-kind-snapshot">Snapshot</label>' +
                '<input type="radio" name="fs_kind" id="fs-kind-new-volume" class="fs-add-radio-btn" value="new_volume"/>' +
                '<label for="fs-kind-new-volume">New volume</label>' +
            '</fieldset>' +
            // Bucket form details
            '</div><div id="add-bucket-form" class="add-fs-details-form-row">' +
                '<table><tr>' +
                    '<td><label for="bucket_name">Bucket name: </label></td>' +
                    '<td><input type="text" size="20" name="bucket_name" id="bucket_name" ' +
                        'placeholder="e.g., 1000genomes"/> (AWS S3 buckets only)</td>' +
                    '</tr><tr>' +
                    '<td><label for="bucket_fs_name">File system name: </label></td>' +
                    '<td><input type="text" size="20" name="bucket_fs_name" id="bucket_fs_name"> ' +
                    '(no spaces, alphanumeric characters only)</td>' +
                '</tr></table></div>' +
                '<div id="add-bucket-fs-creds">' +
                    '<p> It appears you are not running on the AWS cloud. CloudMan supports '+
                    'using only buckets from AWS S3. So, if the bucket you are trying to ' +
                    'use is NOT PUBLIC, you must provide the AWS credentials that can be ' +
                    'used to access this bucket. If the bucket you are trying to use' +
                    'IS PUBLIC, leave below fields empty.</p>' +
                    '<table><tr>' +
                        '<td><label for"bucket_a_key">AWS access key: </label></td>' +
                        '<td><input type="text" id="bucket_a_key" name="bucket_a_key" size="50" /></td>' +
                    '</tr><tr>' +
                        '<td><label for"bucket_s_key">AWS secret key: </label></td>' +
                        '<td><input type="text" id="bucket_s_key" name="bucket_s_key" size="50" /></td>' +
                    '</tr></table>' +
                '</div>' +
            // Volume form details
            '</div><div id="add-volume-form" class="add-fs-details-form-row">' +
                '<table><tr>' +
                    '<td><label for="vol_id">Volume ID: </label></td>' +
                    '<td><input type="text" size="20" name="vol_id" id="vol_id" ' +
                        'placeholder="e.g., vol-456e6973"/></td>' +
                    '</tr><tr>' +
                    '<td><label for="vol_fs_name">File system name: </label></td>' +
                    '<td><input type="text" size="20" name="vol_fs_name" id="vol_fs_name"> ' +
                    '(no spaces, alphanumeric characters only)</td>' +
                '</tr></table>' +
            // Snapshot form details
            '</div><div id="add-snapshot-form" class="add-fs-details-form-row">' +
                '<table><tr>' +
                    '<td><label for="snap_id">Snapshot ID: </label></td>' +
                    '<td><input type="text" size="20" name="snap_id" id="snap_id" ' +
                        'placeholder="e.g., snap-c21cdsi6"/></td>' +
                    '</tr><tr>' +
                    '<td><label for="snap_fs_name">File system name: </label></td>' +
                    '<td><input type="text" size="20" name="snap_fs_name" id="snap_fs_name"> ' +
                    '(no spaces, alphanumeric characters only)</td>' +
                '</tr></table>' +
            // New volume form details
            '</div><div id="add-new-volume-form" class="add-fs-details-form-row">' +
                '<table><tr>' +
                    '<td><label for="new_disk_size">New file system size: </label></td>' +
                    '<td><input type="text" size="20" name="new_disk_size" id="new_disk_size" ' +
                        'placeholder="e.g., 100"> (minimum 1GB, maximum 1000GB)</td>' +
                    '</tr><tr>' +
                    '<td><label for="new_vol_fs_name">File system name: </label></td>' +
                    '<td><input type="text" size="20" name="new_vol_fs_name" id="new_vol_fs_name"> ' +
                    '(no spaces, alphanumeric characters only)</td>' +
                '</tr></table>' +
            '</div><div id="add-fs-dot" class="add-fs-details-form-row">' +
                '<input type="checkbox" name="dot" id="add-fs-dot-box"><label for="add-fs-dot-box">' +
                'If checked, the created disk <b>will be deleted</b> upon cluster termination</label>' +
            '</div><div id="add-fs-persist" class="add-fs-details-form-row">' +
                '<input type="checkbox" name="persist" id="add-fs-persist-box">' +
                '<label for="add-fs-persist-box">If checked, ' +
                'the created disk <b>will be persisted</b> as part of the cluster configuration ' +
                'and thus automatically added the next this this cluster is started</label>' +
            '</div>' +
            '<div id="add-fs-submit-btn" class="add-fs-details-form-row">' +
                '<input type="submit" value="Add new file system"/>' +
                'or <a class="fs-add-form-close" href="#">cancel</a>' +
            '</div>' +
            '</div>',
        tagName: "form",
        className: "fs-add-form",

        events: {
            "submit": "handleAdd",
            "click .fs-add-form-close": "triggerFormClose",
            "click #fs-add-form-close-btn": "triggerFormClose",
            "click #fs-kind-bucket-name": "showBucketForm",
            "click #fs-kind-volume": "showVolumeForm",
            "click #fs-kind-snapshot": "showSnapshotForm",
            "click #fs-kind-new-volume": "showNewVolumeForm",
        },

        initialize: function(options) {
            this.vent = options.vent;
            options.vent.bind("triggerAddFilesystem", this.showForm);
            this.on("click:closeForm", this.closeForm, this);
        },

        render: function() {
            var tmpl = _.template(this.fsAddFormTemplate);
            $(this.el).attr('id', "fs-add-form-id");
            $(this.el).attr('action', add_fs_url);
            $(this.el).attr('method', 'post');
            $(this.el).html(tmpl());
            return this;
        },

        showForm: function() {
            $('#fs-add-form-id').show("blind");
        },

        showBucketForm: function(event) {
            event.stopPropagation();
            this.hideDetailsForm(event);
            $("#add-bucket-form").show("blind");
            if (cloud_type != 'ec2') {
                $('#add-bucket-fs-creds').show();
            }
            $('#add-fs-persist').show("blind");
            $('#add-fs-submit-btn').show("blind");
        },

        showVolumeForm: function() {
            this.hideDetailsForm();
            $("#add-volume-form").show("blind");
            $('#add-fs-dot').show("blind");
            $('#add-fs-persist').show("blind");
            $('#add-fs-submit-btn').show("blind");
        },

        showSnapshotForm: function() {
            this.hideDetailsForm();
            $("#add-snapshot-form").show("blind");
            $('#add-fs-dot').show("blind");
            $('#add-fs-persist').show("blind");
            $('#add-fs-submit-btn').show("blind");
        },

        showNewVolumeForm: function() {
            this.hideDetailsForm();
            $("#add-new-volume-form").show("blind");
            $('#add-fs-dot').show("blind");
            $('#add-fs-persist').show("blind");
            $('#add-fs-submit-btn').show("blind");
        },

        hideDetailsForm: function(event) {
            $('.add-fs-details-form-row').each(function() {
                var elid = $(this).attr('id');
                if ($('#'+elid).is(':visible')) {
                    $(this).hide("blind");
                }
            });
        },

        handleAdd: function(event) {
            // Issues the add request to the back end
            event.preventDefault();
            var el = $('#'+event.currentTarget.id);
            var url = el.attr('action');
            $.post(url, el.serialize(),
                function(data) {
                    $('#msg').html(data).fadeIn();
                    clear_msg();
            });
            popup();
            // Hide the resize form
            this.formElToClose = el;
            this.closeForm();
            // TODO: Update status
            //updateFSStatus(fsName, "Resizing");
        },

        triggerFormClose: function(event) {
            // Capture the form element and trigger actual form closing
            event.preventDefault();
            this.formElToClose = $(event.currentTarget).parents('form');
            this.trigger("click:closeForm");
        },

        closeForm: function() {
            // Clean the form
            $('.fs-add-radio-btn').each(function() {
                $(this).prop('checked', false);
            });
            $('.add-fs-details-form-row').each(function() {
                if ($(this).is(":visible")) {
                    $(this).hide("blind");
                }
            });
            // Close the visible file system add form
            if (this.formElToClose.is(':visible')) {
                this.formElToClose.hide("blind");
            }
            this.vent.trigger("addFilesystemFormClose");
        }

    });

    // Define the view for dealing with the 'Add file system' button
    var AddFilesystemBtnView = Backbone.View.extend({
        el: $('#fs-add-btn'),

        events: {
            "click": "triggerAdd",
        },

        initialize: function(options) {
            this.vent = options.vent;
            this.vent.bind("addFilesystemFormClose", this.render, this);
        },

        render: function() {
            $(this.el).show();
        },

        triggerAdd: function() {
            this.vent.trigger("triggerAddFilesystem");
            $(this.el).hide("blind");
        }

    });

    // --- Driver code ---

    // An app-wide event aggregator object: http://bit.ly/p3nTe6
    var vent = _.extend({}, Backbone.Events);
    // Create an instance of the master view
    var filesystemList = new FilesystemsView();
    // Fetch the initial data from the server
    FScollection.fetch();
    // Create instances of the add new file system button and form views
    // Also, subscribe those to global events
    // TODO: Improve global event triggering? http://bit.ly/AlZ3EJ
    var addFilesystemBtnView= new AddFilesystemBtnView({vent: vent});
    var addFilesystemFormView = new AddFilesystemFormView({vent: vent});
    $('#fs-add-form').html(addFilesystemFormView.render().el);

    function updateFSStatus(fs_name, new_status) {
        // A common method for updating the UI based on user action before the
        // backend info is fetched
        for (var i=0; i<FScollection.models.length; i++) {
            if (FScollection.models[i].attributes.name === fs_name) {
                FScollection.models[i].attributes.status = new_status;
            }
        }
        filesystemList.render();
    };

    function updateFS() {
        // Do not update file systems while a details box is visible because it
        // does not function: conceptually, a file system may dissapear so what
        // to display; also, the UI gets rendered w/ each refresh so it's would
        // have to be handled differently (maybe one day)
        if (!$('.fs-details-box').is(':visible') && !$('.fs-resize-form').is(':visible')) {
            // Keep updating the display with the fresh data from the server
            FScollection.fetch();
        }
        window.setTimeout(function(){updateFS();}, 5000);
    }
    updateFS();
} (jQuery));
