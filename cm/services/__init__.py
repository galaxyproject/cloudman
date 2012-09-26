"""
The base services package; all CloudMan services derive from this class.
"""
import datetime as dt
from cm.util.bunch import Bunch

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
        """
        Add a given service to the pool of services managed by CloudMan, giving
        CloudMan the abilty to monitor and control the service. This is a base
        implementation of the service ``add`` method which calls service's internal
        ``start`` method. Before calling the ``start`` method, service prerequisites
        are checked and, if satisfied, the service is started. If the prerequisites
        are not satisfied, the service is set to state ``UNSTARTED``.
        """
        if self.state != service_states.RUNNING:
            # log.debug("Trying to add service '%s'" % self.svc_type)
            self.state = service_states.STARTING
            self.last_state_change_time = dt.datetime.utcnow()
            failed_prereqs = [] # List of service prerequisites that have not been satisfied
            for svc_type, svc_name in self.reqs.iteritems():
                # log.debug("'%s' service checking its prerequisite '%s:%s'" \
                #    % (self.get_full_name(), svc_type, svc_name))
                for svc in self.app.manager.services:
                    # log.debug("Checking service %s state." % svc.svc_type)
                    if svc_type==svc.svc_type:
                        if svc_name is not None and svc.name==svc_name:
                            # log.debug("Service %s:%s running: %s" % (svc.svc_type, svc.name, svc.running()))
                            if not svc.running():
                                failed_prereqs.append(svc.svc_type)
                        else:
                            # log.debug("Service %s running: %s" % (svc.svc_type, svc.running()))
                            if not svc.running():
                                failed_prereqs.append(svc.svc_type)
            if len(failed_prereqs) == 0:
                log.info("{0} prerequisites OK; starting the service".format(self.get_full_name()))
                self.start()
                return True
            else:
                log.info("{0} service prerequisites are not yet satisfied, missing: {2}. "\
                        "Setting {0} service state to '{1}'"\
                        .format(self.get_full_name(), service_states.UNSTARTED, failed_prereqs))
                # Reset state so it get picked back up by monitor
                self.state = service_states.UNSTARTED
                return False

    def running(self):
        """
        Return ``True`` is service is in state ``RUNNING``, ``False`` otherwise
        """
        return self.state == service_states.RUNNING

    def get_full_name(self):
        """
        Return full name of the service (useful if different from service type)
        """
        return self.svc_type
