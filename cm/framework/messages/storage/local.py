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
        Retrieves a list of known messages and removes any expired messages
        from memory.
        
        This storage always returns everything it has, so return True
        for the all_retrieved flag.
        """
        msgs = self.messages
        # Remove expired messages. A message is expired if it is older than
        # 5 minutes and is not an ERROR message.
        for msg in self.messages:
            if msg.level != constants.ERROR and \
               (dt.datetime.utcnow() - msg.added_at).seconds > 300:
               self.messages.remove(msg)
        return msgs, True

    def _store(self, messages, *args, **kwargs):
        """ Stores a list of messages to memory.
        """
        if messages:
            self.messages += messages
        return []