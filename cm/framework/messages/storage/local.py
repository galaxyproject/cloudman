from cm.framework.messages.storage.base import BaseStorage


class LocalStorage(BaseStorage):
    """ 
    Stores messages in memory.
    """
    
    def __init__(self, *args, **kwargs):
        self.messages = []
        super(LocalStorage, self).__init__(*args, **kwargs)
    
    def _get(self, *args, **kwargs):
        """ Retrieves a list of known messages and remove them from memory.
            This storage always returns everything it has, so return True
            for the all_retrieved flag.
        """
        msgs = self.messages
        self.messages = [] # Clear messages that were read
        return msgs, True

    def _store(self, messages, *args, **kwargs):
        """ Stores a list of messages to memory.
        """
        if messages:
            self.messages += messages
        return []