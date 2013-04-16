var cloudmanIndexModule = angular.module('cloudman.index', ['cloudman.base', 'ui', 'ui.bootstrap', 'ui.bootstrap.dialog', 'ui.bootstrap.alert', 'cloudman.popover', 'cloudman.popover.fstemplate']);

cloudmanIndexModule.service('cmIndexDataService', function ($http, $timeout, cmAlertService) {
		// Server Status Cache
		var _cloudman_status;
		var _log_data = [];
		var _log_cursor = 0;
		var _messages;

		// Local vars
		var _data_timeout_id;
		var _refresh_in_progress = false;
		
		var poll_data = function() {
	        // Poll cloudman status
			_refresh_in_progress = true;
	        $http.get(get_cloudman_index_update_url, {
	            params: {l_log: _log_cursor}
	         }).success(function (data) {
	            _refresh_in_progress = false;
				_cloudman_status = data.ui_update_data;
				_log_data = _log_data.concat(data.log_update_data.log_messages);
				if (_log_data.length > 200) {
					_log_data.splice(0, _log_data.length-200, "The log has been truncated to keep up performance.  The <a href='/cloud/log/'>full log is available here</a>.");
				}
				
				_log_cursor = data.log_update_data.log_cursor;
				var messages = data.messages;				
				_processSystemMessages(messages);
				cmAlertService.setClusterStatus(_cloudman_status.cluster_status);
    		}).error(function (data) {
    		    _refresh_in_progress = false;
    		});
			resumeDataService();
	    };

	    var resumeDataService = function () {
	    	$timeout.cancel(_data_timeout_id); // cancel any existing timers
			_data_timeout_id = $timeout(poll_data, 5000, true);
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
		poll_data();

	    // Public interface
		return {
            pauseDataService: function () {
                $timeout.cancel(_data_timeout_id);
            },
            resumeDataService: resumeDataService,
            getGalaxyRev: function () {
                return _galaxy_rev;
            },
            getCloudmanStatus: function () {
                return _cloudman_status;
            },
            getLogData: function () {
                return _log_data;
            },
            isRefreshInProgress: function () {
                return _refresh_in_progress;
            }
        };
	});

// Uses flot charts: http://www.flotcharts.org/
cloudmanIndexModule.directive('chart', function(){
    return{
        restrict: 'E',
        link: function(scope, elem, attrs) {
            var chart = null;
            var opts = {
				grid: {
					borderWidth: 1,
					minBorderMargin: 10,
					labelMargin: 5,
					hoverable: true,
					clickable: true,
					backgroundColor: {
						colors: ["#fff", "#e4f4f4"]
					},
					margin: {
						top: 8,
						bottom: 8,
						left: 8
					},
				},
				xaxis: {
					mode: "time",
					minTickSize: [30, "second"],
					timeformat: "%H:%M:%S",
				},
				yaxis: {
					min: 0,
					max: 100
				},
				legend: {
					show: true,
					container: $(attrs.legendLocation),
					noColumns: 2
				}
			};
            
            scope.$watch(attrs.ngModel, function(data) {
                if (!chart){
                    chart = $.plot(elem, data , opts);
                    elem.show();
                } else {
                    chart.setData(data);
                    chart.setupGrid();
                    chart.draw();
                }
            }, true);
        }
    };
});

cloudmanIndexModule.controller('cmLoadGraphController', ['$scope', '$http', '$timeout', '$dialog', 'cmIndexDataService', 'cmAlertService', function ($scope, $http, $timeout, $dialog, cmIndexDataService, cmAlertService) {

    	$scope.nodes = [];

    	var _data_timeout_id;
    	var counter = 0;
    	
    	$scope.get_node_fs_status = function(node) {
    		var inst = node.instance;
    	    if ((inst.nfs_data == "1") && (inst.nfs_tools == "1") && (inst.nfs_indices=="1") && (inst.nfs_sge=="1")) {
    	        return "allgood";
    	    }
    	    if ((inst.nfs_data == "0") && (inst.nfs_tools == "0") && (inst.nfs_indices=="0") && (inst.nfs_sge=="0")) {
    	        return "warning";
    	    }
    	    if ((inst.nfs_data == "-1") && (inst.nfs_tools == "-1") && (inst.nfs_indices=="-1") && (inst.nfs_sge=="-1")) {
    	        return "error";
    	    }
    	    return "unknown";
    	}
    	
    	$scope.get_permission_status = function(node) {
    		var inst = node.instance;
    		switch (parseInt(inst.get_cert))
    		{
    			case 1: return "allgood";
    			case 0: return "warning";
    			case -1: return "error";
    			default: return "unknown";
    		}
    	}
    	
    	$scope.get_scheduler_status = function(node) {
    		var inst = node.instance;
    		switch (parseInt(inst.sge_started))
    		{
    			case 1: return "allgood";
    			case 0: return "warning";
    			case -1: return "error";
    			default: return "unknown";
    		}
    	}
    	
    	$scope.rebootInstance = function(node, reboot_url) {
			var title = 'Reboot instance?';
        	var btns = [{result:'confirm', label: 'Confirm', cssClass: 'btn btn-danger'},
        	            {result:'cancel', label: 'Cancel', cssClass: 'btn'}];

            var ud_html = "ID: " + node.instance.id + "<br />IP: " + node.instance.public_ip ;

			$dialog.messageBox(title, ud_html, btns)
		      .open()
		      .then(function(result) {
		    	  if (result == 'confirm') {
		    		 $http.get(reboot_url, {
		  	            params: { instanceid: node.instance.id }
		  	         }).success(function (data) {
		  	        	 cmAlertService.addAlert("Node reboot initiated...", "info");
		      		 });
		      		 return true;
		    	  }
		    });
    	}
    	
    	$scope.terminateInstance = function(node, terminate_url) {
			var title = 'Terminate instance?';
        	var btns = [{result:'confirm', label: 'Confirm', cssClass: 'btn btn-danger'},
        	            {result:'cancel', label: 'Cancel', cssClass: 'btn'}];

            var ud_html = "ID: " + node.instance.id + "<br />IP: " + node.instance.public_ip ;

			$dialog.messageBox(title, ud_html, btns)
		      .open()
		      .then(function(result) {
		    	  if (result == 'confirm') {
		    		 $http.get(terminate_url, {
		  	            params: { instanceid: node.instance.id }
		  	         }).success(function (data) {
		  	        	 cmAlertService.addAlert("Node terminate initiated...", "info");
		      		 });
		      		 return true;
		    	  }
		    });
    	}
    	
    	function getAliveTime(node) {
            var time_string = "";
            var time = Math.floor(node.time_in_state);
            var hours = Math.floor(time / 3600);

            if (hours >= 24) {
                    // More than a day
                    var days = Math.floor(hours / 24);
                    time_string = days + " day";
                    if (days > 1) {
                            time_string += "s";
                    }
            } else if (hours >= 168) {
                    // More than a week
                    var weeks = Math.floor(hours / 168);
                    time_string = weeks + " week";
                    if (weeks > 1) {
                            time_string += "s";
                    }
            } else {
                    // Less than a day
                    time -= (hours * 60 * 60);
                    var minutes = Math.floor(time/60);
                    time -= (minutes * 60);
                    var seconds = Math.floor(time);
                    time_string =  ("0" + hours).slice(-2) + ":" + ("0" + minutes).slice(-2) + ":" + ("0" + seconds).slice(-2);
            }
            return time_string;
    	}

    	
    	var poll_performance_data = function() {
	        // Poll cloudman status
	        $http.get(get_cloudman_status_update_url).success(function (data) {
	        	var remove_list = [];
	        	for (node_index in $scope.nodes) {
	        		var node = $scope.nodes[node_index];
	        		var node_found = false;
	        		// check whether currently known nodes are in the list of newly returned server nodes
	        		for (instance_index in data.instances) {
	        			var instance = data.instances[instance_index];
	        			if (node.id == instance.id) {
	        				// Yes, it's a known node, so just plot the new load value 
	        				node.instance = instance;
	        				addNewLoadValue(node, instance);
	        				node_found = true;
	        				// mark the server returned node as a known node
	        				instance.already_added = true;
	        			}
	        		}
	        		// Node no longer exists on server, Therefore, mark for removal
	        		if (!node_found)
	        			node.should_remove = true;
	        	}
	        	
	        	// Filter all nodes marked for removal
	        	$scope.nodes = $scope.nodes.filter(function(item) { return !item.should_remove });
	        	// Filter all newly added nodes on server
	        	var list_to_add = data.instances.filter(function(item) { return !item.already_added });
	        	
	        	// Add any newly added nodes to our currently known node list
	        	for (instance_index in list_to_add) {
	        		var instance = list_to_add[instance_index];
	        		var node = { id : instance.id,
	        					 instance: instance,
	        					 system_load : [ {  label: "1 min average&nbsp;&nbsp;",
	        						 				data: [], // 1 minute average series
		        									lines: {
		        										fill: true,
		        										show: true
													},
													color: 'lightblue',
													points: {
														show: true
													}
        				   						 },
        				   						 {  label: "5 min average",
        				   							data: [], // 5 minute average series
        				   							color: 'DeepSkyBlue',
 		        									lines: {
 		        										fill: false
 													}
         				   						 }
        				   						 ]
	        				   }
	        		$scope.nodes.push(node);
	        		// Also plot the load values
	        		addNewLoadValue(node, instance);
	        	}
    		});
	        resumePerfDataService();
	    };
	    
	    var resumePerfDataService = function () {
	    	$timeout.cancel(_data_timeout_id); // cancel any existing timers
			_data_timeout_id = $timeout(poll_performance_data, 5000, true);
		};
		
		var pausePerfDataService = function () {
            $timeout.cancel(_data_timeout_id);
		}

		// Execute first time fetch
		poll_performance_data();
		
		//----------------------------------------------------------------------------------
	    // Support functions follow
		//----------------------------------------------------------------------------------
    	function addNewLoadValue(node, instance) {
    		var load = instance.ld;
			var vals = load.split(' ');
			var time = new Date().getTime();
			var point_1_min_avg = [time, vals.pop()*100];
			var point_5_min_avg = [time, vals.pop()*100];
			var points = [point_1_min_avg, point_5_min_avg]
			var frame_rate = 15;
    		var max_series_length = 15;
	        interpolatedAddPointList(node['system_load'], points, frame_rate, max_series_length)
    	}
	    
	    function interpolatedAddPointList(series_list, points_list, frame_rate, max_series_length) {
	    	var closureList = []
		    for (var index in series_list) {
		    	closure = interpolatedAddPoint(series_list[index].data, points_list[index], frame_rate, max_series_length)
		    	if (closure)
		    		closureList.push(closure)
		    }			
		    function animateSeries() {
		    	pausePerfDataService(); // Pause data while animation is in progress
		    	var newList = [];
		    	for (var closure_index in closureList) {
		    		var result = closureList[closure_index]();
		    		if (result)
		    			newList.push(result)
		    	}
		    	
		    	closureList = newList;
		    	if (closureList && closureList.length > 0) {
		    		$timeout(animateSeries, 1000.00 / frame_rate, true);
		    	}
		    	else {
		    		resumePerfDataService();
		    	}
	    	}
		    animateSeries();
	    }
	    
	    //----------------------------------------------------------------------------------
	    // This function adds a new point to a series, but does so incrementally, at the
	    // specified frame_rate, by interpolating the values between its previous point and
	    // the new point. This can be used to create an animated effect in flot charts (or other charts),
	    // which do not support animation during point addition natively.
	    //
	    // Supports an optional argument max_series_length, which, if defined,
	    // limits the series length to this value, and also does an interpolated remove
	    // of the first point, creating a continuous, sliding animation effect.
	    //
	    // This function is self-contained, and works incrementally on each call. Returns
	    // void when the starting point has been interpolated till the end point. Returns
	    // a closure otherwise, which can be invoked via a timer to create the animation effect.
	    //----------------------------------------------------------------------------------
	    function interpolatedAddPoint(series, point, frame_rate, max_series_length) {
	    	var animate_remove = typeof max_series_length !== 'undefined'
	    	frame_rate = typeof frame_rate !== 'undefined' ? frame_rate : 10.0;
	    
	    	if (series.length == 0) {
	    		series.push(point)
	    		return;
	    	}
	    	
	    	var from_point = series[series.length-1];
	    	var to_point = point;	    
	    
	    	var from_y = from_point[0]
	    	var to_y = to_point[0]
	    	var step_y = (to_y - from_y) / frame_rate
	    	
	    	var from_x = from_point[1]
	    	var to_x = to_point[1]
	    	var step_x = (to_x - from_x) / frame_rate
	    	
	    	series.push(from_point); // Push initial point (will be interpolated
	    							// till to_point)

			if (animate_remove && series.length >= max_series_length) {
				var remove_from_y = series[0][0]
			    var remove_to_y = series[1][0]
			    var remove_step_y = (remove_to_y - remove_from_y) / frame_rate
			    	
			    var remove_from_x = series[0][1]
			    var remove_to_x = series[1][1]
			    var remove_step_x = (remove_to_x - remove_from_x) / frame_rate
			}
	    	
	    	var add_counter = 0;
	    	var remove_counter = 0;
	    	
	    	var interpolateValues = function() {
	    	
	    		var animAdd = function() {
		    		if (add_counter > frame_rate) {
		    			series.pop(); // At end of animation, remove all interpolated values
		    			series.push(to_point); // Push last, accurate value, in case of rounding issues
		    			return false;
		    		}
		    		var new_point = [from_y, from_x];
		    		from_y += step_y;
		    		from_x += step_x;
		    		series.pop(); // Pop previous value
		    		series.push(new_point); // Push in new interpolated value towards the to_point
		    		add_counter++;
		    		return true;
		    	}
		    	
		    	var animRemove = function() {
		    		if (remove_counter >= frame_rate) {
		    			series.shift(); // Remove the interpolated element
		    			return;
		    		}
		    		remove_from_y += remove_step_y;
		    		remove_from_x += remove_step_x;
	    			var remove_point = [remove_from_y, remove_from_x];
		    		series.splice(0, 1, remove_point); // Remove first element, and insert interpolated element in its place
		    		remove_counter++;
		    	}
		    	
		    	if (animate_remove && series.length >= max_series_length) {
		    		animRemove();
		    	}
		    	if (!animAdd()) {
		    		return;
		    	}
		    	else
		    		return interpolateValues;
	    	}
	    	
	    	return interpolateValues;
	    }
	}]);

cloudmanIndexModule.controller('cmIndexMainActionsController', ['$scope', '$http', '$dialog', 'cmIndexDataService', 'cmAlertService', function ($scope, $http, $dialog, cmIndexDataService, cmAlertService) {
		
		 
		$scope.showInitialConfig = function() {
			if (initial_cluster_type === 'None') {
				var _opts = {
					backdropClick: false,
					templateUrl: 'partials/initial-config.html',
					controller: 'initialConfigController'
				};
				
				var d = $dialog.dialog(_opts);
					d.open().then(function(result) {
				});
			}
		}
		
		$scope.isRefreshInProgress = function() {
			return cmIndexDataService.isRefreshInProgress();
		}
		
		$scope.getCloudmanStatus = function() {
			return cmIndexDataService.getCloudmanStatus();
		}
		
		$scope.getGalaxyPath = function() {
			if ($scope.isGalaxyAccessible())
				return cmIndexDataService.getCloudmanStatus().dns;
			else
				return null;
		}
		
		$scope.closePopup = false;
	
        $scope.isGalaxyAccessible = function () {
        	var cmstatus = cmIndexDataService.getCloudmanStatus();
        	return cmstatus && cmstatus.dns != '#';
        }
        
        $scope.isAddNodeEnabled = function () {
        	var cmstatus = cmIndexDataService.getCloudmanStatus();
        	return cmstatus && cmstatus.autoscaling.use_autoscaling != true;
        }
        
        $scope.isRemoveNodeEnabled = function () {
        	var cmstatus = cmIndexDataService.getCloudmanStatus();
        	return cmstatus && cmstatus.autoscaling.use_autoscaling != true && cmstatus.instance_status.requested != 0;
        }
        
        $scope.handleFormClick = function($event) {
        	// Prevent the bootstrap popup from closing on clicks: 
        	// http://stackoverflow.com/questions/8110356/dropdown-with-a-form-inside-with-twitter-bootstrap
        	if (!$scope.closePopup) {
        		$scope.closePopup = false;
        		$event.stopPropagation();
        	}
        }
        
        $scope.addNodes = function($event) {
        	cmAlertService.addAlert("Adding new nodes", "info");
        	$('#add_instances_form').ajaxForm({
		        type: 'POST',
		        dataType: 'html',
		        error: function(response) {
		        	cmAlertService.addAlert(response.responseText, "error");
		        },
		        success: function(response) {
		        }
	    	});
        	$scope.closePopup = true;
        }
        
        $scope.removeNodes = function($event) {
        	cmAlertService.addAlert("Removing nodes", "info");
        	$('#remove_instances_form').ajaxForm({
		        type: 'POST',
		        dataType: 'html',
		        error: function(response) {
		        	cmAlertService.addAlert(response.responseText, "error");
		        },
		        success: function(response) {
		        }
	    	});
        	$scope.closePopup = true;
        }
        
		$scope.confirm_terminate = function($event) {
			var _opts = {
				templateUrl: 'partials/terminate-confirm.html',
				controller: 'terminateConfirmController'
			};

			var d = $dialog.dialog(_opts);
	    	d.open().then(function(result) {
		    });
		}
		
		$scope.configureAutoScaling = function($event) {
            cmIndexDataService.pauseDataService();
			var _opts = {
					templateUrl: 'partials/autoscaling-config.html',
					controller: 'autoscalingController'
			};

			var d = $dialog.dialog(_opts);
	    	d.open().then(function(result) {
	    	    cmIndexDataService.resumeDataService();
		    });
		}
		
        $scope.resize_fs = function($event) {
            var _opts =  { 
                templateUrl: 'partials/fs-resize-dialog-template.html',
                controller: 'FSResizeDialogController',
                resolve: {fs: function() { return null; } }            
            };

            var d = $dialog.dialog(_opts);
            d.open().then(function(result) {
            });
        }
        
        $scope.share_cluster = function($event) {
            var _opts =  { 
                templateUrl: 'partials/share_cluster_template.html',
                controller: 'shareClusterController',
                resolve: {fs: function() { return null; } }            
            };

            var d = $dialog.dialog(_opts);
            d.open().then(function(result) {
            });
        }
		

	}]);


function terminateConfirmController($scope, dialog, cmAlertService) {
	  
	  $scope.cancel = function($event, result) {
	  	$event.preventDefault();
	    dialog.close('cancel');
	  };
	  
	  $scope.confirm = function($event, result) {
		// TODO: DOM access in controller. Should be redone
		$('#form_terminate_confirm').ajaxForm({
	        type: 'POST',
	        dataType: 'html',
	        error: function(response) {
	        	cmAlertService.addAlert("An error occured while attempting to terminate the cluster.", "error");
	        },
	        success: function(response) {
	        	cmAlertService.addAlert("Cluster termination initiated...", "info");
	        }
	    });	  	
	    dialog.close('confirm');
	  };
}

function initialConfigController($scope, dialog, cmAlertService) {
	  
		$scope.isCollapsed = true;
	
		$scope.toggleOptions = function($event) {
		  	$event.preventDefault();
		  	$scope.isCollapsed = !$scope.isCollapsed;
		};
	  
	    $scope.cancel = function($event, result) {
		  	$event.preventDefault();
		    dialog.close('cancel');
		  };
	  
		$scope.confirm = function($event, result) {
			// TODO: DOM access in controller. Should be redone
			$('#init_cluster_form').ajaxForm({
		        type: 'POST',
		        dataType: 'html',
		        error: function(response) {
		        	cmAlertService.addAlert("An error occured while trying to initialise cluster", "error");
		        },
		        success: function(response) {
		        	cmAlertService.addAlert("Cluster initialisation started...", "info");
		        	dialog.close('confirm');
		        }
		    });
	    };
}

function autoscalingController($scope, dialog, cmAlertService, cmIndexDataService) {

	$scope.isCollapsed = true;
	
	$scope.isAutoScalingEnabled = function() {
		return cmIndexDataService.getCloudmanStatus().autoscaling.use_autoscaling;
	}
	
	$scope.getAutoscalingSettings = function() {
		return cmIndexDataService.getCloudmanStatus().autoscaling;
	}
	
	$scope.toggleOptions = function($event) {
	  	$event.preventDefault();
	  	$scope.isCollapsed = !$scope.isCollapsed;
	};
	
    $scope.cancel = function($event, result) {
	  	$event.preventDefault();
	    dialog.close('cancel');
	};
	  
	$scope.toggleAutoscaling = function($event, result) {
		cmAlertService.addAlert("Configuring autoscaling...", "info");
		// TODO: DOM access in controller. Should be redone
		$('#form_autoscaling_config').ajaxForm({
	        type: 'POST',
	        dataType: 'html',
	        error: function(response) {
	        	cmAlertService.addAlert("An error occured while configuring autoscaling.", "error");
	        },
	        success: function(response) {
	        }
	    });	  	
	    dialog.close('confirm');
	};
}


function shareClusterController($scope, $http, $dialog, dialog, cmAlertService, cmIndexDataService) {

    $scope.isCollapsed = true;
    $scope.isRetrieving = true;
    $scope.shared_instances = [];
    
    $scope.refreshSharedInstances = function() {
        $http.get(get_shared_instances_url).success(function (data) {
            $scope.shared_instances = data.shared_instances;
            $scope.isRetrieving = false;
        });
    }
    
    $scope.refreshSharedInstances();
    
    $scope.toggleCollapsed = function($event) {
        $event.preventDefault();
        $scope.isCollapsed = !$scope.isCollapsed;
    };
    
    $scope.cancel = function($event, result) {
        $event.preventDefault();
        dialog.close('cancel');
    };
    
    $scope.confirm = function($event, result) {
        $event.preventDefault();
        // TODO: DOM access in controller. Should be redone
        $('#share_a_cluster_form').ajaxForm({
            type: 'POST',
            dataType: 'json',
            error: function(response) {
                $scope.refreshSharedInstances();
            },
            success: function(response) {
                $scope.refreshSharedInstances();
            }
        });
        dialog.close('confirm');
    };
    
    
    $scope.deleteShare = function($event, instance) {
        $event.preventDefault();
        var title = 'Delete shared cluster instance?';
        var btns = [{result:'confirm', label: 'Confirm', cssClass: 'btn btn-danger'},
                    {result:'cancel', label: 'Cancel', cssClass: 'btn'}];

        var ud_html = "<div>Are you sure you want to delete shared cluster instance under <i>" + instance.bucket +
                      "</i> and the corresponding snapshot with ID <i>" + instance.snap + "</i>?<br/>" +
                      "<p>This action cannot be undone.</p></div>";

        $dialog.messageBox(title, ud_html, btns)
          .open()
          .then(function(result) {
              if (result == 'confirm') {
                 $http.get(delete_shared_instances_url, {
                    params: { shared_instance_folder: instance.bucket, snap_id: instance.snap }
                 }).success(function (data) {
                     $scope.refreshSharedInstances();
                 });
                 return true;
              }
        });
    };
}

cloudmanIndexModule.controller('cmClusterLogController', ['$scope', '$http', '$dialog', 'cmIndexDataService', 'cmAlertService', function ($scope, $http, $dialog, cmIndexDataService, cmAlertService) {

	$scope.getLogData = function() {
		return cmIndexDataService.getLogData();
	}
}]);

