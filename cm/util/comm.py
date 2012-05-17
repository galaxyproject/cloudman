import amqplib.client_0_8 as amqp
import logging

log = logging.getLogger( 'cloudman' )

DEFAULT_HOST = 'localhost:5672'

class CMMasterComm( object ):
    def __init__(self, iid='MasterInstance'):
        self.instances = []
        self.user = 'guest'
        self.password = 'guest'
        self.host = DEFAULT_HOST
        if iid is None:
            self.iid = 'MasterInstance'
        else:
            self.iid = iid
        self.exchange = 'comm'
        self.conn = None
        self.channel = None
        self.queue = 'master'
    
    def is_connected(self):
        return self.conn != None
    
    def setup(self):
        """Master will use a static 'master' routing key, while all of the instances use their own iid"""
        try:
            self.conn = amqp.Connection(host = self.host, userid = self.user, password = self.password)
            self.channel = self.conn.channel()
            self.channel.access_request('/data', active=True, write=True)
            self.channel.exchange_declare(self.exchange, type='direct', durable=False, auto_delete = True)
            self.channel.queue_declare(queue = 'master', durable = False, exclusive = False, auto_delete = True)
            self.channel.queue_bind(exchange = self.exchange, queue = 'master', routing_key = 'master')
            log.debug("Successfully established AMQP connection")
        except Exception, e:
            log.debug("AMQP Connection Failure:  %s", e)
            self.conn = None
    
    def shutdown(self):
        log.info("Comm Shutdown Invoked")
        if self.channel:
            self.channel.close()
        if self.conn:
            self.conn.close()
    
    def send(self, message, to):
        # log.debug("S_COMM: Sending from %s to %s message %s" % ('master', to, message ))
        msg = amqp.Message(message, reply_to = 'master', content_type='text/plain')
        self.channel.basic_publish(msg, exchange=self.exchange, routing_key=to)
    
    def recv( self ):
        if self.conn:
            msg = self.channel.basic_get(self.queue)
            if msg is not None:
                if msg.properties['reply_to'] is not None:
                    log.debug("R_COMM: Recv from %s message %s" % (msg.properties['reply_to'], msg.body))
                else:
                    log.debug("R_COMM: Recv from NO_REPLYTO message %s" % msg.body)
                self.channel.basic_ack(msg.delivery_tag)
                return msg
            else:
                return None
    

class CMWorkerComm( object ):
    def __init__(self, iid='WorkerInstance', host=DEFAULT_HOST):
        self.user = 'guest'
        self.password = 'guest'
        self.host = host
        self.iid = iid
        self.exchange = 'comm'
        self.conn = None
        self.channel = None
        self.queue = 'worker_' + iid
        self.got_conn = False
    
    def is_connected(self):
        return self.conn != None
    
    def setup(self):
        try:
            self.conn = amqp.Connection(host = self.host, userid = self.user, password = self.password)
            self.channel = self.conn.channel()
            self.channel.access_request('/data', active=True, write=True)
            self.channel.exchange_declare(self.exchange, type='direct', durable=False, auto_delete = True)
            self.channel.queue_declare(queue = self.queue, durable = False, exclusive = False, auto_delete = True)
            self.channel.queue_bind(exchange = self.exchange, queue = self.queue, routing_key = self.iid)
            self.got_conn = True
            log.debug("Successfully established AMQP connection")
        except Exception, e:
            log.debug("AMQP Connection Failure:  %s", e)
            self.conn = None
    
    def shutdown(self):
        log.info("Comm Shutdown Invoked")
        if self.channel:
            self.channel.close()
        if self.conn:
            self.conn.close()
    
    def send(self, message ):
        if self.conn:
            log.debug("S_COMM: Sending from %s to %s message %s" % (self.iid, 'master', message))
            """Worker will always rout to master, not another worker."""
            msg = amqp.Message(message, reply_to = self.iid ,content_type='text/plain')
            self.channel.basic_publish(msg, exchange = self.exchange, routing_key = 'master')
        else:
            log.error("S_COMM FAILURE: Sending from %s to %s message %s" % (self.iid, 'master', message))
    
    def recv( self ):
        if self.conn:
            msg = self.channel.basic_get(self.queue)
            if msg is not None:
                log.debug("R_COMM: Recv from %s message %s" % (msg.properties['reply_to'], msg.body))
                self.channel.basic_ack(msg.delivery_tag)
                return msg
            else:
                return None
        else:
            log.error("R_COMM FAILURE:  No connection available.")
    
