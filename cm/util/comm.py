import amqplib.client_0_8 as amqp
import logging

log = logging.getLogger('cloudman')

DEFAULT_HOST = 'localhost:5672'


class CMMasterComm(object):
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
        return self.conn is not None

    def setup(self):
        """Master will use a static 'master' routing key, while all of the instances use their own iid"""
        try:
            log.debug("Setting up a new AMQP connection")
            self.conn = amqp.Connection(host=self.host, userid=self.user,
                password=self.password)
            log.debug("Established a new AMQP connection")
            self.channel = self.conn.channel()
            self.channel.access_request('/data', active=True, write=True)
            self.channel.exchange_declare(self.exchange, type='direct',
                                          durable=False, auto_delete=True)
            self.channel.queue_declare(queue='master', durable=False,
                                       exclusive=False, auto_delete=True)
            self.channel.queue_bind(exchange=self.exchange,
                                    queue='master', routing_key='master')
            if self.channel.is_open:
                log.debug("Successfully established AMQP connection channel with ID {0}"
                    .format(self.channel.channel_id))
            else:
                log.error("Tried to establishe an AMQP connection channel but "
                    "the channel did not open?!")
        except Exception, e:
            log.debug("AMQP Connection Failure:  %s", e)
            self.conn = None

    def shutdown(self):
        log.info("Comm Shutdown Invoked")
        if self.channel:
            try:
                self.channel.close()
            except Exception, e:
                log.error("Tried to close self.channel but got an exception: {0}"
                    .format(e))
                self.channel = None
        if self.conn:
            try:
                self.conn.close()
            except Exception, e:
                log.error("Tried to close self.conn but got an exception: {0}"
                    .format(e))
                self.conn = None

    def send(self, message, to):
        # log.debug("S_COMM: Sending from %s to %s message %s" % ('master', to,
        # message ))
        msg = amqp.Message(message, reply_to='master', content_type='text/plain')
        try:
            self.channel.basic_publish(msg, exchange=self.exchange, routing_key=to)
        except Exception, e:
            log.debug("R_COMM send failure: %s", e)

    def recv(self):
        if self.conn:
            try:
                msg = self.channel.basic_get(self.queue)
                if msg is not None:
                    if msg.properties['reply_to'] is not None:
                        # log.debug("R_COMM: Recv from %s (on channel %s) message %s" % (
                        #     msg.properties['reply_to'], self.channel.channel_id, msg.body))
                        pass
                    else:
                        log.debug("R_COMM: Recv from NO_REPLYTO message %s" % msg.body)
                    self.channel.basic_ack(msg.delivery_tag)
                    return msg
                else:
                    return None
            except Exception, e:
                log.error("R_COMM channel basic get exception: {0}".format(e))
                log.debug("\tself.queue: {0}".format(self.queue))
                log.debug("\tself.channel.is_open: {0}".format(self.channel.is_open))
                log.debug("\tself.channel.active: {0}".format(self.channel.active))
                log.debug("\tself.channel.channel_id: {0}".format(self.channel.channel_id))
                log.debug("\tself.conn.channels: {0}".format(self.conn.channels))
                return None


class CMWorkerComm(object):
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
        return self.conn is not None

    def setup(self):
        try:
            self.conn = amqp.Connection(host=self.host,
                                        userid=self.user, password=self.password)
            self.channel = self.conn.channel()
            self.channel.access_request('/data', active=True, write=True)
            self.channel.exchange_declare(self.exchange, type='direct',
                                          durable=False, auto_delete=True)
            self.channel.queue_declare(queue=self.queue, durable=False,
                                       exclusive=False, auto_delete=True)
            self.channel.queue_bind(
                exchange=self.exchange, queue=self.queue, routing_key=self.iid)
            self.got_conn = True
            log.debug("Successfully established AMQP connection with channel ID {0}"
                .format(self.channel.channel_id))
        except Exception, e:
            log.debug("AMQP Connection Failure:  %s", e)
            self.conn = None

    def shutdown(self):
        log.info("Comm Shutdown Invoked")
        if self.channel:
            self.channel.close()
        if self.conn:
            self.conn.close()

    def send(self, message):
        if self.conn:
            log.debug("S_COMM: Sending from %s to %s (on channel ID %s) message %s" % (
                self.iid, 'master', self.channel.channel_id, message))
            """Worker will always rout to master, not another worker."""
            msg = amqp.Message(
                message, reply_to=self.iid, content_type='text/plain')
            try:
                self.channel.basic_publish(
                    msg, exchange=self.exchange, routing_key='master')
            except Exception, e:
                log.error("S_COMM channel publish: {0}".format(e))
        else:
            log.error("S_COMM FAILURE: Sending from %s to %s message %s" % (
                self.iid, 'master', message))

    def recv(self):
        if self.conn:
            msg = self.channel.basic_get(self.queue)
            if msg is not None:
                log.debug("R_COMM: Recv from %s message %s" % (
                    msg.properties['reply_to'], msg.body))
                self.channel.basic_ack(msg.delivery_tag)
                return msg
            else:
                return None
        else:
            log.error("R_COMM FAILURE:  No connection available.")
