var cloudmanBaseModule = angular.module('cloudman.base', []);

cloudmanBaseModule.service('cmAlertService', function ($timeout) {
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
	
cloudmanBaseModule.controller('cmAlertController', ['$scope', 'cmAlertService', function ($scope, cmAlertService) {
		
		$scope.getAlerts = function () {
            return cmAlertService.getAlerts();
        };
        
        $scope.closeAlert = function (alert) {
            cmAlertService.closeAlert(alert);
        };
	}]);
	
	
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