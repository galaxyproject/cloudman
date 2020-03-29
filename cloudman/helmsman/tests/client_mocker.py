from unittest.mock import patch

from clusterman.tests.client_mocker import ClientMocker as CMClientMocker
from clusterman.tests.client_mocker import KubeMocker
from .mock_helm import MockHelm


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


class ClientMocker(CMClientMocker):
    """
    Replaces helm and kube clients with their Mock versions
    """

    """ Mocks all calls to the helm and kubectl commands"""
    def __init__(self, testcase, mockers=None):
        super().__init__(testcase, mockers=mockers or [KubeMocker(), HelmMocker()])
