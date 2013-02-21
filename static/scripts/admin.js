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

function update_application_status(id, content) {
    $(id).html(content);
    // Set color for services - `Running`: green, 'Error': red; anything else is tan
    if (content === 'Running') {
        $(id).css("color", "#037f26");
    }
    else if (content === 'Error') {
        $(id).css("color", "#BF3030");
    }
    else {
        $(id).css("color", "#6F6C61");
    }
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
                update_application_status("#galaxy_status", data.Galaxy);
                update_application_status("#postgres_status", data.Postgres);
                update_application_status("#sge_status", data.SGE);
                update_application_status("#galaxy_reports_status", data.GalaxyReports);
                $('#filesystem_status').html(data.Filesystem);
                if (data.snapshot.status !== "None"){
                    $('#snapshotoverlay').show(); // Overlay that prevents any future clicking
                    $('#update_fs_status').html(" - Wait until the process completes. Status: <i>" +
                        data.snapshot.status + "</i>");
                } else {
                    $('#update_fs_status').html("");
                    $('#snapshotoverlay').hide();
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
    // Clicking the semi-transparent overlay clears any overlays
    $('body').on('click', 'div.overlay', function() { hidebox();});
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

String.prototype.toProperCase = function () {
    // Convert a string to Title Case capitalization
    return this.replace(/\w\S*/g, function(txt){return txt.charAt(0).toUpperCase() + txt.substr(1).toLowerCase();});
};
String.prototype.toSpaced = function(){
    // Convert an underscore-connected string to a space-connected string
    // (e.g., i_am_undescored -> i am underscored)
	return this.replace(/(\_[a-z])/g, function($1){return $1.toUpperCase().replace('_',' ');});
};

// Convert form data to JS object
// http://stackoverflow.com/questions/1184624/convert-form-data-to-js-object-with-jquery
jQuery.fn.serializeObject = function() {
  var arrayData, objectData;
  arrayData = this.serializeArray();
  objectData = {};

  $.each(arrayData, function() {
    var value;

    if (this.value != null) {
      value = this.value;
    } else {
      value = '';
    }

    if (objectData[this.name] != null) {
      if (!objectData[this.name].push) {
        objectData[this.name] = [objectData[this.name]];
      }

      objectData[this.name].push(value);
    } else {
      objectData[this.name] = value;
    }
  });

  return objectData;
};

// Backbone.js components
(function ($) {

    // Define the file system model
    var Filesystem = Backbone.Model.extend({
        defaults: {
            id: null,
            status: 'Unavailable',
            size_used: 'N/A',
            size_pct: 'N/A',
            size: 'N/A',
            DoT: 'N/A'
        }
    });

    // Define the filesystems collection
    var Filesystems = Backbone.Collection.extend({
        model: Filesystem,
        url: get_all_filesystems_url
    });

    // Define an individual file system summary view
    var FilesystemView = Backbone.Marionette.ItemView.extend({
        tagName: "tr",
        template: "#fileSystem-template",
        className: "filesystem-tr",

        events: {
            "click .fs-remove": "triggerRemove",
            "click .fs-details": "showDetails",
            "click .fs-resize": "triggerResize",
            "click .fs-persist": "triggerPersist"
        },

        initialize: function() {
            this.model.bind("change", this.render, this); // watch for any model changes
            this.on("item:before:render", this.onBeforeRender);
        },

        onBeforeRender: function() {
            // Strip the % sign from the value so meter tag can display it
            if (this.model.attributes.size_pct != null) {
                this.model.attributes.size_pct = this.model.attributes.size_pct.match(/\d+/g);
            }
        },

        onRender: function() {
            // Must clear tooltips; otherwise, following a rerender, the binding
            // element no longer exists and thus the tool tip stays on forever
            $(".tipsy").remove();
            // Add state CSS
            if (this.model.attributes.status === 'Available' ||
                this.model.attributes.status === 'Running') {
                this.$el.find('.fs-status').addClass("td-green-txt");
            } else if (this.model.attributes.status === 'Error') {
                this.$el.find('.fs-status').addClass("td-red-txt");
            } else {
                this.$el.find('.fs-status').addClass("td-tan-txt");
            }
            // Add toopltips
            this.$('a.icon-button').tipsy({gravity: 's', fade: true});
            // Return the % symbol that was removed above in ``onBeforeRender`` method
            if (this.model.attributes.size_pct != null) {
                this.model.attributes.size_pct = this.model.attributes.size_pct + "%";
            }
        },

        triggerRemove: function(event) {
            event.preventDefault();
            this.$el.css({backgroundColor: '#FEF1B5'}, "fast");
            // Show a modal confirmation dialog
            var filesystemRemoveConfirmationView =
                new FilesystemRemoveConfirmationView({model: this.model});
            filesystemRemoveConfirmationView.render().showModal();
            // Listen for the modal dialog's action event and act accordingly
            var that = this;
            filesystemRemoveConfirmationView.on('fs:removeFS', function(){
                that.handleRemove();
            });
            // closeModalWindow is automatically triggered by Backbone.ModalView
            filesystemRemoveConfirmationView.on('closeModalWindow', function(){
                that.$el.animate({backgroundColor: 'transparent'}, "slow");
            });
        },

        handleRemove: function() {
            url = this.$el.find('a.fs-remove').attr('href');
            $.get(url, function(data) {
                $('#msg').html(data).fadeIn();
                clear_msg();
            });
            this.model.attributes.status = 'Removing';
            this.model.save();
        },

        showDetails: function(event) {
            event.preventDefault();
            // Before displaying a new details box, close any others and clear tr
            CMApp.vent.trigger("fs:detailsClose");
            // Highlight the file system for which the details are being shown
            this.$el.animate({backgroundColor: '#FEF1B5'}, "fast");
            var detailsView = new FilesystemDetailsView({model: this.model});
            CMApp.fsDetails.show(detailsView);
            // Listen for a hide event on the 'close' button to remove the tr highlight
            var that = this;
            (function () {
                CMApp.vent.on("fs:detailsClose", function(){
                    that.$el.animate({backgroundColor: 'transparent'}, "fast");
                });
            })();
        },

        triggerResize: function(event){
            event.preventDefault();
            // Show the form only if not already shown
            if ($('#fs-resize-form-container').html() === ""){
                this.$el.css({backgroundColor: '#FEF1B5'}, "fast");
                var filesystemResizeFormView = new FilesystemResizeFormView({model: this.model});
                CMApp.fsResizeRegion.show(filesystemResizeFormView);
                // item:before:close is automatically triggered by backbone.Marionette
                var that = this;
                filesystemResizeFormView.on('item:before:close', function(){
                    that.$el.animate({backgroundColor: 'transparent'}, "slow");
                });
                // Update model state on the resizing event
                filesystemResizeFormView.on("fs:resizing", function(){
                    that.model.attributes.status = "Configuring";
                    that.model.save();
                });
            }
        },

        triggerPersist: function(event){
            event.preventDefault();
            this.$el.css({backgroundColor: '#FEF1B5'}, "fast");
            // Show a modal confirmation dialog
            var filesystemPersistConfirmationView =
                new FilesystemPersistConfirmationView({model: this.model});
            filesystemPersistConfirmationView.render().showModal();
            // Listen for the modal dialog's action event and act accordingly
            var that = this;
            filesystemPersistConfirmationView.on('fs:persistFS', function(){
                that.handlePersist();
            });
            // closeModalWindow is automatically triggered by Backbone.ModalView
            filesystemPersistConfirmationView.on('closeModalWindow', function(){
                that.$el.animate({backgroundColor: 'transparent'}, "slow");
            });
        },

        handlePersist: function(){
            url = this.$el.find('a.fs-persist').attr('href');
            $.get(url, function(data) {
                $('#msg').html(data).fadeIn();
                clear_msg();
            });
            this.model.attributes.status = 'Persisting';
            this.model.save();
        }
    });

    // Define the form view for resizing a file system
    var FilesystemResizeFormView = Backbone.Marionette.ItemView.extend({
        template: "#fs-resize-template",
        className: "fs-resize-form",
        tagName: "form",

        events: {
            "click .fs-resize-form-close": "triggerFormClose",
            "submit": "handleResize"
        },

        initialize: function() {
            // Add the form element attributes
            this.$el.attr('action', resize_fs_url);
            this.$el.attr('method', 'post');
        },

        triggerFormClose: function(event) {
            event.preventDefault();
            this.close();
        },

        handleResize: function(event) {
            event.preventDefault();
            // Issue POST request
            var url = this.$el.attr('action');
            $.post(url, this.$el.serialize(),
                function(data) {
                    $('#msg').html(data).fadeIn();
                    clear_msg();
            });
            // Trigger event for the model update
            this.trigger('fs:resizing');
            this.close();
        }
    });

    // Define the details popup view for an individual file system
    var FilesystemDetailsView = Backbone.Marionette.ItemView.extend({
        template: "#fs-details-template",
        className: "fs-details-box modal-box",

        events: {
            "click .close": "hideDetails",
        },

        hideDetails: function() {
            CMApp.vent.trigger("fs:detailsClose");
            CMApp.fsDetails.close();
        }
    });

    // Base ModalConfirmationDialogView - other confirmation views should inherit from this one
    var ModalConfirmationDialogView = Backbone.ModalView.extend({
        template:
            '<div class="modal-dialog-header">Are you sure?</div>' +
            '<div class="modal-dialog-text">Clicking on the <i>Confirm</i> button ' +
                'will initiate the requested action.</div>' +
            '<div class="modal-dialog-buttons">' +
                '<button class="modal-dialog-ok-button">Confirm</button>' +
                '<button class="modal-dialog-cancel-button">Cancel</button>' +
            '</div>',

        events: {
            "click .modal-dialog-ok-button": "confirm",
            "click .modal-dialog-cancel-button": function(){this.hideModal();}
        },

        initialize: function() {
            this.template = _.template(this.template);
        },

        render: function() {
            $(this.el).html(this.template(this.model.toJSON()));
            return this;
        },

        confirm: function() {
            this.trigger("modal-dialog-ok");
            this.hideModal();
        }
    });

    // Define the view for displaying a confirmation dialog before removing a FS
    var FilesystemRemoveConfirmationView = ModalConfirmationDialogView.extend({
        template:
            '<div class="modal-dialog-header">Remove <i><%= name %></i> file system?</div>' +
            '<div class="modal-dialog-text">Removing this file system will first stop any ' +
                'services that require this file system. Then, the file system will be ' +
                'unmounted and the underlying device disconnected from this instance.</div>' +
            '<div class="modal-dialog-buttons">' +
                '<button id="confirm_fs_action" class="modal-dialog-ok-button">Confirm</button>' +
                '<button class="modal-dialog-cancel-button">Cancel</button>' +
            '</div>',

        confirm: function() {
            this.trigger('fs:removeFS');
            this.hideModal();
        }
    });

    // Define the view for displaying a confirmation dialog before persisting changes to a FS
    var FilesystemPersistConfirmationView = ModalConfirmationDialogView.extend({
        template:
            '<div class="modal-dialog-header">Persist <i><%= name %></i> file system changes?</div>' +
            '<div class="modal-dialog-text"><p>If you have made changes to the ' +
                '<i><%= name %></i> file system and would like to persist the changes ' +
                'across cluster invocations, it is required to persist those ' +
                'changes. </p><i>What will happen next?</i></br>' +
                'Persisting file system changes requires that any services running on the ' +
                'file system be stopped and the file system unmounted. Then, a ' +
                'snapshot of the underlying volume will be created and any services ' +
                'running on the file system started back up. Note that depending ' +
                'on the amount of changes you have made to the file system, this ' +
                'process may take a while.</div>' +
            '<div class="modal-dialog-buttons">' +
                '<button id="confirm_fs_persist" class="modal-dialog-ok-button">Confirm</button>' +
                '<button class="modal-dialog-cancel-button">Cancel</button>' +
            '</div>',

        confirm: function() {
            this.trigger('fs:persistFS');
            this.hideModal();
        }
    });

    // Define the master view, i.e., list of all the file systems
    var FilesystemsView = Backbone.Marionette.CompositeView.extend({
        template: "#fileSystems-template",
        tagName: "table",
        id: "filesystems-table",
        itemView: FilesystemView,

        appendHtml: function(collectionView, itemView) {
            collectionView.$("tbody").append(itemView.el);
        }

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
                '<input type="radio" name="fs_kind" id="fs-kind-nfs" class="fs-add-radio-btn" value="nfs"/>' +
                '<label for="fs-kind-nfs">NFS</label>' +
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
                    'used to access this bucket. If the bucket you are trying to use ' +
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
            // NFS form details
            '</div><div id="add-nfs-form" class="add-fs-details-form-row">' +
                '<table><tr>' +
                    '<td><label for="nfs-server">NFS server address: </label></td>' +
                    '<td><input type="text" size="20" name="nfs_server" id="nfs_server" ' +
                        'placeholder="e.g., 172.22.169.17:/nfs_dir"></td>' +
                    '</tr><tr>' +
                    '<td><label for="nfs_fs_name">File system name: </label></td>' +
                    '<td><input type="text" size="20" name="nfs_fs_name" id="nfs_fs_name"> ' +
                    '(no spaces, alphanumeric characters only)</td>' +
                '</tr></table>' +
            '</div><div id="add-fs-dot" class="add-fs-details-form-row">' +
                '<input type="checkbox" name="dot" id="add-fs-dot-box"><label for="add-fs-dot-box">' +
                'If checked, the created disk <b>will be deleted</b> upon cluster termination</label>' +
            '</div><div id="add-fs-persist" class="add-fs-details-form-row">' +
                '<input type="checkbox" name="persist" id="add-fs-persist-box">' +
                '<label for="add-fs-persist-box">If checked, ' +
                'the created disk <b>will be persisted</b> as part of the cluster configuration ' +
                'and thus automatically added the next time this cluster is started</label>' +
            '</div>' +
            '<div id="add-fs-submit-btn" class="add-fs-details-form-row">' +
                '<input type="submit" class="fs-form-submit-button" value="Add new file system"/>' +
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
            "click #fs-kind-nfs": "showNFSForm",
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

        showNFSForm: function() {
            this.hideDetailsForm();
            $("#add-nfs-form").show("blind");
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
            // Based on the kind of the new file system, get the name
            var fs_kind = $('input[type=radio]:checked', el).val();
            var form_obj = el.serializeObject();
            switch(fs_kind) {
                case "bucket":
                    var new_fs_name = form_obj.bucket_fs_name;
                    break;
                case "volume":
                    var new_fs_name = form_obj.vol_fs_name;
                    break;
                case "snapshot":
                    var new_fs_name = form_obj.snap_fs_name;
                    break;
                case "new_volume":
                    var new_fs_name = form_obj.new_vol_fs_name;
                    break;
                case "nfs":
                    var new_fs_name = form_obj.nfs_fs_name;
                    break;
                default:
                    var new_fs_name = "Unknown";
            }
            if (form_obj.dot === 'on'){
                var dot = 'Yes';
            } else {
                var dot = 'No';
            }
            // Make the POST request
            $.post(url, el.serialize(),
                function(data) {
                    $('#msg').html(data).fadeIn();
                    clear_msg();
            });
            // Hide the resize form
            if ($('#add-bucket-fs-creds').is(':visible')){
                $('#add-bucket-fs-creds').hide();
            }
            this.formElToClose = el;
            this.closeForm();
            // Add this file system to the collection to be shown on the UI
            FScollection.add({name: new_fs_name, status: 'Adding', kind: fs_kind,
                mount_point: '/mnt/'+new_fs_name, DoT: dot});
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

    // Define model collection
    var FScollection = new Filesystems(); // A container for all Filesystems

    // Initialize Marionette app
    CMApp = new Backbone.Marionette.Application();
    CMApp.addRegions({
        mainRegion: "#filesystems-container",
        fsDetails: "#fs-details-container",
        fsResizeRegion: "#fs-resize-form-container"
    });
    CMApp.addInitializer(function(options){
        var filesystemsView = new FilesystemsView({
            collection: options.filesystems
        });
        CMApp.mainRegion.show(filesystemsView);
    });
    CMApp.start({filesystems: FScollection});

    // An app-wide event aggregator object: http://bit.ly/p3nTe6
    var vent = _.extend({}, Backbone.Events);
    // Create instances of the add new file system button and form views
    // Also, subscribe those to global events
    // TODO: Improve global event triggering? http://bit.ly/AlZ3EJ
    var addFilesystemBtnView = new AddFilesystemBtnView({vent: vent});
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
        if (!$('.modal-box').is(':visible') && !$('.fs-resize-form').is(':visible')) {
            // Keep updating the display with the fresh data from the server
            FScollection.fetch();
        }
        //window.setTimeout(function(){updateFS();}, 10000);
    }
    updateFS();
} (jQuery));


/***************** ANGULAR JS Modules and Controllers **************************/


//****************** Slightly modified Popup based on Angular-UI's popup ******************

/**
 * The main changes were to
 * 1. Load template from a script block
 * 2. Change scope to use parent scope, so values bind properly (TODO: Better solution needed?)
 * 3. Adjust element position detection code so it works within tables
 * All changes marked with MODIFIED comment
 */
angular.module( 'cloudman.popover', [] )
.directive( 'cloudmanPopup', function () {
  return {
    restrict: 'EA',
    replace: true,
    // MODIFIED: scope: { popoverTitle: '@', popoverContent: '@', placement: '@', animation: '&', isOpen: '&' },
    templateUrl: '#/cm-popover.html' //MODIFIED
  };
})
.directive( 'cmPopover', [ '$compile', '$timeout', '$parse', function ( $compile, $timeout, $parse ) {
  
  var template = 
    '<cloudman-popup '+
      'popover-title="{{tt_title}}" '+
      'popover-content="{{tt_popover}}" '+
      'placement="{{tt_placement}}" '+
      'animation="tt_animation()" '+
      'is-open="tt_isOpen"'+
      '>'+
    '</cloudman-popup>';
  
  return {
    scope: true,
    link: function ( scope, element, attr ) {
      var popover = $compile( template )( scope ), 
          transitionTimeout;

      attr.$observe( 'popover', function ( val ) {
        scope.tt_popover = val;
      });

      attr.$observe( 'popoverTitle', function ( val ) {
        scope.tt_title = val;
      });

      attr.$observe( 'popoverPlacement', function ( val ) {
        // If no placement was provided, default to 'top'.
        scope.tt_placement = val || 'top';
      });

      attr.$observe( 'popoverAnimation', function ( val ) {
        scope.tt_animation = $parse( val );
      });

      // By default, the popover is not open.
      scope.tt_isOpen = false;
      
      // Calculate the current position and size of the directive element.
      function getPosition() {
        return {
          width: element.prop( 'offsetWidth' ),
          height: element.prop( 'offsetHeight' ),
          //MODIFIED: top: element.prop( 'offsetTop' ),
          //MODIFIED: left: element.prop( 'offsetLeft' ),
          top: element.offset().top,
          left: element.offset().left
        };
      }
      
      // Show the popover popup element.
      function show() {
        var position,
            ttWidth,
            ttHeight,
            ttPosition;
          
        // If there is a pending remove transition, we must cancel it, lest the
        // toolip be mysteriously removed.
        if ( transitionTimeout ) {
          $timeout.cancel( transitionTimeout );
        }
        
        // Set the initial positioning.
        popover.css({ top: 0, left: 0, display: 'block' });
        
        // Now we add it to the DOM because need some info about it. But it's not 
        // visible yet anyway.
        element.after( popover );
        
        // Get the position of the directive element.
        position = getPosition();
        
        // Get the height and width of the popover so we can center it.
        ttWidth = popover.prop( 'offsetWidth' );
        ttHeight = popover.prop( 'offsetHeight' );
        
        // Calculate the popover's top and left coordinates to center it with
        // this directive.
        switch ( scope.tt_placement ) {
          case 'right':
            ttPosition = {
              top: (position.top + position.height / 2 - ttHeight / 2) + 'px',
              left: (position.left + position.width) + 'px'
            };
            break;
          case 'bottom':
            ttPosition = {
              top: (position.top + position.height) + 'px',
              left: (position.left + position.width / 2 - ttWidth / 2) + 'px'
            };
            break;
          case 'left':
            ttPosition = {
              top: (position.top + position.height / 2 - ttHeight / 2) + 'px',
              left: (position.left - ttWidth) + 'px'
            };
            break;
          default:
            ttPosition = {
              top: (position.top - ttHeight) + 'px',
              left: (position.left + position.width / 2 - ttWidth / 2) + 'px'
            };
            break;
        }
        
        // Now set the calculated positioning.
        popover.css( ttPosition );
          
        // And show the popover.
        scope.tt_isOpen = true;
      }
      
      // Hide the popover popup element.
      function hide() {
        // First things first: we don't show it anymore.
        //popover.removeClass( 'in' );
        scope.tt_isOpen = false;
        
        // And now we remove it from the DOM. However, if we have animation, we 
        // need to wait for it to expire beforehand.
        // FIXME: this is a placeholder for a port of the transitions library.
        if ( angular.isDefined( scope.tt_animation ) && scope.tt_animation() ) {
          transitionTimeout = $timeout( function () { popover.remove(); }, 500 );
        } else {
          popover.remove();
        }
      }
      
      // Register the event listeners.
      element.bind( 'click', function() {
        if(scope.tt_isOpen){
            scope.$apply( hide );
        } else {
            scope.$apply( show );
        }

      });
    }
  };
}]);

angular.module("cloudman.popover.fstemplate", []).run(["$templateCache", function($templateCache){
  $templateCache.put("#/cm-popover.html",
    "<div class=\"popover {{placement}}\" ng-class=\"{ in: isOpen(), fade: animation() }\">" +
    "  <div class=\"arrow\"></div>" +
    "" +
    "  <div class=\"popover-inner\">" +
    "      <h3 class=\"popover-title\" ng-bind=\"popoverTitle\" ng-show=\"popoverTitle\"></h3>" +
    //"      <div class=\"popover-content\" ng-bind-html-unsafe=\"popoverContent\"></div>" +
    "      <div class=\"popover-content\">" + $("#fs-details-popover-template").html() + "</div>" +
    "  </div>" +
    "</div>" +
    "");
}]);

//*************** END customized Popup *********************

//********** Cloudman Modules and Controllers **************

var cloumanAdminModule = angular.module('cloudman', ['ui.bootstrap', 'ui.bootstrap.dialog', 'ui.bootstrap.alert', 'cloudman.popover', 'cloudman.popover.fstemplate']);

cloumanAdminModule.service('cmAlertService', function ($timeout) {
		var alerts = [];
		
		var getAlerts = function() {
	    	return alerts;
		};
		
		var addAlert = function(message, type) {
			alert = {msg: message, type: type};
			alerts.push(alert);
			$timeout(function() { closeAlert(alert); }, 60000, true);
		};
		
		var closeAlert = function(alert) {
            	var index = alerts.indexOf(alert)
	    		alerts.splice(index, 1);
		}
		
		return {
			getAlerts: getAlerts,
            addAlert: addAlert,
            closeAlert: closeAlert
        };
	});
	
cloumanAdminModule.controller('cmAlertController', ['$scope', 'cmAlertService', function ($scope, cmAlertService) {
		
		$scope.getAlerts = function () {
            return cmAlertService.getAlerts();
        };
        
        $scope.closeAlert = function (alert) {
            cmAlertService.closeAlert(alert);
        };
	}]);

cloumanAdminModule.service('cmAdminDataService', function ($http, $timeout) {
		var services = [];
		var file_systems = [];
		
		(function poll_admin_data() {
	        // Poll application services
	        $http.get(get_application_services_url).success(function (data) {
				services = data;
    		});
    		// Poll file systems
    		$http.get(get_all_filesystems_url).success(function (data) {
	        	file_systems = data;
	        });
			$timeout(poll_admin_data, 10000, true);	        
	    })();
	    
		return {
            getAllFilesystems: function () {
                return file_systems;
            },
            getAllServices: function () {
                return services;
            }
        };
	});
	
cloumanAdminModule.controller('ServiceController', ['$scope', '$http', 'cmAdminDataService', function ($scope, $http, cmAdminDataService) {
		
		$scope.getServices = function () {
            return cmAdminDataService.getAllServices();
        };
        
        $scope.getAvailableFileSystems = function () {
            return cmAdminDataService.getAllFilesystems();
        };
		
		$scope._visibility_flags = {};		
		
		$scope.expandServiceDetails = function() {			
			var service = this.svc.svc_name;
			
			// TODO: This DOM manipulation code should not be in controller.
			// Unselect all previous rows
			for (val in $scope.services) {
				service_row = $scope.services[val].svc_name;
				if (service_row != service)
					$scope._visibility_flags[service_row] = false;
					
				$('#service_row_' + service_row).animate({backgroundColor: 'transparent'}, "fast");
				$('#service_detail_row_' + service_row).animate({backgroundColor: 'transparent'}, "fast");
			}
			
			// Show newly selected row
			if ($scope._visibility_flags[service]) {
				$('#service_row_' + service).animate({backgroundColor: 'transparent'}, "slow");
				$('#service_detail_row_' + service).animate({backgroundColor: 'transparent'}, "slow");
			}
			else {
				$('#service_row_' + service).animate({backgroundColor: '#FEF1B5'}, "fast");
				$('#service_detail_row_' + service).animate({backgroundColor: '#FEF1B5'}, "fast");
			}
		
			$scope._visibility_flags[service] = !$scope._visibility_flags[service];
		};
		
		$scope.is_service_visible = function() {
			return $scope._visibility_flags[this.svc.svc_name];
		}
		
		$scope.is_fs_selected = function() {
			return this.req.assigned_service == this.fs.name;		
		}	
	}]);

cloumanAdminModule.controller('FileSystemController', ['$scope', '$http', '$dialog', 'cmAdminDataService', function ($scope, $http, $dialog, cmAdminDataService) {
		var _opts =  {
			    backdrop: true,
			    keyboard: true,
			    backdropClick: true,
			    modalFade: true,
			  };
			  
		$scope.getFileSystems = function () {
            return cmAdminDataService.getAllFilesystems();
        };
		
		$scope.fs_detail_template = $("#fs-details-popover-template").html();
		
		$scope.is_ready_fs = function(fs) {
			return (fs.status == "Available" || fs.status == "Running");
		}
		
		$scope.is_snapshot_in_progress = function(fs) {
			return (fs.kind == "Volume" && fs.status == "Configuring") && (fs.snapshot_status != "" && fs.snapshot_status != null);
		}
		
		$scope.is_persistable_fs = function(fs) {
			return ((fs.status === "Available" || fs.status === "Running") && (typeof(fs.from_snap) !== "undefined" && typeof(fs.DoT) !== "undefined" && fs.DoT === "Yes"));
		}
		
		$scope.is_resizable_fs = function(fs) {
			return (fs.status === "Available" || fs.status === "Running") && (typeof(fs.kind) != "undefined" && fs.kind === "Volume" );
		}
		
		$scope.remove_fs = function($event, fs) {
			// TODO: DOM access in controller. Should be changed
			_opts.template = $("#fs-delete-dialog-template").html();
			_opts.controller = 'FSRemoveDialogController';
			_opts.resolve = {fs: fs};			
		
			var d = $dialog.dialog(_opts);
	    	d.open().then(function(result) {
		    });
		}		

		$scope.persist_fs = function($event, fs) {
			_opts.template = $("#fs-persist-dialog-template").html(),
			_opts.controller = 'FSPersistDialogController';
			_opts.resolve = {fs: fs};

			var d = $dialog.dialog(_opts);
	    	d.open().then(function(result) {
		    });
		}		
		
		$scope.resize_fs = function($event, fs) {
			_opts.template = $("#fs-resize-dialog-template").html(),
			_opts.controller = 'FSResizeDialogController';
			_opts.resolve = {fs: fs};

			var d = $dialog.dialog(_opts);
	    	d.open().then(function(result) {
		    });
		}
		
	}]);


function FSRemoveDialogController($scope, dialog, fs, cmAlertService) {
	  $scope.fs = fs;
	  $scope.cancel = function($event, result){
	  	$event.preventDefault();
	    dialog.close('cancel');
	  };
	  $scope.confirm = function($event, result){
	  	// TODO: DOM access in controller. Should be redone
		$('#fs_remove_form').ajaxForm({
	        type: 'GET',
	        dataType: 'html',
	        error: function(response) {
	        	cmAlertService.addAlert(response.responseText, "error");
	        },
	        success: function(response) {
	        	cmAlertService.addAlert(response, "info");
	        }
	    });
	  	
	    dialog.close(result);
	  };
}


function FSPersistDialogController($scope, dialog, fs, cmAlertService) {
	  $scope.fs = fs;
	  $scope.cancel = function($event, result){
	  	$event.preventDefault();
	    dialog.close('cancel');
	  };
	  $scope.confirm = function($event, result){
	  	// TODO: DOM access in controller. Should be redone
		$('#fs_persist_form').ajaxForm({
	        type: 'GET',
	        dataType: 'html',
	        error: function(response) {
	        	cmAlertService.addAlert(response.responseText, "error");
	        },
	        success: function(response) {
	        	cmAlertService.addAlert(response, "info");
	        }
	    });
	  	
	    dialog.close(result);
	  };
}


function FSResizeDialogController($scope, dialog, fs, cmAlertService) {
	  $scope.fs = fs;
	  $scope.resize_details = {};  
	  $scope.cancel = function($event, result){
	  	$event.preventDefault();
	    dialog.close('cancel');
	  };
	  $scope.resize = function(result){
		// TODO: DOM access in controller. Should be redone
		$('#fs_resize_form').ajaxForm({
	        type: 'POST',
	        dataType: 'html',
	        error: function(response) {
	        	cmAlertService.addAlert(response.responseText, "error");
	        },
	        success: function(response) {
	        	cmAlertService.addAlert(response, "info");
	        }
	    });
	  	
	    dialog.close('confirm');
	  };
}