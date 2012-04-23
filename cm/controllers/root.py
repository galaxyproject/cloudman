import logging
import os
import re
import subprocess

from cm.util.json import to_json_string
from cm.framework import expose
from cm.base.controller import BaseController
from cm.services import service_states
from cm.util.bunch import BunchToo
import cm.util.paths as paths

log = logging.getLogger( 'cloudman' )

class CM(BaseController):
    @expose
    def index( self, trans, **kwd ):
        if self.app.ud['role'] == 'worker':
            return trans.fill_template('worker_index.mako', master_ip = self.app.ud['master_ip'])
        else:
            cluster = {}
            if self.app.manager.get_instance_state():
                cluster['status'] = self.app.manager.get_instance_state()
            permanent_storage_size = self.app.manager.get_permanent_storage_size()
            initial_cluster_type = self.app.manager.initial_cluster_type
            cluster_name = self.app.ud['cluster_name']
            CM_url = self.get_CM_url(trans)
            return trans.fill_template( 'index.mako',
                                        cluster = cluster,
                                        permanent_storage_size = permanent_storage_size,
                                        initial_cluster_type = initial_cluster_type,
                                        cluster_name = cluster_name,
                                        master_instance_type = self.app.cloud_interface.get_type(),
                                        use_autoscaling = bool(self.app.manager.get_services('Autoscale')),
                                        image_config_support = BunchToo(self.app.config.ic),
                                        CM_url=CM_url,
                                        cloud_type=self.app.ud.get('cloud_type', 'ec2'))
    def get_CM_url(self, trans):
        changesets = self.app.manager.check_for_new_version_of_CM()
        if changesets.has_key('default_CM_rev') and changesets.has_key('user_CM_rev'):
            try:
                CM_url = trans.app.config.get("CM_url", "http://bitbucket.org/galaxy/cloudman/changesets/tip/")
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
        return trans.fill_template('instance_feed.mako', instances = self.app.manager.worker_instances)
    
    @expose
    def instance_feed_json(self, trans):
        dict_feed = {'instances' : [self.app.manager.get_status_dict()] + [x.get_status_dict() for x in self.app.manager.worker_instances]}
        return to_json_string(dict_feed)
    
    @expose
    def minibar(self, trans):
        return trans.fill_template('mini_control.mako')
    
    @expose
    def initialize_cluster(self, trans, g_pss=None, d_pss=None, startup_opt=None, shared_bucket=None):
        if self.app.manager.initial_cluster_type is None:
            pss = None
            if startup_opt == "Galaxy" or startup_opt == "Data" or startup_opt == "SGE":
                if g_pss is not None and g_pss.isdigit():
                    pss = int(g_pss)
                elif d_pss is not None and d_pss.isdigit():
                    pss = int(d_pss)
                self.app.manager.init_cluster(startup_opt, pss)
            elif startup_opt == "Shared_cluster":
                if shared_bucket is not None:
                    self.app.manager.init_shared_cluster(shared_bucket.strip())
                else:
                    return "Must provide shared bucket name; cluster configuration not set."
        else:
            return "Cluster already set to type '%s'" % self.app.manager.initial_cluster_type
        return "Cluster configuration '%s' received and processed." % startup_opt
    
    @expose
    def expand_user_data_volume(self, trans, new_vol_size, vol_expand_desc=None, delete_snap=False):
        if delete_snap:
            delete_snap = True
        try:
            if new_vol_size.isdigit():
                new_vol_size = int(new_vol_size)
                # log.debug("Data volume size before expansion: '%s'" % self.app.manager.get_permanent_storage_size())
                if new_vol_size > self.app.manager.get_permanent_storage_size() and new_vol_size < 1000:
                    self.app.manager.expand_user_data_volume(new_vol_size, vol_expand_desc, delete_snap)
        except ValueError, e:
            log.error("You must provide valid values: %s" % e)
            return "ValueError exception. Check the log."
        except TypeError, ex:
            log.error("You must provide valid value type: %s" % ex)
            return "TypeError exception. Check the log."
        except Exception, g_ex:
            log.error("Unknown Exception: %s" % g_ex)
            return "Unknown exception. Check the log for details."
        return self.instance_state_json(trans)
    
    @expose
    def update_file_system(self, trans, fs_name):
        self.app.manager.update_file_system(fs_name)
        return self.instance_state_json(trans)
    
    @expose
    def add_fs(self, trans, bucket_name):
        if bucket_name != '':
            log.debug("Adding a file system from bucket {0}".format(bucket_name))
            self.app.manager.add_fs(bucket_name)
        else:
            log.error("Wanted to add a file system but provided no bucket name.")
        return "FSACK"
        # return self.get_all_services_status(trans)
    
    @expose
    def power(self, trans, number_nodes=0, pss=None):
        if self.app.manager.get_cluster_status() == 'OFF': # Cluster is OFF, initiate start procedure
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
            # Set state that will initiate starting
            self.app.manager.set_master_state( 'Start workers' )
        else: # Cluster is ON, initiate shutdown procedure
            self.app.shutdown()
        return "ACK"
    
    @expose
    def detailed_shutdown(self, trans, galaxy = True, sge = True, postgres = True, filesystems = True, volumes = True, instances = True):
        self.app.shutdown(sd_galaxy=galaxy, sd_sge=sge, sd_postgres=postgres, sd_filesystems=filesystems, sd_volumes=volumes, sd_instances=instances, sd_volumes_delete=volumes)
    
    @expose
    def kill_all(self, trans, terminate_master_instance=False, delete_cluster=False):
        if delete_cluster:
            delete_cluster = True
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
    def add_instances(self, trans, number_nodes, instance_type='', spot_price=''):
        try:
            number_nodes = int(number_nodes)
            if spot_price != '':
                spot_price = float(spot_price)
            else:
                spot_price = None
        except ValueError, e:
            log.error("You must provide valid value:  %s" % e)
            return self.instance_state_json(trans)
        self.app.manager.add_instances(number_nodes, instance_type, spot_price)
        return self.instance_state_json(trans)
    
    @expose
    def remove_instance(self, trans, instance_id=''):
        if instance_id == '':
            return
        self.app.manager.remove_instance( instance_id)
        return self.instance_state_json(trans)
    
    @expose
    def remove_instances(self, trans, number_nodes, force_termination):
        try:
            number_nodes = int(number_nodes)
            force_termination = True if force_termination == 'True' else False
            log.debug("Num nodes requested to terminate: %s, force termination: %s" \
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
        trans.response.set_content_type( "text" )
        return "\n".join(self.app.logger.logmessages)
    
    def tail(self, file_name, num_lines):
        """ Read num_lines from file_name starting at the end (using UNIX tail cmd)
        """
        ps = subprocess.Popen("tail -n %s %s" % (num_lines, file_name), shell=True, stdout=subprocess.PIPE)
        return str(ps.communicate()[0])
    
    @expose
    def service_log(self, trans, service_name, show=None, num_lines=None, **kwargs):
        # Choose log file path based on service name
        log = "No '%s' log available." % service_name
        if service_name == 'Galaxy':
            log_file = os.path.join(paths.P_GALAXY_HOME, 'paster.log')
        elif service_name == 'Postgres':
            log_file = '/tmp/pgSQL.log'
        elif service_name == 'SGE':
            # For SGE, we can get either the service log file or the queue conf file
            q = kwargs.get('q', None)
            if q == 'conf':
                log_file = os.path.join(paths.P_SGE_ROOT, 'all.q.conf')
            elif q == 'qstat':
                log_file = os.path.join('/tmp', 'qstat.out')
                # Save qstat output into a file so it can be read in the same way as log files
                try:
                    cmd = ('%s - galaxy -c "export SGE_ROOT=%s;\
                        . %s/default/common/settings.sh; \
                        %s/bin/lx24-amd64/qstat -f > %s"' 
                        % (paths.P_SU, paths.P_SGE_ROOT, paths.P_SGE_ROOT, paths.P_SGE_ROOT, log_file))
                    subprocess.call(cmd, shell=True)
                except OSError:
                    pass
            else:
                log_file = os.path.join(paths.P_SGE_CELL, 'messages')
        elif service_name == 'CloudMan':
                log_file = "paster.log"
        # Set log length
        if num_lines:
            if show == 'more':
                num_lines = int(num_lines) + 100
            elif show == 'less':
                num_lines = int(num_lines) - 100
        else:
            num_lines = 200 # By default, read the most recent 200 lines of the log
        # Get the log file content
        if os.path.exists(log_file):
            if show == 'all':
                with open(log_file) as f:
                    log = f.read()
            else:
                log = self.tail(log_file, num_lines=num_lines)
        # Convert the log file contents to unicode for proper display
        log = self.to_unicode(log)
        trans.response.set_content_type("text")
        return trans.fill_template("srvc_log.mako", 
                                   service_name=service_name,
                                   log=log, 
                                   num_lines=num_lines, 
                                   full=(show=='all'), 
                                   log_file=log_file)
    
    def to_unicode(self, a_string):
        """ 
        Convert a string to unicode in utf-8 format; if string is already unicode,
        does nothing because string's encoding cannot be determined by introspection.
        """
        a_string_type = type ( a_string )
        if a_string_type is str:
           return unicode( a_string, 'utf-8' )
        elif a_string_type is unicode:
           return a_string
    
    @expose
    def get_srvc_status(self, trans, srvc):
        return to_json_string({'srvc': srvc,
                               'status': self.app.manager.get_srvc_status(srvc)})
    
    @expose
    def get_all_services_status(self, trans):
        status_dict = self.app.manager.get_all_services_status()
        status_dict['galaxy_dns'] = self.get_galaxy_dns()
        snap_status = self.app.manager.snapshot_status()
        status_dict['snapshot'] = {'status' : str(snap_status[0]),
                                   'progress' : str(snap_status[1])}
        status_dict['master_is_exec_host'] = self.app.manager.master_exec_host
        return to_json_string(status_dict)
    
    @expose
    def full_update(self, trans, l_log=0):
        return to_json_string({ 'ui_update_data' : self.instance_state_json(trans, no_json=True),
                                'log_update_data' : self.log_json(trans, l_log, no_json=True)})
    
    @expose
    def log_json(self, trans, l_log=0, no_json=False):
        if no_json:
            return {'log_messages' : self.app.logger.logmessages[int(l_log):],
                                'log_cursor' : len(self.app.logger.logmessages)}
        else:
            return to_json_string({'log_messages' : self.app.logger.logmessages[int(l_log):],
                                'log_cursor' : len(self.app.logger.logmessages)})
    
    @expose
    def restart_service(self, trans, service_name):
        svcs = self.app.manager.get_services(service_name)
        if svcs:
            for service in svcs:
                service.remove()
            for service in svcs:
                service.start()
            return "%s service restarted." % service_name
        else:
            return "Cannot find %s service." % service_name
    
    @expose
    def update_galaxy(self, trans, repository="http://bitbucket.org/galaxy/galaxy-central", db_only=False):
        if db_only == 'True':
            db_only = True
            log.debug("Updating Galaxy database...")
        else:
            log.debug("Updating Galaxy... Using repository %s" % repository)
        svcs = self.app.manager.get_services('Galaxy')
        if svcs:
            for service in svcs:
                service.remove()
            if not db_only:
                cmd = '%s - galaxy -c "cd %s; hg --config ui.merge=internal:local pull %s --update"' % (paths.P_SU, paths.P_GALAXY_HOME, repository)
                retval = os.system(cmd)
                log.debug("Galaxy update cmd '%s'; return value %s" % (cmd, retval))
            cmd = '%s - galaxy -c "cd %s; sh manage_db.sh upgrade"' % (paths.P_SU, paths.P_GALAXY_HOME)
            retval = os.system(cmd)
            log.debug("Galaxy DB update cmd '%s'; return value %s" % (cmd, retval))
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
            # Test if provided values are in email format and remove non-email formatted ones
            admins_list_check = admins_list
            for admin in admins_list_check:
                 m = re.search('(\w+@\w+(?:\.\w+)+)', admin)
                 if not m:
                     admins_list.remove(admin)
            # Get a handle to Galaxy service and add admins
            svcs = self.app.manager.get_services('Galaxy')
            if len(svcs)>0 and len(admins_list)>0:
                svcs[0].add_galaxy_admin_users(admins_list)
                log.info("Galaxy admins added: %s; restarting Galaxy" % admins_list)
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
    def manage_service(self, trans, service_name, to_be_started=True):
        svcs = self.app.manager.get_services(service_name)
        if svcs:
            log.debug("Managing services: %s" % svcs)
            if to_be_started == "False":
                for s in svcs:
                    s.remove()
                return "%s stopped" % service_name
            else:
                for s in svcs:
                    s.start()
                return "%s started" % service_name
        else:
            return "Cannot find %s service." % service_name
    
    @expose
    def toggle_autoscaling(self, trans, as_min=None, as_max=None, as_instance_type=None):
        if self.app.manager.get_services('Autoscale'):
            log.debug("Turning autoscaling OFF")
            self.app.manager.stop_autoscaling()
        else:
            log.debug("Turning autoscaling ON")
            if self.check_as_vals(as_min, as_max):
                self.app.manager.start_autoscaling(int(as_min), int(as_max), as_instance_type)
            else:
                log.error("Invalid values for autoscaling bounds (min: %s, max: %s). Autoscaling is OFF." % (as_min, as_max))
        if self.app.manager.get_services('Autoscale'):

            return to_json_string({'running' : True,
                                    'as_min' : self.app.manager.get_services('Autoscale')[0].as_min,
                                    'as_max' : self.app.manager.get_services('Autoscale')[0].as_max,
                                    'ui_update_data' : self.instance_state_json(trans, no_json=True)})
        else:
            return to_json_string({'running' : False,
                                    'as_min' : 0,
                                    'as_max' : 0,
                                    'ui_update_data' : self.instance_state_json(trans, no_json=True)})
    
    @expose
    def adjust_autoscaling(self, trans, as_min_adj=None, as_max_adj=None):
        if self.app.manager.get_services('Autoscale'):
            if self.check_as_vals(as_min_adj, as_max_adj):
                # log.debug("Adjusting autoscaling; new bounds min: %s, max: %s" % (as_min_adj, as_max_adj))
                self.app.manager.adjust_autoscaling(int(as_min_adj), int(as_max_adj))
            else:
                log.error("Invalid values to adjust autoscaling bounds (min: %s, max: %s)." % (as_min_adj, as_max_adj))
            return to_json_string({'running' : True,
                                    'as_min' : self.app.manager.get_services('Autoscale')[0].as_min,
                                    'as_max' : self.app.manager.get_services('Autoscale')[0].as_max,
                                    'ui_update_data' : self.instance_state_json(trans, no_json=True)})
        else:
            return to_json_string({'running' : False,
                                    'as_min' : 0,
                                    'as_max' : 0,
                                    'ui_update_data' : self.instance_state_json(trans, no_json=True)})
    
    def check_as_vals(self, as_min, as_max):
        """ Check if limits for autoscaling are acceptable."""
        if as_min is not None and as_min.isdigit() and int(as_min)>=0 and int(as_min)<20 and \
           as_max is not None and as_max.isdigit() and int(as_max)>=int(as_min) and int(as_max)<20:
           return True
        else:
           return False
    
    @expose
    def share_a_cluster(self, trans, visibility, user_ids="", cannonical_ids=""):
        if visibility == 'shared' and user_ids != "" and cannonical_ids != "":
            # Check provided values
            try:
                u_ids = [x.strip() for x in user_ids.split(',')]
                c_ids = [x.strip() for x in cannonical_ids.split(',')]
                if len(u_ids) != len(c_ids):
                    log.error("User account ID fields must contain the same number of entries.")
                    return self.instance_state_json(trans)
                for i, u in enumerate(u_ids):
                    u_ids[i] = u.replace('-', '') # Try to remove any dashes, which is the way the number is displayed on AWS
                    if not u_ids[i].isdigit():
                        log.error("User IDs must be integers only, not '%s'" % u_ids[i])
                        return self.instance_state_json(trans)
            except Exception:
                log.error("Error processing values - user IDs: '%s', canonnical IDs: '%s'" % \
                    (user_ids, cannonical_ids))
                return self.instance_state_json(trans)
        elif visibility == 'public':
            u_ids = c_ids = None
        else:
            log.error("Incorrect values provided - permissions: '%s', user IDs: '%s', canonnical IDs: '%s'" % \
                (visibility, u_ids, c_ids))
            return self.instance_state_json(trans)
        self.app.manager.share_a_cluster(u_ids, c_ids)
        return self.instance_state_json(trans, no_json=True)
    
    @expose
    def get_shared_instances(self, trans):
        return to_json_string({'shared_instances': self.app.manager.get_shared_instances()})
    
    @expose
    def delete_shared_instance(self, trans, shared_instance_folder=None, snap_id=None):
        shared_instance_folder = '/'.join((shared_instance_folder.split('/')[1:]))
        return self.app.manager.delete_shared_instance(shared_instance_folder, snap_id)
    
    @expose
    def toggle_master_as_exec_host(self, trans):
        if self.app.manager.toggle_master_as_exec_host() is True:
            comment = "Master is an execution host."
        else:
            comment = "Master is not an execution host."
        return comment
    
    @expose
    def admin(self, trans):
        # Get names of the file systems
        filesystems = []
        fss = self.app.manager.get_services('Filesystem')
        for fs in fss:
            filesystems.append(fs.name)
        return trans.fill_template('admin.mako',
                                   ip=self.app.cloud_interface.get_self_public_ip(),
                                   key_pair_name=self.app.cloud_interface.get_key_pair_name(),
                                   filesystems=filesystems,
                                   bucket_cluster=self.app.ud['bucket_cluster'])
    
    @expose
    def cluster_status(self, trans):
        return trans.fill_template( "cluster_status.mako", instances = self.app.manager.worker_instances)
    
    @expose
    def get_user_data(self, trans):
        return to_json_string(self.app.ud)
    
    @expose
    def recover_monitor(self, trans, force='False'):
        if self.app.manager.console_monitor and force == 'False':
            return 'There is an existing monitor and force is not used. Try with more force.'
        else:
            if self.app.manager.recover_monitor(force=force):
                return "The instance has a new monitor now."
            else:
                return "There was an error. Can't create a new monitor."
    
    def get_galaxy_dns(self):
        """ Check if Galaxy is running and the the web UI is accessible. Return 
        DNS address if so, `#` otherwise. """
        g_s = self.app.manager.get_services('Galaxy')
        if g_s and g_s[0].state == service_states.RUNNING:
            dns = 'http://%s' % str( self.app.cloud_interface.get_self_public_ip() )
        else:
            # dns = '<a href="http://%s" target="_blank">Access Galaxy</a>' % str( 'localhost:8080' )
            dns = '#'
        return dns
    
    @expose
    def instance_state_json(self, trans, no_json=False):
        dns = self.get_galaxy_dns()
        snap_status = self.app.manager.snapshot_status()
        ret_dict = {'instance_state':self.app.manager.get_instance_state(),
                    'cluster_status':self.app.manager.get_cluster_status(),
                    'dns':dns,
                    'instance_status':{'idle': str(len(self.app.manager.get_idle_instances())),
                                        'available' : str(self.app.manager.get_num_available_workers()),
                                        'requested' : str(len(self.app.manager.worker_instances))},
                    'disk_usage':{'used':str(self.app.manager.disk_used),
                                    'total':str(self.app.manager.disk_total),
                                    'pct':str(self.app.manager.disk_pct)},
                    'data_status':self.app.manager.get_data_status(),
                    'app_status':self.app.manager.get_app_status(),
                    'all_fs' : self.app.manager.all_fs_status_array(),
                    'snapshot' : {'status' : str(snap_status[0]),
                                  'progress' : str(snap_status[1])},
                    'autoscaling': {'use_autoscaling': bool(self.app.manager.get_services('Autoscale')),
                                    'as_min': 'N/A' if not self.app.manager.get_services('Autoscale') else self.app.manager.get_services('Autoscale')[0].as_min,
                                    'as_max': 'N/A' if not self.app.manager.get_services('Autoscale') else self.app.manager.get_services('Autoscale')[0].as_max}
                    }
        if no_json:
            return ret_dict
        else:
            return to_json_string(ret_dict)
    
    @expose
    def update_users_CM(self, trans):
        return to_json_string({'updated':self.app.manager.update_users_CM()})
    
    @expose
    def masthead(self, trans):
        brand = trans.app.config.get( "brand", "" )
        if brand:
            brand ="<span class='brand'>/%s</span>" % brand
        CM_url = self.get_CM_url(trans)
        wiki_url = trans.app.config.get( "wiki_url", "http://g2.trac.bx.psu.edu/" )
        bugs_email = trans.app.config.get( "bugs_email", "mailto:galaxy-bugs@bx.psu.edu"  )
        blog_url = trans.app.config.get( "blog_url", "http://g2.trac.bx.psu.edu/blog"   )
        screencasts_url = trans.app.config.get( "screencasts_url", "http://main.g2.bx.psu.edu/u/aun1/p/screencasts" )
        return trans.fill_template( "masthead.mako", brand=brand, wiki_url=wiki_url, blog_url=blog_url,bugs_email=bugs_email, screencasts_url=screencasts_url, CM_url=CM_url )
    
