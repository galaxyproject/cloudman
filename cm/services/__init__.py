"""
The base services package; all CloudMan services derive from this class.
"""
import datetime as dt
import logging

from cm.util.bunch import Bunch

log = logging.getLogger('cloudman')

service_states = Bunch(
    UNSTARTED="Unstarted",
    WAITING_FOR_USER_ACTION="Waiting for user action",
    CONFIGURING="Configuring",
    STARTING="Starting",
    RUNNING="Running",
    COMPLETED="Completed",
    SHUTTING_DOWN="Shutting down",
    SHUT_DOWN="Shut down",
    ERROR="Error"
)


class ServiceType(object):
    FILE_SYSTEM = "FileSystem"
    APPLICATION = "Application"
    CM_SERVICE = "CloudManService"


class ServiceRole(object):
    JOB_MANAGER = {'type': ServiceType.APPLICATION, 'name': "Job manager"}
    SGE = {'type': ServiceType.APPLICATION, 'name': "Sun Grid Engine"}
    SLURMCTLD = {'type': ServiceType.APPLICATION, 'name': "Slurmctld"}
    SLURMD = {'type': ServiceType.APPLICATION, 'name': "Slurmd"}
    GALAXY = {'type': ServiceType.APPLICATION, 'name': "Galaxy"}
    GALAXY_POSTGRES = {'type': ServiceType.APPLICATION, 'name':
                       "Postgres DB for Galaxy"}
    GALAXY_REPORTS = {'type': ServiceType.APPLICATION, 'name':
                      "Galaxy Reports"}
    AUTOSCALE = {'type': ServiceType.CM_SERVICE, 'name': "Autoscale"}
    PSS = {'type': ServiceType.CM_SERVICE, 'name': "Post Start Script"}
    GALAXY_DATA = {'type': ServiceType.FILE_SYSTEM, 'name': "Galaxy Data FS"}
    GALAXY_INDICES = {'type': ServiceType.FILE_SYSTEM, 'name':
                      "Galaxy Indices FS"}
    GALAXY_TOOLS = {'type': ServiceType.FILE_SYSTEM, 'name': "Galaxy Tools FS"}
    GENERIC_FS = {'type': ServiceType.FILE_SYSTEM, 'name': "Generic FS"}
    TRANSIENT_NFS = {'type': ServiceType.FILE_SYSTEM, 'name':
                     "Transient NFS FS"}
    HADOOP = {'type': ServiceType.APPLICATION, 'name': "Hadoop Service"}
    MIGRATION = {'type': ServiceType.CM_SERVICE, 'name': "Migration Service"}
    HTCONDOR = {'type': ServiceType.APPLICATION, 'name': "HTCondor Service"}
    PULSAR = {'type': ServiceType.APPLICATION, 'name': "Pulsar Service"}

    PROFTPD = {'type': ServiceType.APPLICATION, 'name': "ProFTPd Service"}

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
        roles_list = roles_str.split(",")
        for val in roles_list:
            role = ServiceRole._role_from_string(val.strip())
            if role:
                svc_roles.append(role)
        return svc_roles

    @staticmethod
    def from_string_array(roles_str_array):
        """
        Convert a list of roles as strings ``roles_str`` into a list of
        ``ServiceRole`` objects and return that list.
        """
        if not isinstance(roles_str_array, list):  # preserve backward compatibility
            return ServiceRole.from_string(roles_str_array)
        else:
            svs_roles = []
            for role in roles_str_array:
                svs_roles = svs_roles + ServiceRole.from_string(role)
            return svs_roles

    @staticmethod
    def _role_from_string(val):
        if val == "SGE":
            return ServiceRole.SGE
        elif val == "SLURMCTLD":
            return ServiceRole.SLURMCTLD
        elif val == "SLURMD":
            return ServiceRole.SLURMD
        elif val == "JOB_MANAGER":
            return ServiceRole.JOB_MANAGER
        elif val == "Galaxy":
            return ServiceRole.GALAXY
        elif val == "Postgres":
            return ServiceRole.GALAXY_POSTGRES
        elif val == "GalaxyReports":
            return ServiceRole.GALAXY_REPORTS
        elif val == "Pulsar":
            return ServiceRole.PULSAR
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
        elif val == "Hadoop":
            return ServiceRole.HADOOP
        elif val == "Migration":
            return ServiceRole.MIGRATION
        elif val == "HTCondor":
            return ServiceRole.HTCONDOR
        elif val == "ProFTPd":
            return ServiceRole.PROFTPD
        else:
            log.warn(
                "Attempt to convert unknown role name from string: {0}".format(val))
            return None

    @staticmethod
    def to_string(svc_roles):
        if not isinstance(svc_roles, list):
            svc_roles = [svc_roles]  # Not a list, therefore, convert to list
        str_roles = ""
        for role in svc_roles:
            if role:
                str_roles = str_roles + "," + ServiceRole._role_to_string(role)
        return str_roles[1:]  # strip leading comma

    @staticmethod
    def to_string_array(svc_roles):
        return [ServiceRole.to_string(role) for role in svc_roles]

    @staticmethod
    def _role_to_string(svc_role):
        if svc_role == ServiceRole.SGE:
            return "SGE"
        elif svc_role == ServiceRole.SLURMCTLD:
            return "Slurmctld"
        elif svc_role == ServiceRole.SLURMD:
            return "Slurmd"
        elif svc_role == ServiceRole.JOB_MANAGER:
            return "Job manager"
        elif svc_role == ServiceRole.GALAXY:
            return "Galaxy"
        elif svc_role == ServiceRole.GALAXY_POSTGRES:
            return "Postgres"
        elif svc_role == ServiceRole.GALAXY_REPORTS:
            return "GalaxyReports"
        elif svc_role == ServiceRole.PULSAR:
            return "Pulsar"
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
        elif svc_role == ServiceRole.HTCONDOR:
            return "HTCondor"
        elif svc_role == ServiceRole.HADOOP:
            return "Hadoop"
        elif svc_role == ServiceRole.MIGRATION:
            return "Migration"
        elif svc_role == ServiceRole.PROFTPD:
            return "ProFTPd"
        else:
            raise Exception(
                "Unrecognized role {0}. Cannot convert to string".format(svc_role))

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
        known_roles = ServiceRole.from_string(name)
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

    def __repr__(self):
        return "<ServiceRole:{0},Owning:{1},Assigned:{2}>".format(
            ServiceRole.to_string(self.service_role),
            "None" if self.owning_service is None else self.owning_service.name,
            "None" if self.assigned_service is None else self.assigned_service.name)

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


