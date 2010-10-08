import logging

from cm.util.json import to_json_string

from cm.framework import expose
from cm.base.controller import BaseController
from cm.services import service_states

# from cm.services.apps.postgres import PostgresService
# from cm.services.apps.sge import SGEService
# from cm.services.apps.galaxy import GalaxyService
# from cm.services.data.volume import Volume
# from cm.services.data.filesystem import Filesystem

log = logging.getLogger( 'cloudman' )

class CM( BaseController ):
    @expose
    def index( self, trans, **kwd ):
        cluster = {}
        if self.app.manager.get_instance_state():
            cluster['status'] = self.app.manager.get_instance_state()
        permanent_storage_size = self.app.manager.get_permanent_storage_size()
        initial_cluster_type = self.app.manager.initial_cluster_type
        cluster_name = self.app.ud['cluster_name']
        return trans.fill_template( 'index.mako', 
                                    cluster = cluster,
                                    permanent_storage_size = permanent_storage_size,
                                    initial_cluster_type = initial_cluster_type,
                                    cluster_name = cluster_name )
    
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
            self.app.manager.init_cluster(startup_opt, g_pss)
        else:
            return "Cluster already set to type '%s'" % self.app.manager.initial_cluster_type
        return "Cluster configuration set."
    
    @expose
    def expand_user_data_volume(self, trans, new_vol_size, vol_expand_desc=None):
        try:
            if new_vol_size.isdigit():
                new_vol_size = int(new_vol_size)
                # log.debug("Data volume size before expansion: '%s'" % self.app.manager.get_permanent_storage_size())
                if new_vol_size > self.app.manager.get_permanent_storage_size() and new_vol_size < 1000:
                    self.app.manager.expand_user_data_volume(new_vol_size, vol_expand_desc)
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
                    self.app.manager.create_user_data_vol = True
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
    def kill_all(self, trans):
        self.app.shutdown()
    
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
            return
        self.app.manager.add_instances( number_nodes, instance_type)
        

    @expose
    def remove_instance( self, trans, instance_id = ''):
        if instance_id == '':
            return
        self.app.manager.remove_instance( instance_id)

    @expose
    def remove_instances( self, trans, number_nodes, force_termination ):
        try:
            number_nodes=int(number_nodes)
        except ValueError, e:
            log.error("You must provide valid value.  %s" % e)
            return
        log.debug("Num nodes requested to terminate: %s, force termination: %s" % (number_nodes, force_termination))
        self.app.manager.remove_instances(number_nodes, force_termination)

    @expose
    def log( self, trans, l_log = 0):
        trans.response.set_content_type( "text" )
        return "\n".join(self.app.logger.logmessages)

    @expose
    def log_json(self, trans, l_log = 0):
        return to_json_string({'log_messages' : self.app.logger.logmessages[int(l_log):],
                                'log_cursor' : len(self.app.logger.logmessages)})
    
    @expose
    def manage_galaxy(self, trans, to_be_started=True):
        if to_be_started == "False":
            return self.app.manager.manage_galaxy(to_be_started=False)
        else:
            return self.app.manager.manage_galaxy(to_be_started=True)
    
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
    def admin(self, trans):
        return """<ul>
                <li>This admin panel is only a very temporary way to control galaxy services.  Use with caution.</li>
                <li><strong>Service Control</strong></li>
                <li><a href='manage_galaxy'>Start Galaxy</a></li>
                <li><a href='manage_galaxy?to_be_started=False'>Stop Galaxy</a></li>
                
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
    def instance_state_json(self, trans):
        g_s = self.app.manager.get_services('Galaxy')
        if g_s and g_s[0].state == service_states.RUNNING:
            dns = 'http://%s' % str( self.app.cloud_interface.get_self_public_ip() )
        else: 
            # dns = '<a href="http://%s" target="_blank">Access Galaxy</a>' % str( 'localhost:8080' )
            dns = '#'
        return to_json_string({'instance_state':self.app.manager.get_instance_state(),
                                'cluster_status':self.app.manager.get_cluster_status(),
                                'dns':dns,
                                'instance_status':{'idle': str(len(self.app.manager.get_idle_instances())), 
                                                    'available' : str(self.app.manager.get_num_available_workers()),
                                                    'requested' : str(len(self.app.manager.worker_instances))},
                                'disk_usage':{'used':str(self.app.manager.disk_used),
                                                'total':str(self.app.manager.disk_total),
                                                'pct':str(self.app.manager.disk_pct)},
                                # 'services'  : {'fs' : self.app.manager.fs_status_text(),
                                #                 'pg' : self.app.manager.pg_status_text(),
                                #                 'sge' : self.app.manager.sge_status_text(),
                                #                 'galaxy' : self.app.manager.galaxy_status_text()},
                                'all_fs' : self.app.manager.all_fs_status_array(),
                                'snapshot' : {'progress' : str(self.app.manager.snapshot_progress),
                                              'status' : str(self.app.manager.snapshot_status)}
                               })
    @expose
    def update_users_CM(self, trans):
        self.app.manager.update_users_CM()
        return trans.fill_template('index.mako')

    @expose
    def masthead( self, trans ):
        brand = trans.app.config.get( "brand", "" )
        if brand:
            brand ="<span class='brand'>/%s</span>" % brand
        CM_url = None
        if self.app.manager.check_for_new_version_of_CM():
            CM_url = trans.app.config.get( "CM_url", "http://bitbucket.org/galaxy/cloudman" )
        wiki_url = trans.app.config.get( "wiki_url", "http://g2.trac.bx.psu.edu/" )
        bugs_email = trans.app.config.get( "bugs_email", "mailto:galaxy-bugs@bx.psu.edu"  )
        blog_url = trans.app.config.get( "blog_url", "http://g2.trac.bx.psu.edu/blog"   )
        screencasts_url = trans.app.config.get( "screencasts_url", "http://main.g2.bx.psu.edu/u/aun1/p/screencasts" )
        return trans.fill_template( "masthead.mako", brand=brand, wiki_url=wiki_url, blog_url=blog_url,bugs_email=bugs_email, screencasts_url=screencasts_url, CM_url=CM_url )
