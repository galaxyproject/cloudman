var cloudmanIndexModule = angular.module('cloudman.index', ['cloudman.base', 'ui', 'ui.bootstrap', 'ui.bootstrap.dialog', 'ui.bootstrap.alert', 'cloudman.popover', 'cloudman.popover.fstemplate']);

cloudmanIndexModule.service('cmIndexDataService', function ($http, $timeout, cmAlertService) {
		// Server Status Cache
		var _cloudman_status;
		var _log_update_data;
		var _messages;

		// Local vars
		var _data_timeout_id;

		var poll_data = function() {
	        // Poll cloudman status
	        $http.get(get_cloudman_index_update_url).success(function (data) {
				_cloudman_status = data.ui_update_data;
				_log_update_data = data.log_update_data;
				var messages = data.messages;				
				_processSystemMessages(messages);
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
                	cmAlertService.add(msg, "error");
                }
                else
                	cmAlertService.add(msg, "info");
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
					minBorderMargin: 20,
					labelMargin: 10,
					backgroundColor: {
						colors: ["#fff", "#e4f4f4"]
					},
					margin: {
						top: 8,
						bottom: 20,
						left: 20
					},
					markings: function(axes) {
						var markings = [];
						var xaxis = axes.xaxis;
						for (var x = Math.floor(xaxis.min); x < xaxis.max; x += xaxis.tickSize * 2) {
							markings.push({ xaxis: { from: x, to: x + xaxis.tickSize }, color: "rgba(232, 232, 255, 0.2)" });
						}
						return markings;
					}
				},
				xaxis: {
					tickFormatter: function() {
						return "";
					}
				},
				yaxis: {
					min: 0,
					max: 110
				},
				legend: {
					show: true
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

cloudmanIndexModule.controller('cmIndexStatusController', ['$scope', '$http', '$timeout', 'cmIndexDataService', 'cmAlertService', function ($scope, $http, $timeout, cmIndexDataService, cmAlertService) {

		var series1 = []
        var graphData = [ { data: series1,
        					lines: {
								fill: true
							}
        				   } ];
    
    	$scope.data = graphData;
    	$scope.nodes = [];
    	
    	var _data_timeout_id;
    	var counter = 0;
    	
    	function addNewLoadValue(node, instance) {
    		var load = instance.ld;
			var vals = load.split(' ');
			var point = [counter++, vals.pop()*100];
			var frame_rate = 15;
    		var max_series_length = 15;
	        interpolatedAdd(node['system_load'][0].data, point, frame_rate, max_series_length)
    	}
    
    	var poll_performance_data = function() {
	        // Poll cloudman status
	        $http.get(get_cloudma_status_update_url).success(function (data) {
	        	var remove_list = [];
	        	for (node_index in $scope.nodes) {
	        		var node = $scope.nodes[node_index];
	        		var node_found = false;
	        		for (instance_index in data.instances) {
	        			var instance = data.instances[instance_index];
	        			if (node.public_ip == instance.public_ip) {
	        				addNewLoadValue(node, instance);
	        				node_found = true;
	        				instance.already_added = true;
	        			}
	        		}
	        		if (!node_found)
	        			node.should_remove = true;
	        	}
	        	
	        	$scope.nodes = $scope.nodes.filter(function(item) { return !item.should_remove });
	        	var list_to_add = data.instances.filter(function(item) { return !item.already_added });
	        	
	        	for (instance_index in list_to_add) {
	        		var instance = list_to_add[instance_index];
	        		var node = { public_ip : instance.public_ip,
	        					 system_load : [ { data: [],
		        									lines: {
													fill: true
													}
        				   						 }]
	        				   }
	        		$scope.nodes.push(node);
	        		addNewLoadValue(node, instance);
	        	}
    		});
			resumeDataService();
	    };
	    
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
	    // This function is self-contained, except for a dependency on $timeout. The $timeout
	    // can be replaced with window.timeout if not angular js.
	    //----------------------------------------------------------------------------------
	    function interpolatedAdd(series, point, frame_rate, max_series_length) {
	    	var animate_remove = typeof max_series_length !== 'undefined'
	    	frame_rate = typeof frame_rate !== 'undefined' ? frame_rate : 10.0;
	    
	    	if (series.length == 0) {
	    		series.push(point)
	    		return;
	    	}
	    	
	    	from_point = series[series.length-1];
	    	to_point = point;	    
	    
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
	    		
	    		$timeout(interpolateValues, 1000.00 / frame_rate, true);
	    	}
	    	
	    	$timeout(interpolateValues, 0, true);
	    }

	    var resumeDataService = function () {
	    	$timeout.cancel(_data_timeout_id); // cancel any existing timers
			_data_timeout_id = $timeout(poll_performance_data, 3000, true);
		};

		// Execute first time fetch
		poll_performance_data();
	}]);

cloudmanIndexModule.controller('cmIndexMainActionsController', ['$scope', '$http', 'cmIndexDataService', 'cmAlertService', function ($scope, $http, cmIndexDataService, cmAlertService) {
		
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
        	$event.stopPropagation();
        }
        
        $scope.addNodes = function($event) {
        	$event.preventDefault();
        	cmIndexDataService.pauseDataService();
        	$('#add_instances_form').ajaxForm({
		        type: 'POST',
		        dataType: 'html',
		        error: function(response) {
		        	cmIndexDataService.resumeDataService();
		        	cmAlertService.addAlert(response.responseText, "error");
		        },
		        success: function(response) {
		        	cmIndexDataService.resumeDataService();
		        	cmAlertService.addAlert(response, "info");
		        }
	    	});
        }
        
        $scope.removeNodes = function($event) {
        	$event.preventDefault();
        	cmIndexDataService.pauseDataService();
        	$('#remove_instances_form').ajaxForm({
		        type: 'POST',
		        dataType: 'html',
		        error: function(response) {
		        	cmIndexDataService.resumeDataService();
		        	cmAlertService.addAlert(response.responseText, "error");
		        },
		        success: function(response) {
		        	cmIndexDataService.resumeDataService();
		        	cmAlertService.addAlert(response, "info");
		        }
	    	});
        }

	}]);