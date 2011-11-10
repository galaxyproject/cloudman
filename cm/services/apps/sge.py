import shutil, tarfile, os, time, subprocess, pwd, grp, datetime, commands

from cm.services.apps import ApplicationService
from cm.util import paths, templates
from cm.services import service_states
from cm.util import misc

import logging
log = logging.getLogger( 'cloudman' )


class SGEService( ApplicationService ):
    def __init__(self, app):
        super(SGEService, self).__init__(app)
        self.svc_type = "SGE"
        self.hosts = []
    
    def start(self):
        self.state = service_states.STARTING
        if self.unpack_sge():
            self.configure_sge()
        else:
            log.error("Error adding service '%s'" % self.svc_type)
            self.state = service_states.ERROR
    
    def remove(self):
        # TODO write something to clean up SGE in the case of restarts?
        log.info("Removing SGE service")
        self.state = service_states.SHUTTING_DOWN
        for inst in self.app.manager.worker_instances:
            self.remove_sge_host(inst)
        
        misc.run('export SGE_ROOT=%s; . $SGE_ROOT/default/common/settings.sh; %s/bin/lx24-amd64/qconf -km' % (paths.P_SGE_ROOT, paths.P_SGE_ROOT), "Problems stopping SGE master", "Successfully stopped SGE master")
        self.state = service_states.SHUT_DOWN
    
    def clean(self):
        """ Stop SGE and clean up the system as if SGE was never installed. Useful for CloudMan restarts."""
        self.remove()
        if self.state == service_states.SHUT_DOWN:
            misc.run('rm -rf %s/*' % paths.SGE_ROOT, "Error cleaning SGE_ROOT (%s)" % paths.SGE_ROOT, "Successfully cleaned SGE_ROOT")
            with open(paths.LOGIN_SHELL_SCRIPT, 'r') as f:
                lines = f.readlines()
            d1 = d2 = -1
            for i, l in enumerate(lines):
                if "export SGE_ROOT=%s" % paths.P_SGE_ROOT in l:
                    d1 = i
                if ". $SGE_ROOT/default/common/settings.sh" in l:
                    d2 = i
            if d1 != -1:
                del lines[d1]
            if d2 != -1:
                del lines[d2]
            if d1!=-1 or d2!=-1:
                with open(paths.LOGIN_SHELL_SCRIPT, 'w') as f:
                    f.writelines(lines)
    
    def unpack_sge( self ):
        if self.app.TESTFLAG is True:
            log.debug( "Attempted to get volumes, but TESTFLAG is set." )
            return False
        log.debug("Unpacking SGE from '%s'" % paths.P_SGE_TARS)
        os.putenv( 'SGE_ROOT', paths.P_SGE_ROOT )
        # Ensure needed directory exists
        if not os.path.exists( paths.P_SGE_TARS ):
            log.error( "'%s' directory with SGE binaries does not exist! Aborting SGE setup." % paths.P_SGE_TARS )
            return False
        if not os.path.exists( paths.P_SGE_ROOT ):
            os.mkdir ( paths.P_SGE_ROOT )
        # Ensure SGE_ROOT directory is empty (useful for restarts)
        if len(os.listdir(paths.P_SGE_ROOT)) > 0:
            # Check if qmaster is running in that case
            self.status()
            if self.state==service_states.RUNNING:
                log.info("Found SGE already running; will reconfigure it.")
                self.stop_sge()
            log.debug("Cleaning '%s' directory." % paths.P_SGE_ROOT)
            for base, dirs, files in os.walk(paths.P_SGE_ROOT):
                for f in files:
                    os.unlink(os.path.join(base, f))
                for d in dirs:
                    shutil.rmtree(os.path.join(base, d))
        log.debug( "Unpacking SGE to '%s'." % paths.P_SGE_ROOT )
        tar = tarfile.open( '%s/ge-6.2u5-common.tar.gz' % paths.P_SGE_TARS )
        tar.extractall( path=paths.P_SGE_ROOT )
        tar.close()
        tar = tarfile.open( '%s/ge-6.2u5-bin-lx24-amd64.tar.gz' % paths.P_SGE_TARS )
        tar.extractall( path=paths.P_SGE_ROOT )
        tar.close()
        subprocess.call( '%s -R sgeadmin:sgeadmin %s' % (paths.P_CHOWN, paths.P_SGE_ROOT), shell=True )
        return True
    
    def configure_sge( self ):
        if self.app.TESTFLAG is True:
            log.debug( "Attempted to get volumes, but TESTFLAG is set." )
            return None
        log.info( "Configuring SGE..." )
        # Add master as an execution host
        # Additional execution hosts will be added later, as they start
        exec_nodes = self.app.cloud_interface.get_self_private_ip() 
        SGE_config_file = '%s/galaxyEC2.conf' % paths.P_SGE_ROOT
        with open( SGE_config_file, 'w' ) as f:
            print >> f, templates.SGE_INSTALL_TEMPLATE % ( self.app.cloud_interface.get_self_private_ip(), self.app.cloud_interface.get_self_private_ip(), exec_nodes )
        os.chown(SGE_config_file, pwd.getpwnam("sgeadmin")[2], grp.getgrnam("sgeadmin")[2])
        log.debug("Created SGE install template as file '%s'" % SGE_config_file)
        # Check if /lib64/libc.so.6 exists - it's required by SGE but on 
        # Ubuntu 11.04 the location and name of the library have changed
        if not os.path.exists('/lib64/libc.so.6'):
            if os.path.exists('/lib64/x86_64-linux-gnu/libc-2.13.so'):
                os.symlink('/lib64/x86_64-linux-gnu/libc-2.13.so', '/lib64/libc.so.6')
            else:
                log.debug("SGE config is likely to fail because '/lib64/libc.so.6' lib does not exists...")
        log.debug("Setting up SGE.")
        if misc.run('cd %s; ./inst_sge -m -x -auto %s' % (paths.P_SGE_ROOT, SGE_config_file), "Setting up SGE did not go smoothly", "Successfully set up SGE"):
            log.info("Successfully setup SGE; configuring SGE")
            SGE_allq_file = '%s/all.q.conf' % paths.P_SGE_ROOT
            with open( SGE_allq_file, 'w' ) as f:
                print >> f, templates.ALL_Q_TEMPLATE
            os.chown(SGE_allq_file, pwd.getpwnam("sgeadmin")[2], grp.getgrnam("sgeadmin")[2])
            log.debug("Created SGE all.q template as file '%s'" % SGE_allq_file)
            misc.run('cd %s; ./bin/lx24-amd64/qconf -Mq %s' % (paths.P_SGE_ROOT, SGE_allq_file), "Error modifying all.q", "Successfully modified all.q")
            # Prevent 'Unexpected operator' to show up at shell login (SGE bug on Ubuntu)
            misc.replace_string(paths.P_SGE_ROOT + '/util/arch', "         libc_version=`echo $libc_string | tr ' ,' '\\n' | grep \"2\.\" | cut -f 2 -d \".\"`", "         libc_version=`echo $libc_string | tr ' ,' '\\n' | grep \"2\.\" | cut -f 2 -d \".\" | sort -u`")
            misc.run("sed -i.bak 's/sort -u/sort -u | head -1/g' %s/util/arch" % paths.P_SGE_ROOT, "Error modifying %s/util/arch" % paths.P_SGE_ROOT, "Modified %s/util/arch" % paths.P_SGE_ROOT)
            misc.run("chmod +rx %s/util/arch" % paths.P_SGE_ROOT, "Error chmod %s/util/arch" % paths.P_SGE_ROOT, "Successfully chmod %s/util/arch" % paths.P_SGE_ROOT)
            log.debug("Configuring users' SGE profiles" )
            with open(paths.LOGIN_SHELL_SCRIPT, 'a') as f:
                f.write("\nexport SGE_ROOT=%s" % paths.P_SGE_ROOT)
                f.write("\n. $SGE_ROOT/default/common/settings.sh\n")
            return True
        return False
    
    def add_sge_host( self, inst ):
        # TODO: Should check to ensure SGE_ROOT mounted on worker
        time.sleep(10) # Wait in hope that SGE processed last host addition
        inst_ip = inst.get_private_ip()
        error = False
        if not inst_ip:
            log.error( "Instance '%s' IP not retrieved! Cannot add instance to SGE." % inst.id )
            return False
        log.debug("Adding instance '%s' w/ private IP '%s' to SGE." % (inst.id, inst_ip))
        
        #== Add instance as SGE administrative host
        log.info("Adding instance '%s' as SGE administrative host." % inst.id)
        stderr = stdout = None
        cmd = 'export SGE_ROOT=%s;. $SGE_ROOT/default/common/settings.sh; %s/bin/lx24-amd64/qconf -ah %s' % (paths.P_SGE_ROOT, paths.P_SGE_ROOT, inst_ip)
        log.debug("Add SGE admin host cmd: '%s'" % cmd)
        proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.wait() == 0:
            log.debug("Successfully added instance '%s' w/ private IP '%s' as administrative host." % (inst.id, inst_ip))
        else:
            error = True
            log.error("Process encountered problems adding instance '%s' as administrative host. Process returned code %s" % (inst.id, proc.returncode))
            stdout, stderr = proc.communicate()
            log.debug("Adding instance '%s' SGE administrative host stdout (private IP: '%s'): '%s'" % (inst.id, inst.private_ip, stdout))
            log.debug("Adding instance '%s' SGE administrative host stderr (private IP: '%s'): '%s'" % (inst.id, inst.private_ip, stderr))
        
        #== Add instance as SGE execution host
        # Check if host is already in the exec host list
        cmd = "export SGE_ROOT=%s; . $SGE_ROOT/default/common/settings.sh; %s/bin/lx24-amd64/qconf -sel" % (paths.P_SGE_ROOT, paths.P_SGE_ROOT)
        proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = proc.communicate()
        if inst_ip in stdout:
            log.debug("Instance '%s' already in SGE execution host list" % inst.id)
        else:
            log.info("Adding instance '%s' to SGE execution host list." % inst.id)
            # Create a dir to hold all of workers host configuration files
            host_conf_dir = "%s/host_confs" % paths.P_SGE_ROOT
            if not os.path.exists(host_conf_dir):
                subprocess.call('mkdir -p %s' % host_conf_dir, shell=True)
                os.chown(host_conf_dir, pwd.getpwnam( "sgeadmin" )[2], grp.getgrnam( "sgeadmin" )[2])
            host_conf_file = os.path.join(host_conf_dir, str(inst.id))
            with open(host_conf_file, 'w') as f:
                print >> f, templates.SGE_HOST_CONF_TEMPLATE % (inst_ip)
            os.chown(host_conf_file, pwd.getpwnam("sgeadmin")[2], grp.getgrnam("sgeadmin")[2])
            log.debug("Created SGE host configuration template as file '%s'." % host_conf_file)
            # Add worker instance as execution host to SGE
            cmd = 'export SGE_ROOT=%s; . $SGE_ROOT/default/common/settings.sh; %s/bin/lx24-amd64/qconf -Ae %s' \
                % (paths.P_SGE_ROOT, paths.P_SGE_ROOT, host_conf_file)
            log.debug("Add SGE exec host cmd: '%s'" % cmd)
            proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if proc.wait() == 0:
                log.debug("Successfully added instance '%s' w/ private IP '%s' as execution host." % (inst.id, inst_ip))
            else:
                error = True
                log.error("Process encountered problems adding instance '%s' as execution host. Process returned code %s" % (inst.id, proc.returncode))
                stderr = stdout = None
                stdout, stderr = proc.communicate()
                log.debug("Adding instance '%s' SGE execution host stdout (private IP: '%s'): '%s'" % (inst.id, inst.private_ip, stdout))
                log.debug("Adding instance '%s' SGE execution host stderr (private IP: '%s'): '%s'" % (inst.id, inst.private_ip, stderr))
        
        #== Add given instance's hostname to @allhosts
        # Check if instance is already in allhosts file and do not recreate the 
        # file if so.
        # Additional documentation: allhosts file can be generated by Cloudman
        # each time an instance is added or removed. The file is generetd based
        # on the Instance object Cloudman keeps track of and, as a resul, it
        # includes all of the instances listed. So, some instances, although they
        # have yet to go through the addition process, might have had their IPs
        # already included in the allhosts file. This approach ensures consistency
        # between SGE and Cloudman and has been working much better than trying
        # to sync the two via other methods.
        proc = subprocess.Popen("export SGE_ROOT=%s; . $SGE_ROOT/default/common/settings.sh; %s/bin/lx24-amd64/qconf -shgrp @allhosts" \
            % (paths.P_SGE_ROOT, paths.P_SGE_ROOT), shell=True, stdout=subprocess.PIPE)
        allhosts_out = proc.communicate()[0]
        if inst_ip not in allhosts_out:
            now = datetime.datetime.utcnow()
            ah_file = '/tmp/ah_add_' + now.strftime("%H_%M_%S")
            self.write_allhosts_file( filename=ah_file, to_add = inst_ip)
            if not misc.run('export SGE_ROOT=%s;. $SGE_ROOT/default/common/settings.sh; %s/bin/lx24-amd64/qconf -Mhgrp %s' \
                % (paths.P_SGE_ROOT, paths.P_SGE_ROOT, ah_file), \
                "Problems updating @allhosts aimed at adding '%s'" % inst.id, \
                "Successfully updated @allhosts to add '%s' with IP '%s'" % (inst.id, inst_ip)):
                error = True
        else:
            log.info("Instance '%s' IP is already in SGE's @allhosts" % inst.id)
        
        # On instance reboot, SGE might have already been configured for a given
        # instance and this method will fail along the way although the instance
        # will still operate within SGE so don't explicitly state it was added.
        if error is False:
            log.info("Successfully added instance '%s' to SGE" % inst.id)
        
        return True
    
    def stop_sge(self):
        log.info( "Stopping SGE." )
        for inst in self.app.manager.worker_instances:
            self.remove_sge_host( inst )
        misc.run('export SGE_ROOT=%s; . $SGE_ROOT/default/common/settings.sh; %s/bin/lx24-amd64/qconf -km' % (paths.P_SGE_ROOT, paths.P_SGE_ROOT), "Problems stopping SGE master", "Successfully stopped SGE master." )
    
    def write_allhosts_file(self, filename = '/tmp/ah', to_add = None, to_remove = None):
        ahl = []
        log.debug( "to_add: '%s'" % to_add )
        log.debug( "to_remove: '%s'" % to_remove )
        # Add master instance to the execution host list
        log.debug("Composing SGE's @allhosts group config file '%s':" % filename)
        log.debug(" - adding master instance; IP '%s'" % self.app.cloud_interface.get_self_private_ip())
        ahl.append(self.app.cloud_interface.get_self_private_ip())
        # Add worker instances, excluding the one being removed
        for inst in self.app.manager.worker_instances:
            if inst.get_private_ip() != to_remove:
                log.debug( " - adding instance with IP '%s' (instance state: '%s')" % (inst.get_private_ip(), inst.worker_status))
                ahl.append(inst.private_ip)
            else:
                log.debug( " - instance with IP '%s' marked for removal so not adding it (instance state: '%s')" % (inst.get_private_ip(), inst.worker_status))
            
        # For comparisson purposes, make sure all elements are lower case
        for i in range(len(ahl)):
            ahl[i] = ahl[i].lower()
        
        # Now reasemble and save to file 'filename'
        if len(ahl) > 0:
            new_allhosts = 'group_name @allhosts \n'+'hostlist ' + ' \\\n\t '.join(ahl) + ' \\\n'
        else:
            new_allhosts = 'group_name @allhosts \nhostlist NONE\n'
        f = open( filename, 'w' )
        f.write( new_allhosts )
        f.close()
        log.debug("new_allhosts:\n%s" % new_allhosts)
        log.debug("New SGE @allhosts file written successfully to %s." % filename)
    
    def remove_sge_host( self, inst ):
        log.info( "Removing instance '%s' from SGE" % inst.id )
        log.debug("Removing instance '%s' from SGE administrative host list" % inst.id )
        ret_code = subprocess.call( 'export SGE_ROOT=%s; . $SGE_ROOT/default/common/settings.sh; %s/bin/lx24-amd64/qconf -dh %s' % (paths.P_SGE_ROOT, paths.P_SGE_ROOT, inst.private_ip), shell=True )
        
        inst_ip = inst.get_private_ip()
        log.debug( "Removing instance '%s' with FQDN '%s' from SGE execution host list (including @allhosts)" % ( inst.id, inst_ip) )
        now = datetime.datetime.utcnow()
        ah_file = '/tmp/ah_remove_' + now.strftime("%H_%M_%S")
        self.write_allhosts_file(filename=ah_file, to_remove=inst_ip)
        
        ret_code = subprocess.call( 'export SGE_ROOT=%s; . $SGE_ROOT/default/common/settings.sh; %s/bin/lx24-amd64/qconf -Mhgrp %s' % (paths.P_SGE_ROOT, paths.P_SGE_ROOT, ah_file), shell=True )
        if ret_code == 0:
            log.info( "Successfully updated @allhosts to remove '%s'" % inst.id )
        else:
            log.debug( "Problems updating @allhosts aimed at removing '%s'; process returned code '%s'" % ( inst.id, ret_code ) )  
        
        proc = subprocess.Popen( 'export SGE_ROOT=%s; . $SGE_ROOT/default/common/settings.sh; %s/bin/lx24-amd64/qconf -de %s' % (paths.P_SGE_ROOT,paths.P_SGE_ROOT, inst.private_ip), shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE )
        stderr = None
        std = proc.communicate()
        if std[1]:
            stderr = std[1]
        # TODO: Should be looking at return code and use stdout/err just for info about the process progress...
        if stderr is None or 'removed' in stderr:
            ret_code = subprocess.call( 'export SGE_ROOT=%s; . $SGE_ROOT/default/common/settings.sh; /opt/sge/bin/lx24-amd64/qconf -dconf %s' % (paths.P_SGE_ROOT, inst.private_ip), shell=True )
            log.debug( "Successfully removed instance '%s' with IP '%s' from SGE execution host list." % ( inst.id, inst_ip ) )
            return True
        elif 'does not exist' in stderr:
            log.debug( "Instance '%s' with IP '%s' not found in SGE's exechost list: %s" % ( inst.id, inst_ip, stderr ) )
            return True
        else:
            log.debug( "Failed to remove instance '%s' with FQDN '%s' from SGE execution host list: %s" % ( inst.id, inst_ip, stderr ) )
            return False
    
    def check_sge(self):
        """Check if SGE qmaster is running and a sample job can be successfully run.
        :rtype: bool
        :return: True if the daemon is running and a sample job can be run,
                 False otherwise.
        """
        qstat_out = commands.getoutput('%s - galaxy -c "export SGE_ROOT=%s;\
            . %s/default/common/settings.sh; \
            %s/bin/lx24-amd64/qstat -f | grep all.q"' 
            % (paths.P_SU, paths.P_SGE_ROOT, paths.P_SGE_ROOT, paths.P_SGE_ROOT))
        qstat_out = qstat_out.split('\n')
        cleaned_qstat_out = []
        for line in qstat_out:
            if line.startswith('all.q'):
                cleaned_qstat_out.append(line)
        log.debug("qstat: %s" % cleaned_qstat_out)
        if len(cleaned_qstat_out) > 0: #i.e., at least 1 exec host exists
            # At least 1 exec host exists, assume it will accept jobs
            return True
        elif self.app.manager.get_num_available_workers() == 0:
            # Daemon running but no ready worker instances yet so assume all OK
            return True
        else:
            log.warning("\tNo machines available to test SGE (qstat: %s)." % cleaned_qstat_out)
            return False
    
    def status(self):
        if self.state==service_states.SHUTTING_DOWN or \
           self.state==service_states.SHUT_DOWN or \
           self.state==service_states.UNSTARTED or \
           self.state==service_states.WAITING_FOR_USER_ACTION:
            pass
        elif self._check_daemon('sge'):
            if self.check_sge():
                self.state = service_states.RUNNING
        elif self.state!=service_states.STARTING:
            log.error("SGE error; SGE not runnnig")
            self.state = service_states.ERROR
    
