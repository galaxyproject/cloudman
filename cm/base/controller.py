"""Contains functionality needed in every webapp interface"""
import logging

log = logging.getLogger('cloudman')


class BaseController(object):
    """Base class for CM webapp application controllers."""
    def __init__(self, app):
        """Initialize an interface for application 'app'"""
        self.app = app
