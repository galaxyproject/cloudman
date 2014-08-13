import commands
from datetime import datetime


class SlurmInfo(object):
    """
    A parser for Slurm commands
    """
    def __init__(self):
        self.nodes = []

    @property
    def jobs(self):
        """
            A list of jobs with info about each. Each list entry is a
            dict with the following keys: ``time_job_entered_state`` and
            ``job_state`` keys. Valid ``job_state`` values include: ``running``,
             ``pending``.
        """
        jobs = []
        # For now we're only filtering jobs in pending or running state
        cmd = "squeue -h -o'%T %S' --states=PENDING,RUNNING"
        squeue_out = commands.getoutput(cmd)
        if squeue_out:
            squeue_out = squeue_out.split('\n')
            for job in squeue_out:
                job_state = job.split()[0].lower()
                if job.split()[1] == 'N/A':
                    continue  # The job is still being scheduled
                time_job_entered_state = datetime.strptime(job.split()[1],
                                                           "%Y-%m-%dT%H:%M:%S")
                job_info = {'job_state': job_state, 'time_job_entered_state':
                            time_job_entered_state}
                jobs.append(job_info)
        return jobs
