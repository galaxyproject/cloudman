"""
Placeholder for DataService methods.
"""

from cm.services import Service
from cm.util.bunch import Bunch

class DataService( Service ):
    
    def __init__(self, app):
        super(DataService, self).__init__(app)
    

volume_status = Bunch(
    NONE="does not exist",
    CREATING="creating",
    AVAILABLE="available",
    IN_USE="in use",
    ATTACHED="attached",
    DELETING="deleting"
)

class BlockStorage(object):
    """ Abstract interface for block storage resources (eg, EBS Volume). Classes
        managing block storage resources should implement this interface.
    """
    def __init__(self, app):
        """
            :type app: UniverseApplication
            :param app: The CloudMan application object
        """
        self.app = app
    
    def update(self, bsd):
        """ Update 'self' object reference to point to the argument object 'bsd'
        
        :type bsd: BlockStorage (or its derivation: eg, boto Volume)
        :param bsd: A Block Storage Device object representation
        """
        raise NotImplementedError()
    
    def status(self):
        """ Return the current status of the object represented by this object.
        
        :rtype: string
        :return: See volume_status for the available states.
        """
        raise NotImplementedError()
    
    def get_device(self):
        """ Get the system-level device this block storage resource is attached to
        
        :rtype: string
        :return: The ID of the device this resource is attached to
        """
        raise NotImplementedError()
    
    def create(self):
        """ Create the block storage resource represented by this object
        """
        raise NotImplementedError()
    
    def delete(self):
        """ Delete the block storage resource represented by this object
        """
        raise NotImplementedError()
    
    def attach(self):
        """ Attach the block storage resource to the system
        
        :rtype: bool
        :return: True if successful, False otherwise
        """
        raise NotImplementedError()
    
    def detach(self):
        """ Dettach the block storage resource from the system
        
        :rtype: bool
        :return: True if successful, False otherwise
        """
        raise NotImplementedError()
    
    def snapshot(self):
        """ Create a point-in-time snapshot of this block storage resource
        
        :rtype: string
        :return: The newly created snapshot ID or None if failed
        """
        raise NotImplementedError()
    
    def get_from_snap_id(self):
        """ Get the ID of the snapshot this block storage resoruce was created from
        
        :rtype: string
        :return: Snapshot ID this block storage resoruce was created from or None
        """
        raise NotImplementedError()
    
