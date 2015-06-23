"""Galaxy CM master manager"""
import commands
import datetime as dt
import logging
import logging.config
import os
import shutil
import subprocess
import threading
import time

import git

from cm.instance import Instance
from cm.services import ServiceRole
from cm.services import ServiceType
from cm.services import service_states
from cm.services.registry import ServiceRegistry
from cm.services.data.filesystem import Filesystem
from cm.util import cluster_status, comm, misc, Time
from cm.util.decorators import TestFlag, cluster_ready
from cm.util.manager import BaseConsoleManager
import cm.util.paths as paths

from boto.exception import EC2ResponseError, S3ResponseError

log = logging.getLogger('cloudman')

s3_rlock = threading.RLock()


def synchronized(rlock):
    """
        Synchronization decorator
        http://stackoverflow.com/a/490090
    """
    def wrap(f):
        def newFunction(*args, **kw):
            with rlock:
                return f(*args, **kw)
        return newFunction
    return wrap


class ConsoleManager(BaseConsoleManager):
    node_type = "master"

    def __init__(self, app):
        self.startup_time = Time.now()
        log.debug("Initializing console manager - cluster start time: %s" %
                  self.startup_time)
        self.app = app
        self.console_monitor = ConsoleMonitor(self.app)
        self.root_pub_key = None
        self.cluster_status = cluster_status.STARTING
        self.num_workers_requested = 0  # Number of worker nodes requested by user
        # The actual worker nodes (note: this is a list of Instance objects)
        # (because get_worker_instances currently depends on tags, which is only
        # supported by EC2, get the list of instances only for the case of EC2 cloud.
        # This initialization is applicable only when restarting a cluster.
        self.worker_instances = self.get_worker_instances() if (
            self.app.cloud_type == 'ec2' or self.app.cloud_type == 'openstack') else []
        self.manager_started = False
        self.cluster_manipulation_in_progress = False
        # If this is set to False, the master instance will not be an execution
        # host in SGE and thus not be running any jobs
        self.master_exec_host = True
        self.initial_cluster_type = None
        self.cluster_storage_type = None
        self.service_registry = ServiceRegistry(self.app)
        self.services = []
        self.default_galaxy_data_size = 0

    @property
    def num_cpus(self):
        """
        The number of CPUs on the master instance (as ``int``), as returned by
        ``/usr/bin/nproc`` command.
        """
        return int(commands.getoutput("/usr/bin/nproc"))

    @property
    def total_memory(self):
        """
        Return the total amount of memory (ie, RAM) on this instance, in bytes.
        """
        return int(misc.meminfo().get('total', 1))

    def activate_master_service(self, new_service):
        """
        Mark the `new_service` as *activated* in the service registry, which
        will in turn trigger the service start.

        :type   new_service: object
        :param  new_service: an instance object of the service to activate
        """
        ok = True
        if not new_service:
            log.warning("Tried to activate a master service but no service received")
            return False
        # File system services get explicitly added into the registry. This is
        # because multiple file systems correspond to the same service
        # implementation class.
        if new_service.svc_type == ServiceType.FILE_SYSTEM and \
           new_service.name not in self.service_registry.services:
            log.debug("Adding a new file system service into the registry: {0}"
                      .format(new_service.name))
            ok = self.service_registry.register(new_service)
        if ok:
            # Activate the service
            service = self.service_registry.services.get(new_service.name, None)
            if service:
                log.debug("Activating service {0}".format(new_service.name))
                service.activated = True
                self._update_dependencies(new_service, "ADD")
            else:
                log.debug("Could not find service {0} to activate?!".format(
                          new_service.name))
        else:
            log.warning("Did not activate service {0}".format(new_service))

    def deactivate_master_service(self, service_to_remove, immediately=False):
        """
        Deactivate the `service_to_remove`, updating its dependencies in the
        process.

        :type   service_to_remove: object
        :param  service_to_remove: an instance object of the service to remove

        :type   immediately: bool
        :param  immediately: If set, initiate the service removal process
                             right away. Otherwise, the monitor thread will
                             initiate it the next time it runs.
        """
        service = self.service_registry.get(service_to_remove.name)
        if service:
            log.debug("Deactivating service {0}".format(service_to_remove.name))
            service.activated = False
            self._update_dependencies(service_to_remove, "REMOVE")
            if immediately:
                self.console_monitor._stop_services()
        else:
            log.debug("Could not find service {0} to deactivate?!".format(
                      service_to_remove.name))

    def _update_dependencies(self, new_service, action):
        """
        Updates service dependencies when a new service is added.
        Iterates through all services and if action is "ADD",
        and the newly added service fulfills the requirements of an
        existing service, sets the new service as the service assigned
        to fulfill the existing service.
        If the action is "REMOVE", then the dependent service's
        assigned service property is set to null for all services
        which depend on the new service.
        """
        log.debug("{0} dependencies for service {1}".format(action, new_service.name))
        for svc in self.service_registry.active():
            if action == "ADD":
                for req in new_service.dependencies:
                    if req.is_satisfied_by(svc):
                        # log.debug("Service {0} has a dependency on role {1}. "
                        #           "Dependency updated during service action: {2}"
                        #           .format(req.owning_service.name, new_service.name,
                        #                   action))
                        req.assigned_service = svc
            elif action == "REMOVE":
                for req in svc.dependencies:
                    if req.is_satisfied_by(new_service):
                        # log.debug("Service {0} has a dependency on role {1}. "
                        #           "Dependency updated during service action: {2}"
                        #           .format(req.owning_service.name, new_service.name,
                        #                   action))
                        req.assigned_service = None

    def _stop_app_level_services(self):
        """
        A convenience function that suspends job manager jobs, removes Galaxy &
        Postgres services, allowing system level operations to be performed.
        """
        # Suspend all job manager jobs
        log.debug("Suspending job manager queue")
        for job_manager_svc in self.app.manager.service_registry.active(
                service_role=ServiceRole.JOB_MANAGER):
            job_manager_svc.suspend_queue()
        # Stop application-level services managed via CloudMan
        # If additional service are to be added as things CloudMan can handle,
        # the should be added to do for-loop list (in order in which they are
        # to be removed)
        if self.initial_cluster_type == 'Galaxy':
            njssn = ServiceRole.to_string(ServiceRole.NODEJSPROXY)
            njss = self.service_registry.get(njssn)
            if njss:
                njss.remove()
            # Remove Postgres service, which will (via dependency management)
            # remove higher-level services
            pgsn = ServiceRole.to_string(ServiceRole.GALAXY_POSTGRES)
            pgs = self.service_registry.get(pgsn)
            if pgs:
                pgs.remove()

    def _start_app_level_services(self):
        # Resume application-level services managed via CloudMan
        # If additional service are to be added as things CloudMan can handle,
        # the should be added to do outer-most for-loop.
        als = []
        if self.initial_cluster_type == 'Galaxy':
            als = ['Postgres', 'ProFTPd', 'Galaxy', 'GalaxyReports', 'NodeJSProxy']
        log.debug("Activating app-level services: {0}".format(als))
        for svc_name in als:
            svc = self.service_registry.get(svc_name)
            if svc:
                # Activate only and the Monitor will pick it up to start it
                svc.activated = True
                log.debug("'activated' service {0}.".format(svc_name))
        log.debug("Unsuspending job manager queue")
        for job_manager_svc in self.app.manager.service_registry.active(
                service_role=ServiceRole.JOB_MANAGER):
            job_manager_svc.unsuspend_queue()

    def recover_monitor(self, force='False'):
        if self.console_monitor:
            if force == 'True':
                self.console_monitor.shutdown()
            else:
                return False
        self.console_monitor = ConsoleMonitor(self.app)
        self.console_monitor.start()
        return True

    def snapshot_status(self):
        """
        Get the status of a file system volume currently being snapshoted. This
        method looks through all the file systems and all volumes assoc. with a
        file system and returns the status and progress for thee first volume
        going through the snapshot process.
        In addition, if a file system is marked as needing to 'grow' or sharing
        the cluster is currently pending but no volumes are currently being
        snapshoted, the method returns 'configuring' as the status.

        :rtype: array of strings of length 2
        :return: A pair of values as strings indicating (1) the status (e.g.,
        pending, complete) of the snapshot and (2) the progress.
        """
        fsarr = self.get_services(svc_type=ServiceType.FILE_SYSTEM)
        for fs in fsarr:
            for vol in fs.volumes:
                if vol.snapshot_status is not None:
                    return (vol.snapshot_status, vol.snapshot_progress)
            # No volume is being snapshoted; check if waiting to 'grow' one
            if fs.grow:
                return ("configuring", None)
        if self.cluster_manipulation_in_progress:
            return ("configuring", None)
        return (None, None)

    @TestFlag([])
    @synchronized(s3_rlock)
    def load_legacy_snapshot_data(self):
        """
        Retrieve and return information about the default filesystems.
        This is done by retrieving ``snaps.yaml`` from the default bucket and
        parsing it to match the current cloud, region, and deployment.
        Returns a list of dictionaries.
        """
        s3_conn = self.app.cloud_interface.get_s3_connection()
        snaps_file = 'cm_snaps.yaml'
        snaps = []
        cloud_name = self.app.config.cloud_name
        # Get a list of default file system data sources
        validate = True if self.app.cloud_type == 'ec2' else False
        if s3_conn and misc.get_file_from_bucket(s3_conn, self.app.config['bucket_default'],
           'snaps.yaml', snaps_file, validate=validate):
            pass
        elif misc.get_file_from_public_location(self.app.config, 'snaps.yaml', snaps_file):
            log.warn("Couldn't get snaps.yaml from bucket: {0}. However, managed "
                     "to retrieve it from public location '{1}' instead."
                     .format(self.app.config['bucket_default'],
                             (self.app.config.get('default_bucket_url') or
                              self.app.config['bucket_default'])))
        else:
            log.error("Couldn't get snaps.yaml at all! Will not be able to create Galaxy Data and Index volumes.")
            return []

        snaps_file = misc.load_yaml_file(snaps_file)
        if 'static_filesystems' in snaps_file:
            # Old snaps.yaml format
            snaps = snaps_file['static_filesystems']
            # Convert the old format into the new one and return a
            # uniform snaps dict
            for f in snaps:
                f['name'] = f['filesystem']  # Rename the key
                f.pop('filesystem', None)  # Delete the old key
        else:
            # Unify all Amazon regions and/or name variations to a single one
            if 'amazon' in cloud_name:
                cloud_name = 'amazon'
            for cloud in snaps_file['clouds']:
                if cloud_name == cloud['name'].lower():
                    current_cloud = cloud
                    for r in current_cloud['regions']:
                        if r['name'].lower() == self.app.cloud_interface.get_region_name().lower():
                            for d in r['deployments']:
                                # TODO: Make the deployment name a UD option
                                if d['name'] == 'GalaxyCloud':
                                    snaps = d['filesystems']

        log.debug("Loaded default snapshot data for cloud {1}: {0}".format(snaps, cloud_name))
        return snaps

    @TestFlag(10)
    def get_default_data_size(self):
        if not self.default_galaxy_data_size:
            for fs_template in self.app.config.filesystem_templates:
                roles = ServiceRole.from_string_array(fs_template['roles'])
                if ServiceRole.GALAXY_DATA in roles:
                    if 'size' in fs_template:
                        self.default_galaxy_data_size = fs_template['size']
                    elif 'snap_id' in fs_template:
                        try:
                            self.snapshot = (self.app.cloud_interface.get_ec2_connection()
                                             .get_all_snapshots([fs_template['snap_id']])[0])
                            self.default_galaxy_data_size = self.snapshot.volume_size
                        except EC2ResponseError, e:
                            log.warning("Could not get snapshot {0} size (setting the "
                                        "value to 10): {1}".format(fs_template['snap_id'], e))
                            self.default_galaxy_data_size = 10
                    log.debug("Got default galaxy FS size as {0}GB".format(
                        self.default_galaxy_data_size))
        return str(self.default_galaxy_data_size)

    @TestFlag(15)
    def transient_fs_size(self):
        """
        Return the size of transient file system, in GBs.
        """
        fs_svc = self.service_registry.get_active('transient_nfs')
        if fs_svc:
            return fs_svc.size
        return -1

    @TestFlag(False)
    def start(self):
        """
        This method is automatically called as CloudMan starts; it tries to add
        and start available cluster services (as provided in the cluster's
        configuration and persistent data).
        """
        log.debug("Config Data at manager start, with secret_key and password "
                  "filtered out: %s" % dict((k, self.app.config[k])
                                            for k in self.app.config.keys()
                                            if k not in ['password', 'secret_key', 'freenxpass', 'access_key']))

        self._handle_prestart_commands()
        # Generating public key before any worker has been initialized
        # This is required for configuring Hadoop the main Hadoop worker still needs to be
        # bale to ssh into itself!!!
        # this should happen before SGE is added
        self.get_root_public_key()

        # Always add migration service
        self.activate_master_service(self.service_registry.get('Migration'))

        # Activate Nginx service
        self.activate_master_service(self.service_registry.get('Nginx'))

        # Activate Supervisor service
        self.activate_master_service(self.service_registry.get('Supervisor'))

        # Always add a job manager service
        # Starting with Ubuntu 14.04, we transitioned to using Slurm
        cmd = "cat /etc/lsb-release | grep DISTRIB_RELEASE | cut -f2 -d'='"
        os_release = str(misc.run(cmd)).strip()
        if os_release in ['14.04']:
            log.debug("Running on Ubuntu {0}; using Slurm as the cluster job manager"
                      .format(os_release))
            self.activate_master_service(self.service_registry.get('Slurmctld'))
            self.activate_master_service(self.service_registry.get('Slurmd'))
            self.service_registry.remove('SGE')  # SGE or Slurm can exist, not both
            self.service_registry.remove('Hadoop')  # Hadoop works only w/ SGE
        else:
            log.debug("Running on Ubuntu {0}; using SGE as the cluster job manager"
                      .format(os_release))
            # from cm.services.apps.jobmanagers.sge import SGEService
            self.activate_master_service(self.service_registry.get('SGE'))
            self.service_registry.remove('Slurmctld')  # SGE or Slurm can exist, not both
            self.service_registry.remove('Slurmd')

        # Always share instance transient storage over NFS
        tfs = Filesystem(self.app, 'transient_nfs', svc_roles=[ServiceRole.TRANSIENT_NFS])
        tfs.add_transient_storage()
        self.activate_master_service(tfs)
        # Always add PSS service - note that this service runs only after the cluster
        # type has been selected and all of the services are in RUNNING state
        self.activate_master_service(self.service_registry.get('PSS'))

        if self.app.config.condor_enabled:
            self.activate_master_service(self.service_registry.get('HTCondor'))
        else:
            self.service_registry.remove('HTCondor')
        # KWS: Optionally add Hadoop service based on config setting
        if self.app.config.hadoop_enabled:
            self.activate_master_service(self.service_registry.get('Hadoop'))
        # Check if starting a derived cluster and initialize from share,
        # which calls add_preconfigured_services
        # Note that share_string overrides everything.
        if "share_string" in self.app.config:
            # BUG TODO this currently happens on reboot, and shouldn't.
            self.init_shared_cluster(self.app.config['share_string'].strip())
        # else look if this is a restart of a previously existing cluster
        # and add appropriate services
        elif not self.add_preconfigured_services():
            return False
        # If we have any workers (might be the case following a cluster reboot),
        # reboot the workers so they get embedded into the cluster again
        if self.worker_instances:
            for wi in self.worker_instances:
                wi.reboot(count_reboot=False)
        self.manager_started = True

        # Check if a previously existing cluster is being recreated or if it is a new one
        if not self.initial_cluster_type:  # this can get set by _handle_old_cluster_conf_format
            self.initial_cluster_type = self.app.config.get('cluster_type', None)
            self.userdata_cluster_type = self.app.config.get('initial_cluster_type', None)
            self.cluster_storage_type = self.app.config.get('cluster_storage_type', None)
            if self.initial_cluster_type is not None:
                cc_detail = "Configuring a previously existing cluster of type {0}"\
                    .format(self.initial_cluster_type)
            elif self.userdata_cluster_type:
                cc_detail = "Configuring a predefined cluster of type {0}"\
                    .format(self.userdata_cluster_type)
                self.init_cluster_from_user_data()
            else:
                cc_detail = "This is a new cluster; waiting to configure the type."
                self.cluster_status = cluster_status.WAITING
        else:
            cc_detail = "Configuring an old existing cluster of type {0}"\
                .format(self.initial_cluster_type)
        # Add master's private IP to /etc/hosts (workers need it and
        # master's /etc/hosts is being synced to the workers)
        misc.add_to_etc_hosts(self.app.cloud_interface.get_private_ip(),
                              [self.app.cloud_interface.get_local_hostname(),
                               misc.get_hostname(),
                               'master'])
        # Set the default hostname
        misc.set_hostname(self.app.cloud_interface.get_local_hostname())
        log.info("Completed the initial cluster startup process. {0}".format(
            cc_detail))
        return True

    def handle_prestart_commands(self):
        """
        Inspect the user data key ``master_prestart_commands`` and simply
        execute any commands provided there.

        For example::
            master_prestart_commands:
              - "mkdir -p /mnt/galaxyData/pgsql/"
              - "mkdir -p /mnt/galaxyData/tmp"
              - "chown -R galaxy:galaxy /mnt/galaxyData"
        """
        for command in self.app.config.get("master_prestart_commands", []):
            misc.run(command)

    @TestFlag(False)
    def add_preconfigured_services(self):
        """
        Inspect the cluster configuration and persistent data to add any
        previously defined cluster services.
        """
        log.debug("Checking for and adding any previously defined cluster services")
        return self.add_preconfigured_filesystems() and self.add_preloaded_services()

    def add_preconfigured_filesystems(self):
        try:
            # Process the current cluster config
            log.debug("Processing filesystems in an existing cluster config")
            attached_volumes = self.get_attached_volumes()
            if 'filesystems' in self.app.config:
                for fs in self.app.config.get('filesystems') or []:
                    err = False
                    filesystem = Filesystem(self.app, fs['name'], svc_roles=ServiceRole.from_string_array(
                        fs['roles']), mount_point=fs.get('mount_point', None))
                    # Based on the kind, add the appropriate file system. We can
                    # handle 'volume', 'snapshot', or 'bucket' kind
                    if fs['kind'] == 'volume':
                        if 'ids' not in fs and 'size' in fs:
                            # We're creating a new volume
                            filesystem.add_volume(size=fs['size'])
                        else:
                            # A volume already exists so use it
                            for vol_id in fs['ids']:
                                filesystem.add_volume(vol_id=vol_id)
                    elif fs['kind'] == 'snapshot':
                        for snap in fs['ids']:
                            # Check if an already attached volume maps to this snapshot
                            att_vol = self.get_vol_if_fs(attached_volumes, fs['name'])
                            if att_vol:
                                filesystem.add_volume(vol_id=att_vol.id,
                                                      size=att_vol.size,
                                                      from_snapshot_id=att_vol.snapshot_id)
                            else:
                                filesystem.add_volume(from_snapshot_id=snap)
                    elif fs['kind'] == 'nfs':
                        filesystem.add_nfs(fs['nfs_server'], None, None, mount_options=fs.get('mount_options', None))
                    elif fs['kind'] == 'gluster':
                        filesystem.add_glusterfs(fs['gluster_server'], mount_options=fs.get('mount_options', None))
                    elif fs['kind'] == 'transient':
                        filesystem.add_transient_storage(persistent=True)
                    elif fs['kind'] == 'bucket':
                        a_key = fs.get('access_key', None)
                        s_key = fs.get('secret_key', None)
                        # Can have only a single bucket per file system so
                        # access it directly
                        bucket_name = fs.get('ids', [None])[0]
                        if bucket_name:
                            filesystem.add_bucket(bucket_name, a_key, s_key)
                        else:
                            log.warning("No bucket name for file system {0}!".format(
                                fs['name']))
                    # TODO: include support for `nfs` kind
                    else:
                        # TODO: try to do some introspection on the device ID
                        # to guess the kind before err
                        err = True
                        log.warning("Device kind '{0}' for file system {1} not recognized; "
                                    "not adding the file system.".format(fs['kind'], fs['name']))
                    if not err:
                        log.debug("Adding a previously existing filesystem '{0}' of "
                                  "kind '{1}'".format(fs['name'], fs['kind']))
                        self.activate_master_service(filesystem)
            return True
        except Exception, e:
            log.error(
                "Error processing filesystems in existing cluster configuration: %s" % e)
            self.manager_started = False
            return False

    def add_preloaded_services(self):
        """
        Activate any previously available services. The list of preloaded
        services is extracted from the user data entry ``services``.

        Note that this method is automatically called when an existing cluster
        is being recreated.
        """
        log.debug("Activating previously-available application services from "
                  "an existing cluster config.")
        for service_name in self.app.config.get('services', []):
            if service_name.get('name', None):
                service = self.service_registry.get(service_name['name'])
                if service:
                    self.activate_master_service(service)
                else:
                    log.warning("Cannot find an instance of the previously "
                                "existing service {0} in the current service "
                                "registry?".format(service_name))
        return True

    def get_vol_if_fs(self, attached_volumes, filesystem_name):
        """
        Iterate through the list of (attached) volumes and check if any
        one of them match the current cluster name and filesystem (as stored
        in volume's tags). Return a matching volume (as a ``boto`` object) or
        ``None``.

        *Note* that this method returns the first matching volume and will thus
        not work for filesystems composed of multiple volumes.
        """
        for vol in attached_volumes:
            log.debug("Checking if vol '{0}' is file system '{1}'".format(
                vol.id, filesystem_name))
            if self.app.cloud_interface.get_tag(vol, 'clusterName') == self.app.config['cluster_name'] \
                    and self.app.cloud_interface.get_tag(vol, 'filesystem') == filesystem_name:
                log.debug("Identified attached volume '%s' as filesystem '%s'" % (
                    vol.id, filesystem_name))
                return vol
        return None

    def start_autoscaling(self, as_min, as_max, instance_type):
        """
        Activate the `Autoscale` service, setting the minimum number of worker
        nodes of maintain (`as_min`), the maximum number of worker nodes to
        maintain (`as_max`) and the `instance_type` to use.
        """
        if not self.service_registry.is_active('Autoscale'):
            as_svc = self.service_registry.get('Autoscale')
            if as_svc:
                as_svc.as_min = as_min
                as_svc.as_max = as_max
                as_svc.instance_type = instance_type
                self.activate_master_service(as_svc)
            else:
                log.warning('Cannot find Autoscale service?')
        else:
            log.debug("Autoscaling is already active.")

    def stop_autoscaling(self):
        """
        Deactivate the `Autoscale` service.
        """
        self.deactivate_master_service(self.service_registry.get('Autoscale'))

    def adjust_autoscaling(self, as_min, as_max):
        as_svc = self.get_services(svc_role=ServiceRole.AUTOSCALE)
        if as_svc:
            as_svc[0].as_min = int(as_min)
            as_svc[0].as_max = int(as_max)
            log.debug("Adjusted autoscaling limits; new min: %s, new max: %s" % (as_svc[
                      0].as_min, as_svc[0].as_max))
        else:
            log.debug(
                "Cannot adjust autoscaling because autoscaling is not on.")

    # DBTODO For now this is a quick fix to get a status.
    # Define what 'orange' would be, and don't just count on "Filesystem"
    # being the only data service.
    def get_data_status(self):
        fses = self.get_services(svc_type=ServiceType.FILE_SYSTEM)
        if fses != []:
            for fs in fses:
                if fs.state == service_states.ERROR:
                    return "red"
                elif fs.state != service_states.RUNNING:
                    return "orange"
            return "green"
        else:
            return "gray"

    def get_app_status(self):
        count = 0
        for svc in self.service_registry.active(service_type=ServiceType.APPLICATION):
            count += 1
            if svc.state == service_states.ERROR:
                return "red"
            elif not (svc.state == service_states.RUNNING or svc.state == service_states.COMPLETED):
                return "orange"
        if count != 0:
            return "green"
        else:
            return "gray"

    def get_services(self, svc_type=None, svc_role=None, svc_name=None):
        """
        Returns a list of all services that best match given service type, role
        and name. If service name is specified, it is matched first.
        Next, if a role is specified, returns all services containing that role.
        Lastly, if svc_role is ``None``, but a ``svc_type`` is specified, returns
        all services matching type.
        """
        svcs = []
        for service_name, service in self.service_registry.iteritems():
            if service_name == svc_name:
                return [service]
            elif svc_role in service.svc_roles:
                svcs.append(service)
            elif service.svc_type == svc_type and svc_role is None:
                svcs.append(service)
        return svcs

    def get_srvc_status(self, srvc):
        """
        Get the status a service ``srvc``. If the service is not a recognized as
        a CloudMan-service, return ``Service not recognized``. If the service is
        not currently running (i.e., not currently recognized by CloudMan as a
        service it should be managing), return ``Service not found``.
        """
        svcarr = self.get_services(svc_name=srvc)
        svcarr = [s for s in svcarr if (s.svc_type == ServiceType.FILE_SYSTEM or ServiceRole.fulfills_roles(
            s.svc_roles, [ServiceRole.GALAXY, ServiceRole.SGE, ServiceRole.GALAXY_POSTGRES]))]
        if len(svcarr) > 0:
            return srvc[0].state
        else:
            return "'%s' is not running" % srvc
        return "Service '%s' not recognized." % srvc

    @TestFlag([{"size_used": "184M", "status": "Running", "kind": "Transient",
                "mount_point": "/mnt/transient_nfs", "name": "transient_nfs", "err_msg": None,
                "device": "/dev/vdb", "size_pct": "1%", "DoT": "Yes", "size": "60G",
                "persistent": "No"},
               {"size_used": "33M", "status": "Running", "kind": "Volume",
                "mount_point": "/mnt/galaxyData", "name": "galaxyData", "snapshot_status": None,
                "err_msg": None, "snapshot_progress": None, "from_snap": "snap-galaxyFS",
                "volume_id": "vol-0000000d", "device": "/dev/vdc", "size_pct": "4%",
                "DoT": "No", "size": "1014M", "persistent": "Yes",
                "snapshots_created": ['snap-gFSsnp1', 'snap-gFSsnp2', 'snap-gFSsnp3']},
               {"size_used": "560M", "status": "Running", "kind": "Snapshot",
                "mount_point": "/mnt/galaxyIndices", "name": "galaxyIndices",
                "snapshot_status": None, "err_msg": None, "snapshot_progress": None,
                "from_snap": "snap-indicesFS", "volume_id": "vol-0000000i",
                "device": "/dev/vdd", "size_pct": "55%", "DoT": "Yes", "size": "1014M",
                "persistent": "No", "snapshots_created": []},
               {"size_used": "52M", "status": "Configuring", "kind": "Volume",
                "mount_point": "/mnt/galaxyData", "name": "galaxyDataResize",
                "snapshot_status": "pending", "err_msg": None, "persistent": "Yes",
                "snapshot_progress": "10%", "from_snap": "snap-760fd33d",
                "volume_id": "vol-d5f3f9a9", "device": "/dev/sdh", "size_pct": "2%",
                "DoT": "No", "size": "5.0G"}], quiet=True)
    def get_all_filesystems_status(self):
        """
        Get a list and information about each of the file systems currently
        managed by CloudMan.
        """
        fss = []
        fs_svcs = self.get_services(svc_type=ServiceType.FILE_SYSTEM)
        for fs in fs_svcs:
            fss.append(fs.get_details())
        return fss

        # return []

        # TEMP only; used to alternate input on the UI
        # r = random.choice([1, 2, 3])
        r = 4
        log.debug("Dummy random #: %s" % r)
        dummy = [{"name": "galaxyData",
                  "status": "Running",
                  "device": "/dev/sdg1",
                  "kind": "volume",
                  "mount_point": "/mnt/galaxyData",
                  "DoT": "No",
                  "size": "20G",
                  "size_used": "2G",
                  "size_pct": "90%",
                  "error_msg": None,
                  "volume_id": "vol-dbi23ins"}]
        if r == 2 or r == 4:
            dummy.append(
                {"name": "1000g", "status": "Removing", "bucket_name": "1000genomes",
                 "kind": "bucket", "mount_point": "/mnt/100genomes", "DoT": "No",
                 "size": "N/A", "NFS_shared": True, "size_used": "", "size_pct": "", "error_msg": None})
        if r == 3:
            dummy[0]['status'] = "Adding"
        if r == 4:  # NGTODO: Hardcoded links below to tools and indices?
            dummy.append({"name": "galaxyTools", "status": "Available",
                          "device": "/dev/sdg3", "kind": "snapshot",
                          "mount_point": "/mnt/galaxyTools", "DoT": "Yes",
                          "size": "10G", "size_used": "1.9G", "size_pct": "19%",
                          "error_msg": None, "from_snap": "snap-bdr2whd"})
            dummy.append({"name": "galaxyIndices", "status": "Error", "device":
                          "/dev/sdg2", "kind": "snapshot", "mount_point":
                          "/mnt/galaxyIndices", "DoT": "Yes", "size": "700G",
                          "NFS_shared": True, "size_used": "675G", "size_pct":
                          "96%", "error_msg": "Process returned 2", "from_snap":
                          "snap-89r23hd"})
            dummy.append({"name": "custom", "status": "Available", "device":
                          "/dev/sdg4", "kind": "Volume", "mount_point":
                          "/mnt/custom", "DoT": "No", "size": "70G",
                          "NFS_shared": True, "size_used": "53G", "size_pct":
                          "7%", "error_msg": ""})
        return dummy

    @TestFlag({"Slurmctld": "Running", "Postgres": "Running", "Galaxy": "TestFlag",
               "Filesystems": "Running"}, quiet=True)
    def get_all_services_status(self):
        """
        Return a dictionary containing a list of currently running service and
        their status.

        For example::
            {"Postgres": "Running", "SGE": "Running", "Galaxy": "Running",
            "Filesystems": "Running"}
        """
        status_dict = {}
        for srvc in self.service_registry.itervalues():
            status_dict[srvc.name] = srvc.state  # NGTODO: Needs special handling for file systems
        return status_dict

    def get_galaxy_rev(self):
        """
        Get the Git revision of the Galaxy instance that's running as a
        CloudMan-managed service.

        :rtype: dict
        :return: The following information about the repo: `hexsha`,
                 `authored_date`, `active_branch`, `repo_url`. If repo info
                 cannot be obtained, return an empty dict.
        """
        def _get_remote_url(repo):
            """
            Extract the URL for the `repo`'s 'origin' remote.
            """
            remote_url = None
            for remote in repo.remotes:
                if remote.name == 'origin':
                    remote_url = remote.config_reader.get('url')
                    if remote_url.find('.git') > -1:
                        remote_url = remote_url[0:-4]
                    if remote_url.find('git@') == 0:
                        remote_url = remote_url[4:]
                        remote_url = remote_url.replace(':', '/').rstrip('/')
                        remote_url = u'https://{0}'.format(remote_url)
            return remote_url

        repo = None
        repo_path = self.app.path_resolver.galaxy_home
        try:
            if os.path.exists(repo_path):
                repo = git.Repo(repo_path, odbt=git.GitCmdObjectDB)
            if repo and not repo.bare:
                hexsha = repo.head.commit.hexsha
                authored_date = time.strftime("%d %b %Y", time.gmtime(
                    repo.head.commit.authored_date))
                active_branch = repo.active_branch.name
                repo_url = _get_remote_url(repo)
                return {'hexsha': hexsha, 'authored_date': authored_date,
                        'active_branch': active_branch, 'repo_url': repo_url}
        except git.InvalidGitRepositoryError:
            log.debug("No git repository at {0}?".format(repo_path))
        return {}

    def get_galaxy_admins(self):
        admins = 'None'
        try:
            for cf in ['galaxy.ini', 'universe_wsgi.ini']:
                config_file_path = os.path.join(
                    self.app.path_resolver.galaxy_config_dir, cf)
                if os.path.exists(config_file_path):
                    break
            config_file = open(config_file_path, 'r').readlines()
            for line in config_file:
                if 'admin_users' in line:
                    admins = line.split('=')[1].strip()
                    break
        except IOError:
            pass
        return admins

    def get_permanent_storage_size(self):
        pss = 0
        fs_arr = self.get_services(svc_role=ServiceRole.GALAXY_DATA)
        for fs in fs_arr:
            for vol in fs.volumes:
                pss += int(vol.size)
        return pss

    def check_disk(self):
        """
        Check the usage of the main data disk and set appropriate object fields.

        Depending on the cluster type, check the usage of the main disk (for the
        'Test' cluster type, this is `/mnt/transient_nfs` dir and for the other
        cluster types it is `/mnt/galaxy`) and return a dictionary with
        appropriate values.

        :rtype: dictionary
        :return: A dictionary with keys `total`, `used`, and `used_percent` as
                 strings. Also included is a bool `updated` field, which
                 indicates if the disk status values were updated as part of
                 this function call.
        """
        disk_status = {'total': "0", 'used': "0", 'used_percent': "0%",
                       'updated': False}
        if self.initial_cluster_type == 'Galaxy':
            fs_svc = self.service_registry.get_active('galaxy')
        else:
            fs_svc = self.service_registry.get_active('transient_nfs')
        if fs_svc:
            cmd = ("df -h {0} | sed 1d | awk '{{print $2, $3, $5}}'"
                   .format(fs_svc.mount_point))
            disk_usage = misc.getoutput(cmd, quiet=True)
            disk_usage = disk_usage.split(' ')
            if len(disk_usage) == 3:
                disk_status = {'total': disk_usage[0],
                               'used': disk_usage[1],
                               'used_percent': disk_usage[2],
                               'updated': True}
        return disk_status

    def get_cluster_status(self):
        return self.cluster_status

    def toggle_master_as_exec_host(self, force_removal=False):
        """
            By default, the master instance running all the services is also
            an execution host and is used to run job manager jobs. This method
            allows you to toggle the master instance as being or not being
            an execution host.

            :type force_removal: bool
            :param force_removal: If True, go through the process of removing
                                  the instance from being an execution host
                                  irrespective of the instance's current state.

            :rtype: bool
            :return: ``True`` if the instance is set as an execution host;
                     ``False`` otherwise.
        """
        log.debug("Toggling master instance as exec host")
        for job_manager_svc in self.service_registry.active(
                service_role=ServiceRole.JOB_MANAGER):
            node_alias = 'master'
            node_address = self.app.cloud_interface.get_private_ip()
            if self.master_exec_host or force_removal:
                self.master_exec_host = False
                job_manager_svc.disable_node(node_alias, node_address)
            else:
                self.master_exec_host = True
                job_manager_svc.enable_node(node_alias, node_address)
        if self.master_exec_host:
            log.info("The master instance is set to execute jobs. "
                     "To manually change this, use the CloudMan Admin panel.")
        else:
            log.info("The master instance is set to *not* execute jobs. "
                     "To manually change this, use the CloudMan Admin panel.")
        return self.master_exec_host

    @TestFlag([])
    def get_worker_instances(self):
        instances = []
        log.debug("Trying to discover any worker instances associated with this cluster...")
        filters = {'tag:clusterName': self.app.config['cluster_name'],
                   'tag:role': 'worker'}
        try:
            reservations = self.app.cloud_interface.get_all_instances(filters=filters)
            for reservation in reservations:
                for inst in reservation.instances:
                    if inst.state != 'terminated' and inst.state != 'shutting-down':
                        i = Instance(self.app, inst=inst, m_state=inst.state, reboot_required=True)
                        instances.append(i)
                        log.info("Existing worker instance '%s' found alive "
                                 "(will configure it later)." % inst.id)
        except EC2ResponseError, e:
            log.debug("Error checking for live instances: %s" % e)
        return instances

    @TestFlag([])
    def get_attached_volumes(self):
        """
        Get a list of block storage volumes currently attached to this instance.
        """
        log.debug(
            "Trying to discover any volumes attached to this instance...")
        attached_volumes = []
        # TODO: Abstract filtering into the cloud interface classes
        try:
            if self.app.cloud_type == 'ec2':
                # filtering w/ boto is supported only with ec2
                f = {'attachment.instance-id':
                     self.app.cloud_interface.get_instance_id()}
                attached_volumes = self.app.cloud_interface.get_ec2_connection()\
                    .get_all_volumes(filters=f)
            else:
                volumes = self.app.cloud_interface.get_ec2_connection().get_all_volumes()
                for vol in volumes:
                    if vol.attach_data.instance_id == self.app.cloud_interface.get_instance_id():
                        attached_volumes.append(vol)
        except EC2ResponseError, e:
            log.debug("Error checking for attached volumes: %s" % e)
        log.debug("Attached volumes: %s" % attached_volumes)
        # Add ``clusterName`` tag to any attached volumes
        for att_vol in attached_volumes:
            self.app.cloud_interface.add_tag(att_vol, 'clusterName', self.app.config['cluster_name'])
        return attached_volumes

    @TestFlag(None)
    def shutdown(self, sd_apps=True, sd_filesystems=True, sd_instances=True,
                 sd_autoscaling=True, delete_cluster=False, sd_spot_requests=True,
                 rebooting=False):
        """
        Shut down this cluster. This means shutting down all the services
        (dependent on method arguments) and, optionally, deleting the cluster.

        .. seealso:: `~cm.util.master.delete_cluster`
        """
        log.debug("List of services before shutdown: {0}".format(
                  self.service_registry.services))
        self.cluster_status = cluster_status.SHUTTING_DOWN
        # Services need to be shut down in particular order
        if sd_autoscaling:
            self.stop_autoscaling()
        if sd_instances:
            self.stop_worker_instances()
        if sd_spot_requests:
            for wi in self.worker_instances:
                if wi.is_spot() and not wi.spot_was_filled():
                    wi.terminate()
        # full_svc_list = self.services[:]  # A copy to ensure consistency
        if sd_apps:
            for svc in self.get_services(svc_type=ServiceType.APPLICATION):
                if svc.activated:
                    log.debug("Initiating removal of service {0}".format(svc.name))
                    svc.remove()
                else:
                    log.debug("Service {0} not activated; not removing it."
                              .format(svc.get_full_name()))
        if sd_filesystems:
            for svc in self.get_services(svc_type=ServiceType.FILE_SYSTEM):
                log.debug("Initiating removal of file system service {0}".format(svc.name))
                svc.remove(synchronous=True, delete_devices=delete_cluster)
        # Wait for all the services to shut down before declaring the cluster shut down
        # (but don't wait indefinitely)
        # This is required becasue with the file systems being removed in parallel via
        # separate threads, those processes may not have completed by the time the
        # complete shutdown does.
        time_limit = 300  # wait for max 5 mins before shutting down
        while(time_limit > 0):
            log.debug("Waiting ({0} more seconds) for all the services to shut down.".format(
                time_limit))
            num_off = 0
            for srvc in self.services:
                if srvc.state == service_states.SHUT_DOWN or srvc.state == service_states.ERROR or \
                   srvc.state == service_states.UNSTARTED or srvc.state == service_states.COMPLETED:
                    num_off += 1
            if num_off == len(self.services):
                log.debug("All services shut down")
                break
            elif rebooting and self.app.cloud_type == 'ec2':
                # For the EC2 cloud it's ok to reboot with volumes attached
                log.debug("Not waiting for all the services to shut down because we're just rebooting.")
                break
            sleep_time = 6
            time.sleep(sleep_time)
            time_limit -= sleep_time
        # Automatically delete transient clusters on terminate (because no data
        # will persist so no point in poluting the list of buckets)
        if delete_cluster or (self.cluster_storage_type == 'transient' and not rebooting):
            self.delete_cluster()
            misc.remove(self.app.INSTANCE_PD_FILE)
        self.cluster_status = cluster_status.TERMINATED
        log.info("Cluster %s shut down at %s (uptime: %s). If not done automatically, "
                 "manually terminate the master instance (and any remaining instances "
                 "associated with this cluster) from the %s cloud console."
                 % (self.app.config['cluster_name'], Time.now(), (Time.now() - self.startup_time),
                    self.app.config.cloud_name))

    @TestFlag(False)
    def reboot(self, soft=False):
        """
        Reboot the entire cluster, first shutting down appropriate services.
        """
        # Spot requests cannot be tagged and thus there is no good way of associating those
        # back with a cluster after a reboot so cancel those
        log.debug("Initiating cluster reboot.")
        # Don't detach volumes only on the EC2 cloud
        sd_filesystems = True
        if self.app.cloud_type == 'ec2':
            sd_filesystems = False
        self.shutdown(sd_filesystems=sd_filesystems, sd_instances=False, rebooting=True)
        if soft:
            if misc.run("{0} restart".format(os.path.join(self.app.config['boot_script_path'],
               self.app.config['boot_script_name']))):
                return True
            else:
                log.error(
                    "Trouble restarting CloudMan softly; rebooting instance now.")
        ec2_conn = self.app.cloud_interface.get_ec2_connection()
        try:
            log.debug("Rebooting self now...")
            ec2_conn.reboot_instances(
                [self.app.cloud_interface.get_instance_id()])
            return True
        except EC2ResponseError, e:
            log.error("Error rebooting master instance (i.e., self): %s" % e)
        return False

    def terminate_master_instance(self, delete_cluster=False):
        """
        Terminate the master instance using the cloud middleware API.
        If ``delete_cluster`` is set to ``True``, delete all cluster
        components before terminating the instance.

        .. seealso:: `~cm.util.master.delete_cluster`
        """
        if self.cluster_status != cluster_status.TERMINATED:
            self.shutdown(delete_cluster=delete_cluster)
        log.debug("Terminating the master instance")
        self.app.cloud_interface.terminate_instance(
            self.app.cloud_interface.get_instance_id())

    def delete_cluster(self):
        """
        Completely delete this cluster. This involves deleting the cluster's
        bucket as well as volumes containing user data file system(s)! The
        list of volumes to be deleted can either be provided as an argument or,
        for the case of EC2 only, will be automatically derived.

        .. warning::

            This action is irreversible. All data will be permanently deleted.

        """
        log.info("All services shut down; deleting this cluster.")
        # Delete any remaining volume(s) assoc. w/ the current cluster
        try:
            if self.app.cloud_type == 'ec2':
                filters = {'tag:clusterName': self.app.config['cluster_name']}
                vols = self.app.cloud_interface.get_all_volumes(filters=filters)
                log.debug("Remaining volumes associated with this cluster: {0}".format(vols))
                for vol in vols:
                    if vol.status == 'available':
                        log.debug("As part of cluster deletion, deleting volume '%s'" % vol.id)
                        vol.delete()
                    else:
                        log.debug("Not deleting volume {0} because it is in state {1}"
                                  .format(vol.id, vol.status))
        except EC2ResponseError, e:
            log.error("Error deleting a volume: %s" % e)
        # Delete cluster bucket on S3
        s3_conn = self.app.cloud_interface.get_s3_connection()
        if s3_conn:
            misc.delete_bucket(s3_conn, self.app.config['bucket_cluster'])

    def clean(self):
        """
        Clean the system as if it was freshly booted. All services are shut down
        and any changes made to the system since service start are reverted (this
        excludes any data on user data file system).
        """
        log.debug("Cleaning the system - all services going down")
        # TODO: #NGTODO: Possibility of simply calling remove on ServiceType.FILE_SYSTEM
        # service so that all dependencies are automatically removed?
        svcs = self.get_services(svc_role=ServiceRole.GALAXY)
        for service in svcs:
            service.remove()
        svcs = self.get_services(svc_role=ServiceRole.GALAXY_POSTGRES)
        for service in svcs:
            service.remove()
        self.stop_worker_instances()
        svcs = self.get_services(svc_type=ServiceType.FILE_SYSTEM)
        for service in svcs:
            service.clean()
        svcs = self.get_services(svc_role=ServiceRole.SGE)
        for service in svcs:
            service.clean()

    def get_idle_instances(self):
        """
        Get a list of instances that are currently not executing any job manager
        jobs. Return a list of ``Instance`` objects.
        """
        # log.debug("Looking for idle instances")
        idle_instances = []  # List of Instance objects corresponding to idle instances
        for job_manager_svc in self.service_registry.active(
                service_role=ServiceRole.JOB_MANAGER):
            idle_nodes = job_manager_svc.idle_nodes()
            # Note that master is not part of worker_instances and will thus not
            # get included in the idle_instances list, which is the intended
            # behavior (because idle instances may get terminated and we don't
            # want the master to get terminated).
            for w in self.worker_instances:
                if w.alias in idle_nodes or w.local_hostname in idle_nodes:
                    idle_instances.append(w)
        # log.debug("Idle instaces: %s" % idle_instances)
        return idle_instances

    def remove_instances(self, num_nodes, force=False):
        """
        Remove a number (``num_nodes``) of worker instances from the cluster, first
        deciding which instance(s) to terminate and then removing them from SGE and
        terminating. An instance is deemed removable if it is not currently running
        any jobs.

        Note that if the number of removable instances is smaller than the
        number of instances requested to remove, the smaller number of instances
        is removed. This can be overridden by setting ``force`` to ``True``. In that
        case, removable instances are removed first, then additional instances are
        chosen at random and removed.
        """
        num_terminated = 0
        # First look for idle instances that can be removed
        idle_instances = self.get_idle_instances()
        if len(idle_instances) > 0:
            log.debug("Found %s idle instances; trying to remove %s." %
                      (len(idle_instances), num_nodes))
            for i in range(0, num_nodes):
                for inst in idle_instances:
                    if num_terminated < num_nodes:
                        self.remove_instance(inst.id)
                        num_terminated += 1
        else:
            log.info("No idle instances found")
        log.debug("Num to terminate: %s, num terminated: %s; force set to '%s'"
                  % (num_nodes, num_terminated, force))
        # If force is set, terminate requested number of instances regardless
        # whether they are idle
        if force is True and num_terminated < num_nodes:
            force_kill_instances = num_nodes - num_terminated
            log.info("Forcefully terminating %s instances." % force_kill_instances)
            for i in range(force_kill_instances):
                for inst in self.worker_instances:
                    if not inst.is_spot() or inst.spot_was_filled():
                        self.remove_instance(inst.id)
                        num_terminated += 1
        if num_terminated > 0:
            log.info("Initiated requested termination of instances. Terminating "
                     "'%s' instances." % num_terminated)
        else:
            log.info("Did not terminate any instances.")

    def remove_instance(self, instance_id=''):
        """
        Remove an instance with ID ``instance_id`` from the cluster. This means
        that the instance is first removed from the job manager as a worker and
        then it is terminated via the cloud middleware API.
        """
        if not instance_id:
            log.warning("Tried to remove an instance but did not receive instance ID")
            return False
        log.debug("Specific termination of instance '%s' requested." % instance_id)
        for inst in self.worker_instances:
            if inst.id == instance_id:
                inst.worker_status = 'Stopping'
                log.debug("Set instance {0} state to {1}".format(inst.get_desc(),
                          inst.worker_status))
                for job_manager_svc in self.service_registry.active(
                        service_role=ServiceRole.JOB_MANAGER):
                    job_manager_svc.remove_node(inst)
                # Remove the given instance from /etc/hosts files
                misc.remove_from_etc_hosts(inst.private_ip)
                self.sync_etc_hosts()
                # Terminate the instance
                inst.terminate()
                log.info("Initiated requested termination of instance. "
                         "Terminating '%s'." % instance_id)

    def reboot_instance(self, instance_id='', count_reboot=True):
        """
        Using cloud middleware API, reboot instance with ID ``instance_id``.
        ``count_reboot`` indicates whether this count should be counted toward
        the instance ``self.config.instance_reboot_attempts`` (see `Instance`
        `reboot` method).
        """
        if not instance_id:
            log.warning("Tried to reboot an instance but did not receive instance ID")
            return False
        log.info("Specific reboot of instance '%s' requested." % instance_id)
        for inst in self.worker_instances:
            if inst.id == instance_id:
                inst.reboot(count_reboot=count_reboot)
                log.info("Initiated requested reboot of instance. Rebooting '%s'."
                         % instance_id)

    def add_instances(self, num_nodes, instance_type='', spot_price=None):
        log.debug("Adding {0}{1} {2} instance(s)".format(num_nodes,
                  ' spot' if spot_price else '', instance_type))
        # Remove master from execution queue automatically
        if self.master_exec_host:
            self.toggle_master_as_exec_host(force_removal=True)
        self.app.cloud_interface.run_instances(num=num_nodes,
                                               instance_type=instance_type,
                                               spot_price=spot_price)

    def add_live_instance(self, instance_id):
        """
        Add an existing instance to the list of worker instances tracked by the
        master; get a handle to the instance object in the process.
        """
        try:
            log.debug("Adding live instance '%s'" % instance_id)
            reservation = self.app.cloud_interface.get_all_instances(instance_id)
            if reservation and len(reservation[0].instances) == 1:
                instance = reservation[0].instances[0]
                if instance.state != 'terminated' and instance.state != 'shutting-down':
                    i = Instance(self.app, inst=instance, m_state=instance.state)
                    self.app.cloud_interface.add_tag(instance, 'clusterName',
                                                     self.app.config['cluster_name'])
                    # Default to 'worker' role tag
                    self.app.cloud_interface.add_tag(instance, 'role', 'worker')
                    self.app.cloud_interface.add_tag(instance, 'Name', "Worker: {0}"
                                                     .format(self.app.config['cluster_name']))
                    self.worker_instances.append(i)
                    # Make sure info like ip-address and hostname are updated
                    i.send_alive_request()
                    log.debug('Added instance {0}....'.format(instance_id))
                else:
                    log.debug("Live instance '%s' is at the end of its life "
                              "(state: %s); not adding the instance." %
                              (instance_id, instance.state))
                return True
        except EC2ResponseError, e:
            log.debug("Problem adding a live instance (tried ID: %s): %s" %
                      (instance_id, e))
        except Exception, e:
            log.error("Exception adding a live instance (tried ID: %s): %s" %
                      (instance_id, e))
        return False

    @TestFlag({})
    def initialize_cluster_with_custom_settings(self, startup_opt, galaxy_data_option="custom-size",
                                                pss=None, shared_bucket=None):
        """
        Call this method if the current cluster has not yet been initialized to
        initialize it. This method should be called only once.

        For the ``startup_opt``, choose from ``Galaxy``, ``Data``,
        ``Test``, or ``Shared_cluster``. ``Galaxy`` and ``Data`` type also require
        an integer value for the ``pss`` argument, which will set the initial size
        of the persistent storage associated with this cluster. If ``Shared_cluster``
        ``startup_opt`` is selected, a share string for ``shared_bucket`` argument
        must be provided, which will then be used to derive this cluster from
        the shared one.
        """
        log.debug("initialize_cluster_with_custom_settings: cluster_type={0}, "
                  "data_option={1}, initial_pss_size={2}"
                  .format(startup_opt, galaxy_data_option, pss))
        if self.app.manager.initial_cluster_type is None:
            if startup_opt == "Test":
                self.app.manager.init_cluster(startup_opt, storage_type='transient')
                return None
            if startup_opt == "Galaxy" or startup_opt == "Data":
                # Initialize form on the main UI contains two fields named ``pss``,
                # which arrive as a list so pull out the actual storage size value
                if galaxy_data_option == "transient":
                    storage_type = "transient"
                    pss = 0
                elif galaxy_data_option == "custom-size":
                    storage_type = "volume"
                    if isinstance(pss, list):
                        ss = None
                        for x in pss:
                            if x:
                                ss = x
                        pss = ss
                else:
                    storage_type = "volume"
                    pss = str(self.app.manager.get_default_data_size())
                if storage_type == "transient" or (pss and pss.isdigit()):
                    pss_int = int(pss)
                    self.app.manager.init_cluster(startup_opt, pss_int, storage_type=storage_type)
                    return None
                else:
                    msg = "Wrong or no value provided for the persistent "\
                        "storage size: '{0}'".format(pss)
            elif startup_opt == "Shared_cluster":
                if shared_bucket:
                    # TODO: Check the format of the share string
                    self.app.manager.init_shared_cluster(shared_bucket.strip())
                    return None
                else:
                    msg = "For a shared cluster, you must provide shared bucket "\
                        "name; cluster configuration not set."
        else:
            msg = "Cluster already set to type '%s'" % self.app.manager.initial_cluster_type
        log.warning(msg)
        return msg

    def init_cluster_from_user_data(self):
        cluster_type = self.app.config.get("initial_cluster_type", None)
        if cluster_type:
            self.app.manager.initialize_cluster_with_custom_settings(
                cluster_type,
                galaxy_data_option=self.app.config.get("galaxy_data_option", "transient"),
                pss=self.app.config.get("pss", None),
                shared_bucket=self.app.config.get("shared_bucket", None))

    @TestFlag(None)
    def init_cluster(self, cluster_type, pss=0, storage_type='volume'):
        """
        Initialize the type for this cluster and start appropriate services,
        storing the cluster configuration into the cluster's bucket.

        This method applies only to a new cluster.

        :type cluster_type: string
        :param cluster_type: Type of cluster being setup. Currently, accepting
                             values ``Galaxy``, ``Data``, or ``SGE``

        :type pss: int
        :param pss: Persistent Storage Size associated with data volumes being
                    created for the cluster
        """
        def _add_data_fs(fs_name=None):
            """
            A local convenience method used to add a new data file system
            """
            if self.get_services(svc_role=ServiceRole.GALAXY_DATA):
                log.debug("Tried to add data file system, but GALAXY_DATA service "
                          "already exists.")
                return
            if not fs_name:
                fs_name = ServiceRole.to_string(ServiceRole.GALAXY_DATA)
            log.debug("Creating a new data filesystem: '%s'" % fs_name)
            fs = Filesystem(self.app, fs_name, svc_roles=[ServiceRole.GALAXY_DATA])
            fs.add_volume(size=pss)
            self.activate_master_service(fs)

        self.cluster_status = cluster_status.STARTING
        self.initial_cluster_type = cluster_type
        self.cluster_storage_type = storage_type
        msg = ("Initializing '{0}' cluster type with storage type '{1}'. "
               "Please wait...".format(cluster_type, storage_type))
        log.info(msg)
        self.app.msgs.info(msg)
        if cluster_type == 'Galaxy':
            # Turn those data sources into file systems
            if self.app.config.filesystem_templates:
                attached_volumes = self.get_attached_volumes()
                for fs_template in [s for s in self.app.config.filesystem_templates if 'name' in s]:
                    if 'roles' in fs_template:
                        fs = Filesystem(self.app, fs_template['name'],
                                        svc_roles=ServiceRole.from_string_array(fs_template['roles']))
                        # Check if an already attached volume maps to the current filesystem
                        att_vol = self.get_vol_if_fs(attached_volumes, fs_template['name'])
                        if att_vol:
                            log.debug("{0} file system has volume(s) already attached".format(
                                fs_template['name']))
                            fs.add_volume(vol_id=att_vol.id,
                                          size=att_vol.size, from_snapshot_id=att_vol.snapshot_id)
                        elif 'snap_id' in fs_template:
                            log.debug("There are no volumes already attached for file system {0}"
                                      .format(fs_template['name']))
                            size = 0
                            if ServiceRole.GALAXY_DATA in ServiceRole.from_string_array(fs_template['roles']):
                                size = pss
                            fs.add_volume(size=size, from_snapshot_id=fs_template['snap_id'])
                        elif 'type' in fs_template:
                            if 'archive' == fs_template['type'] and 'archive_url' in fs_template:
                                log.debug("Creating an archive-based ({0}) file system named '{1}'"
                                          .format(fs_template.get('archive_url'), fs_template['name']))
                                if storage_type == 'volume':
                                    if 'size' in fs_template:
                                        size = fs_template.get('size', 10)  # Default to 10GB
                                        if ServiceRole.GALAXY_DATA in ServiceRole.from_string_array(
                                           fs_template['roles']):
                                            if pss > size:
                                                size = pss
                                        from_archive = {'url': fs_template['archive_url'],
                                                        'md5_sum': fs_template.get('archive_md5', None)}
                                        fs.add_volume(size=size, from_archive=from_archive)
                                elif storage_type == 'transient':
                                    from_archive = {'url': fs_template['archive_url'],
                                                    'md5_sum': fs_template.get('archive_md5', None)}
                                    fs.add_transient_storage(from_archive=from_archive)
                                else:
                                    log.error("Unknown storage type {0} for archive extraction."
                                              .format(storage_type))
                            elif 'gluster' == fs_template['type'] and 'server' in fs_template:
                                log.debug("Creating a glusterfs-based filesystem named {0}"
                                          .format(fs_template['name']))
                                fs.add_glusterfs(fs_template['server'],
                                                 mount_options=fs_template.get('mount_options', None))
                            elif 'nfs' == fs_template['type'] and 'server' in fs_template:
                                log.debug("Creating an NFS-based filesystem named {0}"
                                          .format(fs_template['name']))
                                fs.add_nfs(fs_template['server'], None, None,
                                           mount_options=fs_template.get('mount_options', None))
                            elif 's3fs' == (fs_template['type'] and 'bucket_name' in fs_template and
                                            'bucket_a_key' in fs_template and 'bucket_s_key' in fs_template):
                                log.debug("Creating a bucket-based filesystem named {0}"
                                          .format(fs_template['name']))
                                fs.add_bucket(fs_template['bucket_name'], fs_template['bucket_a_key'],
                                              fs_template['bucket_s_key'])
                            else:
                                log.error("Format error in snaps.yaml file. Unrecognised or "
                                          "improperly configured type '{0}' for fs named: {1}"
                                          .format(fs_template['type'], fs_template['name']))
                        self.activate_master_service(fs)
            # Add a file system for user's data
            if self.app.use_volumes:
                _add_data_fs()
            # Add PostgreSQL service
            self.activate_master_service(self.service_registry.get('Postgres'))
            # Add ProFTPd service
            self.activate_master_service(self.service_registry.get('ProFTPd'))
            # Add Galaxy service
            self.activate_master_service(self.service_registry.get('Galaxy'))
            # Add Galaxy Reports service
            self.activate_master_service(self.service_registry.get('GalaxyReports'))
            # Add Galaxy NodeJSProxy service
            self.activate_master_service(self.service_registry.get('NodeJSProxy'))
        elif cluster_type == 'Data':
            # Add a file system for user's data if one doesn't already exist
            _add_data_fs(fs_name='galaxy')
        elif cluster_type == 'Test':
            # Job manager service is automatically added at cluster start (see
            # ``start`` method)
            pass
            # self.activate_master_service(self.service_registry.get('Pulsar'))
            # self.activate_master_service(self.service_registry.get('ClouderaManager'))
        else:
            log.error("Tried to initialize a cluster but received an unknown type: '%s'" % cluster_type)

    @TestFlag(True)
    @synchronized(s3_rlock)
    def init_shared_cluster(self, share_string):
        """
        Initialize a new (i.e., derived) cluster from a shared one, whose details
        need to be provided in the ``share_string`` (e.g.,
        ``cm-808d863548acae7c2328c39a90f52e29/shared/2012-09-17--19-47``)

        This method can only be called at a new cluster start.
        """
        self.cluster_status = cluster_status.STARTING
        log.debug("Initializing a shared cluster from '%s'" % share_string)
        s3_conn = self.app.cloud_interface.get_s3_connection()
        ec2_conn = self.app.cloud_interface.get_ec2_connection()
        try:
            share_string = share_string.strip('/')
            bucket_name = share_string.split('/')[0]
            cluster_config_prefix = os.path.join(
                share_string.split('/')[1], share_string.split('/')[2])
        except Exception, e:
            log.error("Error while parsing provided shared cluster's bucket '%s': %s" % (
                share_string, e))
            return False
        # Check that the shared cluster's bucket exists
        if not misc.bucket_exists(s3_conn, bucket_name):
            log.error("Shared cluster's bucket '%s' does not exist or is not "
                      "accessible!" % bucket_name)
            return False
        # Create the new cluster's bucket
        if not misc.bucket_exists(s3_conn, self.app.config['bucket_cluster']):
            misc.create_bucket(s3_conn, self.app.config['bucket_cluster'])
        # Copy contents of the shared cluster's bucket to the current cluster's
        # bucket
        fl = "shared_instance_file_list.txt"
        if misc.get_file_from_bucket(s3_conn, bucket_name,
                                     os.path.join(cluster_config_prefix, fl),
                                     fl, validate=False):
            key_list = misc.load_yaml_file(fl)
            for key in key_list:
                misc.copy_file_in_bucket(
                    s3_conn, bucket_name, self.app.config['bucket_cluster'],
                    key, key.split('/')[-1], preserve_acl=False, validate=False)
        else:
            log.error("Problem copying shared cluster configuration files. Cannot continue with "
                      "the shared cluster initialization.")
            return False
        # Create a volume from shared cluster's data snap and set current
        # cluster's data volume
        shared_cluster_pd_file = 'shared_p_d.yaml'
        if misc.get_file_from_bucket(
            s3_conn, self.app.config['bucket_cluster'], 'persistent_data.yaml',
                shared_cluster_pd_file):
            scpd = misc.load_yaml_file(shared_cluster_pd_file)
            self.initial_cluster_type = scpd.get('cluster_type', None)
            log.debug("Initializing %s cluster type from shared cluster" % self.initial_cluster_type)
            if 'shared_data_snaps' in scpd:
                shared_data_vol_snaps = scpd['shared_data_snaps']
                try:
                    # TODO: If support for multiple volumes comprising a file system becomes available,
                    # this code will need to adjusted to accommodate that. Currently, the assumption is
                    # that only 1 snap ID will be provided as the data file
                    # system.
                    snap = ec2_conn.get_all_snapshots(shared_data_vol_snaps)[0]
                    # Create a volume here because we'll be dealing with a volume-based file system
                    # and for that we need a volume ID
                    data_vol = ec2_conn.create_volume(
                        snap.volume_size, self.app.cloud_interface.get_zone(),
                        snapshot=snap)
                    # Old style for persistent data - delete if the other method works as expected
                    # scpd['data_filesystems'] = {'galaxyData': [{'vol_id': data_vol.id, 'size': data_vol.size}]}
                    # Compose a persistent_data compatible entry for the shared data volume so that
                    # the appropriate file system can be created as part of ``add_preconfigured_services``
                    # TODO: make it more general vs. galaxy specific
                    data_fs_yaml = {'ids': [data_vol.id],
                                    'kind': 'volume',
                                    'mount_point': '/mnt/galaxy',
                                    'name': 'galaxy',
                                    'roles': ['galaxyTools', 'galaxyData']}
                    scpd['filesystems'].append(data_fs_yaml)
                    log.info("Created a data volume '%s' of size %sGB from shared cluster's snapshot '%s'"
                             % (data_vol.id, data_vol.size, snap.id))
                    # Don't make the new cluster shared by default
                    del scpd['shared_data_snaps']
                    # Update new cluster's persistent_data.yaml
                    cc_file_name = 'cm_cluster_config.yaml'
                    log.debug("Dumping scpd to file {0} (which will become persistent_data.yaml): {1}"
                              .format(cc_file_name, scpd))
                    misc.dump_yaml_to_file(scpd, cc_file_name)
                    misc.save_file_to_bucket(
                        s3_conn, self.app.config[
                            'bucket_cluster'], 'persistent_data.yaml',
                        cc_file_name)
                except EC2ResponseError, e:
                    log.error("EC2 error creating volume from shared cluster's snapshot '%s': %s"
                              % (shared_data_vol_snaps, e))
                    return False
                except Exception, e:
                    log.error("Error creating volume from shared cluster's snapshot '%s': %s"
                              % (shared_data_vol_snaps, e))
                    return False
            else:
                log.error("Loaded configuration from the shared cluster does not have a reference "
                          "to a shared data snapshot. Cannot continue.")
                return False
        # TODO: Reboot the instance so CloudMan source downloaded from the shared
        # instance is used
        # log.info("Rebooting the cluster so shared instance source can be reloaded.")
        # self.reboot(soft=True)
        # Reload user data and start the cluster as normally would
        self.app.config.user_data = self.app.cloud_interface.get_user_data(force=True)
        if misc.get_file_from_bucket(s3_conn, self.app.config['bucket_cluster'], 'persistent_data.yaml', 'pd.yaml'):
            pd = misc.load_yaml_file('pd.yaml')
            self.app.config.user_data = misc.merge_yaml_objects(self.app.config.user_data, pd)
        reload(paths)  # Must reload because paths.py might have changes in it
        self.add_preconfigured_services()
        return True

    @TestFlag({})
    @synchronized(s3_rlock)
    def share_a_cluster(self, user_ids=None, canonical_ids=None):
        """
        Setup the environment to make the current cluster shared (via a shared
        volume snapshot).
        This entails stopping all services to enable creation of a snapshot of
        the data volume, allowing others to create a volume from the created
        snapshot as well giving read permissions to cluster's bucket. If user_ids
        are not provided, the bucket and the snapshot are made public.

        :type user_ids: list
        :param user_ids: The numeric Amazon IDs of users (with no dashes) to
                         give read permissions to the bucket and snapshot

        :type canonical_ids: list
        :param canonical_ids: A list of Amazon Canonical IDs (in the same linear
                              order as the ``user_ids``) that will be used to
                              enable sharing of individual objects in the
                              cluster's bucket.
        """
        # TODO: rewrite this to use > 3 character variable names.
        # TODO: recover services if the process fails midway
        log.info("Setting up the cluster for sharing")
        self.cluster_manipulation_in_progress = True
        self._stop_app_level_services()

        # Initiate snapshot of the galaxyData file system
        snap_ids = []
        svcs = self.get_services(svc_type=ServiceType.FILE_SYSTEM)
        for svc in svcs:
            if ServiceRole.GALAXY_DATA in svc.svc_roles:
                snap_ids = svc.create_snapshot(snap_description="CloudMan share-a-cluster %s; %s"
                                               % (self.app.config['cluster_name'],
                                                  self.app.config['bucket_cluster']))
        self._start_app_level_services()
        # Create a new folder-like structure inside cluster's bucket and copy
        # the cluster configuration files
        s3_conn = self.app.cloud_interface.get_s3_connection()
        # All of the shared cluster's config files will be stored with the
        # specified prefix
        shared_names_root = "shared/%s" % Time.now().strftime("%Y-%m-%d--%H-%M")
        # Create current cluster config and save it to cluster's shared location,
        # including the freshly generated snap IDs
        conf_file_name = 'cm_shared_cluster_conf.yaml'
        addl_data = {'shared_data_snaps': snap_ids}
        self.console_monitor.create_cluster_config_file(
            conf_file_name, addl_data=addl_data)
        # Remove references to cluster's own data; this is shared via the snapshots above
        # TODO: Add an option for a user to include any self-added file systems
        # as well
        sud = misc.load_yaml_file(conf_file_name)
        fsl = sud.get('filesystems', [])
        sfsl = []  # Shared file systems list
        for fs in fsl:
            roles = ServiceRole.from_string_array(fs['roles'])
            # Including GALAXY_TOOLS role here breaks w/ new combined galaxyData/galaxyTools volume.  We should
            # probably change this to actually inspect and share base snapshots if applicable (like galaxyIndices) but
            # never volumes.
            # if ServiceRole.GALAXY_TOOLS in roles or ServiceRole.GALAXY_INDICES in roles:
            if ServiceRole.GALAXY_INDICES in roles:
                sfsl.append(fs)
        sud['filesystems'] = sfsl
        misc.dump_yaml_to_file(sud, conf_file_name)
        misc.save_file_to_bucket(s3_conn, self.app.config['bucket_cluster'],
                                 os.path.join(shared_names_root, 'persistent_data.yaml'), conf_file_name)
        # Keep track of which keys were copied into the shared folder
        copied_key_names = [os.path.join(shared_names_root,
                                         'persistent_data.yaml')]
        # Save the remaining cluster configuration files
        try:
            # Get a list of all files stored in cluster's bucket excluding
            # any keys that include '/' (i.e., are folders) or the previously
            # copied 'persistent_data.yaml'. This way, if the number of config
            # files changes in the future, this will still work
            b = s3_conn.lookup(self.app.config['bucket_cluster'])
            keys = b.list(delimiter='/')
            conf_files = []
            for key in keys:
                if '/' not in key.name and 'persistent_data.yaml' not in key.name:
                    conf_files.append(key.name)
        except S3ResponseError, e:
            log.error("Error collecting cluster configuration files form bucket '%s': %s"
                      % (self.app.config['bucket_cluster'], e))
            return False
        # Copy current cluster's configuration files into the shared folder
        for conf_file in conf_files:
            if 'clusterName' not in conf_file:  # Skip original cluster name file
                misc.copy_file_in_bucket(s3_conn,
                                         self.app.config['bucket_cluster'],
                                         self.app.config['bucket_cluster'],
                                         conf_file, os.path.join(
                                             shared_names_root, conf_file),
                                         preserve_acl=False)
                copied_key_names.append(
                    os.path.join(shared_names_root, conf_file))
        # Save the list of files contained in the shared bucket so derivative
        # instances can know what to get with minimim permissions
        fl = "shared_instance_file_list.txt"
        misc.dump_yaml_to_file(copied_key_names, fl)
        misc.save_file_to_bucket(s3_conn, self.app.config['bucket_cluster'], os.path.join(shared_names_root, fl), fl)
        copied_key_names.append(os.path.join(shared_names_root, fl))  # Add it to the list so it's permissions get set
        # Adjust permissions on the new keys and the created snapshots
        ec2_conn = self.app.cloud_interface.get_ec2_connection()
        for snap_id in snap_ids:
            try:
                if user_ids:
                    log.debug(
                        "Adding createVolumePermission for snap '%s' for users '%s'" % (snap_id, user_ids))
                    ec2_conn.modify_snapshot_attribute(
                        snap_id, attribute='createVolumePermission',
                        operation='add', user_ids=user_ids)
                else:
                    ec2_conn.modify_snapshot_attribute(
                        snap_id, attribute='createVolumePermission',
                        operation='add', groups=['all'])
            except EC2ResponseError, e:
                log.error(
                    "Error modifying snapshot '%s' attribute: %s" % (snap_id, e))
        err = False
        if canonical_ids:
            # In order to list the keys associated with a shared instance, a user
            # must be given READ permissions on the cluster's bucket as a whole.
            # This allows a given user to list the contents of a bucket but not
            # access any of the keys other than the ones granted the permission
            # next (i.e., keys required to bootstrap the shared instance)
            # Grant READ permissions for the keys required to bootstrap the
            # shared instance
            for k_name in copied_key_names:
                if not misc.add_key_user_grant(s3_conn, self.app.config['bucket_cluster'],
                                               k_name, 'READ', canonical_ids):
                    log.error("Error adding READ permission for key '%s'" % k_name)
                    err = True
        else:  # If no canonical_ids are provided, means to set the permissions to public-read
            # See above, but in order to access keys, the bucket root must be given read permissions
            # FIXME: this method sets the bucket's grant to public-read and
            # removes any individual user's grants - something share-a-cluster
            # depends on down the line if the publicly shared instance is deleted
            # misc.make_bucket_public(s3_conn, self.app.config['bucket_cluster'])
            for k_name in copied_key_names:
                if not misc.make_key_public(s3_conn, self.app.config['bucket_cluster'], k_name):
                    log.error("Error making key '%s' public" % k_name)
                    err = True
        if err:
            # TODO: Handle this with more user input?
            log.error("Error modifying permissions for keys in bucket '%s'" %
                      self.app.config['bucket_cluster'])

        self.cluster_manipulation_in_progress = False
        return True

    @TestFlag([{"bucket": "cm-7834hdoeiuwha/TESTshare/2011-08-14--03-02/", "snap":
                'snap-743ddw12', "visibility": 'Shared'},
               {"bucket": "cm-7834hdoeiuwha/TESTshare/2011-08-19--10-49/", "snap":
                'snap-gf69348h', "visibility": 'Public'}])
    @synchronized(s3_rlock)
    def get_shared_instances(self):
        """
        Get a list of point-in-time shared instances of this cluster.
        Returns a list such instances. Each element of the returned list is a
        dictionary with ``bucket``, ``snap``, and ``visibility`` keys.
        """
        lst = []
        try:
            s3_conn = self.app.cloud_interface.get_s3_connection()
            b = misc.get_bucket(s3_conn, self.app.config['bucket_cluster'])
            if b:
                # Get a list of shared 'folders' containing clusters'
                # configuration
                folder_list = b.list(prefix='shared/', delimiter='/')
                for folder in folder_list:
                    # Get snapshot assoc. with the current shared cluster
                    tmp_pd = 'tmp_pd.yaml'
                    if misc.get_file_from_bucket(
                        s3_conn, self.app.config['bucket_cluster'],
                            os.path.join(folder.name, 'persistent_data.yaml'), tmp_pd):
                        tmp_ud = misc.load_yaml_file(tmp_pd)
                        # Currently, only a single volume snapshot can be associated
                        # a shared instance so pull it out of the list
                        if 'shared_data_snaps' in tmp_ud and len(tmp_ud['shared_data_snaps']) == 1:
                            snap_id = tmp_ud['shared_data_snaps'][0]
                        else:
                            snap_id = "Missing-ERROR"
                        try:
                            os.remove(tmp_pd)
                        except OSError:
                            pass  # Best effort temp file cleanup
                    else:
                        snap_id = "Missing-ERROR"
                    # Get permission on the persistent_data file and assume
                    # the entire cluster shares those permissions
                    k = b.get_key(
                        os.path.join(folder.name, 'persistent_data.yaml'))
                    if k is not None:
                        acl = k.get_acl()
                        if 'AllUsers' in str(acl):
                            visibility = 'Public'
                        else:
                            visibility = 'Shared'
                        lst.append(
                            {"bucket": os.path.join(self.app.config['bucket_cluster'],
                                                    folder.name), "snap": snap_id, "visibility": visibility})
        except S3ResponseError, e:
            log.error(
                "Problem retrieving references to shared instances: %s" % e)
        return lst

    @TestFlag(True)
    @synchronized(s3_rlock)
    def delete_shared_instance(self, shared_instance_folder, snap_id):
        """
        Deletes all files under shared_instance_folder (i.e., all keys with
        ``shared_instance_folder`` prefix) and ``snap_id``, thus deleting the
        shared instance of the given cluster.

        :type shared_instance_folder: str
        :param shared_instance_folder: Prefix for the shared cluster instance
            configuration (e.g., ``shared/2011-02-24--20-52/``)

        :type snap_id: str
        :param snap_id: Snapshot ID to be deleted (e.g., ``snap-04c01768``)
        """
        log.debug("Calling delete shared instance for folder '%s' and snap '%s'"
                  % (shared_instance_folder, snap_id))
        ok = True  # Mark if encountered error but try to delete as much as possible
        try:
            s3_conn = self.app.cloud_interface.get_s3_connection()
            # Remove keys and folder associated with the given shared instance
            b = misc.get_bucket(s3_conn, self.app.config['bucket_cluster'])
            key_list = b.list(prefix=shared_instance_folder)
            for key in key_list:
                log.debug("As part of shared cluster instance deletion, deleting "
                          "key '%s' from bucket '%s'" % (key.name, self.app.config['bucket_cluster']))
                key.delete()
        except S3ResponseError, e:
            log.error("Problem deleting keys in '%s': %s" % (
                shared_instance_folder, e))
            ok = False
        # Delete the data snapshot associated with the shared instance being
        # deleted
        try:
            ec2_conn = self.app.cloud_interface.get_ec2_connection()
            ec2_conn.delete_snapshot(snap_id)
            log.debug("As part of shared cluster instance deletion, deleted "
                      "snapshot '%s'" % snap_id)
        except EC2ResponseError, e:
            log.error("As part of shared cluster instance deletion, problem "
                      "deleting snapshot '%s': %s" % (snap_id, e))
            ok = False
        return ok

    @TestFlag(['snap-snapFS'])
    def snapshot_file_system(self, file_system_name):
        """
        Create a snapshot of the volume(s) used for the `file_system_name`.
        Note that this method applies only to volume-backed file systems.

        The method will automatically stop any application-level services,
        create a snapshot of the volume(s) and, after the snapshot(s) have
        been created, start the application-level services. These are the steps:
            1. Suspend all application-level services
            2. Unmount and detach the volume associated with the file system
            3. Create a snapshot of the volume
            4. Re-mount the file system
            5. Unsuspend services
        """
        log.info("Initiating file system '%s' snapshot." % file_system_name)
        self.cluster_manipulation_in_progress = True
        self._stop_app_level_services()
        snap_ids = []
        fs_service = self.service_registry.get(file_system_name)
        if fs_service:
            # Create a snapshot of the given volume/file system
            snap_desc = ("Created by CloudMan ({0}; {1}) from file system '{2}'"
                         .format(self.app.config['cluster_name'],
                                 self.app.config['bucket_cluster'], file_system_name))
            snap_ids = fs_service.create_snapshot(snap_description=snap_desc)
            # Start things back up
            self._start_app_level_services()
            self.cluster_manipulation_in_progress = False
            log.info("File system {0} snapshot complete; snapshot(s): {1}"
                     .format(file_system_name, snap_ids))
        else:
            log.error("Did not find file system with name {0}; snapshot(s) not "
                      "created.".format(file_system_name))
        return snap_ids

    @TestFlag(['snap-updateFS'])
    def update_file_system(self, file_system_name):
        """ This method is used to update the underlying EBS volume/snapshot
        that is used to hold the provided file system. This is useful when
        changes have been made to the underlying file system and those changes
        wish to be preserved beyond the runtime of the current instance. After
        calling this method, terminating and starting the cluster instance over
        will preserve any changes made to the file system (provided the snapshot
        created via this method has not been deleted).
        The method performs the following steps:
        1. Suspend all application-level services
        2. Unmount and detach the volume associated with the file system
        3. Create a snapshot of the volume
        4. Delete references to the original file system's EBS volume
        5. Add a new reference to the created snapshot, which gets picked up
           by the monitor and a new volume is created and file system mounted
        6. Unsuspend services
        """
        log.info("Initiating file system '%s' update." % file_system_name)
        self.cluster_manipulation_in_progress = True
        self._stop_app_level_services()

        # Initiate snapshot of the specified file system
        snap_ids = []
        svcs = self.get_services(svc_type=ServiceType.FILE_SYSTEM)
        found_fs_name = False  # Flag to ensure provided fs name was actually found
        for svc in svcs:
            if svc.name == file_system_name:
                found_fs_name = True
                # Create a snapshot of the given volume/file system
                snap_ids = svc.create_snapshot(
                    snap_description="File system '%s' from CloudMan instance '%s'; bucket: %s"
                    % (file_system_name, self.app.config['cluster_name'],
                       self.app.config['bucket_cluster']))
                # Remove the old volume by removing the entire service
                if len(snap_ids) > 0:
                    log.debug("Removing file system '%s' service as part of the file system update"
                              % file_system_name)
                    svc.remove()
                    log.debug("Creating file system '%s' from snaps '%s'" % (file_system_name, snap_ids))
                    fs = Filesystem(self.app, file_system_name, svc.svc_roles)
                    for snap_id in snap_ids:
                        fs.add_volume(from_snapshot_id=snap_id)
                    self.activate_master_service(fs)
                    # Monitor will pick up the new service and start it up but
                    # need to wait until that happens before can add rest of
                    # the services
                    while fs.state != service_states.RUNNING:
                        log.debug("Service '%s' not quite ready: '%s'" % (
                            fs.get_full_name(), fs.state))
                        time.sleep(6)
        if found_fs_name:
            self._start_app_level_services()
            self.cluster_manipulation_in_progress = False
            log.info("File system '%s' update complete" % file_system_name)
        else:
            log.error("Did not find file system with name '%s'; update not performed." %
                      file_system_name)
        return snap_ids

    def add_fs_bucket(self, bucket_name, fs_name=None, fs_roles=[ServiceRole.GENERIC_FS],
                      bucket_a_key=None, bucket_s_key=None, persistent=False):
        """
        Add a new file system service for a bucket-based file system.
        """
        log.info("Adding a {4} file system {3} from bucket {0} (w/ creds {1}:{2})"
                 .format(bucket_name, bucket_a_key, bucket_s_key, fs_name, persistent))
        fs = Filesystem(self.app, fs_name or bucket_name,
                        persistent=persistent, svc_roles=fs_roles)
        fs.add_bucket(bucket_name, bucket_a_key, bucket_s_key)
        self.activate_master_service(fs)
        # Inform all workers to add the same FS (the file system will be the same
        # and sharing it over NFS does not seems to work)
        for w_inst in self.worker_instances:
            w_inst.send_add_s3fs(bucket_name, fs_roles)
        log.debug("Master done adding FS from bucket {0}".format(bucket_name))

    @TestFlag(None)
    def add_fs_volume(self, fs_name, fs_kind, vol_id=None, snap_id=None, vol_size=0,
                      fs_roles=[ServiceRole.GENERIC_FS], persistent=False, dot=False):
        """
        Add a new file system based on an existing volume, a snapshot, or a new
        volume. Provide ``fs_kind`` to distinguish between these (accepted values
        are: ``volume``, ``snapshot``, or ``new_volume``). Depending on which
        kind is provided, must provide ``vol_id``, ``snap_id``, or ``vol_size``,
        respectively - but not all!
        """
        if fs_name:
            log.info("Adding a {0}-based file system '{1}'".format(fs_kind, fs_name))
            fs = Filesystem(self.app, fs_name, persistent=persistent, svc_roles=fs_roles)
            fs.add_volume(vol_id=vol_id, size=vol_size, from_snapshot_id=snap_id, dot=dot)
            self.activate_master_service(fs)
            log.debug("Master done adding {0}-based FS {1}".format(fs_kind, fs_name))
        else:
            log.error("Wanted to add a volume-based file system but no file "
                      "system name provided; skipping.")

    @TestFlag(None)
    def add_fs_gluster(self, gluster_server, fs_name,
                       fs_roles=[ServiceRole.GENERIC_FS], persistent=False):
        """
        Add a new file system service for a Gluster-based file system.
        """
        if fs_name:
            log.info("Adding a Gluster-based file system {0} from Gluster server {1}"
                     .format(fs_name, gluster_server))
            fs = Filesystem(self.app, fs_name, persistent=persistent, svc_roles=fs_roles)
            fs.add_glusterfs(gluster_server)
            self.activate_master_service(fs)
            # Inform all workers to add the same FS (the file system will be the same
            # and sharing it over NFS does not seems to work)
            for w_inst in self.worker_instances:
                # w_inst.send_add_nfs_fs(nfs_server, fs_name, fs_roles, username, pwd)
                w_inst.send_mount_points()
            log.debug("Master done adding FS from Gluster server {0}".format(gluster_server))
        else:
            log.error("Wanted to add a volume-based file system but no file "
                      "system name provided; skipping.")

    @TestFlag(None)
    def add_fs_nfs(self, nfs_server, fs_name, username=None, pwd=None,
                   fs_roles=[ServiceRole.GENERIC_FS], persistent=False):
        """
        Add a new file system service for a NFS-based file system. Optionally,
        provide password-based credentials (``username`` and ``pwd``) for
        accessing the NFS server.
        """
        if fs_name:
            log.info("Adding a NFS-based file system {0} from NFS server {1}"
                     .format(fs_name, nfs_server))
            fs = Filesystem(self.app, fs_name, persistent=persistent, svc_roles=fs_roles)
            fs.add_nfs(nfs_server, username, pwd)
            self.activate_master_service(fs)
            # Inform all workers to add the same FS (the file system will be the same
            # and sharing it over NFS does not seems to work)
            for w_inst in self.worker_instances:
                w_inst.send_mount_points()
            log.debug("Master done adding FS from NFS server {0}".format(nfs_server))
        else:
            log.error("Wanted to add a volume-based file system but no file "
                      "system name provided; skipping.")

    def stop_worker_instances(self):
        """
        Initiate termination of all worker instances.
        """
        log.info("Stopping all '%s' worker instance(s)" % len(self.worker_instances))
        self.remove_instances(len(self.worker_instances), force=True)

    @TestFlag({})  # {'default_CM_rev': '64', 'user_CM_rev':'60'} # For testing
    @synchronized(s3_rlock)
    def check_for_new_version_of_CM(self):
        """
        Check revision metadata for CloudMan (CM) in user's bucket and the
        default CM bucket.

        :rtype: dict
        :return: A dictionary with 'default_CM_rev' and 'user_CM_rev' keys where
                 each key maps to an string representation of an int that
                 corresponds to the version of CloudMan in the default repository
                 vs. the currently running user's version. If CloudMan is unable
                 to determine the versions, an empty dict is returned.
        """
        log.debug("Checking for new version of CloudMan")
        s3_conn = self.app.cloud_interface.get_s3_connection()
        user_CM_rev = misc.get_file_metadata(
            s3_conn, self.app.config['bucket_cluster'], self.app.config.cloudman_source_file_name, 'revision')
        default_CM_rev = misc.get_file_metadata(
            s3_conn, self.app.config['bucket_default'], self.app.config.cloudman_source_file_name, 'revision')
        log.debug("Revision number for user's CloudMan: '%s'; revision number for default CloudMan: '%s'" %
                  (user_CM_rev, default_CM_rev))
        if user_CM_rev and default_CM_rev:
            try:
                if int(default_CM_rev) > int(user_CM_rev):
                    return {'default_CM_rev': default_CM_rev, 'user_CM_rev': user_CM_rev}
            except Exception:
                pass
        return {}

    @TestFlag(None)
    @synchronized(s3_rlock)
    def update_users_CM(self):
        """
        If the revision number of CloudMan (CM) source file (as stored in file's metadata)
        in user's bucket is less than that of default CM, upload the new version of CM to
        user's bucket. Note that the update will take effect only after the next cluster reboot.

        :rtype: bool
        :return: If update was successful, return True.
                 Else, return False
        """
        if self.check_for_new_version_of_CM():
            log.info("Updating CloudMan application source file in the cluster's bucket '%s'. "
                     "It will be automatically available the next time this cluster is instantiated."
                     % self.app.config['bucket_cluster'])
            s3_conn = self.app.cloud_interface.get_s3_connection()
            # Make a copy of the old/original CM source and boot script in the cluster's bucket
            # called 'copy_name' and 'copy_boot_name', respectively
            copy_name = "%s_%s" % (
                self.app.config.cloudman_source_file_name, dt.date.today())
            copy_boot_name = "%s_%s" % (
                self.app.config['boot_script_name'], dt.date.today())
            if misc.copy_file_in_bucket(s3_conn, self.app.config['bucket_cluster'],
                                        self.app.config['bucket_cluster'], self.app.config.cloudman_source_file_name, copy_name) and \
                misc.copy_file_in_bucket(
                    s3_conn, self.app.config['bucket_cluster'],
                    self.app.config['bucket_cluster'], self.app.config['boot_script_name'], copy_boot_name):
                # Now copy CloudMan source from the default bucket to cluster's bucket as
                # self.app.config.cloudman_source_file_name and cm_boot.py as
                # 'boot_script_name'
                if misc.copy_file_in_bucket(
                    s3_conn, self.app.config['bucket_default'],
                    self.app.config[
                        'bucket_cluster'], self.app.config.cloudman_source_file_name,
                    self.app.config.cloudman_source_file_name) and misc.copy_file_in_bucket(s3_conn,
                                                                                            self.app.config[
                        'bucket_default'], self.app.config['bucket_cluster'],
                        'cm_boot.py', self.app.config['boot_script_name']):
                    return True
        return False

    def expand_user_data_volume(self, new_vol_size, fs_name, snap_description=None,
                                delete_snap=False):
        """
        Mark the file system ``fs_name`` for size expansion. For full details on how
        this works, take a look at the file system expansion method for the
        respective file system type.
        If the underlying file system supports/requires creation of a point-in-time
        snapshot, setting ``delete_snap`` to ``False`` will retain the snapshot
        that will be creted during the expansion process under the given cloud account.
        If the snapshot is to be kept, a brief ``snap_description`` can be provided.
        """
        # Match fs_name with a service or if it's null or empty, default to
        # GALAXY_DATA role
        if fs_name:
            svcs = self.app.manager.get_services(svc_name=fs_name)
            if svcs:
                svc = svcs[0]
            else:
                log.error("Could not initiate expansion of {0} file system because "
                          "the file system was not found?".format(fs_name))
                return
        else:
            svc = self.app.manager.get_services(
                svc_role=ServiceRole.GALAXY_DATA)[0]

        log.debug("Marking '%s' for expansion to %sGB with snap description '%s'"
                  % (svc.get_full_name(), new_vol_size, snap_description))
        svc.state = service_states.CONFIGURING
        svc.grow = {
            'new_size': new_vol_size, 'snap_description': snap_description,
            'delete_snap': delete_snap}

    @TestFlag('TESTFLAG_ROOTPUBLICKEY')
    def get_root_public_key(self):
        """
        Generate or retrieve a public ssh key for the user running CloudMan and
        return it as a string. The key file is stored in ``id_rsa.pub``.
        Also, the private portion of the key is copied to ``/root/.ssh/id_rsa``
        to enable passwordless login by job manager jobs.
        """
        if self.root_pub_key is None:
            if not os.path.exists('id_rsa'):
                log.debug("Generating root user's public key...")
                ret_code = subprocess.call('ssh-keygen -t rsa -N "" -f id_rsa', shell=True)
                if ret_code == 0:
                    log.debug("Successfully generated root user's public key.")
                    f = open('id_rsa.pub')
                    self.root_pub_key = f.readline()
                    f.close()
                    # Must copy private key at least to /root/.ssh for
                    # passwordless login to work
                    shutil.copy2('id_rsa', '/root/.ssh/id_rsa')
                    log.debug(
                        "Successfully retrieved root user's public key from file.")
                else:
                    log.error("Encountered a problem while creating root user's "
                              "public key, process returned error code '%s'." % ret_code)
            else:  # This is master restart, so
                f = open('id_rsa.pub')
                self.root_pub_key = f.readline()
                f.close()
                if not os.path.exists('/root/.ssh/id_rsa'):
                    # Must copy private key at least to /root/.ssh for passwordless login to work
                    shutil.copy2('id_rsa', '/root/.ssh/id_rsa')
                log.info("Successfully retrieved root user's public key from file.")
        return self.root_pub_key

    @TestFlag(None)
    def save_host_cert(self, host_cert):
        """
        Save host certificate ``host_cert`` to ``/root/.ssh/knowns_hosts``
        """
        log.debug("Saving host certificate '%s'" % host_cert)
        log.debug("Saving worker host certificate.")
        f = open("/root/.ssh/known_hosts", 'a')
        f.write(host_cert)
        f.close()
        return True

    def get_num_available_workers(self):
        """
        Return the number of available worker nodes. A worker node is assumed
        available if it is in state ``READY``.
        """
        # log.debug("Gathering number of available workers" )
        num_available_nodes = 0
        for inst in self.worker_instances:
            if inst.worker_status == "Ready":
                num_available_nodes += 1
        return num_available_nodes

    # ==========================================================================
    # ============================ UTILITY METHODS =============================
    # ========================================================================
    def sync_etc_hosts(self):
        """
        Instruct all workers to sync their ``/etc/hosts`` file with master's.

        Copy the master's `/etc/hosts` into an NFS shared folder and send a
        message to the workers to inform them of the change.
        """
        log.debug("Instructing all workers to sync /etc/hosts w/ master")
        try:
            shutil.copy("/etc/hosts", paths.P_ETC_TRANSIENT_PATH)
            for wrk in self.worker_instances:
                wrk.send_sync_etc_host(paths.P_ETC_TRANSIENT_PATH)
        except IOError, e:
            log.error("Trouble copying /etc/hosts to shared NFS {0}: {1}"
                      .format(paths.P_ETC_TRANSIENT_PATH, e))

    def update_condor_host(self, new_worker_ip):
        """
        Add the new pool to the condor big pool
        """
        svc_name = ServiceRole.to_string(ServiceRole.HTCONDOR)
        if self.service_registry.is_active(svc_name):
            log.debug("Updating HTCondor host through master")
            svc = self.service_registry.get(svc_name)
            svc.modify_htcondor("ALLOW_WRITE", new_worker_ip)

    @TestFlag({'id': 'localtest', 'ld': "0.00 0.02 0.39",
               'time_in_state': 4321,
               'instance_type': 'tester', 'public_ip': "127.0.0.1"})
    def get_status_dict(self):
        """
        Return a status dictionary for the current instance.

        The dictionary includes the following keys: ``id`` of the instance;
        ``ld`` as a load of the instance over the past 1, 5, and 15 minutes
        (e.g., ``0.00 0.02 0.39``); ``time_in_state`` as the length of time
        since instance state was last changed; ``instance_type`` as the type
        of the instance provisioned by the cloud; and ``public_ip`` with the
        public IP address of the instance.
        """
        public_ip = self.app.cloud_interface.get_public_ip()
        num_cpus = int(commands.getoutput("cat /proc/cpuinfo | grep processor | wc -l"))
        # Returns system load in format "0.00 0.02 0.39" for the past 1, 5, and 15 minutes, respectively
        load = (commands.getoutput("cat /proc/loadavg | cut -d' ' -f1-3")).strip()
        if load != 0:
            lds = load.split(' ')
            if len(lds) == 3:
                load = "%s %s %s" % (float(lds[0]) / int(num_cpus), float(
                    lds[1]) / int(num_cpus), float(lds[2]) / int(num_cpus))
            else:
                # Debug only, this should never happen.  If the interface is
                # able to display this, there is load.
                load = "0 0 0"
        return {'id': self.app.cloud_interface.get_instance_id(), 'ld': load,
                'time_in_state': misc.format_seconds(Time.now() - self.startup_time),
                'instance_type': self.app.cloud_interface.get_type(), 'public_ip': public_ip}


