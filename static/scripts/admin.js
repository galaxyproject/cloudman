var cloudmanAdminModule = angular.module('cloudman.admin', ['cloudman.base', 'ui', 'ui.bootstrap', 'ui.bootstrap.dialog', 'ui.bootstrap.alert', 'cloudman.popover', 'cloudman.popover.fstemplate']);

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
		var _refresh_in_progress = false;
		
		var poll_admin_data = function() {
	        // Poll cloudman status
	        _refresh_in_progress = true;
	        $http.get(get_cloudman_system_status_url).success(function (data) {
	        	_refresh_in_progress = false;
				_services = data.applications;
				_file_systems = data.file_systems;				
				_galaxy_rev = data.galaxy_rev;
				_galaxy_admins = data.galaxy_admins;
				_master_is_exec_host = data.master_is_exec_host;
				_galaxy_dns = data.galaxy_dns;
				var messages = data.messages;				
				_processSystemMessages(messages);
				cmAlertService.setClusterStatus(data.cluster_status);
    		}).error(function (data) {
    		    _refresh_in_progress = false;
    		});
			resumeDataService();
	    };

	    var resumeDataService = function () {
	    	$timeout.cancel(_admin_data_timeout_id); // cancel any existing timers
			_admin_data_timeout_id = $timeout(poll_admin_data, 5000, true);
		};

		var _processSystemMessages = function(messages) {
			for (msg in messages) {
				var txt = msg + ' (' + msg.added_at.split('.')[0] + ')';
				// Mark CRITICAL msgs & show additional help text
            	if (msg.level == '50') {
                	txt = '[CRITICAL] ' + txt;
                	cmAlertService.addAlert(msg, "error");
                }
                else
                	cmAlertService.addAlert(msg, "info");
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
            },
            isRefreshInProgress: function () {
                return _refresh_in_progress;
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
        
        $scope.isRefreshInProgress = function () {
            return cmAdminDataService.isRefreshInProgress();
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

				//$('#service_row_' + service_row).animate({backgroundColor: 'transparent'}, "fast");
				//$('#service_detail_row_' + service_row).animate({backgroundColor: 'transparent'}, "fast");
			}

			// Show newly selected row
			if ($scope._visibility_flags[service]) {
				//$('#service_row_' + service).animate({backgroundColor: 'transparent'}, "slow");
				//$('#service_detail_row_' + service).animate({backgroundColor: 'transparent'}, "slow");
			}
			else {
				//$('#service_row_' + service).animate({backgroundColor: '#FEF1B5'}, "fast");
				//$('#service_detail_row_' + service).animate({backgroundColor: '#FEF1B5'}, "fast");
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
			var _opts =  { 
				templateUrl: 'partials/fs-delete-dialog-template.html',
				controller: 'FSRemoveDialogController',
				resolve: {fs: function() { return fs } }			
			};

			var d = $dialog.dialog(_opts);
	    	d.open().then(function(result) {
		    });
		}		

		$scope.persist_fs = function($event, fs) {
			var _opts =  { 
				templateUrl: 'partials/fs-persist-dialog-template.html',
				controller: 'FSPersistDialogController',
				resolve: {fs: function() { return fs } }			
			};

			var d = $dialog.dialog(_opts);
	    	d.open().then(function(result) {
		    });
		}		

		$scope.resize_fs = function($event, fs) {
			var _opts =  { 
				templateUrl: 'partials/fs-resize-dialog-template.html',
				controller: 'FSResizeDialogController',
				resolve: {fs: function() { return fs } }			
			};

			var d = $dialog.dialog(_opts);
	    	d.open().then(function(result) {
		    });
		}		
	}]);


cloudmanAdminModule.controller('AddFSController', ['$scope', '$http', 'cmAdminDataService', 'cmAlertService', function ($scope, $http, cmAdminDataService, cmAlertService) {

		$scope.is_adding_fs = false;
		$scope.selected_device = "";

		$scope.showAddNewFSForm = function () {
            $scope.is_adding_fs = true;
        }

        $scope.hideAddNewFSForm = function () {
            $scope.is_adding_fs = false;
            $scope.selected_device = "";
        }

        $scope.addNewFileSystem = function ($event, url) {
            $http({
                method: 'POST',
                url: url,
                // TODO: DOM access in controller. Should be redone
                data: $('#form_add_filesystem').serialize(),
                headers: {'Content-Type': 'application/x-www-form-urlencoded'}
            }).success(function(data, status) {
                cmAlertService.addAlert(data, "info");
            }).error(function(data, status) {
                cmAlertService.addAlert(data, "error");
            }); 
	    	$scope.hideAddNewFSForm();
        }
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

		$scope.executeAction = function($event, url) {
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
  	if (record.status == 'Completed' || record.status == 'Starting')
  		return false;
  	for (req in record.requirements) {
  		if (record.requirements[req].type == 'FILE_SYSTEM')
  			return true;
    }
  	return false;
  };
}