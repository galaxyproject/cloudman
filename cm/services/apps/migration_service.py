import os
import pwd
import grp
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

    def _as_postgres(self, cmd, cwd=None):
        return misc.run('%s - postgres -c "%s"' % (paths.P_SU, cmd), cwd=cwd)

    def _upgrade_postgres_8_to_9(self):
        old_data_dir = os.path.join(self.app.path_resolver.galaxy_data, "pgsql", "data")
        new_data_dir = self.app.path_resolver.psql_dir
        if old_data_dir == new_data_dir:
            log.debug("Nothing to upgrade in database - paths are the same: %s" % old_data_dir)
            return

        if os.path.exists(old_data_dir):
            with open(os.path.join(old_data_dir, "PG_VERSION")) as in_handle:
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
                self._as_postgres("mv %s %s" % (old_data_dir, backup_dir))
                misc.run("mkdir -p %s" % new_data_dir)
                os.chown(new_data_dir, pwd.getpwnam("postgres")[2], grp.getgrnam("postgres")[2])
                self._as_postgres("%s/initdb %s" % (self.app.path_resolver.pg_home,
                    new_data_dir))
                self._as_postgres("sed -i 's|#port = 5432|port = {0}|' {1}"
                                  .format(paths.C_PSQL_PORT, os.path.join(new_data_dir, 'postgresql.conf')))
                # Seems to require a start and stop before the upgrade can work!
                log_loc = os.path.join(new_data_dir, 'cm_postgres_upgrade.log')
                self._as_postgres("{0}/pg_ctl -w -l {1} -D {2} start".
                                  format(self.app.path_resolver.pg_home, log_loc, new_data_dir),
                                  cwd=new_data_dir)
                self._as_postgres("{0}/pg_ctl -w -l {1} -D {2} stop".
                                  format(self.app.path_resolver.pg_home, log_loc, new_data_dir),
                                  cwd=new_data_dir)
                self._as_postgres("{0}/pg_upgrade -d {1} -D {2} -p 5840 -P {3} -b /usr/lib/postgresql/8.4/bin"
                                  " -B {0} -l {4}".
                                  format(self.app.path_resolver.pg_home, backup_dir,
                                         new_data_dir, paths.C_PSQL_PORT, log_loc),
                                  cwd=new_data_dir)
                misc.run("apt-get -y --force-yes remove postgresql-8.4 postgresql-client-8.4")

    def _upgrade_database(self):
        self._upgrade_postgres_8_to_9()

    def _as_galaxy(self, cmd):
        return misc.run('%s - galaxy -c "%s"' % (paths.P_SU, cmd))

    def _copy_to_new_fs(self):
        fs_galaxy_data = self.app.manager.get_services(svc_role=ServiceRole.GALAXY_DATA)[0]
        fs_galaxy_tools = self.app.manager.get_services(svc_role=ServiceRole.GALAXY_TOOLS)[0]
        source_path = os.path.join(fs_galaxy_tools.mount_point, "tools")
        target_path = os.path.join(fs_galaxy_data.mount_point, "tools")
        self._as_galaxy("cp -R {0} {1}".format(source_path, target_path))

        source_path = os.path.join(fs_galaxy_tools.mount_point, "galaxy-central")
        target_path = os.path.join(fs_galaxy_data.mount_point, "galaxy-app")
        if (os.path.exists(target_path)):
            log.debug("Target path galaxy-app already exists! Skipping...")
        else:
            self._as_galaxy("cp -R {0} {1}".format(source_path, target_path))

    def _create_missing_dirs(self):
        # TODO: on the file system missing/renamig dirs: galaxyData/'files' will
        # need to be renamed to galaxy/data'
        pass

    def _upgrade_fs_structure(self):
        self._copy_to_new_fs()
        self._create_missing_dirs()

    def _adjust_stored_paths(self):
        # Adjust galaxy mercurial location for future updates
        galaxy_data_loc = self.app.manager.get_services(svc_role=ServiceRole.GALAXY_DATA)[0].mount_point
        galaxy_loc = os.path.join(galaxy_data_loc, "galaxy-app")
        if os.path.isdir(galaxy_loc):
            self._as_galaxy("sed -i 's/central/dist/' %s" % os.path.join(galaxy_loc, '.hg', 'hgrc'))
        # Adjust tools location in galaxy
        galaxy_ini_loc = os.path.join(galaxy_loc, 'universe_wsgi.ini')
        self._as_galaxy("sed -i 's|tool_dependency_dir = /mnt/galaxyTools/tools|tool_dependency_dir = {0}|' {1}".
                        format(os.path.join(galaxy_data_loc, 'tools'), galaxy_ini_loc))

        self._as_galaxy("sed -i 's|database_connection = postgres://galaxy@localhost:5840/galaxy|database_connection = postgres://galaxy@localhost:{0}/galaxy|' {1}".
                        format(paths.C_PSQL_PORT, galaxy_ini_loc))

    def _update_user_data(self):
        if 'filesystems' in self.app.ud:
            old_fs_list = self.app.ud.get('filesystems') or []
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
                        fs['roles'] = ServiceRole.to_string_array([ServiceRole.GALAXY_TOOLS,
                            ServiceRole.GALAXY_DATA])
                        new_fs_list.append(fs)
                    else:
                        new_fs_list.append(fs)
            self.app.ud['filesystems'] = new_fs_list
        self.app.ud['deployment_version'] = 2
        self.app.ud.pop('galaxy_home', None)  # TODO: Galaxy home is always reset
                                              # to default. Discuss implications

    def _migrate1_prereqs_satisfied(self):
        """
        Make sure prerequisites for applying migration 1 to 2 are satisfied.
        """
        # 'Old' AMIs do not support this CloudMan version so guard against those
        old_AMIs = ['ami-da58aab3', 'ami-9a7485f3', 'ami-46d4792f']
        current_ami = self.app.cloud_interface.get_ami()
        if current_ami in old_AMIs:
            msg = ("The Machine Image you are running ({0}) does not support this version "
                   "of CloudMan. You MUST terminate this instance and launch a new "
                   "one using a more up-to-date Machine Image. See "
                   "<a href='http://wiki.galaxyproject.org/CloudMan/' target='_blank'>"
                   "this page</a> for more details.".format(current_ami))
            log.critical(msg)
            self.app.msgs.critical(msg)
            return False
        fs_galaxy_data_list = self.app.manager.get_services(svc_role=ServiceRole.GALAXY_DATA)
        if not fs_galaxy_data_list:
            log.warn("Required File system GALAXY_DATA missing. Aborting migrate1to2.")
            return False
        fs_galaxy_tools_list = self.app.manager.get_services(svc_role=ServiceRole.GALAXY_TOOLS)
        if not fs_galaxy_tools_list:
            log.warn("Required File system GALAXY_TOOLS missing. Aborting Aborting migrate1to2.")
            return False
        # Get a handle to the actual service objects
        fs_galaxy_data = fs_galaxy_data_list[0]
        fs_galaxy_tools = fs_galaxy_tools_list[0]
        space_available = int(fs_galaxy_data.size) - int(fs_galaxy_data.size_used)
        if space_available < int(fs_galaxy_tools.size_used):
            log.debug("Cannot migrate from 1 to 2: Insufficient space available on "
                      "Galaxy data volume. Available: {0}, Required: {1}"
                      .format(space_available, fs_galaxy_tools.size_used))
            return False
        for svc in self.app.manager.get_services(svc_type=ServiceType.FILE_SYSTEM):
            if ServiceRole.GALAXY_TOOLS in svc.svc_roles and ServiceRole.GALAXY_DATA in svc.svc_roles:
                log.warn("File system appears to have been already migrated! Aborting.")
                return False
        return True

    def migrate_1to2(self):
        # First set the current ``deployment_version``, in case it's empty.
        # This is to prevent it from being set to the latest version when empty
        self.app.ud['deployment_version'] = 1

        if not self._migrate1_prereqs_satisfied():
            msg = "Cannot migrate from version 1 to 2. Pre-requisites not satisfied!"
            log.warn(msg)
            self.app.msgs.warning(msg)
            return False

        msg = ("Migrating this deployment from version 1 to 2. Note that this "
               "may take a while. Please wait until the process completes before "
               "starting to use any services or features.")
        log.info(msg)
        self.app.msgs.info(msg)
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
            svc.remove(synchronous=True)
        log.debug("Migration: Step 6: Migration: Restarting all file system services...")
        # Restart file system services
        self.app.manager.add_preconfigured_filesystems()
        # Migration 1 to 2 complete
        msg = ("Migration from version 1 to 2 complete! Please continue to wait "
               "until all the services have completed initializing.")
        log.info(msg)
        self.app.msgs.info(msg)
        return True


