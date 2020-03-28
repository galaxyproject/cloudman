"""A wrapper around the kubectl commandline client"""
import shutil
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

    @staticmethod
    def _check_environment():
        if not shutil.which("kubectl"):
            raise Exception("Could not find kubectl executable in path")

    @property
    def namespaces(self):
        return self._namespace_svc


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
        return helpers.run_command(["kubectl", "create",
                                    "namespace", namespace_name])

    # def _create_if_not_exists(self, namespace_name):
    #     if namespace_name not in self._list_names():
    #         return self.create(namespace_name)

    def delete(self, namespace_name):
        return helpers.run_command(["kubectl", "delete",
                                    "namespace", namespace_name])
