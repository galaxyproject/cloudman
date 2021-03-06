from unittest.mock import patch

from .mock_kubectl import MockKubeCtl


class KubeMocker(object):

    def __init__(self):
        self.mock_kubectl = MockKubeCtl()

    def can_parse(self, command):
        if isinstance(command, list):
            prog = command[0]
            if prog.startswith("kubectl"):
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
    def __init__(self, testcase, mockers=None):
        self.mockers = mockers or [KubeMocker()]
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