class MigrationService(ApplicationService, Migrate1to2):
    def __init__(self, app):
        super(MigrationService, self).__init__(app)

        self.svc_roles = [ServiceRole.MIGRATION]
        self.name = ServiceRole.to_string(ServiceRole.MIGRATION)

        self.dependencies = []

        if 'filesystems' in self.app.ud:
            for fs in self.app.ud.get('filesystems') or []:
                # Wait for galaxy data, indices and tools to come up before attempting migration
                if ServiceRole.GALAXY_DATA in ServiceRole.from_string_array(fs['roles']):
                    self.dependencies.append(ServiceDependency(self, ServiceRole.GALAXY_DATA))
                if ServiceRole.GALAXY_TOOLS in ServiceRole.from_string_array(fs['roles']):
                    self.dependencies.append(ServiceDependency(self, ServiceRole.GALAXY_TOOLS))
                if ServiceRole.GALAXY_INDICES in ServiceRole.from_string_array(fs['roles']):
                    self.dependencies.append(ServiceDependency(self, ServiceRole.GALAXY_INDICES))

    def start(self):
        """
        Start the migration service
        """
        log.debug("Starting migration service...")
        self.state = service_states.STARTING
        if self._is_migration_needed():
            self.state = service_states.RUNNING
            try:
                self._start()
            except Exception, e:
                log.error("Error starting migration service: {0}".format(e))
                self.state = service_states.ERROR
            else:
                self.state = service_states.COMPLETED
        else:
            log.debug("No migration required. Service complete.")
            self.state = service_states.COMPLETED

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
        if self._get_old_version() <= 1:
            self.migrate_1to2()

    def _is_migration_needed(self):
        return self._get_old_version() < self._get_current_version()

    def _get_current_version(self):
        version = 2
        log.debug("Current deployment version: {0}".format(version))
        return version  # Whichever version that this upgrade script last understands

    def _get_old_version(self):
        # TODO: Need old version discovery. Where do we get that from?
        version = self.app.ud.get('deployment_version', None)
        if not version:
            version = 1  # A version prior to version number being introduced
        log.debug("Old deployment version: {0}".format(version))
        return version

    def remove(self, synchronous=False):
        """
        Remove the migration service
        """
        log.info("Removing Migration service")
        super(MigrationService, self).remove(synchronous)
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
