import datetime
import logging
from cm.services import (Service, ServiceDependency, ServiceRole, ServiceType,
                         service_states)


log = logging.getLogger('cloudman')


class AutoscaleService(Service):
    def __init__(self, app, as_min=-1, as_max=-1, instance_type=None,
                 num_queued_jobs=2, mean_runtime_threshold=60,
                 num_instances_to_add=1):
        """
        :type as_min: int
        :param as_min: The minimum number of worker nodes of maintain.

        :type as_max: int
        :param as_max: The maximum number of worker nodes to maintain.

        :type instance_type: str
        :param instance_type: The type of instance to use.

        :type num_queued_jobs: int
        :param num_queued_jobs: Minimum number of jobs that need to be queued
                                before autoscaling will trigger.

        :type mean_runtime_threshold: int
        :param mean_runtime_threshold: Mean running job runtime before
                                       autoscaling will trigger.

        :type num_instances_to_add: int
        :param num_instances_to_add: Number of instances to add when scaling up.
        """
        super(AutoscaleService, self).__init__(app)
        self.state = service_states.UNSTARTED
        self.svc_roles = [ServiceRole.AUTOSCALE]
        self.svc_type = ServiceType.CM_SERVICE
        self.name = ServiceRole.to_string(ServiceRole.AUTOSCALE)
        self.dependencies = [ServiceDependency(self, ServiceRole.MIGRATION)]
        self.as_max = as_max
        self.as_min = as_min
        self.instance_type = instance_type

    @property
    def num_queued_jobs(self):
        return self._num_queued_jobs if self._num_queued_jobs else 2

    @num_queued_jobs.setter
    def num_queued_jobs(self, value):
        self._num_queued_jobs = value

    @property
    def mean_runtime_threshold(self):
        return self._mean_runtime_threshold if self._mean_runtime_threshold else 60

    @mean_runtime_threshold.setter
    def mean_runtime_threshold(self, value):
        self._mean_runtime_threshold = value

    @property
    def num_instances_to_add(self):
        return self._num_instances_to_add if self._num_instances_to_add else 1

    @num_instances_to_add.setter
    def num_instances_to_add(self, value):
        self._num_instances_to_add = value

    def __repr__(self):
        return "Autoscale"

    def get_full_name(self):
        return "AS"  # A shortcut name for log display

    def start(self):
        if self.state != service_states.RUNNING:
            if self.as_min > -1 and self.as_max > -1:
                if self.instance_type is None or self.instance_type == '':
                    self.instance_type = self.app.cloud_interface.get_type()
                log.debug("Turning autoscaling ON; using instances of type '%s'" %
                          self.instance_type)
                self.state = service_states.RUNNING
            else:
                log.debug("Cannot start autoscaling because limits are not set "
                          "(min: '%s' max: '%s')" % (self.as_min, self.as_max))

    def remove(self, synchronous=False):
        log.info("Removing '%s' service" % self.name)
        super(AutoscaleService, self).remove(synchronous)
        self.as_max = -1
        self.as_min = -1
        self.state = service_states.UNSTARTED

    def status(self):
        """
        Check the status/size of the cluster and initiate appropriate action
        if necessary.
        """
        if self.too_large():
            # Remove idle instances, leaving at least self.as_min
            num_instances_to_remove = self.get_num_instances_to_remove()
            log.debug(
                "Autoscaling DOWN: %s instance(s)" % num_instances_to_remove)
            self.app.manager.remove_instances(num_instances_to_remove)
        elif self.too_small():
            num_instances_to_add = self.get_num_instances_to_add()
            log.debug("Autoscaling UP: %s instance(s)" % num_instances_to_add)
            self.app.manager.add_instances(
                num_instances_to_add, instance_type=self.instance_type)

    def too_large(self):
        """
        Check if the current size of the cluster is too large.
        The following checks are included:
            - number of nodes is more than the max size of the cluster set
              by user
            - there are idle nodes and a new hour is about to begin (so not
              to get charged for the new hour)
        """
        # log.debug("Checking if cluster is too LARGE")
        if len(self.app.manager.worker_instances) > self.as_max:
            log.debug("Cluster is too explicitly large")
            return True
        elif int(datetime.datetime.utcnow().strftime("%M")) > 57 and \
            len(self.app.manager.worker_instances) > self.as_min and \
                self.get_num_instances_to_remove() > 0:
            # len(self.app.manager.get_idle_instances()) > 0 and \
            log.debug("Cluster is too large")
            return True
        return False

    def too_small(self):
        """
        Check if the current size of the cluster is too small.
        The following checks are included:
            - number of nodes is less than the min size of the cluster set by
              user
            - minute in the current hour is less than 55 (this is to ensure
              down-scaling and up-scaling don't conflict)
            - there are no idle resources, jobs are queued and job turnaround
              time is slow
            - there are no workers, jobs are queued and the master is set to
              not run jobs
        """
        log.debug("Checking if cluster too SMALL: minute:%s,idle:%s,total "
                  "workers:%s,avail workers:%s,min:%s,max:%s" %
                  (datetime.datetime.utcnow().strftime("%M"),
                   len(self.app.manager.get_idle_instances()),
                   len(self.app.manager.worker_instances),
                   self.app.manager.get_num_available_workers(), self.as_min,
                   self.as_max))

        if len(self.app.manager.worker_instances) < self.as_min:
            return True
        elif (int(datetime.datetime.utcnow().strftime("%M")) < 55 and
              len(self.app.manager.get_idle_instances()) == 0 and
              len(self.app.manager.worker_instances) < self.as_max and
              len(self.app.manager.worker_instances) ==
              self.app.manager.get_num_available_workers() and
              self.slow_job_turnover()):
            return True
        return False

    # *************** Helper methods ***************
    def slow_job_turnover(self):
        """
        Decide if the jobs currently in the queue are turning over slowly.

        This is a simple heuristic, best-effort implementation that looks at the
        mean time jobs are running and, if that time is greater than the
        threshold (``self.mean_runtime_threshold``) and there are more queued
        jobs then ``self.num_queued_jobs``, returns ``True``.
        """
        q_jobs = self.get_queue_jobs()
        # log.debug('q_jobs: %s' % q_jobs)
        r_jobs_mean, r_jobs_stdv = self.meanstdv(q_jobs['running'])
        qw_jobs_mean, qw_jobs_stdv = self.meanstdv(q_jobs['queued'])
        log.debug('Checking if slow job turnover: queued jobs: %s, avg runtime: %s'
                  % (len(q_jobs['queued']), r_jobs_mean))
        if ((len(q_jobs['queued']) > self.num_queued_jobs and
             r_jobs_mean > self.mean_runtime_threshold) or
            (len(q_jobs['queued']) > 0 and
             not self.app.manager.master_exec_host and
             len(self.app.manager.worker_instances) == 0)):
            return True
        return False

    def get_queue_jobs(self):
        """
        Query job manager queue and filter running and queued jobs. Then,
        calculate total time in the queue (running or queued) for each of the
        jobs. Return a dict with two keys 'running' and 'queued' where each
        key corresponds to a list of queued times (in seconds) for running
        and queued jobs, respectively. For example: {'running': [169147,
        149527], 'queued': [167525, 167512]}
        """
        running_jobs = []
        queued_jobs = []
        for job_manager_svc in self.app.manager.service_registry.active(
                service_role=ServiceRole.JOB_MANAGER):
            jobs = job_manager_svc.jobs()
            # log.debug("Autoscaling jobs: {0}".format(jobs))
            for job in jobs:
                now = datetime.datetime.now()
                if job.get('job_state') == 'running':
                    time_job_entered_state = job.get('time_job_entered_state',
                                                     datetime.datetime.now())
                    running_jobs.append(self.total_seconds(now - time_job_entered_state))
                elif job.get('job_state') == 'pending':
                    time_job_entered_state = job.get('time_job_entered_state',
                                                     datetime.datetime.now)
                    queued_jobs.append(self.total_seconds(now - time_job_entered_state))
        return {'running': running_jobs, 'queued': queued_jobs}

    def get_num_instances_to_remove(self):
        """Return the number of instance to remove during auto-DOWN-scaling.
           The function returns the number of idle instances while respecting
           the min number of instances that autoscaling should maintain."""
        num_instances_to_remove = len(self.app.manager.get_idle_instances())
        # If there are already more running instances than the current as_max,
        # leave the max number of instances running after scaling down
        if len(self.app.manager.worker_instances) > int(self.as_max):
            num_instances_to_remove = len(
                self.app.manager.worker_instances) - int(self.as_max)
        # Ensure the as_min number of instances are maintained
        if len(self.app.manager.worker_instances) - num_instances_to_remove < self.as_min:
            num_instances_to_remove = len(
                self.app.manager.worker_instances) - int(self.as_min)
        return num_instances_to_remove

    def get_num_instances_to_add(self):
        """Return the number of instance to add during auto-UP-scaling.
           The function returns 1 unless the number of instances autoscaling should
           maintain is less then the current number of instances. In that case, it
           returns the difference."""
        num_instances_to_add = self.num_instances_to_add
        if len(self.app.manager.worker_instances) + num_instances_to_add < self.as_min:
            num_instances_to_add = int(
                self.as_min) - len(self.app.manager.worker_instances)
        elif len(self.app.manager.worker_instances) + num_instances_to_add > self.as_max:
            num_instances_to_add = 0  # Already at as_max
        return num_instances_to_add

    def total_seconds(self, td):
        """Compute the total number of seconds in a timedelta object td"""
        return td.seconds + td.days * 24 * 3600

    def meanstdv(self, x):
        """Compute mean and standard deviation of a list x"""
        from math import sqrt
        n, std, mean = len(x), 0, 0
        if n > 0:
            mean = sum(x) / n
        if n > 1:
            for a in x:
                std += (a - mean) ** 2
            std = sqrt(std / float(n - 1))
        return mean, std

    def __str__(self):
        return ("Autoscaling limits min: %s max: %s; instance type: '%s'" %
                (self.as_min, self.as_max, self.instance_type))
