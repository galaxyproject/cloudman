<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN" "http://www.w3.org/TR/html4/loose.dtd">
<html>
  <head>
    <title>Galaxy</title>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
    <link href="${h.url_for('/static/style/base.css')}" rel="stylesheet" type="text/css" />
    <link href="${h.url_for('/static/style/masthead.css')}" rel="stylesheet" type="text/css" />
  </head>
  <body class="mastheadPage">
    <table width="100%" cellspacing="0" border="0">
      <tr valign="middle">
        <td width="26px">
          <a target="_blank" href="${wiki_url}">
          <img border="0" src="${h.url_for('/static/images/cloudmanIcon_noText.png')}"></a>
        </td>
        <td align="left" valign="middle"><div class="pageTitle">Galaxy${brand}</div></td>
        <td align="right" valign="middle">
          %if CM_url:
			  There is a <span style="color:#5CBBFF">new version</span> of CloudMan:
			  <a target="_blank" href="${CM_url}">What's New</a> |
			  <a target="_top" href="${h.url_for( controller='root', action='update_users_CM' )}">Update CloudMan</a>
	          &nbsp;&nbsp;&nbsp;
		  %endif
		  Info: <a href="${bugs_email}">report bugs</a>
          | <a target="_blank" href="${wiki_url}">wiki</a>
          | <a target="_blank" href="${screencasts_url}">screencasts</a>
          &nbsp;
        </td>
      </tr>
    </table>
  </body>
</html>
