import json
import logging
import os
import subprocess
import time

import cm.util.paths as paths
from cm.util import Time
from cm.util import misc
from cm.base.controller import BaseController
from cm.framework import expose
from cm.services import ServiceRole, ServiceType, service_states
from cm.util.decorators import TestFlag
from cm.util import cluster_status

log = logging.getLogger('cloudman')


class CM(BaseController):
    @expose
    def index(self, trans, **kwd):
        if self.app.config['role'] == 'worker':
            return trans.fill_template('worker_index.mako',
                                       master_ip=self.app.config['master_public_ip'])
        else:
            permanent_storage_size = self.app.manager.get_permanent_storage_size()
            initial_cluster_type = self.app.manager.initial_cluster_type
            cluster_name = self.app.config['cluster_name']
            instance_types = self.app.config.instance_types
            CM_url = self.get_CM_url(trans)
            system_message = None
            if os.path.exists(paths.SYSTEM_MESSAGES_FILE):
                # Cloudman system messages from cm_boot exist
                with open(paths.SYSTEM_MESSAGES_FILE) as f:
                    system_message = f.read()
            default_data_size = self.app.manager.get_default_data_size() if \
                self.app.manager.get_default_data_size() == cluster_status.READY else 1
            return trans.fill_template('index.mako',
                                       permanent_storage_size=permanent_storage_size,
                                       initial_cluster_type=initial_cluster_type,
                                       cluster_name=cluster_name,
                                       master_instance_type=self.app.cloud_interface.get_type(),
                                       use_autoscaling=self.app.manager.service_registry.is_active('Autoscale'),
                                       CM_url=CM_url,
                                       cloud_type=self.app.config.cloud_type,
                                       instance_types=instance_types,
                                       system_message=system_message,
                                       default_data_size=default_data_size,
                                       transient_fs_size=self.app.manager.transient_fs_size(),
                                       cluster_storage_type=self.app.manager.cluster_storage_type)

    @expose
    @TestFlag({})
    def initialize_cluster(self, trans, startup_opt, storage_type="transient",
                           storage_size='0', share_string=None):
        """
        Initialize an uninitialized cluster. This method can be called only once.

        :type startup_opt: string
        :param startup_opt: Name of the cluster type option. Choose from
                            ``Galaxy``, ``Data``, or ``Shared_cluster``

        :type storage_type: string
        :param storage_type: Type of storage to use. Choose from ``volume``
                            or ``transient``.

        :type storage_size: list or string
        :param storage_size: The size of persistent storage medium. If supplying
                             a list, the first value in the list will be used.
                             The list values or a single string all must be
                             string representations of an integer.

        :type share_string: string
        :param share_string: Share-string ID from a shared cluster (e.g.,
            ``cm-0011923649e9271f17c4f83ba6846db0/shared/2013-07-01--21-00``).
            If this parameter is set, storage type and size parameters are
            ignored because they're defined by the cluster share.
        """
        # log.debug("startup_opt: {0}; storage_type: {1}; storage_size: {2}; "
        #           "share_string: {3}".format(startup_opt, storage_type,
        #                                      storage_size, share_string))
        if isinstance(storage_size, list):
            # There are couple of fields on the web form with the same
            # name so they come in as a list; parse the list and get the value
            storage_size = [x for x in storage_size if x]
            # Grab the value or default to 10 if not value was provided for
            # a volume-based storage or default to 0 otherwise (e.g., transient)
            if storage_size:
                storage_size = storage_size[0]
            elif storage_type == 'volume':
                storage_size = '10'
            else:
                storage_size = '0'
        try:
            storage_size = int(storage_size)
        except TypeError, te:
            error = "Wrong format for storage_size variable: {0}".format(te)
            log.debug(error)
            self.app.msgs.info(error)
            return error
        except ValueError, ve:
            error = "Wrong value for storage_size variable: {0}".format(ve)
            log.debug(error)
            self.app.msgs.info(error)
            return error
        error = self.app.manager.initialize_cluster_with_custom_settings(
            startup_opt, storage_type, storage_size, share_string)
        return error or self.instance_state_json(trans)

    @expose
    def cloudman_version(self, trans):
        dict_version = {'version': self.app.DEPLOYMENT_VERSION}
        return json.dumps(dict_version)

    def get_CM_url(self, trans):
        changesets = self.app.manager.check_for_new_version_of_CM()
        if 'default_CM_rev' in changesets and 'user_CM_rev' in changesets:
            try:
                CM_url = trans.app.config.cloudman_repo_url
                # num_changes = int(changesets['default_CM_rev']) - int(changesets['user_CM_rev'])
                CM_url += changesets['user_CM_rev'] + '::' + changesets['default_CM_rev']
                return CM_url
            except Exception, e:
                log.debug("Error calculating changeset range for CM 'What's new' link: %s" % e)
        return None

    @expose
    def combined(self, trans):
        return trans.fill_template('cm_combined.mako')

    @expose
    def instance_feed(self, trans):
        return trans.fill_template('instance_feed.mako',
                                   instances=self.app.manager.worker_instances)

    @expose
    def instance_feed_json(self, trans):
        dict_feed = {'instances': [self.app.manager.get_status_dict()] +
                     [x.get_status_dict() for x in self.app.manager.worker_instances]}
        return json.dumps(dict_feed)

    @expose
    def minibar(self, trans):
        return trans.fill_template('mini_control.mako')

    @expose
    def cluster_type(self, trans):
        """
        Get the type of the cluster that's been configured as a JSON dict
        """
        cluster_type = {'cluster_type': self.app.manager.initial_cluster_type}
        return json.dumps(cluster_type)

    @expose
    def expand_user_data_volume(self, trans, new_vol_size, fs_name='', vol_expand_desc='',
                                delete_snap=False):
        """
        Check for the validity of provided information and initiate expansion of
        a volume underlying the file system. If ``fs_name`` is provided, look for
        a file system with that name; otherwise, default to file system with role
        ``GALAXY_DATA``. During the resizing process, a volume snapshot is created.
        This snapshot can be preserved in user's account or with an optional
        description ``vol_expand_desc`` or deleted upon process completion by
        setting ``delete_snap``.
        """
        if delete_snap:
            delete_snap = True
        if not fs_name:
            fs_name = 'galaxy'  # Default to resizing the 'galaxy' file system
        log.debug("Initiating expansion of {0} file system to size {1} w/ "
                  "snap desc '{2}', which {3} be deleted after the expansion process "
                  "completes.".format(fs_name, new_vol_size, vol_expand_desc,
                                      "will" if delete_snap else "will not"))
        try:
            if new_vol_size.isdigit():
                new_vol_size = int(new_vol_size)
                log.debug("Data volume size before expansion: '%s'" %
                          self.app.manager.get_permanent_storage_size())
                if (new_vol_size > self.app.manager.get_permanent_storage_size()
                   and new_vol_size < 16000):
                    self.app.manager.expand_user_data_volume(new_vol_size,
                                                             fs_name=fs_name,
                                                             snap_description=vol_expand_desc,
                                                             delete_snap=delete_snap)
        except ValueError, e:
            log.error("You must provide valid values: %s" % e)
            return "ValueError exception. Check the log."
        except TypeError, ex:
            log.error("You must provide valid value type: %s" % ex)
            return "TypeError exception. Check the log."
        except Exception, g_ex:
            log.error("Unknown Exception: %s" % g_ex)
            return "Unknown exception. Check the log for details."
        return "Initiated '{0}' file system expansion".format(fs_name)

    @expose
    def snapshot_file_system(self, trans, fs_name):
        snap_ids = self.app.manager.snapshot_file_system(fs_name)
        return "Created snapshot(s) of file system {0}: {1}".format(fs_name, snap_ids)

    @expose
    def update_file_system(self, trans, fs_name):
        self.app.manager.update_file_system(fs_name)
        return "Updated file system '{0}'".format(fs_name)

    @expose
    def add_file_system(self, trans, fs_kind, dot=False, persist=False,
                        new_disk_size='', new_vol_fs_name='', vol_id=None,
                        vol_fs_name='', snap_id=None, snap_fs_name='',
                        bucket_name='', bucket_fs_name='', bucket_a_key='',
                        bucket_s_key='', nfs_server=None, nfs_fs_name='',
                        nfs_username='', nfs_pwd='', **kwargs):
        """
        Decide on the new file system kind and call the appropriate manager method.

        There are four options from which a new file system can be added (the
        value in parentheses is the expected value of ``fs_kind`` argument for
        the corresponding option)::
            * (AWS S3) bucket (bucket)
            * Existing volume (volume)
            * Existing snapshot (snapshot)
            * New volume (new_volume)
            * External NFS server (nfs)

        The ``dot`` parameter, if set to ``True``, will mark
        the new file system to be **deleted on termination**. The ``persist``
        parameter will, if set to ``True``, add the new file system to the
        cluster configuration, thus automatically adding it the next time
        this cluster is started.
        Note that although both of these two arguments can be set simultaneously,
        they are conflicting and the ``dot`` parameter will take precedence.

        The rest of the parameters define the details for each file system kind.
        """
        dot = True if dot == 'on' else False
        persist = True if persist == 'on' else False
        log.debug("Wanting to add a {1} file system of kind {0}"
                  .format(fs_kind, "persistent" if persist else "temporary"))
        if fs_kind == 'bucket':
            if bucket_name != '':
                # log.debug("Adding file system {0} from bucket {1}".format(bucket_fs_name, bucket_name))
                # Clean form input data
                if bucket_a_key == '':
                    bucket_a_key = None
                else:
                    bucket_a_key = bucket_a_key.strip()
                if bucket_s_key == '':
                    bucket_s_key = None
                else:
                    bucket_s_key = bucket_s_key.strip()
                self.app.manager.add_fs_bucket(bucket_name.strip(),
                                               bucket_fs_name.strip(),
                                               bucket_a_key=bucket_a_key,
                                               bucket_s_key=bucket_s_key,
                                               persistent=persist)
            else:
                log.error("Wanted to add a new file system from a bucket but no "
                          "bucket name was provided.")
        elif fs_kind == 'volume' or fs_kind == 'snapshot':
            log.debug("Adding '{2}' file system based on an existing {0}, {1}"
                      .format(fs_kind, vol_id if fs_kind == 'volume' else snap_id,
                              vol_fs_name if fs_kind == 'volume' else snap_fs_name))
            if fs_kind == 'volume':
                self.app.manager.add_fs_volume(vol_id=vol_id, fs_kind='volume',
                                               fs_name=vol_fs_name,
                                               persistent=persist, dot=dot)
            else:
                self.app.manager.add_fs_volume(snap_id=snap_id,
                                               fs_kind='snapshot',
                                               fs_name=snap_fs_name,
                                               persistent=persist, dot=dot)
        elif fs_kind == 'new_volume':
            log.debug("Adding a new '{0}' file system: volume-based,{2} persistent,{3} to "
                      "be deleted, of size {1}".format(new_vol_fs_name, new_disk_size, ('' if persist else ' not'),
                                                       ('' if dot else ' not')))
            self.app.manager.add_fs_volume(fs_name=new_vol_fs_name,
                                           fs_kind='new_volume',
                                           vol_size=new_disk_size,
                                           persistent=persist, dot=dot)
        elif fs_kind == 'nfs':
            log.debug("Adding a new '{0}' file system: nfs-based,{1} persistent."
                      .format(nfs_fs_name, ('' if persist else ' not')))
            self.app.manager.add_fs_nfs(nfs_server, nfs_fs_name,
                                        username=nfs_username, pwd=nfs_pwd,
                                        persistent=persist)
        else:
            log.error("Wanted to add a file system but did not recognize kind {0}".format(fs_kind))
        return "Initiated file system addition"

    @expose
    def power(self, trans, number_nodes=0, pss=None):
        if self.app.manager.get_cluster_status() == 'OFF':  # Cluster is OFF, initiate start procedure
            try:
                # If value of permanent_storage_size was supplied (i.e., this cluster is being
                # started for the first time), store the pss value in the app
                if pss:
                    self.app.permanent_storage_size = int(pss)
                self.app.manager.num_workers_requested = int(number_nodes)
            except ValueError, e:
                log.error("You must provide valid values: %s" % e)
                return
            except TypeError, ex:
                log.error("You must provide valid values: %s" % ex)
                return
        else:  # Cluster is ON, initiate shutdown procedure
            self.app.shutdown()
        return "ACK"

    @expose
    def detailed_shutdown(self, trans, galaxy=True, sge=True, postgres=True,
                          filesystems=True, volumes=True, instances=True):
        self.app.shutdown(
            sd_galaxy=galaxy, sd_sge=sge, sd_postgres=postgres,
            sd_filesystems=filesystems, sd_volumes=volumes,
            sd_instances=instances, sd_volumes_delete=volumes)

    @expose
    def kill_all(self, trans, terminate_master_instance=False, delete_cluster=False):
        print "delete_cluster='%s'" % delete_cluster
        if delete_cluster in ['True', 'true', 'on']:
            delete_cluster = True
        else:
            delete_cluster = False
        if terminate_master_instance:
            self.app.manager.terminate_master_instance(delete_cluster=delete_cluster)
            return self.instance_state_json(trans)
        self.app.shutdown(delete_cluster=delete_cluster)
        return self.instance_state_json(trans)

    @expose
    def reboot(self, trans):
        r = 'initiated' if self.app.manager.reboot() else 'failed'
        return "Reboot %s." % r

    @expose
    def cleanup(self, trans):
        self.app.manager.shutdown()

    @expose
    def hard_clean(self, trans):
        self.app.manager.clean()

    @expose
    def add_instances(self, trans, number_nodes, instance_type='', spot_price='',
                      custom_instance_type=''):
        try:
            number_nodes = int(number_nodes)
            if spot_price != '':
                spot_price = float(spot_price)
            else:
                spot_price = None
            if instance_type == 'custom_instance_type' and custom_instance_type:
                instance_type = custom_instance_type.strip()
            elif not instance_type:
                instance_type = self.app.cloud_interface.get_type()
        except ValueError, e:
            log.error("You must provide valid value:  %s" % e)
            return self.instance_state_json(trans)
        self.app.manager.add_instances(number_nodes, instance_type, spot_price)
        return self.instance_state_json(trans)

    @expose
    def remove_instance(self, trans, instance_id=''):
        if instance_id == '':
            return
        self.app.manager.remove_instance(instance_id)
        return self.instance_state_json(trans)

    @expose
    def reboot_instance(self, trans, instance_id=''):
        if instance_id == '':
            return
        # Set `count_reboot` to False by default because we don't want to count
        # manually-invoked reboots.
        self.app.manager.reboot_instance(instance_id, count_reboot=False)
        return self.instance_state_json(trans)

    @expose
    def remove_instances(self, trans, number_nodes, force_termination):
        try:
            number_nodes = int(number_nodes)
            force_termination = True if force_termination == 'True' else False
            log.debug("Num nodes requested to terminate: %s, force termination: %s"
                      % (number_nodes, force_termination))
            self.app.manager.remove_instances(number_nodes, force_termination)
        except ValueError, e:
            log.error("You must provide valid value.  %s" % e)
        return self.instance_state_json(trans)

    @expose
    def store_cluster_config(self, trans):
        self.app.manager.console_monitor.store_cluster_config()

    @expose
    def log(self, trans, l_log=0):
        trans.response.set_content_type("text")
        return "\n".join(self.app.logger.logmessages)

    def tail(self, file_name, num_lines):
        """ Read num_lines from file_name starting at the end (using UNIX tail cmd)
        """
        ps = subprocess.Popen("tail -n %s %s" % (num_lines, file_name), shell=True, stdout=subprocess.PIPE)
        return str(ps.communicate()[0])

    @expose
    def service_log(self, trans, service_name, show=None, num_lines=None, **kwargs):
        # Choose log file path based on service name
        log_contents = "No '%s' log available." % service_name
        log_file = None
        if service_name == 'Galaxy':
            log_file = os.path.join(self.app.path_resolver.galaxy_home, 'main.log')
        elif service_name == 'Postgres':
            log_file = '/tmp/pgSQL.log'
        elif service_name == "slurmctld":
            # For slurmctld, we can get queue status (ie, sinfo)
            q = kwargs.get('q', None)
            if q == 'sinfo':
                log_file = os.path.join('/tmp', 'sinfo.out')
                # Save sinfo output into a file so it can be read as a log file
                try:
                    cmd = ('/usr/bin/sinfo -l > {0}'.format(log_file))
                    subprocess.call(cmd, shell=True)
                except OSError:
                    pass
            else:
                log_file = "/var/log/slurm-llnl/slurmctld.log"
        elif service_name == "slurmd":
            log_file = "/var/log/slurm-llnl/slurmd.log"
        elif service_name == 'SGE':
            # For SGE, we can get either the service log file or the queue conf file
            q = kwargs.get('q', None)
            if q == 'conf':
                log_file = os.path.join(self.app.path_resolver.sge_root, 'all.q.conf')
            elif q == 'qstat':
                log_file = os.path.join('/tmp', 'qstat.out')
                # Save qstat output into a file so it can be read in the same way as log files
                try:
                    cmd = ('%s - galaxy -c "export SGE_ROOT=%s;\
                        . %s/default/common/settings.sh; \
                        %s/bin/lx24-amd64/qstat -f > %s"'
                           % (paths.P_SU, self.app.path_resolver.sge_root,
                              self.app.path_resolver.sge_root,
                              self.app.path_resolver.sge_root, log_file))
                    subprocess.call(cmd, shell=True)
                except OSError:
                    pass
            else:
                log_file = os.path.join(self.app.path_resolver.sge_cell, 'messages')
        elif service_name == 'CloudMan':
            log_file = "/var/log/cloudman/cloudman.log"
        elif service_name == 'GalaxyReports':
            log_file = os.path.join(self.app.path_resolver.galaxy_home, 'reports_webapp.log')
        elif service_name == 'Pulsar':
            log_file = os.path.join(self.app.path_resolver.pulsar_home, 'paster.log')
        # Set log length
        if num_lines:
            if show == 'more':
                num_lines = int(num_lines) + 100
            elif show == 'less':
                num_lines = int(num_lines) - 100
        else:
            num_lines = 200  # By default, read the most recent 200 lines of the log
        # Get the log file content
        if log_file and os.path.exists(log_file):
            if show == 'all':
                with open(log_file) as f:
                    log_contents = f.read()
            else:
                log_contents = self.tail(log_file, num_lines=num_lines)
        # Convert the log file contents to unicode for proper display
        log_contents = self.to_unicode(log_contents)
        trans.response.set_content_type("text")
        return trans.fill_template("srvc_log.mako",
                                   service_name=service_name,
                                   log_contents=log_contents,
                                   num_lines=num_lines,
                                   full=(show == 'all'),
                                   log_file=log_file)

    def to_unicode(self, a_string):
        """
        Convert a string to unicode in utf-8 format; if string is already unicode,
        does nothing because string's encoding cannot be determined by introspection.
        """
        a_string_type = type(a_string)
        if a_string_type is str:
            return unicode(a_string, 'utf-8')
        elif a_string_type is unicode:
            return a_string

    @expose
    def get_srvc_status(self, trans, srvc):
        return json.dumps({'srvc': srvc,
                           'status': self.app.manager.get_srvc_status(srvc)})

    @expose
    def get_all_services_status(self, trans):
        status_dict = self.app.manager.get_all_services_status()
        # status_dict['filesystems'] = self.app.manager.get_all_filesystems_status()
        status_dict['galaxy_dns'] = self.get_galaxy_dns(trans)
        status_dict['galaxy_rev'] = self.app.manager.get_galaxy_rev()
        status_dict['galaxy_admins'] = self.app.manager.get_galaxy_admins()
        snap_status = self.app.manager.snapshot_status()
        status_dict['snapshot'] = {'status': str(snap_status[0]),
                                   'progress': str(snap_status[1])}
        status_dict['master_is_exec_host'] = self.app.manager.master_exec_host
        status_dict['ignore_deps_framework'] = self.app.config.ignore_unsatisfiable_dependencies
        status_dict['messages'] = self.messages_string(self.app.msgs.get_messages())
        status_dict['cluster_startup_time'] = self.app.manager.startup_time.strftime("%b %d %Y %H:%M:%S")
        cluster_uptime = misc.format_time_delta(Time.now() - self.app.manager.startup_time)
        status_dict['cluster_uptime'] = cluster_uptime
        # status_dict['dummy'] = str(datetime.now()) # Used for testing only
        # print "status_dict: %s" % status_dict
        return json.dumps(status_dict)

    @expose
    def get_all_filesystems(self, trans):
        return json.dumps(self.app.manager.get_all_filesystems_status())

    @expose
    def full_update(self, trans):
        return json.dumps(
            {'ui_update_data': self.instance_state_json(trans, no_json=True),
             'log_update_data': self.log_json(trans, no_json=True),
             'messages': self.messages_string(self.app.msgs.get_messages())})

    @expose
    def log_json(self, trans, no_json=False):
        if no_json:
            return {'log_messages': self.app.logger.logmessages}
        else:
            return json.dumps({'log_messages': self.app.logger.logmessages})

    def messages_string(self, messages):
        """
        Convert all messages into a string representation.
        """
        msgs = []
        for msg in messages:
            msgs.append({'message': msg.message, 'level':
                        msg.level, 'added_at': str(msg.added_at)})
        return msgs

    @expose
    def dismiss_messages(self, trans):
        self.app.msgs.dismiss()

    @expose
    def restart_service(self, trans, service_name, service_role=None):
        svcs = self.app.manager.get_services(svc_role=service_role, svc_name=service_name)
        if svcs:
            for service in svcs:
                log.debug("As part of service restart, removing {0}".format(
                    service))
                self.app.manager.deactivate_master_service(service)
                # Wait until the service shuts down
                while (service.state != service_states.SHUT_DOWN and
                       service.state != service_states.ERROR):
                    time.sleep(2)
            for service in svcs:
                log.debug("As part of service restart, starting {0}".format(
                    service))
                self.app.manager.activate_master_service(service)
            return "%s service restarted." % service_name
        else:
            return "Cannot find %s service." % service_name

    @expose
    def update_galaxy(self, trans, repository="http://bitbucket.org/galaxy/galaxy-dist", db_only=False):
        if db_only == 'True':
            db_only = True
            log.debug("Updating Galaxy database...")
        else:
            log.debug("Updating Galaxy... Using repository %s" % repository)
        svcs = self.app.manager.get_services(svc_role=ServiceRole.GALAXY)
        if svcs:
            for service in svcs:
                service.remove()
            if not db_only:
                cmd = '%s - galaxy -c "cd %s; hg --config ui.merge=internal:local pull %s --update"' % (
                    paths.P_SU, self.app.path_resolver.galaxy_home, repository)
                retval = os.system(cmd)
                log.debug(
                    "Galaxy update cmd '%s'; return value %s" % (cmd, retval))
            cmd = '%s - galaxy -c "cd %s; sh manage_db.sh upgrade"' % (
                paths.P_SU, self.app.path_resolver.galaxy_home)
            retval = os.system(cmd)
            log.debug(
                "Galaxy DB update cmd '%s'; return value %s" % (cmd, retval))
            for service in svcs:
                service.start()
            comment = "Done updating Galaxy."
            log.debug(comment)
            return comment
        else:
            comment = "Galaxy service does not seem to be configured."
            log.warning(comment)
            return comment

    @expose
    def add_galaxy_admin_users(self, trans, admin_users=None):
        log.info("Received following list of admin users: '%s'" % admin_users)
        if admin_users is not None:
            admins_list = admin_users.split(',')
            # Test if provided values are in email format and remove non-email
            # formatted ones
            admins_list_check = admins_list
            for admin in admins_list_check:
                if '@' not in admin:
                    admins_list.remove(admin)
            # Get a handle to Galaxy service and add admins
            svcs = self.app.manager.get_services(svc_role=ServiceRole.GALAXY)
            if len(svcs) > 0 and len(admins_list) > 0:
                svcs[0].add_galaxy_admin_users(admins_list)
                log.info(
                    "Galaxy admins added: %s; restarting Galaxy" % admins_list)
                svcs[0].restart()
                return "Galaxy admins added: %s" % admins_list
            else:
                comment = "Either no acceptable admin values provided (%s) or Galaxy service not found." % admins_list
                log.warning(comment)
                return comment
        else:
            comment = "No admin users provided: '%s'" % admin_users
            log.warning(comment)
            return comment

    @expose
    def add_flocking_ip(self, trans, fDNS):
        """
        adding remote resource IP as a flocking IP into condor,
        allowing a local condor job to be run over a remote condor
        machine.

        The remote resource should have provided us with enough
        privilege such as allow_write and flock_from variables
        in their condor config file.
        """
        svcs = self.app.manager.get_services(svc_role=ServiceRole.HTCONDOR)
        if len(svcs) > 0:
            svcs[0].modify_htcondor("FLOCK_TO", "{0}".format(fDNS))
            svcs[0].modify_htcondor("ALLOW_WRITE", "{0}".format(fDNS))
            msg = "HTCondor flock IP {0} added".format(fDNS)
            log.info(msg)
            return msg
        else:
            comment = "HTCondor service not found."
            log.warning(comment)
            return comment

    @expose
    def manage_service(self, trans, service_name, to_be_started='True', is_filesystem=False):
        """
        Manage a CloudMan service identified by ``service_name``. Currently,
        managing a service means that the service can be started (if
        ``to_be_started`` argument is set to ``True``) or stopped (the default
        action). If wanting to manipulate a file system service, set
        ``is_filesystem`` to ``True`` and set ``service_name`` to be the file
        system name.
        """
        is_filesystem = (is_filesystem == 'True')  # convert to boolean
        to_be_started = (to_be_started == 'True')
        if is_filesystem:
            svc_type = ServiceType.FILE_SYSTEM
        else:
            svc_type = ServiceType.APPLICATION
        svcs = self.app.manager.get_services(
            svc_type=svc_type, svc_name=service_name)
        if svcs:
            log.debug("Managing services (starting? %s): %s" % (to_be_started, svcs))
            if to_be_started is False:
                for s in svcs:
                    self.app.manager.deactivate_master_service(s)
                return "%s stopped" % service_name
            else:
                for s in svcs:
                    self.app.manager.activate_master_service(s)
                return "%s started" % service_name
        else:
            msg = "Cannot find service '{0}'".format(service_name)
            # self.app.msgs.warning(msg)
            log.warning(msg)
            return msg

    @expose
    def toggle_autoscaling(self, trans, as_min=None, as_max=None, instance_type=None,
                           custom_instance_type='', num_queued_jobs='',
                           mean_runtime_threshold='', num_instances_to_add=''):
        if self.app.manager.service_registry.is_active('Autoscale'):
            log.debug("Turning autoscaling OFF")
            self.app.manager.stop_autoscaling()
        else:
            err = False
            log.debug("Turning autoscaling ON")
            if instance_type == 'custom_instance_type' and custom_instance_type:
                instance_type = custom_instance_type.strip()
            try:
                num_queued_jobs = int(num_queued_jobs) if num_queued_jobs else None
                mean_runtime_threshold = int(mean_runtime_threshold) if mean_runtime_threshold else None
                num_instances_to_add = int(num_instances_to_add) if num_instances_to_add else None
            except ValueError, e:
                log.error("Parameter value error: {0}".format(e))
                err = True
            if not err and self.check_as_vals(as_min, as_max):
                self.app.manager.start_autoscaling(
                    int(as_min), int(as_max), instance_type, num_queued_jobs,
                    mean_runtime_threshold, num_instances_to_add)
            else:
                log.error("Invalid values for autoscaling bounds (min: %s, "
                          "max: %s).  Autoscaling is OFF." % (as_min, as_max))
        if self.app.manager.service_registry.is_active('Autoscale'):
            return json.dumps({'running': True,
                               'as_min': self.app.manager.service_registry.get('Autoscale').as_min,
                               'as_max': self.app.manager.service_registry.get('Autoscale').as_max,
                               'ui_update_data': self.instance_state_json(trans, no_json=True)})
        else:
            return json.dumps({'running': False,
                               'as_min': 0,
                               'as_max': 0,
                               'ui_update_data': self.instance_state_json(trans, no_json=True)})

    @expose
    def adjust_autoscaling(self, trans, as_min_adj=None, as_max_adj=None,
                           instance_type=None, custom_instance_type='',
                           num_queued_jobs='', mean_runtime_threshold='',
                           num_instances_to_add=''):
        err = False
        if instance_type == 'custom_instance_type' and custom_instance_type:
            instance_type = custom_instance_type.strip()
        try:
            num_queued_jobs = int(num_queued_jobs) if num_queued_jobs else None
            mean_runtime_threshold = int(mean_runtime_threshold) if mean_runtime_threshold else None
            num_instances_to_add = int(num_instances_to_add) if num_instances_to_add else None
        except ValueError, e:
            log.error("Parameter value error: {0}".format(e))
            err = True
        if not err and self.app.manager.service_registry.is_active('Autoscale'):
            if self.check_as_vals(as_min_adj, as_max_adj):
                self.app.manager.adjust_autoscaling(
                    int(as_min_adj), int(as_max_adj), custom_instance_type,
                    num_queued_jobs, mean_runtime_threshold, num_instances_to_add)
            else:
                log.error("Invalid values to adjust autoscaling bounds (min: %s, max: %s)." % (
                    as_min_adj, as_max_adj))
            return json.dumps({'running': True,
                               'as_min': self.app.manager.service_registry.get('Autoscale').as_min,
                               'as_max': self.app.manager.service_registry.get('Autoscale').as_max,
                               'ui_update_data': self.instance_state_json(trans, no_json=True)})
        else:
            return json.dumps({'running': False,
                               'as_min': 0,
                               'as_max': 0,
                               'ui_update_data': self.instance_state_json(trans, no_json=True)})

    def check_as_vals(self, as_min, as_max):
        """ Check if limits for autoscaling are acceptable."""
        if as_min is not None and as_min.isdigit() and int(as_min) >= 0 and int(as_min) < 20 and \
                as_max is not None and as_max.isdigit() and int(as_max) >= int(as_min) and int(as_max) < 20:
            return True
        else:
            return False

    @expose
    def share_a_cluster(self, trans, visibility, user_ids="", canonical_ids="",
                        share_desc=""):
        if visibility == 'shared' and user_ids != "" and canonical_ids != "":
            # Check provided values
            try:
                u_ids = [x.strip() for x in user_ids.split(',')]
                c_ids = [x.strip() for x in canonical_ids.split(',')]
                if len(u_ids) != len(c_ids):
                    log.error(
                        "User account ID fields must contain the same number of entries.")
                    return self.instance_state_json(trans)
                for i, u in enumerate(u_ids):
                    u_ids[i] = u.replace(
                        '-', '')  # Try to remove any dashes, which is the way the number is displayed on AWS
                    if not u_ids[i].isdigit():
                        log.error(
                            "User IDs must be integers only, not '%s'" % u_ids[i])
                        return self.instance_state_json(trans)
            except Exception:
                log.error("Error processing values - user IDs: '%s', canonnical IDs: '%s'" % (user_ids, canonical_ids))
                return self.instance_state_json(trans)
        elif visibility == 'public':
            u_ids = c_ids = None
        else:
            log.error("Incorrect values provided - permissions: '%s', user IDs: '%s', "
                      "canonnical IDs: '%s'" % (visibility, u_ids, c_ids))
            return self.instance_state_json(trans)
        self.app.manager.share_a_cluster(u_ids, c_ids, share_desc[:255])
        return self.instance_state_json(trans, no_json=True)

    @expose
    def get_shared_instances(self, trans):
        return json.dumps({'shared_instances': self.app.manager.get_shared_instances()})

    @expose
    def delete_shared_instance(self, trans, shared_instance_folder=None, snap_id=None):
        shared_instance_folder = '/'.join(
            (shared_instance_folder.split('/')[1:]))
        return self.app.manager.delete_shared_instance(shared_instance_folder, snap_id)

    @expose
    def toggle_master_as_exec_host(self, trans):
        """
        Toggle the master instance's role as a job manager execution host.

        Calling this method happens as a user-invoked action and it hence
        sets an internal flag to stick with the user's preferred choice.
        """
        if self.app.manager.toggle_master_as_exec_host() is True:
            comment = "Master is an execution host."
            # This means the user wants to keep the master an exec host
            self.app.manager.keep_master_exec_host = True
        else:
            comment = "Master is not an execution host."
            self.app.manager.keep_master_exec_host = False
        return comment

    @expose
    def toggle_ssl(self, trans):
        """
        Toggle use of SSL for the nginx proxy server.

        This will generate a self-signed certificate and update nginx config to
        use it - note that this will result in a browser warning regarding an
        untrusted certificate. Also note that this only works on images that
        have nginx v1.4+.

        TODO: Extract nginx into its own service so SSL can be turned on
        without requiring Galaxy service.
        """
        log.debug("Toggling SSL")
        nginx_service = self.app.manager.service_registry.get('Nginx')
        if nginx_service:
            nginx_service.reconfigure(setup_ssl=(not nginx_service.ssl_is_on))
            return "SSL toggled"

    @expose
    def toggle_dependency_framework(self, trans):
        """
        Toggle config option ``ignore_unsatisfiable_dependencies``.

        With ``ignore_unsatisfiable_dependencies`` set, Cloudman's service
        dependency framework is disabled a service can be started without its
        dependencies being met.
        """
        self.app.config.ignore_unsatisfiable_dependencies = (
            not self.app.config.ignore_unsatisfiable_dependencies)
        return "Ignore dependencies set to {0}".format(
            self.app.config.ignore_unsatisfiable_dependencies)

    @expose
    def admin(self, trans):
        if self.app.config['role'] == 'worker':
            return trans.fill_template('worker_index.mako', master_ip=self.app.config['master_public_ip'])
        # Get names of the file systems
        filesystems = []
        fss = self.app.manager.get_services(svc_type=ServiceType.FILE_SYSTEM)
        for fs in fss:
            filesystems.append(fs.name)
        # Get a list of APPLICATION services
        app_services = []
        sl = self.app.manager.get_services(svc_type=ServiceType.APPLICATION)
        for s in sl:
            app_services.append(s.name)
        # Explicitly add the PSSService
        app_services.append(self.app.manager.service_registry.get('PSS'))
        return trans.fill_template('admin.mako',
                                   ip=self.app.cloud_interface.get_public_ip(),
                                   key_pair_name=self.app.cloud_interface.get_key_pair_name(),
                                   filesystems=filesystems,
                                   bucket_cluster=self.app.config['bucket_cluster'],
                                   cloud_type=self.app.config.cloud_type,
                                   initial_cluster_type=self.app.manager.initial_cluster_type,
                                   cluster_name=self.app.config['cluster_name'],
                                   app_services=sorted(app_services),
                                   cluster_storage_type=self.app.manager.cluster_storage_type)

    @expose
    def cluster_status(self, trans):
        return trans.fill_template("cluster_status.mako", instances=self.app.manager.worker_instances)

    @expose
    def get_user_data(self, trans):
        return json.dumps(self.app.config.user_data)

    @expose
    def recover_monitor(self, trans, force='False'):
        if self.app.manager.console_monitor and force == 'False':
            return 'There is an existing monitor and force is not used. Try with more force.'
        else:
            if self.app.manager.recover_monitor(force=force):
                return "The instance has a new monitor now."
            else:
                return "There was an error. Can't create a new monitor."

    def get_galaxy_dns(self, trans):
        """ Check if Galaxy is running and the the web UI is accessible.
        If it is, return the base url of the request (which is where Galaxy is hosted) instead of
        using the cloud service provided ipv4.
        This allows the use of custom external domains pointed to elastic ips, like those used
        for cloud1.galaxyproject.org.  It's not feasible to gather this information from the EC2 interface.
        """
        g_s = self.app.manager.get_services(svc_role=ServiceRole.GALAXY)
        if g_s and g_s[0].state == service_states.RUNNING:
            try:
                dns = '%s/galaxy' % trans.request.host_url
            except:
                # Default to the old method in case of error.
                dns = 'http://%s/galaxy' % str(self.app.cloud_interface.get_public_hostname())
        else:
            dns = '#'
        return dns

    @expose
    def static_instance_state_json(self, trans, no_json=False):
        ret_dict = {'master_ip': self.app.cloud_interface.get_public_ip(),
                    'master_id': self.app.cloud_interface.get_instance_id(),
                    'ami_id': self.app.cloud_interface.get_ami(),
                    'availability_zone': self.app.cloud_interface.get_zone(),
                    'key_pair_name': self.app.cloud_interface.get_key_pair_name(),
                    'security_groups': self.app.cloud_interface.get_security_groups(),
                    'master_host_name': self.app.cloud_interface.get_public_hostname()
                    }
        if no_json:
            return ret_dict
        else:
            return json.dumps(ret_dict)

    @expose
    def instance_state_json(self, trans, no_json=False):
        dns = self.get_galaxy_dns(trans)
        snap_status = self.app.manager.snapshot_status()
        ret_dict = {'cluster_status': self.app.manager.get_cluster_status(),
                    'dns': dns,
                    'testflag': self.app.TESTFLAG,
                    'instance_status': {'idle': str(len(self.app.manager.get_idle_instances())),
                                        'available': str(self.app.manager.get_num_available_workers()),
                                        'requested': str(len(self.app.manager.worker_instances))},
                    'disk_usage': self.app.manager.check_disk(),
                    'data_status': self.app.manager.get_data_status(),
                    'app_status': self.app.manager.get_app_status(),
                    'cluster_storage_type': self.app.manager.cluster_storage_type,
                    'snapshot': {'status': str(snap_status[0]),
                                 'progress': str(snap_status[1])},
                    'autoscaling': self.autoscaling_state(trans, no_json=True)}
        if no_json:
            return ret_dict
        else:
            return json.dumps(ret_dict)

    @expose
    def autoscaling_state(self, trans, no_json=False):
        """
        Return the properties of the Autoscale service.
        """
        use_autoscaling = self.app.manager.service_registry.is_active('Autoscale')
        if use_autoscaling:
            svc = self.app.manager.service_registry.get('Autoscale')
        ret_dict = {
            'use_autoscaling': use_autoscaling,
            'as_min': 'N/A' if not use_autoscaling else svc.as_min,
            'as_max': 'N/A' if not use_autoscaling else svc.as_max,
            'as_num_queued_jobs': 2 if not use_autoscaling else svc.num_queued_jobs,
            'as_mean_runtime_threshold': 60 if not use_autoscaling else svc.mean_runtime_threshold,
            'as_num_instances_to_add': 1 if not use_autoscaling else svc.num_instances_to_add}
        if no_json:
            return ret_dict
        else:
            return json.dumps(ret_dict)

    @expose
    def update_users_CM(self, trans):
        pass
        # return json.dumps({'updated': self.app.manager.update_users_CM()})

    @expose
    def masthead(self, trans):
        brand = trans.app.config.info_brand
        if brand:
            brand = "<span class='brand'>/%s</span>" % brand
        CM_url = self.get_CM_url(trans)
        wiki_url = trans.app.config.info_wiki_url
        bugs_email = trans.app.config.info_bugs_email
        blog_url = trans.app.config.info_blog_url
        screencasts_url = trans.app.config.info_screencasts_url
        return trans.fill_template("masthead.mako", brand=brand, wiki_url=wiki_url,
                                   blog_url=blog_url, bugs_email=bugs_email,
                                   screencasts_url=screencasts_url, CM_url=CM_url)
