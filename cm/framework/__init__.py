"""
CM application framework
"""

import os, sys, time, socket, random, string
import base
import pickle
from cm import util
from cm.util.json import to_json_string, from_json_string

import simplejson

import helpers
# This adds the routes url_for function to the helpers bundle that gets sent for template generation.
helpers.url_for = base.routes.url_for

from paste.deploy.converters import asbool

import mako.template
import mako.lookup
import mako.runtime

import logging
log = logging.getLogger( __name__ )

url_for = base.routes.url_for

def expose( func ):
    """
    Decorator: mark a function as 'exposed' and thus web accessible
    """
    func.exposed = True
    return func
    
def json( func ):
    def decorator( self, trans, *args, **kwargs ):
        trans.response.set_content_type( "text/javascript" )
        return simplejson.dumps( func( self, trans, *args, **kwargs ) )
    if not hasattr(func, '_orig'):
        decorator._orig = func
    decorator.exposed = True
    return decorator

def json_pretty( func ):
    def decorator( self, trans, *args, **kwargs ):
        trans.response.set_content_type( "text/javascript" )
        return simplejson.dumps( func( self, trans, *args, **kwargs ), indent=4, sort_keys=True )
    if not hasattr(func, '_orig'):
        decorator._orig = func
    decorator.exposed = True
    return decorator

class MessageException( Exception ):
    """
    Exception to make throwing errors from deep in controllers easier
    """
    def __init__( self, err_msg, type="info" ):
        self.err_msg = err_msg
        self.type = type
        
def error( message ):
    raise MessageException( message, type='error' )

def form( *args, **kwargs ):
    return FormBuilder( *args, **kwargs )
    
class WebApplication( base.WebApplication ):
    def __init__( self, galaxy_app, session_cookie='galaxysession' ):
        base.WebApplication.__init__( self )
        self.set_transaction_factory( lambda e: UniverseWebTransaction( e, galaxy_app, self, session_cookie ) )
        # Mako support
        self.mako_template_lookup = mako.lookup.TemplateLookup(
            directories = [ galaxy_app.config.template_path ] ,
            collection_size = 500,
            output_encoding = 'utf-8' )
    def handle_controller_exception( self, e, trans, **kwargs ):
        if isinstance( e, MessageException ):
            return trans.show_message( e.err_msg, e.type )
    def make_body_iterable( self, trans, body ):
        if isinstance( body, FormBuilder ):
            body = trans.show_form( body )
        return base.WebApplication.make_body_iterable( self, trans, body )
    
