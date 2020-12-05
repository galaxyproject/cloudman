"""A wrapper around the kubectl commandline client"""
import shutil

import tenacity

from . import helpers


class KubeService(object):
    """Marker interface for CloudMan services"""
    def __init__(self, client):
        self._client = client

    def client(self):
        return self._client


class KubeClient(KubeService):

    def __init__(self):
        self._check_environment()
        super(KubeClient, self).__init__(self)
        self._namespace_svc = KubeNamespaceService(self)
        self._node_svc = KubeNodeService(self)
        self._secret_svc = KubeSecretService(self)

    @staticmethod
    def _check_environment():
        if not shutil.which("kubectl"):
            raise Exception("Could not find kubectl executable in path")

    @property
    def namespaces(self):
        return self._namespace_svc

    @property
    def nodes(self):
        return self._node_svc

    @property
    def secrets(self):
        return self._secret_svc


class KubeNamespaceService(KubeService):

    def __init__(self, client):
        super(KubeNamespaceService, self).__init__(client)

    def list(self):
        data = helpers.run_list_command(["kubectl", "get", "namespaces"],
                                        delimiter=" ", skipinitialspace=True)
        return data

    # def _list_names(self):
    #     data = self.list()
    #     output = [each.get('NAME') for each in data]
    #     return output

    def create(self, namespace_name):
        return helpers.run_command(
            ["kubectl", "create", "namespace", namespace_name])

    # def _create_if_not_exists(self, namespace_name):
    #     if namespace_name not in self._list_names():
    #         return self.create(namespace_name)

    def delete(self, namespace_name):
        return helpers.run_command(
            ["kubectl", "delete", "namespace", namespace_name])


class KubeNodeService(KubeService):

    def __init__(self, client):
        super(KubeNodeService, self).__init__(client)

    def list(self):
        data = helpers.run_yaml_command(["kubectl", "get", "nodes", "-o", "yaml"])
        return data['items']

    def find(self, node_ip):
        nodes = self.list()
        return [node for node in nodes
                if node_ip in [addr.get('address') for addr in
                               node.get('status', {}).get('addresses', {})]]

    def cordon(self, node):
        name = node.get('metadata', {}).get('name')
        return helpers.run_command(["kubectl", "cordon", name])

    def _get_job_pods_in_node(self, node_name, state):
        """
        Return a list of all pods in a node in a particular state, such
        as Running. Only looks for pods that belong to a job
        (job-name selector).
        """
        return helpers.run_yaml_command(
            ["kubectl", "get", "pods", "--all-namespaces", "--field-selector",
             f"spec.nodeName={node_name},status.phase={state}",
             "--selector", "job-name", "-o", "yaml"])

    def wait_till_jobs_complete(self, node, timeout=3600*24*7):
        name = node.get('metadata', {}).get('name')
        retryer = tenacity.Retrying(
            stop=tenacity.stop_after_delay(timeout),
            retry=tenacity.retry_if_result(
                lambda result: len(result.get('items', [])) != 0),
            wait=tenacity.wait_fixed(5))
        retryer(self._get_job_pods_in_node, name, "Running")

    def drain(self, node, force=True, timeout=120, ignore_daemonsets=True):
        name = node.get('metadata', {}).get('name')
        return helpers.run_command(
            ["kubectl", "drain", name, f"--timeout={timeout}s",
             f"--force={'true' if force else 'false'}",
             f"--ignore-daemonsets={'true' if ignore_daemonsets else 'false'}"]
        )

    def delete(self, node):
        name = node.get('metadata', {}).get('name')
        return helpers.run_command(
            ["kubectl", "delete", "node", name]
        )


class KubeSecretService(KubeService):

    def __init__(self, client):
        super(KubeSecretService, self).__init__(client)

    def get(self, secret_name, namespace=None):
        command = ["kubectl", "get", "secrets", "-o", "yaml", secret_name]
        if namespace:
            command += ["-n", namespace]
        data = helpers.run_yaml_command(command)
        return data
