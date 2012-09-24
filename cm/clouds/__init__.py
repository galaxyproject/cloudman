from cm.util import misc
from cm.util import paths

import logging
log = logging.getLogger('cloudman')

class CloudInterface(object):
    # Global fields
    ec2_conn = None
    s3_conn = None
    # Instance details
    ami = None
    instance_type = None
    instance_id = None
    instance = None # boto object representation of the instance
    zone = None
    security_groups = None
    key_pair_name = None
    self_private_ip = None
    local_hostname = None
    self_public_ip = None
    instance_type = None
    fqdn = None
    user_data = None
    aws_access_key = None
    aws_secret_key = None
    
    def get_user_data(self, force=False):
        """ Override this method in a cloud-specific interface if the 
            default approach does not apply.
            NOTE that this method should call the set_configuration method!
            
            :type force: boolean
            :param force: If set to True, reload the user data regardless if
                          the data is already stored in the class field
                          
            :rtype: dict
            :return: A key-value dictionary containing the user data.
        """
        if self.user_data is None or force:
            self.user_data = misc.load_yaml_file(paths.USER_DATA_FILE)
            self.set_configuration()
        return self.user_data
    
    def set_configuration(self):
        """ Set the configuration fields for the given cloud interface.
            This should primarily be used to set credentials and such.
            It is expected that this method is called in the process of loading
            the user data.
            
            This method should be overriden for any cloud interface that requires
            more credentials than the access credentials included in this default
            implementation.
        """
        if self.user_data is None:
            self.get_user_data()
        self.aws_access_key = self.user_data.get('access_key', None)
        self.aws_secret_key = self.user_data.get('secret_key', None)
        self.tags = {}
    
    def get_configuration(self):
        """ Return a dict with all the class variables.
        """
        return vars(self)
    
    # Non-implemented methods
    
    def get_local_hostname(self):
        log.warning("Unimplemented")
        pass
    
    def run_instances(self, num, instance_type, **kwargs):
        """ Run an image.
        """
        log.warning("Unimplemented")
        pass
    
