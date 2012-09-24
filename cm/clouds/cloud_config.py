from cm.util import misc
from cm.util import paths

from cm.clouds.ec2 import EC2Interface
from cm.clouds.openstack import OSInterface
from cm.clouds.opennebula import ONInterface
from cm.clouds.dummy import DummyInterface
from cm.clouds.eucalyptus import EucaInterface

class CloudConfig(object):
    """ Configuration class that is used as a mediator for support between
        different clouds.
    """
    def __init__(self, app):
        self.app = app
    
    def get_cloud_type(self):
        """ Determine the type of cloud currently being running on. 
            If needed, this method should be extended to include other
            (or alternative) methods for detecting the type of cloud.
            
            The current assumption is that the type of cloud is included as
            part of user data and stored in paths.USER_DATA_FILE file
            under 'cloud_type' key.
        """
        return misc.load_yaml_file(paths.USER_DATA_FILE).get('cloud_type', 'ec2').lower()
    
    def get_cloud_interface(self, cloud_type=None):
        """ Return the approprtae cloud interface object based on the cloud_type
            
            :type cloud_type: string
            :param cloud_type: The type of cloud currently running on. 
                               Currently, the accepted values include:
                               'ec2', 'openstack', 'opennebula', and 'dummy'
                               
            :return: The cloud interface object for the specific cloud type
        """
        if cloud_type is None:
            cloud_type = self.get_cloud_type()
        cloud_interface = None
        if cloud_type == "ec2":
            cloud_interface = EC2Interface(app=self.app)
        elif cloud_type.lower() == 'os' or cloud_type.lower() == 'openstack':
            cloud_interface = OSInterface(app=self.app)
        elif cloud_type.lower() == 'opennebula':
            cloud_interface = ONInterface(app=self.app)
        elif cloud_type == 'dummy':
            cloud_interface = DummyInterface(app=self.app)
        elif cloud_type == 'euca' or cloud_type.lower()=='eucalyptus':
            cloud_interface = EucaInterface(app=self.app)
        return cloud_interface
        
    
