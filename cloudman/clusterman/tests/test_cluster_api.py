import os
import yaml

from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase, APILiveServerTestCase
from unittest.mock import patch
from unittest.mock import PropertyMock

from django.test.testcases import LiveServerThread, QuietWSGIRequestHandler
from django.core.servers.basehttp import WSGIServer

import responses


def load_test_data(filename):
    cluster_data_path = os.path.join(
        os.path.dirname(__file__), 'data', filename)
    with open(cluster_data_path) as f:
        return yaml.safe_load(f)


def load_cluster_data():
    return load_test_data('initial_cluster_data.yaml')


def load_kube_config():
    data = load_test_data('kube_config.yaml')
    return yaml.dump(data)


# Create your tests here.
class CMClusterServiceTestBase(APITestCase):

    CLUSTER_DATA = {
        'name': 'testcluster2',
        'cluster_type': 'KUBE_RANCHER',
        'connection_settings': load_cluster_data()
    }

    def setUp(self):
        self.patcher = patch('clusterman.cluster_templates.CMRancherTemplate.fetch_kube_config',
                             new_callable=PropertyMock,
                             return_value=load_kube_config)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.client.force_login(
            User.objects.get_or_create(username='admin')[0])

    def tearDown(self):
        self.client.logout()


class CMClusterServiceTests(CMClusterServiceTestBase):

    # TODO: Check that attempting to create an existing
    # object raises exception
    # TODO: Add test for updating objects

    @responses.activate
    def test_crud_cluster(self):
        """
        Ensure we can register a new cluster with cloudman.
        """
        # create the object
        url = reverse('clusterman:clusters-list')
        responses.add(responses.POST, 'https://127.0.0.1:4430/v3/clusters/c-abcd1?action=generateKubeconfig',
                      json={'config': load_kube_config()}, status=200)
        response = self.client.post(url, self.CLUSTER_DATA, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED,
                         response.content)

        # check it exists
        url = reverse('clusterman:clusters-detail', args=[response.data['id']])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        cluster_data = dict(self.CLUSTER_DATA)
        cluster_data.pop('connection_settings')
        self.assertDictContainsSubset(cluster_data,
                                      response.data)

        # delete the object
        url = reverse('clusterman:clusters-detail', args=[response.data['id']])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # check it no longer exists
        url = reverse('clusterman:clusters-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


# Bug: https://stackoverflow.com/questions/48353002/sqlite-database-table-is-locked-on-tests
class LiveServerSingleThread(LiveServerThread):
    """Runs a single threaded server rather than multi threaded. Reverts https://github.com/django/django/pull/7832"""

    def _create_server(self):
        return WSGIServer((self.host, self.port), QuietWSGIRequestHandler, allow_reuse_address=False)


class LiveServerSingleThreadedTestCase(APILiveServerTestCase):
    "A thin sub-class which only sets the single-threaded server as a class"
    server_thread_class = LiveServerSingleThread


class CMClusterNodeServiceTests(CMClusterServiceTestBase, LiveServerSingleThreadedTestCase):

    NODE_DATA = {
        'name': 'testvm1',
        'instance_type': 'm1.medium'
    }

    fixtures = ['initial_test_data.json']

    def setUp(self):
        cloudlaunch_url = f'{self.live_server_url}/cloudman/cloudlaunch/api/v1'
        self.patcher = patch('clusterman.api.CMServiceContext.cloudlaunch_url',
                             new_callable=PropertyMock,
                             return_value=cloudlaunch_url)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        super().setUp()

    @responses.activate
    def test_crud_cluster_node(self):
        """
        Ensure we can register a new node with cloudman.
        """
        # create the object
        url = reverse('clusterman:clusters-list')
        responses.add(responses.POST, 'https://127.0.0.1:4430/v3/clusters/c-abcd1?action=generateKubeconfig',
                      json={'config': load_kube_config()}, status=200)
        response = self.client.post(url, self.CLUSTER_DATA, format='json')
        cluster_id = response.data['id']

        responses.add(responses.POST, 'https://127.0.0.1:4430/v3/clusterregistrationtoken',
                      json={'nodeCommand': 'docker run rancher --worker'}, status=200)
        responses.add_passthru('http://localhost')
        url = reverse('clusterman:node-list', args=[cluster_id])
        response = self.client.post(url, self.NODE_DATA, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)

        # check it exists
        url = reverse('clusterman:node-detail', args=[cluster_id, response.data['id']])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # self.assertDictContainsSubset({'vmType': 'm1.medium'},
        #                               (response.data.get('deployment')
        #                                .get('application_config')
        #                                .get('config_cloudlaunch')))

        # delete the object
        url = reverse('clusterman:node-detail', args=[cluster_id, response.data['id']])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # check it no longer exists
        url = reverse('clusterman:node-list', args=[cluster_id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
