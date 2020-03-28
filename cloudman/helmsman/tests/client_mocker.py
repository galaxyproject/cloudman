from unittest.mock import patch

from .mock_helm import MockHelm
from .mock_kubectl import MockKubeCtl


class HelmMocker(object):

    def __init__(self):
        self.mock_helm = MockHelm()

    def can_parse(self, command):
        if isinstance(command, list):
            prog = command[0]
            if prog.startswith("helm"):
                return True
        return False

    @staticmethod
    def extra_patches():
        return [patch(
            'helmsman.clients.helm_client.HelmClient._check_environment',
            return_value=True)]

    def run_command(self, command):
        return self.mock_helm.run_command(command)


class KubeMocker(object):

    def __init__(self):
        self.mock_kubectl = MockKubeCtl()

    def can_parse(self, command):
        if isinstance(command, list):
            prog = command[0]
            if prog.startswith("kubectl"):
                if 'namespace' in command or 'namespaces' in command:
                    return True
        return False

    @staticmethod
    def extra_patches():
        return [patch(
          'clusterman.clients.kube_client.KubeClient._check_environment',
          return_value=True)]

    def run_command(self, command):
        return self.mock_kubectl.run_command(command)


class ClientMocker(object):
    """
    Replaces helm and kube clients with their Mock versions
    """

    """ Mocks all calls to the helm and kubectl commands"""
    def __init__(self, testcase):
        self.mockers = [HelmMocker(), KubeMocker()]
        self.extra_patches = []
        for mocker in self.mockers:
            self.extra_patches += mocker.extra_patches()
        self.patch1 = patch('clusterman.clients.helpers.run_command',
                            self.mock_run_command)
        self.patch1.start()
        testcase.addCleanup(self.patch1.stop)
        for each in self.extra_patches:
            each.start()
            testcase.addCleanup(each.stop)

    def mock_run_command(self, command, shell=False):
        for mocker in self.mockers:
            if mocker.can_parse(command):
                return mocker.run_command(command)
