import config, logging, logging.config, sys
from cm.util import misc
from cm.util import paths
from cm.framework import messages

from cm.clouds.cloud_config import CloudConfig

log = logging.getLogger( 'cloudman' )
logging.getLogger('boto').setLevel(logging.INFO)

class CMLogHandler(logging.Handler):
    def __init__(self, app):
        logging.Handler.__init__(self)
        self.formatter = logging.Formatter("%(asctime)s - %(message)s", "%H:%M:%S")
        # self.formatter = logging.Formatter("[%(levelname)s] %(module)s:%(lineno)d %(asctime)s: %(message)s")
        self.setFormatter(self.formatter)
        self.logmessages = []
    
    def emit(self, record):
        self.logmessages.append(self.formatter.format(record))
    

class UniverseApplication( object ):
    """Encapsulates the state of a Universe application"""
    def __init__( self, **kwargs ):
        print "Python version: ", sys.version_info[:2]
        cc = CloudConfig(app=self)
        # Get the type of cloud currently running on
        self.cloud_type = cc.get_cloud_type()
        # Create an approprite cloud connection
        self.cloud_interface = cc.get_cloud_interface(self.cloud_type)
        # Load user data into a local field through a cloud interface
        self.ud = self.cloud_interface.get_user_data()
        # From user data determine if object store (S3) should be used.
        self.use_object_store = ud.get("use_object_store", True)
        # Read config file and check for errors
        self.config = config.Configuration( **kwargs )
        self.config.check()
        # Setup logging
        self.logger = CMLogHandler(self)
        if self.ud.has_key("testflag"):
            self.TESTFLAG = bool(self.ud['testflag'])
            self.logger.setLevel(logging.DEBUG)
        else:
            self.TESTFLAG = False
            self.logger.setLevel(logging.INFO)
        
        if self.ud.has_key("localflag"):
            self.LOCALFLAG = bool(self.ud['localflag'])
            self.logger.setLevel(logging.DEBUG)
        else:
            self.LOCALFLAG = False
            self.logger.setLevel(logging.INFO)
        log.addHandler(self.logger)
        config.configure_logging(self.config)
        log.debug( "Initializing app" )
        log.debug("Running on '{0}' type of cloud.".format(self.cloud_type))
        
        # App-wide object to store messages that need to travel between the back-end
        # and the UI. 
        # TODO: Ideally, this should be stored some form of more persistent
        # medium (eg, database, file, session) and used as a simple module (vs. object)
        # but that's hopefully still forthcoming.
        self.msgs = messages.Messages()
        
        # Check that we actually got user creds in user data and inform user
        if not ('access_key' in self.ud or 'secret_key' in self.ud):
            self.msgs.error("No access credentials provided in user data. "
                "You will not be able to add any services.")
        # Update user data to include persistent data stored in cluster's bucket, if it exists
        # This enables cluster configuration to be recovered on cluster re-instantiation
        self.manager = None
        if self.use_object_store and self.ud.has_key('bucket_cluster'):
            log.debug("Getting pd.yaml")
            if misc.get_file_from_bucket(self.cloud_interface.get_s3_connection(), self.ud['bucket_cluster'], 'persistent_data.yaml', 'pd.yaml'):
                pd = misc.load_yaml_file('pd.yaml')
                self.ud = misc.merge_yaml_objects(self.ud, pd)
        if self.ud.has_key('role'):
            if self.ud['role'] == 'master':
                log.info( "Master starting" )
                from cm.util import master
                self.manager = master.ConsoleManager(self)
            elif self.ud['role'] == 'worker':
                log.info( "Worker starting" )
                from cm.util import worker
                self.manager = worker.ConsoleManager(self)
            self.manager.console_monitor.start()
        else:
            log.error("************ No ROLE in %s - this is a fatal error. ************" % paths.USER_DATA_FILE)
    
    def shutdown(self, delete_cluster=False):
        if self.manager:
            self.manager.shutdown(delete_cluster=delete_cluster)
    
    