class ConsoleMonitor(object):
    def __init__(self, app):
        self.app = app
        self.last_state_change_time = None
        self.conn = comm.CMMasterComm()
        if not self.app.TESTFLAG:
            self.conn.setup()
        self.sleeper = misc.Sleeper()
        self.running = True
        # Keep some local stats to be able to adjust system updates
        self.last_update_time = Time.now()
        self.last_system_change_time = Time.now()
        self.update_frequency = 10  # Frequency (in seconds) between system updates
        self.num_workers = -1
        # Start the monitor thread
        self.monitor_thread = threading.Thread(target=self.__monitor)

    def start(self):
        """
        Start the monitor thread, which monitors and manages all the services
        visible to CloudMan.
        """
        self.last_state_change_time = Time.now()
        # Assign tags for the master instance
        try:
            i_id = self.app.cloud_interface.get_instance_id()
            ir = self.app.cloud_interface.get_all_instances(i_id)
            self.app.cloud_interface.add_tag(
                ir[0].instances[0], 'clusterName', self.app.config['cluster_name'])
            self.app.cloud_interface.add_tag(
                ir[0].instances[0], 'role', self.app.config['role'])
            self.app.cloud_interface.add_tag(ir[0].instances[0], 'Name',
                                             "{0}: {1}".format(self.app.config['role'],
                                                               self.app.config['cluster_name']))
        except Exception, e:
            log.debug("Error setting tags on the master instance: %s" % e)
        self.app.manager.service_registry.load_services()
        log.debug("Loaded services: {0}".format(self.app.manager.service_registry.services))
        self.monitor_thread.start()

    def shutdown(self):
        """
        Attempts to gracefully shut down the monitor thread, in turn stopping
        system updates.
        """
        log.info("Monitor received stop signal")
        try:
            log.info("Sending stop signal to the Monitor thread")
            if self.conn:
                self.conn.shutdown()
            self.running = False
            self.sleeper.wake()
            log.info("ConsoleMonitor thread stopped")
        except:
            pass

    def _update_frequency(self):
        """ Update the frequency value at which system updates are performed by the monitor.
        """
        # Check if a worker was added/removed since the last update
        if self.num_workers != len(self.app.manager.worker_instances):
            self.last_system_change_time = Time.now()
            self.num_workers = len(self.app.manager.worker_instances)
        # Update frequency: as more time passes since a change in the system,
        # progressivley back off on frequency of system updates
        if (Time.now() - self.last_system_change_time).seconds > 600:
            self.update_frequency = 60  # If no system changes for 10 mins, run update every minute
        elif (Time.now() - self.last_system_change_time).seconds > 300:
            self.update_frequency = 30  # If no system changes for 5 mins, run update every 30 secs
        else:
            self.update_frequency = 10  # If last system change within past 5 mins, run update every 10 secs

    def expand_user_data_volume(self):
        # TODO: recover services if process fails midway
        log.info("Initiating user data volume resizing")
        self.app.manager._stop_app_level_services()

        # Grow galaxyData filesystem
        svcs = self.app.manager.get_services(svc_type=ServiceType.FILE_SYSTEM)
        for svc in svcs:
            if ServiceRole.GALAXY_DATA in svc.svc_roles:
                log.debug("Expanding '%s'" % svc.get_full_name())
                svc.expand()

        self.app.manager._start_app_level_services()
        return True

    def create_cluster_config_file(self, file_name='persistent_data-current.yaml', addl_data=None):
        """
        Capture the current cluster configuration in a file (i.e., ``persistent_data.yaml``
        in cluster's bucket). The generated file is stored in CloudMan's running
        directory as ``file_name``. If provided, ``addl_data`` is included in
        the created configuration file.
        """
        try:
            cc = {}  # cluster configuration
            svcs = []  # list of services
            fss = []  # list of filesystems
            if addl_data:
                cc = addl_data
            # Save cloud tags, in case the cloud doesn't support them natively
            cc['tags'] = self.app.cloud_interface.tags
            for srvc in self.app.manager.service_registry.active():
                if srvc.svc_type == ServiceType.FILE_SYSTEM:
                    if srvc.persistent:
                        fs = {}
                        fs['name'] = srvc.name
                        fs['roles'] = ServiceRole.to_string_array(srvc.svc_roles)
                        fs['mount_point'] = srvc.mount_point
                        fs['kind'] = srvc.kind
                        if srvc.kind == 'bucket':
                            fs['ids'] = [b.bucket_name for b in srvc.buckets]
                            fs['access_key'] = b.a_key
                            fs['secret_key'] = b.s_key
                        elif srvc.kind == 'volume':
                            fs['ids'] = [v.volume_id for v in srvc.volumes]
                        elif srvc.kind == 'snapshot':
                            fs['ids'] = [
                                v.from_snapshot_id for v in srvc.volumes]
                        elif srvc.kind == 'nfs':
                            fs['nfs_server'] = srvc.nfs_fs.device
                            fs['mount_options'] = srvc.nfs_fs.mount_options
                        elif srvc.kind == 'gluster':
                            fs['gluster_server'] = srvc.gluster_fs.device
                            fs['mount_options'] = srvc.gluster_fs.mount_options
                        elif srvc.kind == 'transient':
                            pass
                        else:
                            log.error("For filesystem {0}, unknown kind: {1}"
                                      .format(srvc.name, srvc.kind))
                        fss.append(fs)
                else:
                    s = {}
                    s['name'] = srvc.name
                    s['roles'] = ServiceRole.to_string_array(srvc.svc_roles)
                    if ServiceRole.GALAXY in srvc.svc_roles:
                        s['home'] = self.app.path_resolver.galaxy_home
                    if ServiceRole.AUTOSCALE in srvc.svc_roles:
                        # We do not persist Autoscale service
                        pass
                    else:
                        svcs.append(s)
            cc['filesystems'] = fss
            cc['services'] = svcs
            cc['cluster_type'] = self.app.manager.initial_cluster_type
            cc['cluster_storage_type'] = self.app.manager.cluster_storage_type
            cc['cluster_name'] = self.app.config['cluster_name']
            cc['placement'] = self.app.cloud_interface.get_zone()
            cc['machine_image_id'] = self.app.cloud_interface.get_ami()
            cc['persistent_data_version'] = self.app.PERSISTENT_DATA_VERSION
            # If 'deployment_version' is not in UD, don't store it in the config
            if 'deployment_version' in self.app.config.user_data:
                cc['deployment_version'] = self.app.config.user_data['deployment_version']
            misc.dump_yaml_to_file(cc, file_name)
            # Reload the user data object in case anything has changed
            self.app.config.user_data = misc.merge_yaml_objects(cc, self.app.config.user_data)
        except Exception, e:
            log.error("Problem creating cluster configuration file: '%s'" % e)
        return file_name

    @cluster_ready
    @synchronized(s3_rlock)
    def store_cluster_config(self):
        """
        Create a cluster configuration file and store it into cluster's bucket under name
        ``persistent_data.yaml``. The cluster configuration is considered the set of currently
        seen services in the master.

        In addition, store the local Galaxy configuration files to the cluster's
        bucket (do so only if they are not already there).
        """
        # Create a cluster configuration file
        cc_file_name = self.create_cluster_config_file()
        if self.app.manager.initial_cluster_type == 'Test' or \
           self.app.manager.cluster_storage_type == 'transient':
            # Place the cluster configuration file to a locaiton that lives
            # across cluster reboots
            misc.move(cc_file_name, self.app.INSTANCE_PD_FILE)
            log.debug("This is a transient cluster; we do not create a cluster "
                      "bucket to store cluster configuration for this type.")
            return
        log.debug("Storing cluster configuration to cluster's bucket")
        s3_conn = self.app.cloud_interface.get_s3_connection()
        if not s3_conn:
            # s3_conn will be None is use_object_store is False, in this case just skip this
            # function.
            return
        if not misc.bucket_exists(s3_conn, self.app.config['bucket_cluster']):
            misc.create_bucket(s3_conn, self.app.config['bucket_cluster'])
        # Save/update the current Galaxy cluster configuration to cluster's
        # bucket
        misc.save_file_to_bucket(s3_conn, self.app.config['bucket_cluster'],
                                 'persistent_data.yaml', cc_file_name)
        log.debug("Saving current instance boot script (%s) to cluster bucket "
                  "'%s' as '%s'" % (os.path.join(self.app.config['boot_script_path'],
                                    self.app.config['boot_script_name']),
                                    self.app.config['bucket_cluster'],
                                    self.app.config['boot_script_name']))
        misc.save_file_to_bucket(s3_conn, self.app.config['bucket_cluster'],
                                 self.app.config['boot_script_name'],
                                 os.path.join(self.app.config['boot_script_path'],
                                 self.app.config['boot_script_name']))
        log.debug("Saving CloudMan source (%s) to cluster bucket '%s' as '%s'" % (
            os.path.join(self.app.config['cloudman_home'], self.app.config.cloudman_source_file_name),
            self.app.config['bucket_cluster'], self.app.config.cloudman_source_file_name))
        misc.save_file_to_bucket(
            s3_conn, self.app.config['bucket_cluster'], self.app.config.cloudman_source_file_name,
            os.path.join(self.app.config['cloudman_home'], self.app.config.cloudman_source_file_name))
        # [May 2015] Not being used for the time being so disable
        # try:
        #     # Currently, metadata only works on ec2 so set it only there
        #     if self.app.cloud_type == 'ec2':
        #         with open(os.path.join(self.app.config['cloudman_home'], 'cm_revision.txt'), 'r') as rev_file:
        #             rev = rev_file.read()
        #         misc.set_file_metadata(s3_conn, self.app.config[
        #             'bucket_cluster'], self.app.config.cloudman_source_file_name, 'revision', rev)
        # except Exception, e:
        #     log.debug("Error setting revision metadata on newly copied cm.tar.gz in bucket %s: %s"
        #               % (self.app.config['bucket_cluster'], e))
        # Create an empty file whose name is the name of this cluster (useful
        # as a reference)
        cn_file = os.path.join(self.app.config['cloudman_home'],
                               "%s.clusterName" % self.app.config['cluster_name'])
        with open(cn_file, 'w'):
            pass
        if os.path.exists(cn_file):
            log.debug("Saving '%s' file to cluster bucket '%s' as '%s.clusterName'" % (
                cn_file, self.app.config['bucket_cluster'], self.app.config['cluster_name']))
            misc.save_file_to_bucket(s3_conn, self.app.config['bucket_cluster'],
                                     "%s.clusterName" % self.app.config['cluster_name'], cn_file)

    def _start_services(self):
        config_changed = False  # Flag to indicate if cluster conf was changed
        # Check and add any new services
        for service in self.app.manager.service_registry.active():
            if service.state == service_states.UNSTARTED or \
               service.state == service_states.SHUT_DOWN and \
               service.state != service_states.STARTING:
                log.debug("Monitor adding service '%s'" % service.get_full_name())
                self.last_system_change_time = Time.now()
                if service.add():
                    log.debug("Monitor done adding service {0} (setting config_changed)"
                              .format(service.get_full_name()))
                    config_changed = True
            # log.debug("Monitor DIDN'T add service {0}? Service state: {1}"\
            # .format(service.get_full_name(), service.state))
            # Store cluster conf after all services have been added.
            # NOTE: this flag relies on the assumption service additions are
            # sequential (i.e., monitor waits for the service add call to complete).
            # If any of the services are to be added via separate threads, a
            # system-wide flag should probably be maintained for that particular
            # service that would indicate the configuration of the service is
            # complete. This could probably be done by monitoring
            # the service state flag that is already maintained?
        svcs = self.app.manager.get_services(svc_type=ServiceType.FILE_SYSTEM)
        for svc in svcs:
            if ServiceRole.GALAXY_DATA in svc.svc_roles and svc.grow is not None:
                self.last_system_change_time = Time.now()
                self.expand_user_data_volume()
        return config_changed

    def _stop_services(self):
        """
        Initiate stopping of any services that have been marked as not `active`
        yet are not already UNSTARTED, COMPLETED, or SHUT_DOWN.
        """
        config_changed = False  # Flag to indicate if cluster conf was changed
        for service in self.app.manager.service_registry.itervalues():
            if not service.activated and service.state not in [
               service_states.UNSTARTED, service_states.COMPLETED,
               service_states.SHUT_DOWN]:
                log.debug("Monitor stopping service '%s'" % service.get_full_name())
                self.last_system_change_time = Time.now()
                service.remove()
                config_changed = True
        return config_changed

    def __check_amqp_messages(self):
        # Check for any new AMQP messages
        m = self.conn.recv()
        while m is not None:
            def do_match():
                match = False
                for inst in self.app.manager.worker_instances:
                    if str(inst.id) == str(m.properties['reply_to']):
                        match = True
                        inst.handle_message(m.body)
                return match

            if not do_match():
                log.debug("No instance (%s) match found for message %s; will add instance now!"
                          % (m.properties['reply_to'], m.body))
                if self.app.manager.add_live_instance(m.properties['reply_to']):
                    do_match()
                else:
                    log.warning("Potential error, got message from instance '%s' "
                                "but not aware of this instance. Ignoring the instance."
                                % m.properties['reply_to'])
            m = self.conn.recv()

    def __check_if_cluster_ready(self):
        """
        Check if all active cluster services are running and set cluster state
        to READY.
        """
        cluster_ready_flag = True
        # Check if an activated service is still not RUNNING
        for s in self.app.manager.service_registry.active():
            if not (s.state == service_states.RUNNING or
                    s.state == service_states.COMPLETED):
                cluster_ready_flag = False
                break
        if self.app.manager.cluster_status != cluster_status.READY and \
           self.app.manager.cluster_status != cluster_status.SHUTTING_DOWN and \
           self.app.manager.cluster_status != cluster_status.TERMINATED and \
           cluster_ready_flag:
            self.app.manager.cluster_status = cluster_status.READY
            self.store_cluster_config()  # Always save config on cluster_ready
            msg = "All cluster services started; the cluster is ready for use."
            log.info(msg)
            self.app.msgs.info(msg)

    def __monitor(self):
        log.debug("Starting __monitor thread")
        if not self.app.manager.manager_started:
            if not self.app.manager.start():
                log.critical("\n\n***** Manager failed to start *****\n")
                return False
        log.debug("Monitor started; manager started")
        while self.running:
            self.sleeper.sleep(4)
            self.__check_amqp_messages()
            if self.app.manager.cluster_status == cluster_status.TERMINATED:
                self.running = False
                return
            # In case queue connection was not established, try again (this will happen if
            # RabbitMQ does not start in time for CloudMan)
            if not self.conn.is_connected():
                log.debug(
                    "Trying to setup AMQP connection; conn = '%s'" % self.conn)
                self.conn.setup()
                continue
            # Do a periodic system state update (eg, services, workers)
            self._update_frequency()
            if (Time.now() - self.last_update_time).seconds > self.update_frequency:
                self.last_update_time = Time.now()
                for service in self.app.manager.service_registry.active():
                    service.status()
                # Indicate migration is in progress
                migration_service = self.app.manager.get_services(svc_role=ServiceRole.MIGRATION)
                if migration_service:
                    migration_service = migration_service[0]
                    msg = "Migration service in progress; please wait."
                    if migration_service.state == service_states.RUNNING:
                        if not self.app.msgs.message_exists(msg):
                            self.app.msgs.critical(msg)
                    elif migration_service.state == service_states.COMPLETED:
                        self.app.msgs.remove_message(msg)
                # Log current services' states (in condensed format)
                svcs_state = "S&S: "
                for s in self.app.manager.service_registry.itervalues():
                    svcs_state += "%s..%s; " % (s.get_full_name(), 'OK' if s.state == 'Running' else s.state)
                log.debug(svcs_state)
                # Check the status of worker instances
                for w_instance in self.app.manager.worker_instances:
                    if w_instance.is_spot():
                        w_instance.update_spot()
                        if not w_instance.spot_was_filled():
                            # Wait until the Spot request has been filled to start
                            # treating the instance as a regular Instance
                            continue
                    # Send current mount points to ensure master and workers FSs are in sync
                    if w_instance.worker_status == "Ready":
                        w_instance.send_mount_points()
                    # As long we we're hearing from an instance, assume all OK.
                    if (Time.now() - w_instance.last_comm).seconds < 22:
                        # log.debug("Instance {0} OK (heard from it {1} secs ago)".format(
                        #     w_instance.get_desc(),
                        #     (Time.now() - w_instance.last_comm).seconds))
                        continue
                    # Explicitly check the state of a quiet instance (but only
                    # periodically)
                    elif (Time.now() - w_instance.last_state_update).seconds > 30:
                        log.debug("Have not heard from or checked on instance {0} "
                                  "for a while; checking now.".format(w_instance.get_desc()))
                        w_instance.maintain()
                    else:
                        log.debug("Instance {0} has been quiet for a while (last check "
                                  "{1} secs ago); will wait a bit longer before a check..."
                                  .format(w_instance.get_desc(), (Time.now() - w_instance.last_state_update).seconds))
            # Store cluster configuraiton if the configuration has changed
            config_changed = self._start_services()
            config_changed = config_changed or self._stop_services()
            self.__check_if_cluster_ready()
            # Opennebula has no object storage, so this is not working (yet)
            if config_changed and self.app.cloud_type != 'opennebula':
                self.store_cluster_config()
