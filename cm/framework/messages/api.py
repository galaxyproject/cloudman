from cm.framework.messages import constants
from cm.framework.messages.storage import default_storage

# __all__ = (
#     'add_message', 'get_messages',
#     'get_level', 'set_level',
#     'debug', 'info', 'success', 'warning', 'error',
# )


class MessageFailure(Exception):
    pass

class Messages(object):
    """
    An object vs. module to make up for lack of a session.
    """
    
    def __init__(self):
        self.storage = default_storage()
    
    def add_message(self, level, message):
        """
        Attempts to add a message to the request using the 'messages' module.
        """
        # storage = default_storage()
        self.storage.add(level, message)
    
    def get_messages(self):
        """
        Returns stored messages, otherwise returns an empty list.
        NOTE that once read, messages are deleted from the back end (ie, read once).
        """
        messages = []
        # storage = default_storage()
        messages, retrieved = self.storage._get()
        return messages
    
    def dismiss(self):
        """
        Irreversably dismiss all the currently stored messages.
        """
        self.storage.dismiss()
    
    def get_level(self):
        """
        Returns the minimum level of messages to be recorded.
        
        """
        storage = default_storage()
        return storage.level
    
    def set_level(self, level):
        """
        Sets the minimum level of messages to be recorded, returning ``True`` if
        the level was recorded successfully.
        
        If set to ``None``, the default level will be used (see the ``get_level``
        method).
        """
        return True
    
    def debug(self, message):
        """
        Adds a message with the ``DEBUG`` level.
        """
        self.add_message(constants.DEBUG, message)
    
    def info(self, message):
        """
        Adds a message with the ``INFO`` level.
        """
        self.add_message(constants.INFO, message)
    
    def success(self, message):
        """
        Adds a message with the ``SUCCESS`` level.
        """
        self.add_message(constants.SUCCESS, message)
    
    def warning(self, message):
        """
        Adds a message with the ``WARNING`` level.
        """
        self.add_message(constants.WARNING, message)
    
    def error(self, message):
        """
        Adds a message with the ``ERROR`` level.
        """
        self.add_message(constants.ERROR, message)
    
    def critical(self, message):
        """
        Adds a message with the ``CRITICAL`` level.
        """
        self.add_message(constants.CRITICAL, message)
    
