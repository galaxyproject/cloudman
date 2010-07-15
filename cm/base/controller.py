"""Contains functionality needed in every webapp interface"""
import os, time, logging
from cm import util

log = logging.getLogger( __name__ )

class BaseController( object ):
    """Base class for CM webapp application controllers."""
    def __init__( self, app ):
        """Initialize an interface for application 'app'"""
        self.app = app