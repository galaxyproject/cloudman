"""
CM actions classes.
"""

import logging

# It would be beneficial if log messages at INFO level could be saved to a file
# or database so they can be displayed on the web status console while DEBUG
# level messages can go to a log file...
log = logging.getLogger('cloudman')


class ControlInstance(object):
    def __init__(self, app):
        self.app = app
        log.debug("Instance controller...")
