import datetime as dt
from cm.framework.messages import constants, utils


LEVEL_TAGS = utils.get_level_tags()


class Message(object):
    """ Represents an actual message that can be stored in any of the supported
        storage classes and rendered in a view or template.
    """
    
    def __init__(self, level, message):
        self.level = int(level)
        self.message = message
        self.added_at = dt.datetime.utcnow()
    

class BaseStorage(object):
    """
    This is the base backend for temporary message storage.
    
    This is not a complete class; to be a usable storage backend, it must be
    subclassed and the two methods ``_get`` and ``_store`` overridden.
    """
    
    def __init__(self, *args, **kwargs):
        self._queued_messages = []
        self._level = kwargs['level'] if kwargs.get('level', None) else constants.INFO
        super(BaseStorage, self).__init__(*args, **kwargs)
    
    def __len__(self):
        return len(self._loaded_messages) + len(self._queued_messages)
    
    def __iter__(self):
        self.used = True
        if self._queued_messages:
            self._loaded_messages.extend(self._queued_messages)
            self._queued_messages = []
        return iter(self._loaded_messages)
    
    def __contains__(self, item):
        return item in self._loaded_messages or item in self._queued_messages
    
    @property
    def _loaded_messages(self):
        """
        Returns a list of loaded messages, retrieving them first if they have
        not been loaded yet.
        """
        if not hasattr(self, '_loaded_data'):
            messages, all_retrieved = self._get()
            self._loaded_data = messages or []
        return self._loaded_data
    
    def _get(self, *args, **kwargs):
        """
        Retrieves a list of stored messages. Returns a tuple of the messages
        and a flag indicating whether or not all the messages originally
        intended to be stored in this storage were, in fact, stored and
        retrieved; e.g., ``(messages, all_retrieved)``.
        
        **This method must be implemented by a subclass.**
        
        If it is possible to tell if the backend was not used (as opposed to
        just containing no messages) then ``None`` should be returned in
        place of ``messages``.
        """
        raise NotImplementedError()
    
    def _store(self, messages, *args, **kwargs):
        """
        Stores a list of messages, returning a list of any messages which could
        not be stored.
        
        One type of object must be able to be stored, ``Message``.
        
        **This method must be implemented by a subclass.**
        """
        raise NotImplementedError()
    
    def update(self):
        """
        Stores all unread messages.
        """
        messages = self._loaded_messages + self._queued_messages
        not_stored_msgs = self._store(messages)
        # Any msgs not saved get saved to _queued_messages to try storing again later
        self._queued_messages = not_stored_msgs
    
    def add(self, level, message):
        """ 
        Queues a message to be stored.
        
        The message is only queued if it contained something and its level is
        not less than the recording level (``self.level``).
        """
        if not message:
            return
        # Check that the message level is not less than the recording level.
        level = int(level)
        if level < self.level:
            return
        # Add the message.
        message = Message(level, message)
        self._queued_messages.append(message)
        self.update()
    
    def _get_level(self):
        """ 
        Returns the minimum recorded level.
        """
        return self._level
    
    def _set_level(self, value=None):
        """ 
        Sets a custom minimum recorded level.
        
        If set to ``None``, the default level will be used (see the
        ``_get_level`` method).
        """
        if value is None and hasattr(self, '_level'):
            del self._level
        else:
            self._level = int(value)
    
    level = property(_get_level, _set_level, _set_level)