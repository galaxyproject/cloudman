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
    CONFIGURING="Configuring",
    STARTING="Starting",
    RUNNING = "Running",
    SHUTTING_DOWN = "Shutting down",
    SHUT_DOWN="Shut down",
    ERROR="Error"
 )


class ServiceType(object):
    FILE_SYSTEM = "FileSystem"
    APPLICATION = "Application"


class ServiceRole(object):
    SGE = {'type': ServiceType.APPLICATION, 'name': "Sun Grid Engine"}
    GALAXY = {'type': ServiceType.APPLICATION, 'name': "Galaxy"}
    GALAXY_POSTGRES = {'type': ServiceType.APPLICATION, 'name': "Postgres DB for Galaxy"}
    GALAXY_REPORTS = {'type': ServiceType.APPLICATION, 'name': "Galaxy Reports"}
    AUTOSCALE = {'type': ServiceType.APPLICATION, 'name': "Autoscale"}
    PSS = {'type': ServiceType.APPLICATION, 'name': "Post Start Script"}
    GALAXY_DATA  = {'type': ServiceType.FILE_SYSTEM, 'name': "Galaxy Data FS"}
    GALAXY_INDICES  = {'type': ServiceType.FILE_SYSTEM, 'name': "Galaxy Indices FS"}
    GALAXY_TOOLS = {'type': ServiceType.FILE_SYSTEM, 'name': "Galaxy Tools FS"}
    GENERIC_FS = {'type': ServiceType.FILE_SYSTEM, 'name': "Generic FS"}
    TRANSIENT_NFS = {'type': ServiceType.FILE_SYSTEM, 'name': "Transient NFS FS"}

    @staticmethod
    def get_type(role):
        return role['type']

    @staticmethod
    def from_string(roles_str):
        """
        Convert a list of roles as strings ``roles_str`` into a list of
        ``ServiceRole`` objects and return that list.
        """
        svc_roles = []
        if not isinstance(roles_str, list):
            roles_str = [roles_str] # Not a list, therefore, convert to list
        for role_str in roles_str:
            svc_roles.append(ServiceRole._role_from_string(role_str))
        return svc_roles

    @staticmethod
    def _role_from_string(val):
        if val == "SGE":
            return ServiceRole.SGE
        elif val == "Galaxy":
            return ServiceRole.GALAXY
        elif val == "Postgres":
            return ServiceRole.GALAXY_POSTGRES
        elif val == "GalaxyReports":
            return ServiceRole.GALAXY_REPORTS
        elif val == "Autoscale":
            return ServiceRole.AUTOSCALE
        elif val == "PSS":
            return ServiceRole.PSS
        elif val == "galaxyData":
            return ServiceRole.GALAXY_DATA
        elif val == "galaxyIndices":
            return ServiceRole.GALAXY_INDICES
        elif val == "galaxyTools":
            return ServiceRole.GALAXY_TOOLS
        elif val == "GenericFS":
            return ServiceRole.GENERIC_FS
        elif val == "TransientNFS":
            return ServiceRole.TRANSIENT_NFS
        else:
            return None

    @staticmethod
    def to_string(svc_roles):
        if not isinstance(svc_roles, list):
            svc_roles = [svc_roles] # Not a list, therefore, convert to list
        str_roles = ""
        for role in svc_roles:
            str_roles = str_roles + "," + ServiceRole._role_to_string(role)
        return str_roles[1:] # strip leading comma

    @staticmethod
    def _role_to_string(svc_role):
        if svc_role == ServiceRole.SGE:
            return "SGE"
        elif svc_role == ServiceRole.GALAXY:
            return "Galaxy"
        elif svc_role == ServiceRole.GALAXY_POSTGRES:
            return "Postgres"
        elif svc_role == ServiceRole.GALAXY_REPORTS:
            return "GalaxyReports"
        elif svc_role == ServiceRole.AUTOSCALE:
            return "Autoscale"
        elif svc_role == ServiceRole.PSS:
            return "PSS"
        elif svc_role == ServiceRole.GALAXY_DATA:
            return "galaxyData"
        elif svc_role == ServiceRole.GALAXY_INDICES:
            return "galaxyIndices"
        elif svc_role == ServiceRole.GALAXY_TOOLS:
            return "galaxyTools"
        elif svc_role == ServiceRole.GENERIC_FS:
            return "GenericFS"
        elif svc_role == ServiceRole.TRANSIENT_NFS:
            return "TransientNFS"
        else:
            raise Exception("Unrecognized role {0}. Cannot convert to string".format(svc_role))

    @staticmethod
    def fulfills_roles(svc_roles, list_to_check):
        """
        Iterates through the list of services ``list_to_check`` and if any
        service in that list is present in ``svc_roles`` list, return ``True``.
        Else, return ``False``.
        """
        for role in list_to_check:
            if role in svc_roles:
                return True
        return False

    @staticmethod
    def legacy_convert(name):
        """
        Legacy name to role conversion support. Supports the conversion of
        known service names such as SGE, galaxyData, galaxyTools etc. to role types.
        """
        known_roles = ServiceRole.from_string([name])
        if not known_roles:
            known_roles = [ServiceRole.GENERIC_FS]
        return ServiceRole.to_string(known_roles)


