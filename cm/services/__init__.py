"""Services Package"""
from cm.util.bunch import Bunch

import logging
log = logging.getLogger( 'cloudman' )


service_states = Bunch(
    UNSTARTED="Unstarted",
    WAITING_FOR_USER_ACTION="Waiting for user action",
    STARTING="Initial startup",
    RUNNING = "Running",
    SHUTTING_DOWN = "Shutting down",
    SHUT_DOWN="Shut down",
    ERROR="Error"
 )


class Service( object):
    
    def __init__( self, app, service_type=None ):
        self.app = app
        self.state = service_states.UNSTARTED
        self.svc_type = "BaseService"
        self.reqs = {}

    def add (self):
        log.info("Trying to add service '%s'" % self.svc_type)
        self.state = service_states.STARTING
        flag = True # indicate if current service prerequisites are satisfied
        for svc_type, svc_name in self.reqs.iteritems():
            log.debug("Checking service prerequisite '%s:%s' for service '%s'" % (svc_type, svc_name, self.svc_type))
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
            log.info("Starting service '%s'" % self.svc_type)
            self.start()
        else:
            log.info("Cannot start service '%s' because prerequisites are not yet satisfied." % self.svc_type)
    
    def running(self):
        return self.state == service_states.RUNNING
        
    def get_full_name(self):
        """ Return full name of the service (useful if different from service type)"""
        return self.svc_type