class UniverseWebTransaction( base.DefaultWebTransaction ):
    """
    Encapsulates web transaction specific state for the Universe application
    (specifically the user's "cookie" session and history)
    """
    def __init__( self, environ, app, webapp, session_cookie ):
        self.app = app
        self.webapp = webapp
        base.DefaultWebTransaction.__init__( self, environ )

    @base.lazy_property
    def template_context( self ):
        return dict()

    @property
    def model( self ):
        return self.app.model

    def make_form_data( self, name, **kwargs ):
        rval = self.template_context[name] = FormData()
        rval.values.update( kwargs )
        return rval

    def set_message( self, message ):
        """
        Convenience method for setting the 'message' element of the template
        context.
        """
        self.template_context['message'] = message
    def get_message( self ):
        """
        Convenience method for getting the 'message' element of the template
        context.
        """
        return self.template_context['message']
    def show_message( self, message, type='info', refresh_frames=[], cont=None, use_panels=False, active_view="" ):
        """
        Convenience method for displaying a simple page with a single message.
        
        `type`: one of "error", "warning", "info", or "done"; determines the
                type of dialog box and icon displayed with the message
                
        `refresh_frames`: names of frames in the interface that should be 
                          refreshed when the message is displayed
        """
        return self.fill_template( "message.mako", status=type, message=message, refresh_frames=refresh_frames, cont=cont, use_panels=use_panels, active_view=active_view )
    def show_error_message( self, message, refresh_frames=[], use_panels=False, active_view="" ):
        """
        Convenience method for displaying an error message. See `show_message`.
        """
        return self.show_message( message, 'error', refresh_frames, use_panels=use_panels, active_view=active_view )
    def show_ok_message( self, message, refresh_frames=[], use_panels=False, active_view="" ):
        """
        Convenience method for displaying an ok message. See `show_message`.
        """
        return self.show_message( message, 'done', refresh_frames, use_panels=use_panels, active_view=active_view )
    def show_warn_message( self, message, refresh_frames=[], use_panels=False, active_view="" ):
        """
        Convenience method for displaying an warn message. See `show_message`.
        """
        return self.show_message( message, 'warning', refresh_frames, use_panels=use_panels, active_view=active_view )
    def show_form( self, form, header=None, template="form.mako", use_panels=False, active_view="" ):
        """
        Convenience method for displaying a simple page with a single HTML
        form.
        """    
        return self.fill_template( template, form=form, header=header, use_panels=use_panels, active_view=active_view )
    def fill_template(self, filename, **kwargs):
        """
        Fill in a template, putting any keyword arguments on the context.
        """
        if filename.endswith( ".mako" ):
            return self.fill_template_mako( filename, **kwargs )
        else:
            template = Template( file=os.path.join(self.app.config.template_path, filename), 
                                 searchList=[kwargs, self.template_context, dict(caller=self, t=self, h=helpers, util=util, request=self.request, response=self.response, app=self.app)] )
            return str( template )

    def fill_template_mako( self, filename, **kwargs ):
        template = self.webapp.mako_template_lookup.get_template( filename )
        template.output_encoding = 'utf-8' 
        data = dict( caller=self, t=self, trans=self, h=helpers, util=util, request=self.request, response=self.response, app=self.app )
        data.update( self.template_context )
        data.update( kwargs )
        return template.render( **data )
    def stream_template_mako( self, filename, **kwargs ):
        template = self.webapp.mako_template_lookup.get_template( filename )
        template.output_encoding = 'utf-8' 
        data = dict( caller=self, t=self, trans=self, h=helpers, util=util, request=self.request, response=self.response, app=self.app )
        data.update( self.template_context )
        data.update( kwargs )
        ## return template.render( **data )
        def render( environ, start_response ):
            response_write = start_response( self.response.wsgi_status(), self.response.wsgi_headeritems() )
            class StreamBuffer( object ):
                def write( self, d ):
                    response_write( d.encode( 'utf-8' ) )
            buffer = StreamBuffer()
            context = mako.runtime.Context( buffer, **data )
            template.render_context( context )
            return []
        return render
    def fill_template_string(self, template_string, context=None, **kwargs):
        """
        Fill in a template, putting any keyword arguments on the context.
        """
        template = Template( source=template_string,
                             searchList=[context or kwargs, dict(caller=self)] )
        return str(template)

class FormBuilder( object ):
    """
    Simple class describing an HTML form
    """
    def __init__( self, action="", title="", name="form", submit_text="submit" ):
        self.title = title
        self.name = name
        self.action = action
        self.submit_text = submit_text
        self.inputs = []
    def add_input( self, type, name, label, value=None, error=None, help=None, use_label=True  ):
        self.inputs.append( FormInput( type, label, name, value, error, help, use_label ) )
        return self
    def add_text( self, name, label, value=None, error=None, help=None  ):
        return self.add_input( 'text', label, name, value, error, help )
    def add_password( self, name, label, value=None, error=None, help=None  ):
        return self.add_input( 'password', label, name, value, error, help )
        
class FormInput( object ):
    """
    Simple class describing a form input element
    """
    def __init__( self, type, name, label, value=None, error=None, help=None, use_label=True ):
        self.type = type
        self.name = name
        self.label = label
        self.value = value
        self.error = error
        self.help = help
        self.use_label = use_label
    
class FormData( object ):
    """
    Class for passing data about a form to a template, very rudimentary, could
    be combined with the tool form handling to build something more general.
    """
    def __init__( self ):
        self.values = Bunch()
        self.errors = Bunch()
        
class Bunch( dict ):
    """
    Bunch based on a dict
    """
    def __getattr__( self, key ):
        if key not in self: raise AttributeError, key
        return self[key]
    def __setattr__( self, key, value ):
        self[key] = value