class ServiceDependency(object):
    """
    Represents a dependency that another service required for its function.
    A service dependency may have the following attributes:
    owning_service - The parent service whose dependency this instance describes.
    service_role - The specific roles that this instance of the service is playing.
                   For example, there may be multiple File System services
                   providing/fulfilling different requirements
    assigned_service - Represents the service currently assigned to fulfill this dependency.
    """
    def __init__(self, owning_service, service_role, assigned_service=None):
        self._owning_service = owning_service
        self._service_role = service_role
        self._assigned_service = assigned_service

    @property
    def owning_service(self):
        return self._owning_service

    @property
    def service_type(self):
        return ServiceRole.get_type(self._service_role)

    @property
    def service_role(self):
        return self._service_role

    @property
    def assigned_service(self):
        return self._assigned_service

    @assigned_service.setter
    def assigned_service(self, value):
        self._assigned_service = value

    def is_satisfied_by(self, service):
        """
        Determines whether this service dependency is satisfied by a given service
        """
        return self.service_role in service.svc_roles

    
class Service( object):

    def __init__( self, app, service_type=None ):
        self.app = app
        self.state = service_states.UNSTARTED
        self.last_state_change_time = dt.datetime.utcnow()
        self.name = None
        self.svc_roles = []
        self.reqs = []

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
            # log.debug("Trying to add service '%s'" % self.name)
            self.state = service_states.STARTING
            self.last_state_change_time = dt.datetime.utcnow()
            failed_prereqs = [] # List of service prerequisites that have not been satisfied
            for dependency in self.reqs:
                #log.debug("'%s' service checking its prerequisite '%s:%s'" \
                #   % (self.get_full_name(), ServiceRole.to_string(dependency.service_role), dependency.owning_service.name))
                for svc in self.app.manager.services:
                    #log.debug("Checking service %s state." % svc.name)
                    if dependency.is_satisfied_by(svc):
                        #log.debug("Service %s:%s running: %s" % (svc.name, svc.name, svc.running()))
                        if not svc.running():
                            failed_prereqs.append(svc.get_full_name())
            if len(failed_prereqs) == 0:
                log.info("{0} service prerequisites OK; starting the service".format(self.get_full_name()))
                self.start()
                return True
            else:
                log.debug("{0} service prerequisites are not yet satisfied, missing: {2}. "\
                        "Setting {0} service state to '{1}'"\
                        .format(self.get_full_name(), service_states.UNSTARTED, failed_prereqs))
                # Reset state so it get picked back up by monitor
                self.state = service_states.UNSTARTED
                return False

    def remove(self):
        """
        Recursively removes a service and all services that depend on it.
        Child classes which override this method should ensure this is called
        for proper removal of service dependencies.
        """
        log.debug("Removing dependencies of service: {0}".format(self.name))
        for service in self.app.manager.services:
            for dependency in service.reqs:
                if (dependency.is_satisfied_by(self)):
                    log.debug("Dependency {0} found. Removing...".format(service.name))
                    service.remove()

    def running(self):
        """
        Return ``True`` is service is in state ``RUNNING``, ``False`` otherwise
        """
        return self.state == service_states.RUNNING

    def get_full_name(self):
        """
        Return full name of the service (useful if different from service type)
        """
        return self.name
