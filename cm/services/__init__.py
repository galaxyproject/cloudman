"""Services Package"""
from cm.util.bunch import Bunch
import datetime as dt

import logging
log = logging.getLogger( 'cloudman' )


service_states = Bunch(
    UNSTARTED="Unstarted",
    WAITING_FOR_USER_ACTION="Waiting for user action",
    STARTING="Starting",
    RUNNING = "Running",
    SHUTTING_DOWN = "Shutting down",
    SHUT_DOWN="Shut down",
    ERROR="Error"
 )


class Service( object):
    
    def __init__( self, app, service_type=None ):
        self.app = app
        self.state = service_states.UNSTARTED
        self.last_state_change_time = dt.datetime.utcnow()
        self.svc_type = "BaseService"
        self.reqs = {}

    def add (self):
        if self.state != service_states.RUNNING:
            log.debug("Trying to add service '%s'" % self.svc_type)
            self.state = service_states.STARTING
            self.last_state_change_time = dt.datetime.utcnow()
            flag = True # indicate if current service prerequisites are satisfied
            for svc_type, svc_name in self.reqs.iteritems():
                log.debug("'%s' service checking its prerequisite '%s:%s'" % (self.svc_type, svc_type, svc_name))
                for svc in self.app.manager.services:
                    # log.debug("Checking service %s state." % svc.svc_type)
                    if svc_type==svc.svc_type:
                        if svc_name is not None and svc.name==svc_name:
                            # log.debug("Service %s:%s running: %s" % (svc.svc_type, svc.name, svc.running()))
                            if not svc.running():
                                flag = False
                        else:
                            # log.debug("Service %s running: %s" % (svc.svc_type, svc.running()))
                            if not svc.running():
                                flag = False
            if flag:
                log.info("Prerequisites OK; starting service '%s'" % self.svc_type)
                self.start()
                return True
            else:
                log.info("Cannot start service '%s' because prerequisites are not yet satisfied." % self.svc_type)
                return False
    
    def running(self):
        return self.state == service_states.RUNNING
        
    def get_full_name(self):
        """ Return full name of the service (useful if different from service type)"""
        return self.svc_type
