import commands
import datetime
import grp
import logging
import os
import pwd
import shutil
import subprocess
import tarfile
import time
import urllib2
from string import Template

from cm.conftemplates import sge
from cm.services import ServiceDependency, ServiceRole, service_states
from cm.services.apps import ApplicationService
from cm.util import misc, paths
from cm.util.decorators import TestFlag

log = logging.getLogger('cloudman')


def fix_libc():
    """Check if /lib64/libc.so.6 exists - it's required by SGE but
    the location changes as minor versions increase with new Ubuntu releases.
    """
    if not os.path.exists('/lib64/libc.so.6'):
        fixed = False
        # Handles Ubuntu 11.04-13.04 and future proofed for new minor releases
        for libbase in ["/lib", "/lib64"]:
            for minor_version in range(13, 50):
                libname = '%s/x86_64-linux-gnu/libc-2.%s.so' % (libbase, minor_version)
                if not fixed and os.path.exists(libname):
                    os.symlink(libname, '/lib64/libc.so.6')
                    fixed = True
        if not fixed:
            log.error("SGE config is likely to fail because '/lib64/libc.so.6' does not exist.")


class SGEService(ApplicationService):
    def __init__(self, app):
        super(SGEService, self).__init__(app)
        self.svc_roles = [ServiceRole.SGE]
        self.name = ServiceRole.to_string(ServiceRole.SGE)
        self.dependencies = [ServiceDependency(self, ServiceRole.MIGRATION)]
        self.hosts = []

    def start(self):
        self.state = service_states.STARTING
        if self.unpack_sge():
            self.configure_sge()
            # self.app.manager.services.append(HadoopService(self.app))
        else:
            log.error("Error adding service '%s'" % self.name)
            self.state = service_states.ERROR

    def remove(self, synchronous=False):
        # TODO write something to clean up SGE in the case of restarts?
        log.info("Removing SGE service")
        super(SGEService, self).remove(synchronous)
        self.state = service_states.SHUTTING_DOWN
        for inst in self.app.manager.worker_instances:
            if not inst.is_spot() or inst.spot_was_filled():
                self.remove_sge_host(inst.get_id(), inst.get_private_ip())

        misc.run(
            'export SGE_ROOT=%s; . $SGE_ROOT/default/common/settings.sh; %s/bin/lx24-amd64/qconf -km' % (
                self.app.path_resolver.sge_root, self.app.path_resolver.sge_root),
            "Problems stopping SGE master", "Successfully stopped SGE master")
        self.state = service_states.SHUT_DOWN

    def clean(self):
        """
        Stop SGE and clean up the system as if SGE was never installed.
        Useful for CloudMan restarts.
        """
        self.remove()
        if self.state == service_states.SHUT_DOWN:
            misc.run('rm -rf %s/*' % self.app.path_resolver.sge_root, "Error cleaning SGE_ROOT (%s)" %
                     self.app.path_resolver.sge_root, "Successfully cleaned SGE_ROOT")
            with open(paths.LOGIN_SHELL_SCRIPT, 'r') as f:
                lines = f.readlines()
            d1 = d2 = -1
            for i, l in enumerate(lines):
                if "export SGE_ROOT=%s" % self.app.path_resolver.sge_root in l:
                    d1 = i
                if ". $SGE_ROOT/default/common/settings.sh" in l:
                    d2 = i
            if d1 != -1:
                del lines[d1]
            if d2 != -1:
                del lines[d2]
            if d1 != -1 or d2 != -1:
                with open(paths.LOGIN_SHELL_SCRIPT, 'w') as f:
                    f.writelines(lines)

    def _download_sge(self):
        """
        Download a Grid Engine binaries tar ball. Return the path to the downloaded
        file.
        """
        ge_url = 'http://dl.dropbox.com/u/47200624/respin/ge2011.11.tar.gz'
        downloaded_file = 'ge.tar.gz'
        try:
            r = urllib2.urlopen(ge_url, downloaded_file)
        except urllib2.HTTPError, e:
            log.error("Error downloading Grid Engine binaries from {0}: {1}"
                      .format(ge_url, e))
        if r.code == 200:
            return downloaded_file
        else:
            return ""

    @TestFlag(False)
    def unpack_sge(self):
        log.debug("Unpacking SGE from '%s'" % self.app.path_resolver.sge_tars)
        os.putenv('SGE_ROOT', self.app.path_resolver.sge_root)
        # Ensure needed directory exists
        if not os.path.exists(self.app.path_resolver.sge_tars):
            log.error("'%s' directory with SGE binaries does not exist! Aborting SGE setup." %
                      self.app.path_resolver.sge_tars)
            return False
        if not os.path.exists(self.app.path_resolver.sge_root):
            os.mkdir(self.app.path_resolver.sge_root)
        # Ensure SGE_ROOT directory is empty (useful for restarts)
        if len(os.listdir(self.app.path_resolver.sge_root)) > 0:
            log.debug("SGE_ROOT directory %s is not empty" % self.app.path_resolver.sge_root)
            # Check if qmaster is running in that case
            self.status()
            if self.state == service_states.RUNNING:
                log.info("Found SGE already running; will reconfigure it.")
                self.stop_sge()
            log.debug("Cleaning '%s' directory." % self.app.path_resolver.sge_root)
            for base, dirs, files in os.walk(self.app.path_resolver.sge_root):
                for f in files:
                    os.unlink(os.path.join(base, f))
                for d in dirs:
                    shutil.rmtree(os.path.join(base, d))
        log.debug("Unpacking SGE to '%s'." % self.app.path_resolver.sge_root)
        tar = tarfile.open('%s/ge-6.2u5-common.tar.gz' % self.app.path_resolver.sge_tars)
        tar.extractall(path=self.app.path_resolver.sge_root)
        tar.close()
        tar = tarfile.open('%s/ge-6.2u5-bin-lx24-amd64.tar.gz' %
                           self.app.path_resolver.sge_tars)
        tar.extractall(self.app.path_resolver.sge_root)
        tar.close()
        subprocess.call('%s -R sgeadmin:sgeadmin %s' % (
            paths.P_CHOWN, self.app.path_resolver.sge_root), shell=True)
        return True

    def _get_sge_install_conf(self):
        # Add master as an execution host
        # Additional execution hosts will be added later, as they start
        exec_nodes = self.app.cloud_interface.get_private_ip()
        sge_install_template = Template(sge.SGE_INSTALL_TEMPLATE)
        sge_params = {
            "cluster_name": "GalaxyEC2",
            "admin_host_list": self.app.cloud_interface.get_private_ip(),
            "submit_host_list": self.app.cloud_interface.get_private_ip(),
            "exec_host_list": exec_nodes,
            "hostname_resolving": "true",
        }
        for key, value in self.app.ud.iteritems():
            if key.startswith("sge_"):
                key = key[len("sge_"):]
                sge_params[key] = value

        return sge_install_template.substitute(sge_params)

    @TestFlag(None)
    def configure_sge(self):
        log.info("Setting up SGE...")
        SGE_config_file = '%s/galaxyEC2.conf' % self.app.path_resolver.sge_root
        with open(SGE_config_file, 'w') as f:
            print >> f, self._get_sge_install_conf()
        os.chown(SGE_config_file, pwd.getpwnam("sgeadmin")[2],
                 grp.getgrnam("sgeadmin")[2])
        log.debug(
            "Created SGE install template as file '%s'" % SGE_config_file)
        fix_libc()
        log.debug("Setting up SGE.")
        self._fix_util_arch()
        if misc.run('cd %s; ./inst_sge -m -x -auto %s' % (self.app.path_resolver.sge_root, SGE_config_file), "Setting up SGE did not go smoothly", "Successfully set up SGE"):
            log.debug("Successfully setup SGE; configuring SGE")
            log.debug("Adding parallel environments")
            pes = ['SMP_PE', 'MPI_PE']
            for pe in pes:
                pe_file_path = os.path.join('/tmp', pe)
                with open(pe_file_path, 'w') as f:
                    print >> f, getattr(sge, pe)
                misc.run('cd %s; ./bin/lx24-amd64/qconf -Ap %s' % (
                    self.app.path_resolver.sge_root, pe_file_path))
            log.debug("Creating queue 'all.q'")

            SGE_allq_file = '%s/all.q.conf' % self.app.path_resolver.sge_root
            all_q_template = Template(sge.ALL_Q_TEMPLATE)
            if self.app.config.hadoop_enabled:
                all_q_params = {
                    "slots": int(commands.getoutput("nproc")),
                    "prolog_path": os.path.join(paths.P_HADOOP_HOME, paths.P_HADOOP_INTEGRATION_FOLDER + "/hdfsstart.sh"),
                    "epilog_path": os.path.join(paths.P_HADOOP_HOME, paths.P_HADOOP_INTEGRATION_FOLDER + "/hdfsstop.sh")
                }
            else:
                all_q_params = {
                    "slots": int(commands.getoutput("nproc")),
                    "prolog_path": 'NONE',
                    "epilog_path": 'NONE'
                }

            with open(SGE_allq_file, 'w') as f:
                print >> f, all_q_template.substitute(
                    all_q_params)
            os.chown(SGE_allq_file, pwd.getpwnam("sgeadmin")[
                     2], grp.getgrnam("sgeadmin")[2])
            log.debug(
                "Created SGE all.q template as file '%s'" % SGE_allq_file)
            misc.run(
                'cd %s; ./bin/lx24-amd64/qconf -Mq %s' % (
                    self.app.path_resolver.sge_root, SGE_allq_file),
                "Error modifying all.q", "Successfully modified all.q")
            log.debug("Configuring users' SGE profiles")
            misc.append_to_file(paths.LOGIN_SHELL_SCRIPT,
                                "\nexport SGE_ROOT=%s" % self.app.path_resolver.sge_root)
            misc.append_to_file(paths.LOGIN_SHELL_SCRIPT,
                                "\n. $SGE_ROOT/default/common/settings.sh\n")
            # Write out the .sge_request file for individual users
            sge_request_template = Template(sge.SGE_REQUEST_TEMPLATE)
            sge_request_params = {
                'psql_home': self.app.path_resolver.pg_home,
                'galaxy_tools_dir': self.app.path_resolver.galaxy_tools,
            }
            users = ['galaxy', 'ubuntu']
            for user in users:
                sge_request_file = os.path.join('/home', user, '.sge_request')
                with open(sge_request_file, 'w') as f:
                    print >> f, sge_request_template.substitute(sge_request_params)
                os.chown(sge_request_file, pwd.getpwnam(user)[2], grp.getgrnam(user)[2])
            return True
        return False

    def _fix_util_arch(self):
        """
        Edit ``$SGE_ROOT/util/`` to prevent ``Unexpected operator`` error to
        show up at shell login (SGE bug on Ubuntu).
        """
        misc.replace_string(
            self.app.path_resolver.sge_root +
            '/util/arch', "         libc_version=`echo $libc_string | tr ' ,' '\\n' | grep \"2\.\" | cut -f 2 -d \".\"`",
            "         libc_version=`echo $libc_string | tr ' ,' '\\n' | grep \"2\.\" | cut -f 2 -d \".\" | sort -u`")
        # Support 3.0, 3.2, 3.5 kernels in Ubuntu 11.10 & 12.04 & 12.10
        # Future proof it a bit to work with new 3.x kernels as they
        # come online
        misc.replace_string(
            self.app.path_resolver.sge_root + '/util/arch', "   2.[46].*)",
            "   [23].[24567890]?.*)")
        misc.replace_string(
            self.app.path_resolver.sge_root + '/util/arch', "      2.6.*)",
            "      [23].[24567890]?.*)")
        misc.run("sed -i.bak 's/sort -u/sort -u | head -1/g' %s/util/arch" % self.app.path_resolver.sge_root, "Error modifying %s/util/arch" %
                 self.app.path_resolver.sge_root, "Modified %s/util/arch" % self.app.path_resolver.sge_root)
        misc.run("chmod +rx %s/util/arch" % self.app.path_resolver.sge_root, "Error chmod %s/util/arch" %
                 self.app.path_resolver.sge_root, "Successfully chmod %s/util/arch" % self.app.path_resolver.sge_root)
        # Ensure lines starting with 127.0.1. are not included in /etc/hosts
        # because SGE fails to install if that's the case. This line is added
        # to /etc/hosts by cloud-init
        # (http://www.cs.nott.ac.uk/~aas/Software%2520Installation%2520and%2520Development%2520Problems.html)
        misc.run("sed -i.bak '/^127.0.1./s/^/# (Commented by CloudMan) /' /etc/hosts")

    def add_sge_host(self, inst_id, inst_private_ip):
        """
        Add the instance ``inst_id`` into the SGE cluster. This implies adding
        the instance as an administrative host and an execution host. Returns
        ``True`` if the addition was successful; ``False`` otherwise.

        ``inst_id`` is used only in log statements while the the ``inst_private_ip``
        is the IP address (or hostname) of the given instance, which must be
        visible (i.e., accessible) to the other nodes in the clusters.
        """
        # TODO: Should check to ensure SGE_ROOT mounted on worker
        time.sleep(10)  # Wait in hope that SGE processed last host addition
        log.debug("Adding instance {0} w/ private IP/hostname {1} to SGE"
                  .format(inst_id, inst_private_ip))

        # == Add instance as SGE administrative host
        self._add_instance_as_admin_host(inst_id, inst_private_ip)

        # == Add instance as SGE execution host
        return self._add_instance_as_exec_host(inst_id, inst_private_ip)

    def _add_instance_as_admin_host(self, inst_id, inst_private_ip):
        """
        Add instance with ``inst_id`` and ``inst_private_ip`` to the SGE
        administrative host list.

        ``inst_id`` is used only in log statements while the the ``inst_private_ip``
        is the IP address (or hostname) of the given instance, which must be
        visible (i.e., accessible) to the other nodes in the clusters.
        """
        log.debug(
            "Adding instance {0} as SGE administrative host.".format(inst_id))
        stderr = stdout = None
        error = False
        cmd = 'export SGE_ROOT=%s;. $SGE_ROOT/default/common/settings.sh; %s/bin/lx24-amd64/qconf -ah %s' \
            % (self.app.path_resolver.sge_root, self.app.path_resolver.sge_root, inst_private_ip)
        log.debug("Add SGE admin host cmd: {0}".format(cmd))
        proc = subprocess.Popen(
            cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.wait() == 0:
            log.debug("Successfully added instance {0} w/ private IP {1} as administrative host."
                      .format(inst_id, inst_private_ip))
        else:
            error = True
            log.error("Process encountered problems adding instance {0} as administrative host. "
                      "Process returned code {1}".format(inst_id, proc.returncode))
            stdout, stderr = proc.communicate()
            log.debug("Adding instance {0} SGE administrative host stdout (private IP: {1}): {2}"
                      .format(inst_id, inst_private_ip, stdout))
            log.debug("Adding instance {0} SGE administrative host stderr (private IP: {1}): {2}"
                      .format(inst_id, inst_private_ip, stderr))
        return error

    def _add_instance_as_exec_host(self, inst_id, inst_private_ip):
        """
        Add instance with ``inst_id`` and ``inst_private_ip`` to the SGE
        execution host list.

        ``inst_id`` is used only in log statements while the the ``inst_private_ip``
        is the IP address (or hostname) of the given instance, which must be
        visible (i.e., accessible) to the other nodes in the clusters.
        """
        error = False
        # Check if host is already in the exec host list
        cmd = "export SGE_ROOT=%s; . $SGE_ROOT/default/common/settings.sh; %s/bin/lx24-amd64/qconf -sel" \
            % (self.app.path_resolver.sge_root, self.app.path_resolver.sge_root)
        proc = subprocess.Popen(
            cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = proc.communicate()
        if inst_private_ip in stdout:
            log.debug(
                "Instance '%s' already in SGE execution host list" % inst_id)
        else:
            log.debug(
                "Adding instance '%s' to SGE execution host list." % inst_id)
            # Create a dir to hold all of workers host configuration files
            host_conf_dir = "%s/host_confs" % self.app.path_resolver.sge_root
            if not os.path.exists(host_conf_dir):
                subprocess.call('mkdir -p %s' % host_conf_dir, shell=True)
                os.chown(host_conf_dir, pwd.getpwnam(
                    "sgeadmin")[2], grp.getgrnam("sgeadmin")[2])
            host_conf_file = os.path.join(host_conf_dir, str(inst_id))
            with open(host_conf_file, 'w') as f:
                print >> f, sge.SGE_HOST_CONF_TEMPLATE % (
                    inst_private_ip)
            os.chown(host_conf_file, pwd.getpwnam("sgeadmin")[
                     2], grp.getgrnam("sgeadmin")[2])
            log.debug(
                "Created SGE host configuration template as file '%s'." % host_conf_file)
            # Add worker instance as execution host to SGE
            cmd = 'export SGE_ROOT=%s; . $SGE_ROOT/default/common/settings.sh; %s/bin/lx24-amd64/qconf -Ae %s' \
                % (self.app.path_resolver.sge_root, self.app.path_resolver.sge_root, host_conf_file)
            log.debug("Add SGE exec host cmd: {0}".format(cmd))
            proc = subprocess.Popen(cmd, shell=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if proc.wait() == 0:
                log.debug("Successfully added instance '%s' w/ private IP '%s' as an execution host."
                          % (inst_id, inst_private_ip))
            else:
                error = True
                log.error("Process encountered problems adding instance '%s' as an SGE execution host. "
                          "Process returned code %s" % (inst_id, proc.returncode))
                stderr = stdout = None
                stdout, stderr = proc.communicate()
                log.debug(" - adding instance '%s' SGE execution host stdout (private IP: %s): '%s'"
                          % (inst_id, inst_private_ip, stdout))
                log.debug(" - adding instance '%s' SGE execution host stderr (private IP: %s): '%s'"
                          % (inst_id, inst_private_ip, stderr))

        # == Add given instance's hostname to @allhosts
        # Check if instance is already in allhosts file and do not recreate the
        # file if so.
        # Additional documentation: allhosts file can be generated by CloudMan
        # each time an instance is added or removed. The file is generated based
        # on the Instance object CloudMan keeps track of and, as a result, it
        # includes all of the instances listed. So, some instances, although they
        # have yet to go through the addition process, might have had their IPs
        # already included in the allhosts file. This approach ensures consistency
        # between SGE and CloudMan and has been working much better than trying
        # to sync the two via other methods.
        proc = subprocess.Popen("export SGE_ROOT=%s; . $SGE_ROOT/default/common/settings.sh; "
                                "%s/bin/lx24-amd64/qconf -shgrp @allhosts"
                                % (self.app.path_resolver.sge_root, self.app.path_resolver.sge_root), shell=True, stdout=subprocess.PIPE)
        allhosts_out = proc.communicate()[0]
        if inst_private_ip not in allhosts_out:
            now = datetime.datetime.utcnow()
            ah_file = '/tmp/ah_add_' + now.strftime("%H_%M_%S")
            self.write_allhosts_file(
                filename=ah_file, to_add=inst_private_ip)
            if not misc.run('export SGE_ROOT=%s;. $SGE_ROOT/default/common/settings.sh; '
                            '%s/bin/lx24-amd64/qconf -Mhgrp %s'
                            % (self.app.path_resolver.sge_root, self.app.path_resolver.sge_root, ah_file),
                            "Problems updating @allhosts aimed at adding '%s'" % inst_id,
                            "Successfully updated @allhosts to add '%s' with address '%s'" % (inst_id, inst_private_ip)):
                error = True
        else:
            log.debug(
                "Instance '%s' IP is already in SGE's @allhosts" % inst_id)

        # On instance reboot, SGE might have already been configured for a given
        # instance and this method will fail along the way although the instance
        # will still operate within SGE so don't explicitly state it was added.
        if error is False:
            log.debug("Successfully added instance '%s' to SGE" % inst_id)

        return True

    def stop_sge(self):
        log.info("Stopping SGE.")
        for inst in self.app.manager.worker_instances:
            self.remove_sge_host(inst.get_id(), inst.get_private_ip())
        misc.run('export SGE_ROOT=%s; . $SGE_ROOT/default/common/settings.sh; %s/bin/lx24-amd64/qconf -km'
                 % (self.app.path_resolver.sge_root, self.app.path_resolver.sge_root),
                 "Problems stopping SGE master", "Successfully stopped SGE master.")

    def write_allhosts_file(self, filename='/tmp/ah', to_add=None, to_remove=None):
        ahl = []
        log.debug("to_add: '%s'" % to_add)
        log.debug("to_remove: '%s'" % to_remove)
        # Add master instance to the execution host list
        log.debug("Composing SGE's @allhosts group config file {0}:".format(
            filename))
        if self.app.manager.master_exec_host:
            log.debug(" - adding master instance; IP: {0}"
                      .format(self.app.cloud_interface.get_private_ip()))
            ahl.append(self.app.cloud_interface.get_private_ip())
        else:
            log.debug(
                " - master is marked as non-exec host and will not be included in @allhosts file")
        # Add worker instances, excluding the one being removed or pending
        for inst in self.app.manager.worker_instances:
            if not inst.is_spot() or inst.spot_was_filled():
                if inst.get_private_ip() != to_remove and \
                    inst.worker_status != 'Stopping' and \
                    inst.worker_status != 'Error' and \
                    inst.worker_status != 'Pending' and \
                        inst.get_private_ip() is not None:
                    log.debug(" - adding instance %s with IP %s (instance state: %s)"
                              % (inst.id, inst.get_private_ip(), inst.worker_status))
                    ahl.append(inst.get_private_ip())
                else:
                    log.debug(" - instance %s with IP %s is being removed or in state %s so "
                              "not adding it." % (inst.id, inst.get_private_ip(), inst.worker_status))

        # For comparison purposes, make sure all elements are lower case
        for i in range(len(ahl)):
            ahl[i] = ahl[i].lower()

        # Now reasemble and save to file 'filename'
        if len(ahl) > 0:
            new_allhosts = 'group_name @allhosts \n' + \
                'hostlist ' + ' \\\n\t '.join(ahl) + ' \\\n'
        else:
            new_allhosts = 'group_name @allhosts \nhostlist NONE\n'
        f = open(filename, 'w')
        f.write(new_allhosts)
        f.close()
        log.debug("new_allhosts:\n%s" % new_allhosts)
        log.debug(
            "New SGE @allhosts file written successfully to %s." % filename)

    def remove_sge_host(self, inst_id, inst_private_ip):
        """ Remove the instance from being tracked/controlled by SGE. This implies
            removing the instance form being an administrative host and a execution
            host.

            :type inst_id: string
            :param inst_id: ID of the instance. This value is used only in the print
                            statements.

            :type inst_private_ip: string
            :param inst_private_ip: IP address of the instance to remove from SGE.
                                    This needs to be the IP address visible to the
                                    other nodes in the cluster (ie, private IP).
        """
        log.debug("Removing instance {0} from SGE".format(inst_id))
        self._remove_instance_from_admin_list(inst_id, inst_private_ip)
        return self._remove_instance_from_exec_list(inst_id, inst_private_ip)

    def _remove_instance_from_admin_list(self, inst_id, inst_private_ip):
        """
        Remove instance ``inst_id`` from SGE's administrative host list.
        """
        log.debug("Removing instance {0} from SGE administrative host list".format(
            inst_id))
        return subprocess.call('export SGE_ROOT=%s; . $SGE_ROOT/default/common/settings.sh; '
                               '%s/bin/lx24-amd64/qconf -dh %s' % (
                                   self.app.path_resolver.sge_root, self.app.path_resolver.sge_root, inst_private_ip),
                               shell=True)

    def _remove_instance_from_exec_list(self, inst_id, inst_private_ip):
        """
        Remove instance ``inst_id`` with the provided private IP from SGE's
        execution host list. If the removal was detected as being successful,
        return ``True``, else return ``False``.
        """
        if not inst_private_ip:
            log.warning("Got empty private IP for instance {0}; cannot remove it "
                        "from SGE's execution host list!".format(inst_id))
            return False
        log.debug("Removing instance '%s' with FQDN '%s' from SGE execution host list (including @allhosts)"
                  % (inst_id, inst_private_ip))
        now = datetime.datetime.utcnow()
        ah_file = '/tmp/ah_remove_' + now.strftime("%H_%M_%S")
        self.write_allhosts_file(filename=ah_file, to_remove=inst_private_ip)

        ret_code = subprocess.call('export SGE_ROOT=%s; . $SGE_ROOT/default/common/settings.sh; '
                                   '%s/bin/lx24-amd64/qconf -Mhgrp %s' % (self.app.path_resolver.sge_root, self.app.path_resolver.sge_root, ah_file), shell=True)
        if ret_code == 0:
            log.debug(
                "Successfully updated @allhosts to remove '%s'" % inst_id)
        else:
            log.debug("Problems updating @allhosts aimed at removing '%s'; process returned code '%s'"
                      % (inst_id, ret_code))

        proc = subprocess.Popen('export SGE_ROOT=%s; . $SGE_ROOT/default/common/settings.sh; '
                                '%s/bin/lx24-amd64/qconf -de %s' % (
                                    self.app.path_resolver.sge_root, self.app.path_resolver.sge_root, inst_private_ip),
                                shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stderr = None
        std = proc.communicate()
        if std[1]:
            stderr = std[1]
        # TODO: Should be looking at return code and use stdout/err just for
        # info about the process progress
        if stderr is None or 'removed' in stderr:
            ret_code = subprocess.call('export SGE_ROOT=%s; . $SGE_ROOT/default/common/settings.sh; '
                                       '/opt/sge/bin/lx24-amd64/qconf -dconf %s' % (self.app.path_resolver.sge_root, inst_private_ip), shell=True)
            log.debug("Successfully removed instance '%s' with IP '%s' from SGE execution host list."
                      % (inst_id, inst_private_ip))
            return True
        elif 'does not exist' in stderr:
            log.debug("Instance '%s' with IP '%s' not found in SGE's exechost list: %s"
                      % (inst_id, inst_private_ip, stderr))
            return True
        else:
            log.debug("Failed to remove instance '%s' with FQDN '%s' from SGE execution host list: %s"
                      % (inst_id, inst_private_ip, stderr))
            return False

    def check_sge(self):
        """
        Check if SGE qmaster is running and qstat returns at least one node
        (assuming one should be available based on the current state of the
        cluster). If so, return ``True``, ``False`` otherwise.
        """
        qstat_out = commands.getoutput('%s - galaxy -c "export SGE_ROOT=%s;\
            . %s/default/common/settings.sh; \
            %s/bin/lx24-amd64/qstat -f | grep all.q"'
                                       % (paths.P_SU, self.app.path_resolver.sge_root, self.app.path_resolver.sge_root, self.app.path_resolver.sge_root))
        qstat_out = qstat_out.split('\n')
        cleaned_qstat_out = []
        for line in qstat_out:
            if line.startswith('all.q'):
                cleaned_qstat_out.append(line)
        log.debug("qstat: %s" % cleaned_qstat_out)
        if len(cleaned_qstat_out) > 0:  # i.e., at least 1 exec host exists
            # At least 1 exec host exists, assume it will accept jobs
            return True
        elif self.app.manager.get_num_available_workers() == 0:
            # Daemon running but no ready worker instances yet so assume all OK
            return True
        else:
            log.warning(
                "\tNo machines available to test SGE (qstat: %s)." % cleaned_qstat_out)
            return False

    def status(self):
        """
        Check and update the status of SGE service. If the service state is
        ``SHUTTING_DOWN``, ``SHUT_DOWN``, ``UNSTARTED``, or ``WAITING_FOR_USER_ACTION``,
        the method doesn't do anything. Otherwise, it updates service status (see
        ``check_sge``) by setting ``self.state``, whose value is always the method's
        return value.
        """
        if self.state == service_states.SHUTTING_DOWN or \
            self.state == service_states.SHUT_DOWN or \
            self.state == service_states.UNSTARTED or \
                self.state == service_states.WAITING_FOR_USER_ACTION:
            pass
        elif self._check_daemon('sge'):
            if self.check_sge():
                self.state = service_states.RUNNING
        elif self.state != service_states.STARTING:
            log.error("SGE error; SGE not runnnig")
            self.state = service_states.ERROR
        return self.state
