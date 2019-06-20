from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase, APILiveServerTestCase
from unittest.mock import patch
from unittest.mock import PropertyMock

from django.test.testcases import LiveServerThread, QuietWSGIRequestHandler
from django.core.servers.basehttp import WSGIServer

import responses


class MockHelm(object):

    """ Mocks all calls to the helm command"""
    def __init__(self, testcase):
        self.patch1 = patch(
            'helmsman.helm.client.HelmClient._check_environment',
            return_value=True)
        self.patch2 = patch('helmsman.helm.helpers.run_command',
                            self.mock_run_command)
        self.patch1.start()
        self.patch2.start()
        testcase.addCleanup(self.patch2.stop)
        testcase.addCleanup(self.patch1.stop)

    def mock_run_command(self, command, shell=False):
        prog = None
        if isinstance(command, list):
            prog = " ".join(command)
        else:
            prog = command

        if prog.startswith("helm init"):
            # pretend to succeed
            pass
        elif prog.startswith("helm list"):
            return (
                "NAME             	REVISION	UPDATED                 	STATUS  	CHART            	APP VERSION	NAMESPACE\n"
                "turbulent-markhor	12      	Fri Apr 19 05:33:37 2019	DEPLOYED	cloudlaunch-0.2.0	2.0.2      	cloudlaunch\n"
                "precise-sparrow	1       	Wed Jun 19 18:02:26 2019	DEPLOYED	galaxy-3.0.0	v19.05     	gvl")
        elif prog.startswith("helm install"):
            # pretend to succeed
            pass
        elif prog.startswith("helm get values"):
            return "hello: world"
        elif prog.startswith("kubectl create"):
            # pretend to succeed
            pass
        else:
            raise Exception("Unrecognised command: {0}".format(prog))


# Create your tests here.
class HelmsManServiceTestBase(APITestCase):

    def setUp(self):
        self.mock_helm = MockHelm(self)
        self.client.force_login(
            User.objects.get_or_create(username='admin')[0])

    def tearDown(self):
        self.client.logout()


class RepoServiceTests(HelmsManServiceTestBase):

    def test_crud_repo(self):
        """
        Ensure we can register a new cluster with cloudman.
        """
        # Check listing
        url = reverse('repositories-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class ChartServiceTests(HelmsManServiceTestBase):

    CHART_DATA = {
        'id': 'precise-sparrow',
        'name': 'galaxy',
        'display_name': 'Galaxy',
        'chart_version': '3.0.0',
        'app_version': 'v19.05',
        'project': 'gvl',
        'access_address': "/galaxy/",
        'state': "DEPLOYED",
        'updated': "Wed Jun 19 18:02:26 2019",
        'values': {
            'hello': 'world'
        }
    }

    def test_crud_chart(self):
        """
        Ensure we can register a new cluster with cloudman.
        """
        # create the object
        url = reverse('charts-list')
        with self.assertRaises(NotImplementedError):
            self.client.post(url, self.CHART_DATA, format='json')

        # list existing objects
        url = reverse('charts-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # check it exists
        url = reverse('charts-detail', args=[response.data['results'][1]['id']])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertDictContainsSubset(self.CHART_DATA,
                                      response.data)
        # # delete the object
        # url = reverse('charts-detail', args=[response.data['id']])
        # response = self.client.delete(url)
        # self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        #
        # # check it no longer exists
        # url = reverse('clusters-list')
        # response = self.client.get(url)
        # self.assertEqual(response.status_code, status.HTTP_200_OK)
