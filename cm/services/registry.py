"""A Registry of CloudMan services"""
import os
import glob
import importlib
import pyclbr

import logging
log = logging.getLogger('cloudman')


class ServiceRegistry(object):

    def __init__(self, app):
        self.app = app
        self.services = {}
        self.directories = ['cm/services']

    def __iter__(self):
        return iter(self.services)

    def iteritems(self):
        return iter(self.services.iteritems())

    def itervalues(self):
        return iter(self.services.itervalues())

    def get(self, service_name):
        """
        A getter method for retrieving a service object based on the
        `service_name`. If a service with the given name is not found,
        return `None`.
        """
        return self.services.get(service_name, None)

    def get_active(self, service_name):
        """
        Given a `service_name`, check of the given service exists in the
        registry and if it is active. If so, return a handle to the service
        object. Otherwise, return `None`.
        """
        if self.get(service_name) and self.is_active(service_name):
            return self.get(service_name)
        return None

    def active(self, service_type=None, service_role=None):
        """
        An iterator of currently `active` service objects, possibly filtered based on
        provided arguments. Note that either of the arguments can be provided
        but not both (if both are provided, `service_role` takes precedence).

        :type   service_type: cm.services.ServiceType
        :param  service_type: If provided, filter only services of the specified
                              type.

        :type   service_role: cm.services.ServiceRole
        :param  service_role: If provided, filter only services having the
                              specified role.
        """
        active = []
        for service in self.itervalues():
            if service.activated:
                if service_role and service_role in service.svc_roles:
                    active.append(service)
                elif service_type and service_type == service.svc_type:
                    active.append(service)
                elif not service_role and not service_type:
                    active.append(service)
        # log.debug("Active services (filtered by type: {0}; role: {1}): {2}"
        #           .format(service_type, service_role, active))
        return iter(active)

    def is_active(self, service_name):
        """
        Indicate if the service with `service_name` is active.
        """
        service = self.services.get(service_name, None)
        if service and self.services[service_name].activated:
            return True
        return False

    def __repr__(self):
        return "ServiceRegistry"

    def register(self, service_object):
        """
        Explicitly register (ie. add) a `service_object` with the registry.
        The `service_object` needs to be an instantiated instance of the
        service object.
        """
        try:
            service_name = service_object.name
            log.debug("Registering service {0} with the registry".format(
                      service_name))
            if service_name not in self.services:
                self.services[service_name] = service_object
                return True
            else:
                log.warning("Service {0} already exists in the registry."
                            .format(service_name))
        except Exception, e:
            log.error("Service object {0} does not have name attribute: {1}"
                      .format(service_object, e))
        return False

    def load_service(self, service_path):
        """
        Load the service class pointed to by `service_path` and return an
        object of the service.
        """
        log.debug("Loading service class in module '{0}'".format(service_path))
        module_name = os.path.splitext(os.path.basename(service_path))[0]
        module_dir = os.path.dirname(service_path)
        module = (os.path.splitext(service_path)[0]).replace('/', '.')
        # Figure out the class name for the service
        module_classes = pyclbr.readmodule(module_name, [module_dir])
        # log.debug("Module {0} classes: {1}".format(module_name, module_classes))
        service_class_name = None
        for c in module_classes.iterkeys():
            if c.lower() == ('{0}service'.format(module_name)).lower():
                service_class_name = c
                break
        # log.debug('service_class_name: %s' % service_class_name)
        # Import the service module and instantiate the service class
        service = None
        if service_class_name:
            log.debug("Importing service name {0} as module {1}".format(
                      service_class_name, module))
            service_module = importlib.import_module(module)
            service = getattr(service_module, service_class_name)(self.app)
        else:
            log.warning("Could not extract service class name from module at {0}"
                        .format(service_path))
        # log.debug("Loaded service {0}".format(service))
        return service

    def load_services(self):
        """
        Load all service classes found in `cm/services/` into the service
        registry. Return a dictionary of loaded services. Each element of the
        dictionary contains the service name as the key and the service object
        as the value.

        :rtype: dictionary
        :returns: loaded services
        """
        log.debug("Initiating loading of services")
        for service_path in self.find_services():
            try:
                service = self.load_service(service_path)
                if service and service.name not in self.services:
                    self.services[service.name] = (service)
                    log.debug("Loaded service {0}".format(service.name))
                elif service and service.name in self.services:
                    # Reload instead of skip?
                    log.warning('Service with name {0} already exists. Skipping.'
                        .format(service.name))
                else:
                    log.warning('Could not load service at {0}'.format(service_path))
            except Exception, e:
                log.warning('Exception loading service at {0}'.format(e))
        return self.services

    def find_services(self):
        """
        Return the directory paths of service classes within `self.directories`.
        Paths are considered a service path if they pass `self.is_service`.

        :rtype: string generator
        :returns: paths of valid services
        """
        for directory in self.directories:
            # log.debug("1 Looking in dir {0}".format(directory))
            for dl in os.walk(directory):  # dl = directory listing
                # log.debug(" 2 Walking dir {0}".format(dl))
                for sp in glob.glob(os.path.join(dl[0], '*.py')):  # sp = service path
                    # log.debug("   3 Found py file {0}".format(sp))
                    if self.is_service(sp):
                        yield sp

    def is_service(self, service_path):
        """
        Determines whether the given filesystem path contains a service class.

        :type   service_path: string
        :param  service_path: relative filesystem path to the potential service

        :rtype: bool
        :returns: `True` if the path contains a service; `False` otherwise
        """
        service_name = os.path.splitext(os.path.basename(service_path))[0]
        # Look for a definition of the service class that matches the service
        # file name
        if "class {0}service".format(service_name) in open(service_path).read().lower():
            # log.debug("    4 {0} is in fact a service impl".format(service_path))
            return True
        # log.debug("    5 {0} is not a service impl".format(service_path))
        return False
