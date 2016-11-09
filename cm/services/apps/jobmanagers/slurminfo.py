"""Module for supplying Slurm info."""
import commands
import datetime
import logging

log = logging.getLogger('cloudman')


class SlurmInfo(object):
    """A parser for Slurm commands."""

    def __init__(self):
        self.nodes = []

    @property
    def jobs(self):
        """
        Get list of jobs with info about each.

        Each list entry is a dict with the following keys:
        ``time_job_entered_state`` and ``job_state`` keys. Valid ``job_state``
        values include: ``running``,  ``pending``.
        """
        jobs = []
        # For now we're only filtering jobs in pending or running state
        cmd = "squeue -h -o'%T %S %R' --states=PENDING,RUNNING"
        squeue_out = commands.getoutput(cmd)
        if squeue_out:
            squeue_out = squeue_out.split('\n')
            for job in squeue_out:
                job_state = job.split()[0].lower()
                job_submit_time = job.split()[1]
                reason = job.split()[2].lower()
                req_node_not_avail = False
                # log.debug("Job state: %s, job_submit_time: %s, reason: %s" %
                #           (job_state, job_submit_time, reason))
                if reason in ['(reqnodenotavail)']:
                    req_node_not_avail = True
                    time_job_entered_state = \
                        datetime.datetime.now() - datetime.timedelta(minutes=5)
                elif job_submit_time == 'N/A':
                    continue  # The job is still being scheduled
                else:
                    time_job_entered_state = datetime.datetime.strptime(
                        job_submit_time, "%Y-%m-%dT%H:%M:%S")
                job_info = {'job_state': job_state, 'time_job_entered_state':
                            time_job_entered_state, 'req_node_not_avail':
                            req_node_not_avail}
                # log.debug("job_info: %s" % job_info)
                jobs.append(job_info)
        return jobs
