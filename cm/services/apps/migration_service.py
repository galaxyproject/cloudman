import os
from cm.services import ServiceRole
from cm.services import service_states
from cm.services import ServiceDependency
from cm.services import ServiceType
from cm.services.apps import ApplicationService
from cm.util import misc, paths

import logging
log = logging.getLogger('cloudman')


class Migrate1to2:
    """Functionality for upgrading from version 1 to 2.
    """
    def __init__(self, app):
        self.app = app

    def _as_postgres(self, cmd):
        return misc.run('%s - postgres -c "%s"' % (paths.P_SU, cmd))

    def _upgrade_postgres_8_to_9(self):
        data_dir = os.path.join(self.app.path_resolver.galaxy_data, "pgsql", "data")
        if os.path.exists(data_dir):
            with open(os.path.join(data_dir, "PG_VERSION")) as in_handle:
                version = in_handle.read().strip()
            if version.startswith("8"):
                log.info("Upgrading Postgres from version 8 to 9")
                old_debs = ["http://launchpadlibrarian.net/102366400/postgresql-client-8.4_8.4.11-1_amd64.deb",
                            "http://launchpadlibrarian.net/102366396/postgresql-8.4_8.4.11-1_amd64.deb"]
                for deb in old_debs:
                    misc.run("wget %s" % deb)
                    misc.run("dpkg -i %s" % os.path.basename(deb))
                    misc.run("rm -f %s" % os.path.basename(deb))
                backup_dir = os.path.join(self.app.path_resolver.galaxy_data, "pgsql",
                                          "data-backup-v%s" % version)
                self._as_postgres("mv %s %s" % (data_dir, backup_dir))
                self._as_postgres("%s/initdb %s" % (self.app.path_resolver.pg_home, data_dir))
                self._as_postgres("pg_createcluster -d %s %s old_galaxy" % (backup_dir, version))
                self._as_postgres("pg_upgradecluster %s old_galaxy %s" % (version, data_dir))
                misc.run("apt-get remove postgresql-8.4 postgresql-client-8.4")

    def _move_postgres_location(self):
        old_dir = os.path.join(self.app.path_resolver.galaxy_data, "pgsql")
        if os.path.exists(old_dir) and not os.path.exists(self.app.path_resolver.psql_dir):
            log.info("Moving Postgres location from %s to %s" %
                     (old_dir, self.app.path_resolver.psql_dir))
            misc.run("mv %s %s" % (old_dir, self.app.path_resolver.psql_dir))

    def _upgrade_database(self):
        self._upgrade_postgres_8_to_9()
        self._move_postgres_location()

    def _copy_to_new_fs(self):
        fs_galaxy_data = self.app.manager.get_services(svc_role=ServiceRole.GALAXY_DATA)[0]
        fs_galaxy_tools = self.app.manager.get_services(svc_role=ServiceRole.GALAXY_TOOLS)[0]
        source_path = os.path.join(fs_galaxy_tools.mount_point, "tools")
        target_path = os.path.join(fs_galaxy_data.mount_point, "tools")
        misc.run("cp -R {0} {1}".format(source_path, target_path))

        source_path = os.path.join(fs_galaxy_tools.mount_point, "galaxy-central")
        target_path = os.path.join(fs_galaxy_data.mount_point, "galaxy-app")
        misc.run("cp -R {0} {1}".format(source_path, target_path))

    def _create_missing_dirs(self):
        # TODO: on the file system missing/renamig dirs: galaxyData/'files' will need to be renamed to galaxy/data'
        pass

    def _upgrade_fs_structure(self):
        self._copy_to_new_fs()
        self._create_missing_dirs()

    def _adjust_stored_paths(self):
        # Adjust galaxy mercurial location for future updates
        galaxy_data_loc = self.app.manager.get_services(svc_role=ServiceRole.GALAXY_DATA)[0].mount_point
        galaxy_loc = os.path.join(galaxy_data_loc, "galaxy-app")
        if os.path.isdir(galaxy_loc):
            misc.run("sed -i 's/central/dist/' %ss/.hg/hgrc" % galaxy_loc)

    def _update_user_data(self):
        if 'filesystems' in self.app.ud:
            old_fs_list = self.app.ud['filesystems']
            new_fs_list = []
            # clear 'services' and replace with the new format
            for fs in old_fs_list:
                svc_roles = ServiceRole.from_string_array(fs['roles'])
                if ServiceRole.GALAXY_TOOLS in svc_roles and ServiceRole.GALAXY_DATA in svc_roles:
                    # This condition should only occur in new configs, but check
                    # added so that things work properly even if run against a new config
                    # Only works for default configs though...
                    new_fs_list.append(fs)
                elif ServiceRole.GALAXY_TOOLS in svc_roles:
                    pass  # skip adding the galaxy tools file system, no longer needed.
                else:
                    if ServiceRole.GALAXY_DATA in ServiceRole.from_string_array(fs['roles']):
                        fs['roles'] = ServiceRole.to_string_array([ServiceRole.GALAXY_TOOLS, ServiceRole.GALAXY_DATA])
                        new_fs_list.append(fs)
                    else:
                        new_fs_list.append(fs)
            self.app.ud['filesystems'] = new_fs_list
        self.app.ud['cloudman_version'] = 2


class MigrationService(ApplicationService, Migrate1to2):
    def __init__(self, app):
        super(MigrationService, self).__init__(app)

        self.svc_roles = [ServiceRole.MIGRATION]
        self.name = ServiceRole.to_string(ServiceRole.MIGRATION)
        # Wait for galaxy data & indices to come up before attempting migration
        self.reqs = [ServiceDependency(self, ServiceRole.GALAXY_DATA),
                     ServiceDependency(self, ServiceRole.GALAXY_TOOLS),
                     ServiceDependency(self, ServiceRole.GALAXY_INDICES)]

    def start(self):
        """
        Start the migration service
        """
        log.debug("Starting migration service...")
        self.state = service_states.STARTING
        if self._is_migration_needed():
            self.state = service_states.RUNNING
            self._start()
            self.state = service_states.SHUT_DOWN
        else:
            log.debug("No migration required. Service not started.")
            self.state = service_states.SHUT_DOWN


    def _start(self):
        """
        Do the actual work
        """
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

    def _migrate1_prereqs_satisfied(self):
        # TODO: Check whether galaxy data has sufficient space to accommodate tools dir
        return False

    def migrate_1(self):
        if not self._migrate1_prereqs_satisfied():
            log.debug("Cannot migrate from version 1 to 2. Pre-requisites not satisfied.")
            return

        log.debug("Migrating from version 1 to 2...")
        log.debug("Migration: Step 1: Upgrading Postgres Database...")
        self._upgrade_database()
        log.debug("Migration: Step 2: Upgrading to new file system structure...")
        self._upgrade_fs_structure()
        log.debug("Migration: Step 3: Adjusting paths in configuration files...")
        self._adjust_stored_paths()
        log.debug("Migration: Step 4: Updating user data...")
        self._update_user_data()
        log.debug("Migration: Step 5: Shutting down all file system services...")
        fs_svcs = self.app.manager.get_services(svc_type=ServiceType.FILE_SYSTEM)
        # TODO: Is a clean necessary?
        for svc in fs_svcs:
            svc.remove()

        log.debug("Migration: Step 6: Migration: Restarting all file system services...")
        # Restart file system services
        self.app.manager.add_preconfigured_services()
        log.debug("Migration from version 1 to 2 complete!")

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
