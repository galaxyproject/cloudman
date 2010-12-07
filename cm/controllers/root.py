import logging, os, re

from cm.util.json import to_json_string
from cm.framework import expose
from cm.base.controller import BaseController
from cm.services import service_states
import cm.util.paths as paths
# from cm.services.apps.postgres import PostgresService
# from cm.services.apps.sge import SGEService
# from cm.services.apps.galaxy import GalaxyService
# from cm.services.data.volume import Volume
# from cm.services.data.filesystem import Filesystem

log = logging.getLogger( 'cloudman' )

class CM( BaseController ):
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
                                        use_autoscaling = bool(self.app.manager.get_services('Autoscale')),
                                        CM_url=CM_url)
    def get_CM_url(self, trans):
        CM_url = trans.app.config.get( "CM_url", "http://bitbucket.org/galaxy/cloudman/changesets/" )
        changesets = self.app.manager.check_for_new_version_of_CM()
        if changesets.has_key('default_CM_rev') and changesets.has_key('user_CM_rev'):
            try:
                num_changes = int(changesets['default_CM_rev']) - int(changesets['user_CM_rev'])
                CM_url += changesets['default_CM_rev'] + '/' + str(num_changes)
            except Exception, e:
                log.debug("Error calculating changeset range for CM 'What's new' link: %s" % e)
        return CM_url
    
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
    def initialize_cluster(self, trans, g_pss=None, d_pss=None, startup_opt=None):
        if self.app.manager.initial_cluster_type is None:
            pss = None
            if startup_opt == "Galaxy" or startup_opt == "Data":
                if g_pss is not None and g_pss.isdigit():
                    pss = int(g_pss)
                elif d_pss is not None and d_pss.isdigit():
                    pss = int(d_pss)
            self.app.manager.init_cluster(startup_opt, pss)
        else:
            return "Cluster already set to type '%s'" % self.app.manager.initial_cluster_type
        return "Cluster configuration set."
    
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
    
    @expose
    def power( self, trans, number_nodes=0, pss=None ):
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
        if terminate_master_instance:
            self.app.manager.terminate_master_instance()
            return self.instance_state_json(trans)
        if delete_cluster:
            delete_cluster = True
        self.app.shutdown(delete_cluster=delete_cluster)
        return self.instance_state_json(trans)
    
    @expose
    def reboot(self, trans):
        return to_json_string({'rebooting':self.app.manager.reboot()})
    
    @expose
    def cleanup(self, trans):
        self.app.manager.shutdown()
    
    @expose
    def hard_clean( self, trans ):
        self.app.manager.clean()
    
    @expose
    def add_instances( self, trans, number_nodes, instance_type = ''):
        try:
            number_nodes = int(number_nodes)
        except ValueError, e:
            log.error("You must provide valid value.  %s" % e)
        self.app.manager.add_instances( number_nodes, instance_type)
        return self.instance_state_json(trans)
    
    @expose
    def remove_instance( self, trans, instance_id = ''):
        if instance_id == '':
            return
        self.app.manager.remove_instance( instance_id)
        return self.instance_state_json(trans)
    
    @expose
    def remove_instances( self, trans, number_nodes, force_termination ):
        try:
            number_nodes=int(number_nodes)
            log.debug("Num nodes requested to terminate: %s, force termination: %s" % (number_nodes, force_termination))
            self.app.manager.remove_instances(number_nodes, force_termination)
        except ValueError, e:
            log.error("You must provide valid value.  %s" % e)
        return self.instance_state_json(trans)
    
    @expose
    def log( self, trans, l_log = 0):
        trans.response.set_content_type( "text" )
        return "\n".join(self.app.logger.logmessages)
    
    @expose
    def galaxy_log( self, trans):
        # We might want to do some cleanup of the log here to display 
        # only relevant information, but for now, send the whole thing.
        trans.response.set_content_type( "text" )
        if os.path.exists('/mnt/galaxyTools/galaxy-central/paster.log'):
            f = open('/mnt/galaxyTools/galaxy-central/paster.log', 'rt')
            log = f.read()
            f.close()
            return log
        else:
            return "No galaxy log available."

    @expose
    def full_update(self, trans, l_log = 0):
        return to_json_string({ 'ui_update_data' : self.instance_state_json(trans, no_json=True),
                                'log_update_data' : self.log_json(trans, l_log, no_json=True)})

    
    @expose
    def log_json(self, trans, l_log = 0, no_json = False):
        if no_json:
            return {'log_messages' : self.app.logger.logmessages[int(l_log):],
                                'log_cursor' : len(self.app.logger.logmessages)}
        else:
            return to_json_string({'log_messages' : self.app.logger.logmessages[int(l_log):],
                                'log_cursor' : len(self.app.logger.logmessages)})
    
    @expose
    def manage_galaxy(self, trans, to_be_started=True):
        if to_be_started == "False":
            return self.app.manager.manage_galaxy(to_be_started=False)
        else:
            return self.app.manager.manage_galaxy(to_be_started=True)
    
    @expose
    def update_galaxy(self, trans, repository="http://bitbucket.org/galaxy/galaxy-central"):
        log.debug("Updating Galaxy... Using repository %s" % repository)
        svcs = self.app.manager.get_services('Galaxy')
        for service in svcs:
            service.remove()
        cmd = '%s - galaxy -c "cd %s; hg --config ui.merge=internal:local pull %s --update"' % (paths.P_SU, paths.P_GALAXY_HOME, repository)
        retval = os.system(cmd)
        log.debug("Galaxy update cmd '%s'; return value %s" % (cmd, retval))
        cmd = '%s - galaxy -c "cd %s; sh manage_db.sh upgrade"' % (paths.P_SU, paths.P_GALAXY_HOME)
        retval = os.system(cmd)
        log.debug("Galaxy DB update cmd '%s'; return value %s" % (cmd, retval))
        for service in svcs:
            service.start()
        log.debug("Done updating Galaxy")
    
    @expose
    def add_galaxy_admin_users(self, trans, admin_users=None):
        log.info('Received following list of admin users: %s' % admin_users)
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
                log.error("Either no admins provided (%s) or Galaxy service not found" % admins_list)
                return "Either no admins provided (%s) or Galaxy service not found" % admins_list
        else:
            log.error("No admin users provided: %s" % admin_users)
            return "No admin users provided: %s" % admin_users
    
    @expose
    def manage_sge(self, trans, to_be_started=True):
        if to_be_started == "False":
            return self.app.manager.manage_sge(to_be_started=False)
        else:
            return self.app.manager.manage_sge(to_be_started=True)
    
    @expose
    def manage_postgres(self, trans, to_be_started=True):
        if to_be_started == "False":
            return self.app.manager.manage_postgres(to_be_started=False)
        else:
            return self.app.manager.manage_postgres(to_be_started=True)
    
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
    def admin(self, trans):
        return """
            <ul>
                <li>This admin panel is only a very temporary way to control galaxy services.  Use with caution.</li>
                <li><strong>Service Control</strong></li>
                <li><a href='manage_galaxy'>Start Galaxy</a></li>
                <li><a href='manage_galaxy?to_be_started=False'>Stop Galaxy</a></li>
                <form action="update_galaxy" method="get">
                    <input type="text" value="http://bitbucket.org/galaxy/galaxy-central" name="repository">
                    <input type="submit" value="Update Galaxy">
                </form>
                <form action="add_galaxy_admin_users" method="get">
                    <input type="text" value="CSV list of emails" name="admin_users">
                    <input type="submit" value="Add admin users">
                </form>
                <li><a href="/cloud/root/reboot">Reboot master</a></li>
                
                <li><a href='manage_postgres'>Start Postgres</a></li>
                <li><a href='manage_postgres?to_be_started=False'>Start Postgres</a></li>
                
                <li><a href='manage_sge'>Start SGE</a></li>
                <li><a href='manage_sge?to_be_started=False'>Stop SGE</a></li>
                
                <li><strong>Emergency Tools -use with care.</strong></li>
                <li><a href='recover_monitor'>Recover monitor.</a></li>
                <li><a href='recover_monitor?force=True'>Recover monitor *with Force*.</a></li>
                <li><a href='add_instances?number_nodes=1'>Add one instance</a></li>
                <li><a href='remove_instances?number_nodes=1'>Remove one instance</a></li>
                <li><a href='remove_instances?number_nodes=1&force=True'>Remove one instance *with Force*.</a></li>
                <li><a href='cleanup'>Cleanup - shutdown all services/instances, keep volumes</a></li>
                <li><a href='kill_all'>Kill all - shutdown everything, disconnect/delete all.</a></li>
            </ul>
                """
    
    @expose
    def cluster_status( self, trans ):
        return trans.fill_template( "cluster_status.mako", instances = self.app.manager.worker_instances)
    
    @expose
    def recover_monitor(self, trans, force='False'):
        if self.app.manager.console_monitor and force == 'False':
            return 'Force is unset or set to false, and there is an existing monitor.  Try with more force.  (force=True)'
        else:
            if self.app.manager.recover_monitor(force=force):
                return "The instance has a new monitor now."
            else:
                return "There was an error.  Can't create a new monitor."
    
    @expose
    def instance_state_json(self, trans, no_json=False):
        g_s = self.app.manager.get_services('Galaxy')
        if g_s and g_s[0].state == service_states.RUNNING:
            dns = 'http://%s' % str( self.app.cloud_interface.get_self_public_ip() )
        else: 
            # dns = '<a href="http://%s" target="_blank">Access Galaxy</a>' % str( 'localhost:8080' )
            dns = '#'
        ss_status = self.app.manager.snapshot_status()
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
                                'snapshot' : {'progress' : str(ss_status[1]),
                                              'status' : str(ss_status[0])},
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
    def masthead( self, trans ):
        brand = trans.app.config.get( "brand", "" )
        if brand:
            brand ="<span class='brand'>/%s</span>" % brand
        CM_url = self.get_CM_url(trans)
        wiki_url = trans.app.config.get( "wiki_url", "http://g2.trac.bx.psu.edu/" )
        bugs_email = trans.app.config.get( "bugs_email", "mailto:galaxy-bugs@bx.psu.edu"  )
        blog_url = trans.app.config.get( "blog_url", "http://g2.trac.bx.psu.edu/blog"   )
        screencasts_url = trans.app.config.get( "screencasts_url", "http://main.g2.bx.psu.edu/u/aun1/p/screencasts" )
        return trans.fill_template( "masthead.mako", brand=brand, wiki_url=wiki_url, blog_url=blog_url,bugs_email=bugs_email, screencasts_url=screencasts_url, CM_url=CM_url )
    
