<%
from routes import url_for
%>

## Set to HTML5
<!DOCTYPE html>

## Default title
<%def name="title()">CloudMan</%def>

## Default stylesheets
<%def name="stylesheets()">
<!--  <link href="${h.url_for('/static/style/masthead.css')}" rel="stylesheet" type="text/css" /> -->
  <link href="${h.url_for('/static/bootstrap/css/bootstrap.min.css')}" rel="stylesheet" type="text/css" />
  <link href="${h.url_for('/static/style/base.css')}" rel="stylesheet" type="text/css" />
</%def>

## Default javascripts
<%def name="javascripts()">
  <!--[if lt IE 7]>
  <script type='text/javascript' src="/static/scripts/IE7.js"></script>
  <script type='text/javascript' src="/static/scripts/IE8.js"></script>
  <script type='text/javascript' src="/static/scripts/ie7-recalc.js"></script>
  <![endif]-->
  <script type='text/javascript' src="${h.url_for('/static/scripts/jquery-1.7.1.min.js')}"></script>
  <script type='text/javascript' src="${h.url_for('/static/scripts/jquery-ui-1.8.10.custom.min.js')}"></script>
  <script type='text/javascript' src="${h.url_for('/static/scripts/livevalidation_standalone.compressed.js')}"></script>
  <script type='text/javascript' src="${h.url_for('/static/bootstrap/js/bootstrap.min.js')}"></script>
  <script type='text/javascript' src="http://code.angularjs.org/1.1.2/angular.min.js"></script>
  <script type='text/javascript' src="https://raw.github.com/angular-ui/angular-ui/master/build/angular-ui.min.js"></script>
  <script type='text/javascript' src="${h.url_for('/static/scripts/ui-bootstrap-tpls-0.1.0.js')}"></script>
</%def>

## Default late-load javascripts
<%def name="late_javascripts()">
</%def>
    
## Masthead
<%def name="masthead()">
<div class="navbar navbar-inverse navbar-fixed-top">
      <div class="navbar-inner">
        <div class="container">
          <a class="brand" href="${h.url_for(controller='root', action='index')}"><img border="0" src="${h.url_for('/static/images/galaxyIcon_noText.png')}">CloudMan for Galaxy</a>
          <div class="nav-collapse collapse">
            <ul class="nav pull-right">
		      %if CM_url:
			  <li>
		        <span id='cm_update_message'>
		              There is a <span style="color:#5CBBFF">new version</span> of CloudMan:
		              <a target="_blank" href="${CM_url}">What's New</a> | 
		              <a id='update_cm' href="#">Update CloudMan</a>
		              &nbsp;&nbsp;&nbsp;
		        </span>
		         <span style='display:none' id="update_reboot_now"><a href="#">Restart cluster now?</a></span>&nbsp;&nbsp;&nbsp;
              </li>
		      %endif
              <li class="active"><a href="${h.url_for(controller='root', action='admin')}">Admin</a></li>
              <li class="dropdown">
                <a href="#" class="dropdown-toggle" data-toggle="dropdown">Help <b class="caret"></b></a>
                <ul class="dropdown-menu">
                  <li><a target="_blank" href="http://usegalaxy.org/cloud">Wiki</a></li>
              	  <li><a target="_blank" href="http://screencast.g2.bx.psu.edu/cloud/">Screencast</a></li>
              	  <li><a href="#about"><a href="mailto:galaxy-bugs@bx.psu.edu">Report bugs</a></li>
                </ul>
              </li>
            </ul>
          </div><!--/.nav-collapse -->
        </div>
      </div>
    </div>
</%def>

## Document
<html lang="en" ng-app="cloudman">
  <head>
    <title>${self.title()}</title>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
    ${self.javascripts()}
    ${self.stylesheets()}
  </head>
  <body>
    ## Layer masthead iframe over background
    <div id="masthead">
      ${self.masthead()}
      <!-- TODO: Kludge to leave space after header. Redo properly -->
      <br /><br /><br />      
    </div>
    ## Display main CM body
    
    <div id="main_body" class="container">
      ${self.main_body()}
    </div>
    
    ## Allow other body level elements
    ${next.body()}


    <footer>
	</footer>

  </body>
  ## Scripts can be loaded later since they progressively add features to
  ## the panels, but do not change layout
  ${self.late_javascripts()}
</html>
