import sys, config, logging, logging.config, urllib, socket
from cm.util import actions, misc

from boto.s3.connection import S3Connection
from boto.ec2.connection import EC2Connection
from boto.sqs.connection import SQSConnection
from boto.exception import EC2ResponseError, S3ResponseError

log = logging.getLogger( __name__ )
logging.getLogger('boto').setLevel(logging.INFO)

class CMLogHandler(logging.Handler):
    def __init__(self, app):
        logging.Handler.__init__(self)
        self.formatter = logging.Formatter("%(asctime)s - %(message)s", "%H:%M:%S")
        self.setFormatter(self.formatter)
        self.logmessages = []

    def emit(self, record):
        self.logmessages.append(self.formatter.format(record))


class UniverseApplication( object ):
    """Encapsulates the state of a Universe application"""
    def __init__( self, **kwargs ):
        self.shell_vars = misc.shellVars2Dict("userData.txt")
        # Testflag to disable all S3 for local testing.
        if self.shell_vars.has_key("TESTFLAG"):
            self.TESTFLAG = True
        else:
            self.TESTFLAG = False
        self.logger = CMLogHandler(self)
        if self.TESTFLAG is True:
            self.logger.setLevel(logging.DEBUG)
        else:
            self.logger.setLevel(logging.INFO)
        log.addHandler(self.logger)
        log.info("Testing?")
        # Read config file and check for errors
        self.config = config.Configuration( **kwargs )
        self.config.check()
        config.configure_logging( self.config )
        log.debug( "Initializing app" )
        self.manager = None
        # Global fields
        self.permanent_storage_size = 0
        self.ami = None
        self.type = None
        self.instance_id = None
        self.zone = None
        self.security_groups = None
        self.key_pair_name = None
        self.ec2_conn = None
        self.s3_conn = None
        self.sqs_conn = None
        self.self_private_ip = None
        self.self_public_ip = None
        self.fqdn = None
        if self.shell_vars.has_key('ROLE'):
            if self.shell_vars['ROLE'] == 'master':
                log.info( "Master starting..." )
                from cm.util import master
                self.manager = master.ConsoleManager(self)
            elif self.shell_vars['ROLE'] == 'worker':
                log.info( "Worker starting..." )
                from cm.util import worker
                self.manager = worker.ConsoleManager(self)
            self.manager.console_monitor.start()
        else:
            log.error("No ROLE in userData.  This is a fatal error.")
                
    def shutdown( self ):
        self.manager.shutdown()
    
    
    def get_ami( self ):
        if self.ami is None:
            for i in range(0, 5):
                try:
                    log.debug('Gathering instance ami, attempt %s' % i)
                    fp = urllib.urlopen('http://169.254.169.254/latest/meta-data/ami-id')
                    self.ami = fp.read()
                    fp.close()
                    if self.ami:
                        break
                except IOError:
                    pass
        return self.ami
        
    def get_type( self ):
        if self.TESTFLAG is True:
                return "d1.xtreme"
        if self.type is None:
            for i in range(0, 5):
                try:
                    log.debug('Gathering instance type, attempt %s' % i)
                    fp = urllib.urlopen('http://169.254.169.254/latest/meta-data/instance-type')
                    self.type = fp.read()
                    fp.close()
                    if self.type:
                        break
                except IOError:
                    pass
        return self.type
        
    def get_instance_id( self ):
        if self.TESTFLAG is True:
            if self.shell_vars['ROLE'] == 'master':
                return "Node231xQ"
            else:
                return "TestWorker"
        if self.instance_id is None:
            for i in range(0, 5):
                try:
                    log.debug('Gathering instance id, attempt %s' % i)
                    fp = urllib.urlopen('http://169.254.169.254/latest/meta-data/instance-id')
                    self.instance_id = fp.read()
                    fp.close()
                    if self.instance_id:
                        break
                except IOError:
                    pass
        return self.instance_id

    def get_zone( self ):
        if self.zone is None:
            for i in range(0, 5):
                try:
                    log.debug('Gathering instance zone, attempt %s' % i)
                    fp = urllib.urlopen('http://169.254.169.254/latest/meta-data/placement/availability-zone')
                    self.zone = fp.read()
                    fp.close()
                    if self.zone:
                        break
                except IOError:
                    pass
        return self.zone
        
    def get_security_groups( self ):
        if self.security_groups is None:
            for i in range(0, 5):
                try:
                    log.debug('Gathering instance security group, attempt %s' % i)
                    fp = urllib.urlopen('http://169.254.169.254/latest/meta-data/security-groups')
                    self.security_groups = []
                    for line in fp.readlines():
                        self.security_groups.append(line.strip())
                    fp.close()
                    if self.security_groups:
                        break
                except IOError:
                    pass
        return self.security_groups

    def get_key_pair_name( self ):
        if self.key_pair_name is None:
            for i in range(0, 5):
                try:
                    log.debug('Gathering instance public keys (i.e., key pairs), attempt %s' % i)
                    fp = urllib.urlopen('http://169.254.169.254/latest/meta-data/public-keys')
                    public_keys = fp.read()
                    self.key_pair_name = public_keys.split('=')[1]
                    fp.close()
                    if self.key_pair_name:
                        log.debug( "Got key pair: '%s'" % self.key_pair_name )
                        break
                except IOError:
                    pass
        return self.key_pair_name
        
    def get_self_private_ip( self ):
        if self.self_private_ip is None:
            for i in range(0, 5):
                try:
                    log.debug('Gathering instance private hostname, attempt %s' % i)
                    fp = urllib.urlopen('http://169.254.169.254/latest/meta-data/local-hostname')
                    self.self_private_ip = fp.read()
                    fp.close()
                    if self.self_private_ip:
                        break
                except IOError:
                    pass
        return self.self_private_ip
        
    def get_self_public_ip( self ):
        if self.TESTFLAG is True:
            return "http://localhost:8080"
        if self.self_public_ip is None:
            for i in range(0, 5):
                try:
                    log.debug('Gathering instance public hostname, attempt %s' % i)
                    fp = urllib.urlopen('http://169.254.169.254/latest/meta-data/public-hostname')
                    self.self_public_ip = fp.read()
                    fp.close()
                    if self.self_public_ip:
                        break
                except Exception, e:
                    log.error ( "Error retrieving FQDN: %s" % e )
                                
        return self.self_public_ip
        
    def get_sqs_connection(self):
        if self.TESTFLAG is True:
            log.debug("Attempted to get SQS Connection, but TESTFLAG is set.")
            return None
        log.debug('Establishing or Retrieving SQS connection')
        if self.sqs_conn == None:
            try:
                self.sqs_conn = SQSConnection(self.shell_vars['AWS_ACCESS_KEY'], self.shell_vars['AWS_PRIVATE_KEY'])
            except Exception, e:
                log.error(e)
        return self.sqs_conn
    
    def get_fqdn(self):
        log.debug( "Retrieving FQDN" )
        if self.fqdn == None:
            try:
                self.fqdn = socket.getfqdn()
            except IOError:
                pass
        return self.fqdn
        
    
    def get_ec2_connection( self ):
        if self.TESTFLAG is True:
            log.debug("Attempted to get EC2 Connection, but TESTFLAG is set.")
            return None
        # log.debug( 'Establishing boto EC2 connection' )
        if self.ec2_conn == None:
            try:
                self.ec2_conn = EC2Connection( self.shell_vars['AWS_ACCESS_KEY'], self.shell_vars['AWS_PRIVATE_KEY'] )
                log.debug( 'Got boto EC2 connection.' )
            except Exception, e:
                log.error(e)
        return self.ec2_conn
        
    def get_s3_connection( self ):
        if self.TESTFLAG is True:
            log.debug("Attempted to get S3 Connection, but TESTFLAG is set.")
            return None
        log.debug( 'Establishing boto S3 connection' )
        if self.s3_conn == None:
            log.debug("No S3 Connection, creating a new one.")
            try:
                self.s3_conn = S3Connection( self.shell_vars['AWS_ACCESS_KEY'], self.shell_vars['AWS_PRIVATE_KEY'] )
                log.debug( 'Got boto S3 connection.' )
            except Exception, e:
                log.error(e)
        return self.s3_conn