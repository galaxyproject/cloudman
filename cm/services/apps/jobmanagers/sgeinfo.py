from xml.dom import minidom


class SGEInfo(object):
    """
    A parser for SGE commands
    """
    def __init__(self):
        self.nodes = []
        self.jobs = []

    def _parse_node(self, node):
        """
            Given an XML representation of a ``node`` from the output of ``qstat``,
            return a dict with parsed node info. The returned dict contains the
            following keys: ``node_name``, ``slots_total``, and ``slots_used``.
        """
        node_name = node.getElementsByTagName("name")[0].childNodes[0].data
        node_name = node_name.split('@')[1]  # Omit the queue name from the name
        slots_total = int(node.getElementsByTagName("slots_total")[0].childNodes[0].data)
        slots_used = int(node.getElementsByTagName("slots_used")[0].childNodes[0].data)
        node_info = {'node_name': node_name, 'slots_total': slots_total,
                     'slots_used': slots_used}
        return node_info

    def _parse_job(self, job):
        """
            Given an XML representation of a ``job`` from the output of ``qstat``,
            return a dict with parsed job info. The returned dict contains the
            following keys: ``job_state``, ``job_number``, ``job_slots``,
            ``job_submission_time``, and ``job_node_name``.
        """
        job_state = job.getAttribute("state")
        job_number = int(job.getElementsByTagName('JB_job_number')[0].childNodes[0].data)
        job_submission_time = job.getElementsByTagName('JAT_start_time')[0].childNodes[0].data
        job_slots = int(job.getElementsByTagName('slots')[0].childNodes[0].data)
        job_node_name = job.parentNode.getElementsByTagName('name')[0].childNodes[0].data
        job_info = {'job_state': job_state, 'job_number': job_number,
                    'job_submission_time': job_submission_time, 'job_slots': job_slots,
                    'job_node_name': job_node_name}
        return job_info

    def parse_qstat(self, qstat_out):
        """
            Parse the XML provided in the ``qstat_out`` argument and return a
            dictionary. The returned dictionary contains the following keys:
            ``nodes``, ``jobs`` with the value being a list of parsed values.
        """
        # Reset old values
        self.nodes = []
        self.jobs = []
        doc = minidom.parseString(qstat_out)
        for node in doc.getElementsByTagName("Queue-List"):
            self.nodes.append(self._parse_node(node))
            for job in node.getElementsByTagName("job_list"):
                self.jobs.append(self._parse_job(job))
        for job in doc.getElementsByTagName("job_list"):
            if job.parentNode.nodeName == 'job_info':  # Queued jobs
                self.jobs.append(self._parse_job(job))
        return {'nodes': self.nodes, 'jobs': self.jobs}
