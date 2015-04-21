"""Post Start Script service implementation."""
import os
import threading
from cm.util import misc
from cm.services import service_states
from cm.services import ServiceRole, ServiceType
from cm.services.apps import ApplicationService
from urlparse import urlparse

import logging
log = logging.getLogger('cloudman')


class PSSService(ApplicationService):
    """ post_start_script service - this service runs once at the end of the
        configuration of all services defined in CloudMan. It runs user-defined
        scripts or script directories.
        Defining a service for something simple like this may be overkill
        but it's also the simplest way to ensure this runs only after all other
        services have been configured and are running. Plus, it can eventually
        be extended to run an arbitrary script when a condition is met."""

    def __init__(self, app, instance_role='master'):
        super(PSSService, self).__init__(app)
        self.svc_roles = [ServiceRole.PSS]
        self.name = ServiceRole.to_string(ServiceRole.PSS)
        self.svc_type = ServiceType.CM_SERVICE
        self.instance_role = instance_role
        log.debug("Configured PSS as {0}".format(self.instance_role))
        # Name of the default script to run

    def _prime_data(self):
        """
        Cache some of the instance-specific cloud variables.

        Some data is slow to obtain because a call to the cloud middleware
        is required. When such data is required to complete a user request,
        the request may be slow to complete. In an effort to alleviate some
        of those delays, prime the data into local variables (particularly
        the ones that do not change over a lifetime of a cluster).
        """
        log.debug("Priming local data variables...")
        self.app.cloud_interface.get_ami()
        self.app.cloud_interface.get_zone()
        self.app.cloud_interface.get_key_pair_name()
        self.app.cloud_interface.get_security_groups()
        self.app.cloud_interface.get_private_ip()
        self.app.cloud_interface.get_public_ip()
        self.app.cloud_interface.get_local_hostname()


    def add(self):
        """
        Check if prerequisites for running this service are satisfied and, if so,
        start the service.

        The prerequisites for this service are satisfied only after all other
        'active' CloudMan services are in state `RUNNING`. Return ``True`` if
        the service was started, else set its state to ``UNSTARTED`` and return
        ``False``.
        """
        if (self.state != service_states.COMPLETED and
           self.app.manager.initial_cluster_type is not None):
            self.state = service_states.STARTING
            prereqs_ok = True
            # There is a race condition w/ this service so when we're setting up
            # a 'Galaxy' clutser, make sure Galaxy service actually exists before
            # deciding all the services are running.
            # TODO: there's probably a better way to do this
            awaiting_galaxy = False
            if self.app.manager.initial_cluster_type == 'Galaxy':
                awaiting_galaxy = True
            # If there is a service other than self that is not running, return.
            # Otherwise, start this service.
            for srvc in self.app.manager.service_registry.itervalues():
                if srvc.activated and srvc != self and \
                   not (srvc.running() or srvc.completed()):
                    prereqs_ok = False
                    break
            if prereqs_ok and awaiting_galaxy:
                # Make sure Galaxy service exists before assuming all services
                # are there
                galaxy_svc = self.app.manager.get_services(svc_role=ServiceRole.GALAXY)
                if not galaxy_svc:
                    log.debug("No Galaxy service in a Galaxy cluster; waiting.")
                    prereqs_ok = False
                elif len(galaxy_svc) > 0 and not galaxy_svc[0].running():
                    log.debug("Galaxy service not running yet; waiting.")
                    prereqs_ok = False
                else:
                    log.debug("Galaxy service OK for PSS")
            if not prereqs_ok:
                log.debug("%s not running (%s), %s service prerequisites not "
                          "met afterall, not starting the service yet" %
                          (srvc.get_full_name(), srvc.state, self.name))
                # Reset state so it gets picked up by the monitor thread again
                self.state = service_states.UNSTARTED
                return False
            # Running the pss may take a while, so do it in its own thread.
            threading.Thread(target=self.start).start()
            return True
        else:
            log.debug("Not adding {0} svc; it completed ({1}) or the cluster was "
                      "not yet initialized ({2})"
                      .format(self.name, self.state == service_states.COMPLETED,
                              self.app.manager.initial_cluster_type))
            return False

    def start(self):
        """
        Start this service by running the 'Post Start Script'.

        Post start scripts are resolved in the following order:
        1. If a `post_start_script_url` (for master) or `worker_post_start_script_url`
        (for worker) is defined in user_data, it is processed first.
        These can be semi-colon separated lists, in which case they are executed one at a time,
        and can contain http paths, filenames or local file paths.
        E.g.:
        1. `http://domain.org/scripts/myscript.sh;/opt/app/start.d;bucket_script.sh;/opt/app/poststart.d;`
        2. 'file:///opt/app/mystartup.d;hello'

        For each url found, the following rules apply:
            a. If the url is an http url, the file is downloaded and executed
            b. If it's a filename only (no path), the cluster bucket will be first checked
            for the filename, and if it exists, downloaded and executed. Otherwise, the
            script will be assumed to be local and executed from the system path.
            c. If the path refers to a local directory, all scripts in that directory will
            be executed using the run-parts utility. (Refer to Ubuntu man pages for documentation
            on run-parts).
            d. If it's a local file, the script will be directly executed.

        2. If these URL's are not defined in the user data, falls back to legacy behaviour,
        by checking if files `post_start_script` or `worker_post_start_script`, for master
        and worker respectively, exist in the cluster bucket. If available, they are downloaded
        and executed.

        Finally, the service is marked as COMPLETED and as 'not active'.
        """
        log.debug("Starting %s service" % self.name)
        self.state = service_states.RUNNING
        default_pss_filename = 'post_start_script' if self.instance_role == 'master' \
            else 'worker_post_start_script'
        pss_urls = (self.app.config.get('post_start_script_url', None)
                   if self.instance_role == 'master' else
                   self.app.config.get('worker_post_start_script_url', None))
        default_local_pss_file = os.path.join(self.app.config['cloudman_home'], default_pss_filename)
        # Check user data first to allow overwriting of potentially existing pss
        if pss_urls:
            url_list = [url for url in pss_urls.split(';') if url]
            for pss_url in url_list:
                parse_result = urlparse(pss_url)
                if "http" in parse_result.scheme:
                    # This assumes the provided URL is readable to anyone w/o authentication
                    # First check if the file actually exists
                    if misc.run('wget --server-response %s' % pss_url):
                        misc.run('wget --output-document=%s %s' % (
                            default_local_pss_file, pss_url))
                        log.info("Downloaded script %s'; executing it... " % (pss_url))
                        self._execute_local_script(default_local_pss_file)
                    else:
                        log.error("Specified post_start_script_url (%s) does not exist. Continuing..."
                                  % pss_url)
                else:
                    # assume it's a file
                    local_pss = parse_result.path
                    # if file doesn't contain a path, check whether bucket contains that file.
                    # If the file exists in  bucket, it gets priority, otherwise, the local script is executed.
                    if not os.path.dirname(local_pss):
                        if self._fetch_script_from_bucket(local_pss, default_local_pss_file):
                            self._execute_local_script(default_local_pss_file)
                        else:
                            self._execute_local_script(local_pss)
                    else:
                        self._execute_local_script(local_pss)
        else:
            log.debug("post_start_script_url not provided, will check if default script "
                      "{0} exists in the cluster bucket.".format(default_pss_filename))
            if self._fetch_script_from_bucket(default_pss_filename, default_local_pss_file):
                self._execute_local_script(default_local_pss_file)
            else:
                log.debug("No PSS provided or obtained; continuing.")

        # Prime the object with instance data
        self._prime_data()
        # self.activated = False
        self.remove()
        self.state = service_states.COMPLETED
        log.debug("%s service done and marked as '%s'" % (self.name, self.state))

    def remove(self, synchronous=False):
        """Mark this service as 'not active' within CloudMan."""
        super(PSSService, self).remove(synchronous)
        if self.state == service_states.UNSTARTED:
            self.state = service_states.SHUT_DOWN
        log.debug("Removing service %s" % self.name)
        self.app.manager.deactivate_master_service(self)

    def status(self):
        """Do nothing: PSS runs once so there's no daemon to keep checking on."""
        pass

    def _execute_local_script(self, script):
        if os.path.isdir(script):
            log.info("Found local directory %s'; executing all scripts therein (note that this "
                     "may take a while)" % (script))
            misc.run('cd %s; run-parts %s' % (script, script))
            log.info("Done running PSS scripts in {0}".format(script))
        elif os.path.isfile(script) and os.path.getsize(script) > 0:
            log.info("Found local file %s'; running it now (note that this "
                     "may take a while)" % (script))
            os.chmod(script, 0755)  # Ensure the script is executable
            working_dir = os.path.dirname(script) or self.app.config['cloudman_home']
            misc.run('cd %s;./%s' % (working_dir, script))
            log.info("Done running PSS {0}".format(script))
        else:
            log.debug("Specified local PSS file or directory (%s) does not exist; continuing." % script)

    def _fetch_script_from_bucket(self, script_name, target_path):
        # Try to download the pss from the cluster's bucket
        cluster_bucket_name = self.app.config['bucket_cluster']
        log.debug("Attempting to fetch script {0} from cluster bucket ({1})."
                      .format(script_name, cluster_bucket_name))
        s3_conn = self.app.cloud_interface.get_s3_connection()
        return misc.get_file_from_bucket(s3_conn, cluster_bucket_name,
                                  script_name, target_path)