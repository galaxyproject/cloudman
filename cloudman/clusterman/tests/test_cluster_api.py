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
        patcher = patch('clusterman.cluster_templates.CMRancherTemplate.fetch_kube_config',
                             new_callable=PropertyMock,
                             return_value=load_kube_config)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client.force_login(
            User.objects.get_or_create(username='clusteradmin', is_staff=True)[0])

    def tearDown(self):
        self.client.logout()


class CMClusterServiceTests(CMClusterServiceTestBase):

    # TODO: Check that attempting to create an existing
    # object raises exception
    # TODO: Add test for updating objects

    def _create_cluster(self):
        url = reverse('clusterman:clusters-list')
        responses.add(responses.POST, 'https://127.0.0.1:4430/v3/clusters/c-abcd1?action=generateKubeconfig',
                      json={'config': load_kube_config()}, status=200)
        return self.client.post(url, self.CLUSTER_DATA, format='json')

    def _list_cluster(self):
        url = reverse('clusterman:clusters-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        cluster_data = dict(self.CLUSTER_DATA)
        cluster_data.pop('connection_settings')
        self.assertDictContainsSubset(cluster_data, response.data['results'][0])
        return response.data['results'][0]['id']

    def _check_cluster_exists(self, cluster_id):
        url = reverse('clusterman:clusters-detail', args=[cluster_id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        cluster_data = dict(self.CLUSTER_DATA)
        cluster_data.pop('connection_settings')
        self.assertDictContainsSubset(cluster_data, response.data)
        return response.data['id']

    def _delete_cluster(self, cluster_id):
        url = reverse('clusterman:clusters-detail', args=[cluster_id])
        return self.client.delete(url)

    def _check_no_clusters_exist(self):
        url = reverse('clusterman:clusters-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 0)

    @responses.activate
    def test_crud_cluster(self):
        """
        Ensure we can register a new cluster with cloudman.
        """
        # create the object
        response = self._create_cluster()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED,
                         response.content)

        # list the object
        cluster_id = self._list_cluster()
        # Assert that the originally created cluster id is the same as the one
        # returned by list
        self.assertEquals(response.data['id'], cluster_id)

        # check details
        cluster_id = self._check_cluster_exists(cluster_id)

        # delete the object
        response = self._delete_cluster(cluster_id)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT, response.data)

        # check it no longer exists
        self._check_no_clusters_exist()

    def test_create_unauthorized(self):
        self.client.force_login(
            User.objects.get_or_create(username='notaclusteradmin', is_staff=False)[0])
        response = self._create_cluster()
        self.assertEquals(response.status_code, 403, response.data)
        self._check_no_clusters_exist()

    def test_list_unauthorized(self):
        self.client.force_login(
            User.objects.get_or_create(username='notaclusteradmin', is_staff=False)[0])
        self._check_no_clusters_exist()

    def test_delete_unauthorized(self):
        self._create_cluster()
        cluster_id_then = self._list_cluster()
        self.client.force_login(
            User.objects.get_or_create(username='notaclusteradmin', is_staff=False)[0])
        response = self._delete_cluster(cluster_id_then)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)
        self.client.force_login(
            User.objects.get(username='clusteradmin'))
        cluster_id_now = self._list_cluster()
        assert cluster_id_now  # should still exist
        assert cluster_id_then == cluster_id_now  # should be the same cluster

    def test_cannot_view_other_clusters(self):
        self._create_cluster()
        self.client.force_login(
            User.objects.get_or_create(username='notaclusteradmin', is_staff=False)[0])
        self._check_no_clusters_exist()


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
        'instance_type': 'm1.medium'
    }

    fixtures = ['initial_test_data.json']

    def setUp(self):
        cloudlaunch_url = f'{self.live_server_url}/cloudman/cloudlaunch/api/v1'
        patcher1 = patch('clusterman.api.CMServiceContext.cloudlaunch_url',
                             new_callable=PropertyMock,
                             return_value=cloudlaunch_url)
        patcher1.start()
        self.addCleanup(patcher1.stop)

        def create_mock_provider(self, name, config):
            provider_class = self.get_provider_class("mock")
            return provider_class(config)

        patcher2 = patch('cloudbridge.factory.CloudProviderFactory.create_provider',
                         new=create_mock_provider)
        patcher2.start()
        self.addCleanup(patcher2.stop)

        patcher3 = patch('cloudlaunch.configurers.SSHBasedConfigurer._check_ssh')
        patcher3.start()
        self.addCleanup(patcher3.stop)

        patcher4 = patch('cloudlaunch.configurers.AnsibleAppConfigurer.configure')
        patcher4.start()
        self.addCleanup(patcher4.stop)

        super().setUp()

    def _create_cluster(self):
        url = reverse('clusterman:clusters-list')
        responses.add(responses.POST, 'https://127.0.0.1:4430/v3/clusters/c-abcd1?action=generateKubeconfig',
                      json={'config': load_kube_config()}, status=200)
        response = self.client.post(url, self.CLUSTER_DATA, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return response.data['id']

    def _create_cluster_node(self, cluster_id):
        responses.add(responses.POST, 'https://127.0.0.1:4430/v3/clusterregistrationtoken',
                      json={'nodeCommand': 'docker run rancher --worker'}, status=200)
        responses.add_passthru('http://localhost')
        url = reverse('clusterman:node-list', args=[cluster_id])
        return self.client.post(url, self.NODE_DATA, format='json')

    def _list_cluster_node(self, cluster_id):
        url = reverse('clusterman:node-list', args=[cluster_id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        cluster_data = dict(self.CLUSTER_DATA)
        cluster_data.pop('connection_settings')
        self.assertDictContainsSubset(cluster_data, response.data['results'][0]['cluster'])
        return response.data['results'][0]['id']

    def _check_cluster_node_exists(self, cluster_id, node_id):
        url = reverse('clusterman:node-detail', args=[cluster_id, node_id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        cluster_data = dict(self.CLUSTER_DATA)
        cluster_data.pop('connection_settings')
        self.assertDictContainsSubset(cluster_data, response.data['cluster'])
        return response.data['id']

    def _delete_cluster_node(self, cluster_id, node_id):
        url = reverse('clusterman:node-detail', args=[cluster_id, node_id])
        return self.client.delete(url)

    def _check_no_cluster_nodes_exist(self, cluster_id):
        url = reverse('clusterman:node-list', args=[cluster_id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 0)

    @responses.activate
    def test_crud_cluster_node(self):
        """
        Ensure we can register a new node with cloudman.
        """
        # create the parent cluster
        cluster_id = self._create_cluster()

        # create cluster node
        response = self._create_cluster_node(cluster_id)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)

        # list existing objects
        node_id = self._list_cluster_node(cluster_id)

        # check it exists
        node_id = self._check_cluster_node_exists(cluster_id, node_id)

        # delete the object
        response = self._delete_cluster_node(cluster_id, node_id)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # check it no longer exists
        self._check_no_cluster_nodes_exist(cluster_id)

    @responses.activate
    def test_node_create_unauthorized(self):
        cluster_id = self._create_cluster()
        self.client.force_login(
            User.objects.get_or_create(username='notaclusteradmin', is_staff=False)[0])
        response = self._create_cluster_node(cluster_id)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    @responses.activate
    def test_node_delete_unauthorized(self):
        cluster_id = self._create_cluster()
        self._create_cluster_node(cluster_id)
        node_id_then = self._list_cluster_node(cluster_id)
        self.client.force_login(
            User.objects.get_or_create(username='notaclusteradmin', is_staff=False)[0])
        response = self._delete_cluster_node(cluster_id, node_id_then)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)
        self.client.force_login(
            User.objects.get(username='clusteradmin'))
        node_id_now = self._list_cluster_node(cluster_id)
        assert node_id_now  # should still exist
        assert node_id_then == node_id_now  # should be the same node


class CMClusterAutoScalerTests(CMClusterServiceTestBase):

    AUTOSCALER_DATA = {
        'name': 'default',
        'instance_type': 'm1.medium',
        'zone_id': 1
    }

    fixtures = ['initial_test_data.json']

    def _create_cluster(self):
        url = reverse('clusterman:clusters-list')
        responses.add(responses.POST, 'https://127.0.0.1:4430/v3/clusters/c-abcd1?action=generateKubeconfig',
                      json={'config': load_kube_config()}, status=200)
        response = self.client.post(url, self.CLUSTER_DATA, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return response.data['id']

    def _create_autoscaler(self, cluster_id):
        url = reverse('clusterman:autoscaler-list', args=[cluster_id])
        return self.client.post(url, self.AUTOSCALER_DATA, format='json')

    def _list_autoscalers(self, cluster_id):
        url = reverse('clusterman:autoscaler-list', args=[cluster_id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        cluster_data = dict(self.CLUSTER_DATA)
        cluster_data.pop('connection_settings')
        self.assertDictContainsSubset(cluster_data, response.data['results'][0]['cluster'])
        return response.data['results'][0]['id']

    def _check_autoscaler_exists(self, cluster_id, node_id):
        url = reverse('clusterman:autoscaler-detail', args=[cluster_id, node_id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        cluster_data = dict(self.CLUSTER_DATA)
        cluster_data.pop('connection_settings')
        self.assertDictContainsSubset(cluster_data, response.data['cluster'])
        return response.data['id']

    def _delete_autoscaler(self, cluster_id, node_id):
        url = reverse('clusterman:autoscaler-detail', args=[cluster_id, node_id])
        return self.client.delete(url)

    def _check_no_autoscalers_exist(self, cluster_id):
        url = reverse('clusterman:autoscaler-list', args=[cluster_id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 0)

    @responses.activate
    def test_crud_autoscaler(self):
        """
        Ensure we can register a new node with cloudman.
        """
        # create the parent cluster
        cluster_id = self._create_cluster()

        # create cluster autoscaler
        response = self._create_autoscaler(cluster_id)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)

        # list existing objects
        autoscaler_id = self._list_autoscalers(cluster_id)

        # check it exists
        autoscaler_id = self._check_autoscaler_exists(cluster_id, autoscaler_id)

        # delete the object
        response = self._delete_autoscaler(cluster_id, autoscaler_id)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # check it no longer exists
        self._check_no_autoscalers_exist(cluster_id)

    @responses.activate
    def test_autoscaler_create_unauthorized(self):
        cluster_id = self._create_cluster()
        self.client.force_login(
            User.objects.get_or_create(username='notaclusteradmin', is_staff=False)[0])
        response = self._create_autoscaler(cluster_id)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    @responses.activate
    def test_autoscaler_delete_unauthorized(self):
        cluster_id = self._create_cluster()
        self._create_autoscaler(cluster_id)
        autoscaler_id_then = self._list_autoscalers(cluster_id)
        self.client.force_login(
            User.objects.get_or_create(username='notaclusteradmin', is_staff=False)[0])
        response = self._delete_autoscaler(cluster_id, autoscaler_id_then)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)
        self.client.force_login(
            User.objects.get(username='clusteradmin'))
        autoscaler_id_now = self._list_autoscalers(cluster_id)
        assert autoscaler_id_now  # should still exist
        assert autoscaler_id_then == autoscaler_id_now  # should be the same autoscaler
