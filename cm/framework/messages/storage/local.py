import datetime as dt

from cm.framework.messages.storage.base import BaseStorage
from cm.framework.messages import constants

class LocalStorage(BaseStorage):
    """ 
    Stores messages in memory.
    """
    
    def __init__(self, *args, **kwargs):
        self.messages = []
        super(LocalStorage, self).__init__(*args, **kwargs)
    
    def _get(self, *args, **kwargs):
        """ 
        Retrieves a list of all known messages.
        
        This storage always returns everything it has, so return True
        for the all_retrieved flag.
        """
        return self.messages, True

    def _store(self, messages, *args, **kwargs):
        """ Stores a list of messages to memory.
        """
        if messages:
            self.messages += messages
        return []
    
    def dismiss(self):
        """
        Dismiss/remove all but CRITICAL messages from memory.
        CRITICAL messages cannot be dismissed.
        """
        for msg in list(self.messages):
            if msg.level != constants.CRITICAL:
                self.messages.remove(msg)
    

        