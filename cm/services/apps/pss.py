"""Post Start Script service implementation."""
import os
import threading
from cm.util import misc
from cm.services import service_states
from cm.services import ServiceRole, ServiceType
from cm.services.apps import ApplicationService

import logging
log = logging.getLogger('cloudman')


class PSSService(ApplicationService):
    """ post_start_script service - this service runs once at the end of the
        configuration of all services defined in CloudMan. It runs a predefined
        script.
        Defining a service for something simple like this may be an overkill
        but it's also the simplest way to ensure this runs only after all other
        servces have been configured and are running. Plus, it can eventually
        be extended to run arbitrary script when a condition is met."""

    def __init__(self, app, instance_role='master'):
        super(PSSService, self).__init__(app)
        self.svc_roles = [ServiceRole.PSS]
        self.name = ServiceRole.to_string(ServiceRole.PSS)
        self.svc_type = ServiceType.CM_SERVICE
        self.instance_role = instance_role
        log.debug("Configured PSS as {0}".format(self.instance_role))
        # Name of the default script to run
        self.pss_filename = 'post_start_script' if self.instance_role == 'master' \
            else 'worker_post_start_script'
        self.pss_url = (self.app.config.get('post_start_script_url', None)
                        if self.instance_role == 'master' else
                        self.app.config.get('worker_post_start_script_url', None))

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

        Attempt to download `post_start_script` from `post_start_script_url`
        (for master) or `worker_post_start_script_url` (for worker)
        as they are defined in user data. If these URL's are not defined in the
        user data, look if files `post_start_script` or
        `worker_post_start_script` for master and worker respectivley exist in
        the cluster bucket and download those. If obtained, run the script(s),
        else mark the service as COMPLETED and as 'not active'.
        """
        log.debug("Starting %s service" % self.name)
        self.state = service_states.RUNNING
        local_pss_file = os.path.join(self.app.config['cloudman_home'], self.pss_filename)
        # Check user data first to allow overwriting of potentially existing pss
        if self.pss_url:
            # This assumes the provided URL is readable to anyone w/o authentication
            # First check if the file actually exists
            if misc.run('wget --server-response %s' % self.pss_url):
                misc.run('wget --output-document=%s %s' % (
                    local_pss_file, self.pss_url))
            else:
                log.error("Specified post_start_script_url (%s) does not exist."
                          % self.pss_url)
        else:
            # Try to download the pss from the cluster's bucket
            cluster_bucket_name = self.app.config['bucket_cluster']
            log.debug("post_start_script_url not provided, will check if file "
                      "{0} exists in the cluster bucket ({1})."
                      .format(self.pss_filename, cluster_bucket_name))
            s3_conn = self.app.cloud_interface.get_s3_connection()
            misc.get_file_from_bucket(s3_conn, cluster_bucket_name,
                                      self.pss_filename, local_pss_file)
        # If we got a script, run it
        if os.path.exists(local_pss_file) and os.path.getsize(local_pss_file) > 0:
            log.info("%s found and saved to '%s'; running it now (note that this "
                     "may take a while)" % (self.pss_filename, os.path.join(
                                            self.app.config['cloudman_home'],
                                            self.pss_filename)))
            os.chmod(local_pss_file, 0755)  # Ensure the script is executable
            misc.run('cd %s;./%s' % (self.app.config[
                     'cloudman_home'], self.pss_filename))
            self.save_to_bucket()
            log.info("Done running PSS {0}".format(self.pss_filename))
        else:
            log.debug("No PSS provided or obtained; continuing.")
        # Prime the object with instance data
        self._prime_data()
        self.state = service_states.COMPLETED
        self.activated = False
        log.debug("%s service done and marked as '%s'" % (self.name, self.state))

    def save_to_bucket(self):
        """
        Save the current post start script file to the cluster's bucket.

        The script is saved only if the file does not already exist there
        and it not older than the local one.
        """
        s3_conn = self.app.cloud_interface.get_s3_connection()
        cluster_bucket_name = self.app.config['bucket_cluster']
        if not s3_conn or not misc.bucket_exists(s3_conn, cluster_bucket_name):
            log.debug("No s3_conn or cluster bucket {0} does not exist; not "
                      "saving the pss in the bucket".format(cluster_bucket_name))
            return
        pss_file = os.path.join(
            self.app.config['cloudman_home'], self.pss_filename)
        if misc.file_in_bucket_older_than_local(s3_conn,
                                                self.app.config['bucket_cluster'],
                                                self.pss_filename,
                                                pss_file):
            if os.path.exists(pss_file):
                log.debug("Saving current instance post start script (%s) to "
                          "cluster bucket '%s' as '%s'" %
                          (pss_file, self.app.config['bucket_cluster'],
                           self.pss_filename))
                misc.save_file_to_bucket(s3_conn,
                                         self.app.config['bucket_cluster'],
                                         self.pss_filename, pss_file)
            else:
                log.debug("No instance post start script (%s)" % pss_file)
        else:
            log.debug("A current post start script {0} already exists in bucket "
                      "{1}; not updating it".format(self.pss_filename,
                                                    self.app.config['bucket_cluster']))

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
