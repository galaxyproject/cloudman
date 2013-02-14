
String.prototype.toProperCase = function () {
    // Convert a string to Title Case capitalization
    return this.replace(/\w\S*/g, function(txt){return txt.charAt(0).toUpperCase() + txt.substr(1).toLowerCase();});
};
String.prototype.toSpaced = function(){
    // Convert an underscore-connected string to a space-connected string
    // (e.g., i_am_undescored -> i am underscored)
	return this.replace(/(\_[a-z])/g, function($1){return $1.toUpperCase().replace('_',' ');});
};


/***************** ANGULAR JS Modules and Controllers **************************/


//****************** Override default template provided by Angular-UI bootstrap ******************

angular.module("template/dialog/message.html", []).run(["$templateCache", function($templateCache){
  $templateCache.put("template/dialog/message.html",
    "<div class=\"modal-header\">" +
    "	<h1>{{ title }}</h1>" +
    "</div>" +
    "<div class=\"modal-body\">" +
    "	<p ng-bind-html-unsafe='message' />" +
    "</div>" +
    "<div class=\"modal-footer\">" +
    "	<button ng-repeat=\"btn in buttons\" ng-click=\"close(btn.result)\" class=btn ng-class=\"btn.cssClass\">{{ btn.label }}</button>" +
    "</div>" +
    "");
}]);

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
            // MODIFIED: scope.$apply( hide );
            hide();
        } else {
            // MODIFIED: scope.$apply( show );
            show();
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

var cloudmanAdminModule = angular.module('cloudman', ['ui', 'ui.bootstrap', 'ui.bootstrap.dialog', 'ui.bootstrap.alert', 'cloudman.popover', 'cloudman.popover.fstemplate']);

cloudmanAdminModule.service('cmAlertService', function ($timeout) {
		var alert_counter = 0; 
		var alerts = [];
		
		var getAlerts = function() {
	    	return alerts;
		};
		
		var addAlert = function(message, type, timeout) {
			var alert = {id: alert_counter++, msg: message, type: type};			
			alerts.push(alert);
			if (!timeout)
				timeout = 60000;
			$timeout(function() { closeAlert(alert); }, timeout, true);
			return alert;
		};
		
		var closeAlert = function(alert) {
			var result = $.grep(alerts, function(e){ return e.id == alert.id; });
			if (result.length == 1) {
				var index = alerts.indexOf(result[0])
				alerts.splice(index, 1);
			}
		}
		
		// Public interface
		return {
			getAlerts: getAlerts,
            addAlert: addAlert,
            closeAlert: closeAlert
        };
	});
	
cloudmanAdminModule.controller('cmAlertController', ['$scope', 'cmAlertService', function ($scope, cmAlertService) {
		
		$scope.getAlerts = function () {
            return cmAlertService.getAlerts();
        };
        
        $scope.closeAlert = function (alert) {
            cmAlertService.closeAlert(alert);
        };
	}]);

cloudmanAdminModule.service('cmAdminDataService', function ($http, $timeout, cmAlertService) {
		// Server Status Cache
		var _services = [];
		var _file_systems = [];
		var _galaxy_rev;
		var _galaxy_admins;
		var _master_is_exec_host;
		var _galaxy_dns;
		
		// Local vars
		var _admin_data_timeout_id;
		
		var poll_admin_data = function() {
	        // Poll cloudman status
	        $http.get(get_cloudman_system_status_url).success(function (data) {
				_services = data.applications;
				_file_systems = data.file_systems;				
				_galaxy_rev = data.galaxy_rev;
				_galaxy_admins = data.galaxy_admins;
				_master_is_exec_host = data.master_is_exec_host;
				_galaxy_dns = data.galaxy_dns;
				var messages = data.messages;				
				_processSystemMessages(messages);
    		});
			resumeDataService();
	    };
	    
	    var resumeDataService = function () {
	    	$timeout.cancel(_admin_data_timeout_id); // cancel any existing timers
			_admin_data_timeout_id = $timeout(poll_admin_data, 10000, true);
		};
		
		var _processSystemMessages = function(messages) {
			for (msg in messages) {
				var txt = msg + ' (' + msg.added_at.split('.')[0] + ')';
				// Mark CRITICAL msgs & show additional help text
            	if (msg.level == '50') {
                	txt = '[CRITICAL] ' + txt;
                	cmAlertService.add(msg, "error");
                }
                else
                	cmAlertService.add(msg, "info");
             }
		};
		
		// Execute first time fetch
		poll_admin_data();
	    
	    // Public interface
		return {
            getAllFilesystems: function () {
                return _file_systems;
            },
            getAllServices: function () {
                return _services;
            },
            pauseDataService: function () {
                $timeout.cancel(_admin_data_timeout_id);
            },
            resumeDataService: resumeDataService,
            getGalaxyRev: function () {
                return _galaxy_rev;
            },
            getGalaxyAdmins: function () {
                return _galaxy_admins;
            },
            getGalaxyDns: function () {
                return _galaxy_dns;
            },
            getMasterIsExecHost: function () {
                return _master_is_exec_host;
            }
        };
	});
	
cloudmanAdminModule.controller('ServiceController', ['$scope', '$http', 'cmAdminDataService', 'cmAlertService', function ($scope, $http, cmAdminDataService, cmAlertService) {
		
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
		
		$scope.performServiceAction = function($event, action) {
			// TODO: Ugly hack to let some stuff passthrough. Fix.
			if (action.action_url.indexOf("log") > 0)
				return;
				
			$event.preventDefault();
			var alert = cmAlertService.addAlert("Action Initiated", "info", 3000);
			$http.get(action.action_url).success(function (response) {
				cmAlertService.closeAlert(alert);
	        	cmAlertService.addAlert(response, "info");
	        });			
		}	
	}]);

cloudmanAdminModule.controller('FileSystemController', ['$scope', '$http', '$dialog', 'cmAdminDataService', function ($scope, $http, $dialog, cmAdminDataService) {
		var _opts =  {
			    backdrop: true,
			    keyboard: true,
			    backdropClick: true,
			    modalFade: true,
			  };
			  
		$scope.getFileSystems = function () {
            return cmAdminDataService.getAllFilesystems();
        };
		
		// TODO: Dom manipulation in controller. Fix.
		$scope.toggleDetailView = function($event, fs) {
			if (fs._showing_detail_popup) {				
				$('#fs-details-popover-' + fs.name).click();
				cmAdminDataService.resumeDataService();
			}		
			else {
				cmAdminDataService.pauseDataService(); // Don't let updates reset file state
				var test = $('#fs-details-popover-' + fs.name).click();
			}
			fs._showing_detail_popup = !fs._showing_detail_popup;
		}		
		
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


cloudmanAdminModule.controller('AddFSController', ['$scope', '$http', 'cmAdminDataService', function ($scope, $http, cmAdminDataService) {
		
		$scope.is_adding_fs = false;
		$scope.selected_device = "";
		
		$scope.showAddNewFSForm = function () {
            $scope.is_adding_fs = true;
        };
        
        $scope.hideAddNewFSForm = function () {
            $scope.is_adding_fs = false;
            $scope.selected_device = "";
        };        
	}]);


cloudmanAdminModule.controller('GalaxyController', ['$scope', '$http', 'cmAdminDataService', 'cmAlertService', function ($scope, $http, cmAdminDataService, cmAlertService) {
		
		$scope.getGalaxyAdmins = function() {
			return cmAdminDataService.getGalaxyAdmins();
		}
		
		$scope.getGalaxyRev = function() {
			return cmAdminDataService.getGalaxyRev();
		}
		
		$scope.getGalaxyDns = function() {
			return cmAdminDataService.getGalaxyDns();
		}
		
		$scope.addAdminUsers = function($event) {
			var alert = cmAlertService.addAlert("Action Initiated", "info", 3000);
			$('#galaxy_admin_users_form').ajaxForm({
		        type: 'POST',
		        dataType: 'html',
		        error: function(response) {
		        	cmAlertService.closeAlert(alert);
		        	cmAlertService.addAlert(response.responseText, "error");
		        },
		        success: function(response) {
		        	cmAlertService.closeAlert(alert);
		        	cmAlertService.addAlert(response, "info");
		        }
		    });
		}
		
		$scope.updateRespositoryUrl = function($event) {
			var alert = cmAlertService.addAlert("Action Initiated", "info", 3000);
			$('#galaxy_repository_form').ajaxForm({
		        type: 'POST',
		        dataType: 'html',
		        error: function(response) {
		        	cmAlertService.closeAlert(alert);
		        	cmAlertService.addAlert(response.responseText, "error");
		        },
		        success: function(response) {
		        	cmAlertService.closeAlert(alert);
		        	cmAlertService.addAlert(response, "info");
		        }
		    });
		}
	}]);
	

cloudmanAdminModule.controller('SystemController', ['$scope', '$http', '$dialog', 'cmAdminDataService', 'cmAlertService', function ($scope, $http, $dialog, cmAdminDataService, cmAlertService) {
		
		$scope.getMasterIsExecHost = function() {
			cmAdminDataService.getMasterIsExecHost();
		}
		
		$scope.showUserData = function() {
			_opts.template = $("#fs-resize-dialog-template").html(),
			_opts.controller = 'FSResizeDialogController';
			_opts.resolve = {fs: fs};

			var d = $dialog.dialog(_opts);
	    	d.open().then(function(result) {
		    });
		}
		
		$scope.toggleMasterAsExecHost = function($event, url) {
			$event.preventDefault();
			var alert = cmAlertService.addAlert("Action Initiated", "info", 3000);
			$http.get(url).success(function (response) {
				cmAlertService.closeAlert(alert);
	        	cmAlertService.addAlert(response, "info");
	        });			
		}
		
		$scope.showUserData = function($event, url) {
			$event.preventDefault();
			
			var alert = cmAlertService.addAlert("Fetching user data...", "info", 3000);
			$http.get(url).success(function (response) {
				cmAlertService.closeAlert(alert);
	        	var title = 'User Data';
	        	var btns = [{result:'ok', label: 'OK', cssClass: 'btn-primary'}];
	        	
	            var ud_html = "<pre>" + JSON.stringify(response, null, 2) + "</pre>";

    			$dialog.messageBox(title, ud_html, btns)
			      .open()
			      .then(function(result){
			    });
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


function AssignedServiceController($scope, $element, $http, cmAlertService, cmAdminDataService) {
  $scope.is_editing = false;
  $scope.master = $scope.svc
  $scope.record = angular.copy($scope.master);

  $scope.save = function(record, url) {
  
  	var dto = { svc_name: record.svc_name,
    			requirements: record.requirements
	};  
	$http({
		method: 'POST',
        url: url,
        data: JSON.stringify(dto),
        headers: {'Content-Type': 'application/json'}
	}).success(function(data, status) {
    	cmAlertService.addAlert(data, "info");
	}).error(function(data, status) {
    	cmAlertService.addAlert(data, "error");
	}); 
	
    $scope.master = angular.copy(record);
    $scope.is_editing = false;
    cmAdminDataService.resumeDataService();
    return false;
  };
 
  $scope.isUnchanged = function(record) {
    return angular.equals(record, $scope.master);
  };
  
  $scope.beginEdit = function(record) {
    $scope.is_editing = true;
    $scope.record = angular.copy($scope.master);
    cmAdminDataService.pauseDataService();
  };
  
  $scope.cancelEdit = function(record) {
  	$scope.record = angular.copy($scope.master);
    $scope.is_editing = false;
    cmAdminDataService.resumeDataService();
  };
  
  $scope.isReassignable = function(record) {
  	for (req in record.requirements) {
  		if (req.type == 'FILE_SYSTEM')
  			return true;
    }
  	return false;
  };
}