class Service(object):

    def __init__(self, app, service_type=None):
        self.app = app
        self.state = service_states.UNSTARTED
        self.last_state_change_time = dt.datetime.utcnow()
        self.name = None
        self.svc_roles = []
        self.dependencies = []

    def start(self):
        raise NotImplementedError("Subclasses of Service must implement this.")

    def add(self):
        """
        Add a given service to the pool of services managed by CloudMan, giving
        CloudMan the ability to monitor and control the service. This is a base
        implementation of the service ``add`` method which calls service's internal
        ``start`` method. Before calling the ``start`` method, service prerequisites
        are checked and, if satisfied, the service is started. If the prerequisites
        are not satisfied, the service is set to state ``UNSTARTED``.
        """
        if self.state != service_states.RUNNING:
            # log.debug("Trying to add service '%s'" % self.name)
            self.state = service_states.STARTING
            self.last_state_change_time = dt.datetime.utcnow()
            failed_prereqs = self.dependencies[:]
            # List of service prerequisites that have not been satisfied
            for dependency in self.dependencies:
                # log.debug("'%s' service checking its prerequisite '%s:%s'" \
                #   % (self.get_full_name(), ServiceRole.to_string(dependency.service_role), dependency.owning_service.name))
                no_services_satisfy_dependency = True
                remove_dependency = False
                for svc in self.app.manager.services:
                    # log.debug("Checking service %s state." % svc.name)
                    if dependency.is_satisfied_by(svc):
                        no_services_satisfy_dependency = False
                        # log.debug("Service %s:%s running: %s" % (svc.name,
                        # svc.name, svc.state))
                        if svc.running() or svc.completed():
                            remove_dependency = True
                if no_services_satisfy_dependency:
                    if self.app.ud.get("ignore_unsatisfiable_dependencies", False):
                        remove_dependency = True
                    else:
                        # Fall into infinite loop.
                        pass
                if remove_dependency and dependency in failed_prereqs:
                    failed_prereqs.remove(dependency)
            if len(failed_prereqs) == 0:
                log.info("{0} service prerequisites OK; starting the service".format(
                    self.get_full_name()))
                self.start()
                return True
            else:
                log.debug("{0} service prerequisites are not yet satisfied, waiting for: {2}. "
                          "Setting {0} service state to '{1}'"
                          .format(self.get_full_name(), service_states.UNSTARTED, failed_prereqs))
                # Reset state so it get picked back up by monitor
                self.state = service_states.UNSTARTED
                return False

    def remove(self, synchronous=False):
        """
        Recursively removes a service and all services that depend on it.
        Child classes which override this method should ensure this is called
        for proper removal of service dependencies.
        """
        log.debug("Removing dependencies of service: {0}".format(self.name))
        for service in self.app.manager.services:
            for dependency in service.dependencies:
                if (dependency.is_satisfied_by(self)):
                    service.remove()

    def running(self):
        """
        Return ``True`` is service is in state ``RUNNING``, ``False`` otherwise
        """
        return self.state == service_states.RUNNING

    def completed(self):
        """
        Return ``True`` is service is in state ``COMPLETED``, ``False`` otherwise
        """
        return self.state == service_states.COMPLETED

    def get_full_name(self):
        """
        Return full name of the service (useful if different from service type)
        """
        return "{0}".format(self.name)
