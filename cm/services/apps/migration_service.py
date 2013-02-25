import os
from cm.services import ServiceRole
from cm.services import service_states
from cm.services import ServiceDependency
from cm.services import ServiceType
from cm.services.apps import ApplicationService

import logging
log = logging.getLogger('cloudman')


class MigrationService(ApplicationService):
    def __init__(self, app):
        super(MigrationService, self).__init__(app)
        self.svc_roles = [ServiceRole.MIGRATION]
        self.name = ServiceRole.to_string(ServiceRole.MIGRATION)
        # Wait for galaxy data & indices to come up before attempting migration
        self.reqs = [ServiceDependency(self, ServiceRole.GALAXY_DATA),
                     ServiceDependency(self, ServiceRole.GALAXY_INDICES)]

    def start(self):
        """
        Start the migration service
        """
        log.debug("Starting migration service...")
        self.state = service_states.STARTING
        self._start()
        self.state = service_states.RUNNING

    def _start(self):
        """
        Do the actual work
        """
        if self._is_migration_needed():
            log.debug("Migration is required. Starting...")
            self._perform_migration()

    def _perform_migration(self):
        """
        Based on the version number, carry out appropriate migration actions
        """
        if self._get_old_cm_version() <= 1:
            self.migrate_1()

    def _is_migration_needed(self):
        return self._get_old_cm_version() < self._get_new_cm_version()

    def _get_new_cm_version(self):
        return 2  # Whichever version that this upgrade script last understands

    def _get_old_cm_version(self):
        # TODO: Need old version discovery. Where do we get that from?
        version = self.app.ud.get('cloudman_version', None)
        if version is None:
            version = 1  # A version prior to version number being introduced

    def migrate_1(self):
        log.debug("Migrating from version 1 to 2...")
        # mount file systems from persistent_data.yaml
        # Upgrade DB
        # copy tools FS to the data FS
        # adjust directory names/paths to match the new FS structure
        # sed for predefined full old paths (eg, Galaxy's env.sh files, EMBOSS tools?)
        # create new directory structure with any missing dirs
        # unmount file systems from persistent_data.yaml
        # update persistent_data.yaml

        # Finally - shutdown all filesystem services
        log.debug("Migration: Shutting down all file system services...")
        fs_svcs = self.app.manager.get_services(svc_type=ServiceType.FILE_SYSTEM)
        # TODO: Is a clean necessary?
        for svc in fs_svcs:
            svc.remove()

        log.debug("Migration: Restarting all file system services...")
        # Restart file system services
        self.app.manager.add_preconfigured_services()

    def remove(self):
        """
        Remove the migration service
        """
        log.info("Removing Migration service")
        self.state = service_states.SHUTTING_DOWN
        self._clean()
        self.state = service_states.SHUT_DOWN

    def _clean(self):
        """
        Clean up the system
        """
        pass

    def status(self):
        """
        Check and update the status of service
        """
        pass
