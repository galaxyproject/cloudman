import os
import yaml

from unittest.mock import patch
from unittest.mock import PropertyMock

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.servers.basehttp import WSGIServer
from django.test.testcases import LiveServerThread, QuietWSGIRequestHandler
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase, APILiveServerTestCase

from clusterman.clients.kube_client import KubeClient
from .client_mocker import ClientMocker


def load_test_data(filename):
    cluster_data_path = os.path.join(
        os.path.dirname(__file__), 'data', filename)
    with open(cluster_data_path) as f:
        return yaml.safe_load(f)


def load_cluster_data():
    return load_test_data('initial_cluster_data_aws.yaml')


def load_kube_config():
    data = load_test_data('kube_config.yaml')
    return yaml.dump(data)


# Create your tests here.
class CMClusterServiceTestBase(APITestCase):

    CLUSTER_DATA = {
        'name': 'testcluster2',
        'cluster_type': 'KUBE_RKE',
        'connection_settings': load_cluster_data()
    }

    def setUp(self):
        self.mock_client = ClientMocker(self)

        # Patch some background celery tasks to reduce noise in the logs.
        # They don't really affect the tests
        patcher_update_task = patch('cloudlaunch.tasks.update_status_task')
        patcher_update_task.start()
        self.addCleanup(patcher_update_task.stop)
        patcher_migrate_task = patch('cloudlaunch.tasks.migrate_launch_task')
        patcher_migrate_task.start()
        self.addCleanup(patcher_migrate_task.stop)
        patcher_migrate_result = patch('cloudlaunch.tasks.migrate_task_result')
        patcher_migrate_result.start()
        self.addCleanup(patcher_migrate_result.stop)

        self.client.force_login(
            User.objects.get_or_create(username='clusteradmin', is_superuser=True, is_staff=True)[0])


class CMClusterServiceTests(CMClusterServiceTestBase):

    fixtures = ['initial_test_data.json']

    # TODO: Check that attempting to create an existing
    # object raises exception

    def _create_cluster(self):
        url = reverse('clusterman:clusters-list')
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

    def _update_cluster(self, cluster_id):
        url = reverse('clusterman:clusters-detail', args=[cluster_id])
        cluster_data = dict(self.CLUSTER_DATA)
        cluster_data['name'] = 'new_name'
        cluster_data['autoscale'] = False
        response = self.client.put(url, cluster_data, format='json')
        return response.data

    def _delete_cluster(self, cluster_id):
        url = reverse('clusterman:clusters-detail', args=[cluster_id])
        return self.client.delete(url)

    def _check_no_clusters_exist(self):
        url = reverse('clusterman:clusters-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 0)

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
        self.assertEquals(response.data['default_vm_type'], 'm5.24xlarge')
        self.assertEquals(response.data['default_zone']['name'], 'us-east-1b')

        # check details
        cluster_id = self._check_cluster_exists(cluster_id)

        # update cluster
        response = self._update_cluster(cluster_id)
        self.assertEquals(response['name'], 'new_name')

        # delete the object
        response = self._delete_cluster(cluster_id)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT, response.data)

        # check it no longer exists
        self._check_no_clusters_exist()

    def test_create_duplicate_name(self):
        self._create_cluster()
        response = self._create_cluster()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

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
        QuietWSGIRequestHandler.handle = QuietWSGIRequestHandler.handle_one_request
        return WSGIServer((self.host, self.port), QuietWSGIRequestHandler, allow_reuse_address=False)


class LiveServerSingleThreadedTestCase(APILiveServerTestCase):
    "A thin sub-class which only sets the single-threaded server as a class"
    server_thread_class = LiveServerSingleThread


class CMClusterNodeTestBase(CMClusterServiceTestBase, LiveServerSingleThreadedTestCase):

    def setUp(self):
        self.client.force_login(
            User.objects.get_or_create(username='clusteradmin', is_superuser=True, is_staff=True)[0])

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

        patcher4 = patch('cloudlaunch.configurers.AnsibleAppConfigurer.configure',
                         side_effect=self._add_dummy_node)
        patcher4.start()
        self.addCleanup(patcher4.stop)

        super().setUp()

    def _add_dummy_node(self, app_config, provider_config, playbook_vars=None):
        node_name = app_config.get('config_kube_rke', {}).get('rke_cluster_id')
        node_ip = provider_config.get('host_config', {}).get('public_ip')
        node = {
            "apiVersion": "v1",
            "kind": "Node",
            "metadata": {
                "labels": {
                    "kubernetes.io/hostname": node_name,
                    "node-role.kubernetes.io/master": ""
                },
                "name": node_name,
                "resourceVersion": "3932510",
                "selfLink": f"/api/v1/nodes/{node_name}",
                "uid": "166c6e35-76b7-4f28-a1a0-590dd3e05662"
            },
            "spec": {},
            "status": {
                "addresses": [
                    {
                        "address": node_ip,
                        "type": "ExternalIP"
                    }
                ],
            }
        }
        kube_mocker = self.mock_client.mockers[0]
        kube_mocker.mock_kubectl._kubectl_add_node(node)
        return {}


class CMClusterNodeServiceTests(CMClusterNodeTestBase):

    NODE_DATA = {
        'vm_type': 'm1.medium'
    }

    fixtures = ['initial_test_data.json']

    def _create_cluster(self):
        url = reverse('clusterman:clusters-list')
        response = self.client.post(url, self.CLUSTER_DATA, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return response.data['id']

    def _create_cluster_node(self, cluster_id):
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

    def test_celery_task_create_cluster_node(self):
        # create the parent cluster
        cluster_id = self._create_cluster()

        # should initially have 1 node
        client = KubeClient()
        node_list = client.nodes.list()
        self.assertEqual(len(node_list), 1)

        # create cluster node
        response = self._create_cluster_node(cluster_id)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)

        # A new node should have been added
        node_list = client.nodes.list()
        self.assertEqual(len(node_list), 2)

    def test_celery_task_create_cluster_node_retry(self):
        # create the parent cluster
        cluster_id = self._create_cluster()

        # should initially have 1 node
        client = KubeClient()
        node_list = client.nodes.list()
        self.assertEqual(len(node_list), 1)

        # create cluster node, but fail to add node
        with patch('cloudlaunch.configurers.AnsibleAppConfigurer.configure',
                   return_value={}) as node_add_fail:
            self._create_cluster_node(cluster_id)
            self.assertEqual(node_add_fail.call_count, 2)

        # A new node should not have been added
        node_list = client.nodes.list()
        self.assertEqual(len(node_list), 1)

    def test_celery_task_create_cluster_node_succeed_on_second_try(self):
        # create the parent cluster
        cluster_id = self._create_cluster()

        # should initially have 1 node
        client = KubeClient()
        node_list = client.nodes.list()
        self.assertEqual(len(node_list), 1)

        counter_ref = [0]

        def succeed_on_second_try(count_ref, *args, **kwargs):
            if count_ref[0] > 0:
                self._add_dummy_node(*args, **kwargs)
            count_ref[0] += 1

        # create cluster node, but trigger a retry
        with patch('cloudlaunch.configurers.AnsibleAppConfigurer.configure',
                   side_effect=lambda *args, **kwargs: succeed_on_second_try(
                       counter_ref, *args, **kwargs)) as node_add_fail:
            self._create_cluster_node(cluster_id)
            self.assertEqual(node_add_fail.call_count, 2)

        # A new node should have been added
        node_list = client.nodes.list()
        self.assertEqual(len(node_list), 2)

    def test_node_create_unauthorized(self):
        cluster_id = self._create_cluster()
        self.client.force_login(
            User.objects.get_or_create(username='notaclusteradmin', is_staff=False)[0])
        response = self._create_cluster_node(cluster_id)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

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
        'vm_type': 'm1.medium',
        'zone': 2,
        'min_nodes': 2,
        'max_nodes': 7
    }

    AUTOSCALER_UPDATE_DATA = {
        'name': 'test_name',
        'vm_type': 'm3.medium',
        'zone': 3,
        'min_nodes': 0,
        'max_nodes': 6
    }

    fixtures = ['initial_test_data.json']

    def _create_cluster(self):
        url = reverse('clusterman:clusters-list')
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

    def _check_autoscaler_exists(self, cluster_id, autoscaler_id):
        url = reverse('clusterman:autoscaler-detail', args=[cluster_id, autoscaler_id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertDictContainsSubset(self.AUTOSCALER_UPDATE_DATA, response.data)
        cluster_data = dict(self.CLUSTER_DATA)
        cluster_data.pop('connection_settings')
        self.assertDictContainsSubset(cluster_data, response.data['cluster'])
        return response.data['id']

    def _update_autoscaler(self, cluster_id, autoscaler_id):
        url = reverse('clusterman:autoscaler-detail', args=[cluster_id, autoscaler_id])
        response = self.client.put(url, self.AUTOSCALER_UPDATE_DATA, format='json')
        return response.data

    def _delete_autoscaler(self, cluster_id, autoscaler_id):
        url = reverse('clusterman:autoscaler-detail', args=[cluster_id, autoscaler_id])
        return self.client.delete(url)

    def _check_no_autoscalers_exist(self, cluster_id):
        url = reverse('clusterman:autoscaler-list', args=[cluster_id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 0)

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

        # update autoscaler
        response = self._update_autoscaler(cluster_id, autoscaler_id)
        self.assertDictContainsSubset(self.AUTOSCALER_UPDATE_DATA, response)

        # check it exists
        autoscaler_id = self._check_autoscaler_exists(cluster_id, autoscaler_id)

        # delete the object
        response = self._delete_autoscaler(cluster_id, autoscaler_id)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # check it no longer exists
        self._check_no_autoscalers_exist(cluster_id)

    def test_autoscaler_create_unauthorized(self):
        cluster_id = self._create_cluster()
        self.client.force_login(
            User.objects.get_or_create(username='notaclusteradmin', is_staff=False)[0])
        response = self._create_autoscaler(cluster_id)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

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


class CMClusterScaleSignalTests(CMClusterNodeTestBase):

    NODE_DATA = {
        'vm_type': 'm1.medium'
    }

    AUTOSCALER_DATA = {
        'name': 'default',
        'vm_type': 'm1.medium',
        'zone': 2,
        'min_nodes': '1',
        'max_nodes': '2'
    }

    AUTOSCALER_DATA_SECOND_ZONE = {
        'name': 'secondary',
        'vm_type': 'm1.medium',
        'zone': 3,
        'min_nodes': '0',
        'max_nodes': '2'
    }

    AUTOSCALER_DATA_ALLOWED_VM_TYPES = {
        'name': 'secondary',
        'vm_type': 'm1.medium',
        'allowed_vm_type_prefixes': 'i5.,m3',
        'zone': 3,
        'min_nodes': '0',
        'max_nodes': '2'
    }

    SCALE_SIGNAL_DATA = {
        "receiver": "cloudman",
        "status": "resolved",
        "alerts": [
            {
                "status": "resolved",
                "labels": {
                    "alertname": "KubeCPUOvercommit",
                    "hostname": "testhostname",
                    "instance": "192.168.1.1:8000",
                    "job": "node-exporter",
                    "severity": "critical",
                    "tier": "svc"
                },
                "annotations": {
                    "summary": "Cluster has overcommitted CPU resources"
                },
                "startsAt": "2019-01-02T10:31:46.05445419Z",
                "endsAt": "2019-01-02T10:36:46.05445419Z",
                "generatorURL": "http://prometheus.int/graph?g0.expr=up%7Bjob%3D%22node-exporter%22%2Ctier%21%3D%22ephemeral%22%7D+%3D%3D+0&g0.tab=1"
            }
        ],
        "groupLabels": {
            "alertname": "KubeCPUOvercommit"
        },
        "commonLabels": {
            "alertname": "KubeCPUOvercommit",
            "hostname": "testhostname",
            "instance": "192.168.1.1:8000",
            "job": "node-exporter",
            "severity": "critical",
            "tier": "svc"
        },
        "commonAnnotations": {
            "host_tier": "testhostname",
            "summary": "Cluster has overcommitted CPU resources"
        },
        "externalURL": "http://alertmanager:9093",
        "version": "4",
        "groupKey": "{}/{}:{alertname=\"KubeCPUOvercommit\"}"
    }

    SCALE_SIGNAL_DATA_SECOND_ZONE = {
        "receiver": "cloudman",
        "status": "resolved",
        "alerts": [
            {
                "status": "resolved",
                "labels": {
                    "alertname": "KubeCPUOvercommit",
                    "availability_zone": "us-east-1c"
                },
                "annotations": {
                    "summary": "Cluster has overcommitted CPU resources"
                }
            }
        ],
        "commonLabels": {
            "alertname": "KubeCPUOvercommit",
            "availability_zone": "us-east-1c"
        },
        "version": "4",
        "groupKey": "{}/{}:{alertname=\"KubeCPUOvercommit\"}"
    }

    SCALE_SIGNAL_DATA_POD_UNSCHEDULABLE = {
        "receiver": "cloudman",
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "PodNotSchedulable",
                    "container": "job-container",
                    "cpus": "92.5",
                    "instance": "10.42.0.19:8080",
                    "job": "kube-state-metrics",
                    "memory": "691100000000.5",
                    "pod": "galaxy-galaxy-1596991139-245-lc4mg",
                    "severity": "warning"
                },
                "annotations": {
                    "cpus": "92.5",
                    "memory": "691100000000.5",
                    "message": "Cluster has unschedulable pods due to insufficient CPU or memory"
                },
                "startsAt": "2020-08-21T11:47:31.470370261Z",
                "endsAt": "0001-01-01T00:00:00Z",
                "generatorURL": "http://prometheus.int/graph?g0.expr=up%7Bjob%3D%22node-exporter%22%2Ctier%21%3D%22ephemeral%22%7D+%3D%3D+0&g0.tab=1"
            }
        ],
        "groupLabels": {
            "alertname": "PodNotSchedulable"
        },
        "commonLabels": {
            "alertname": "PodNotSchedulable",
            "container": "job-container",
            "cpus": "92.5",
            "instance": "10.42.0.19:8080",
            "job": "kube-state-metrics",
            "memory": "691100000000.5",
            "pod": "galaxy-galaxy-1596991139-245-lc4mg",
            "severity": "warning"
        },
        "commonAnnotations": {
            "cpus": "92.5",
            "memory": "691100000000.5",
            "message": "Cluster has unschedulable pods due to insufficient CPU or memory"
        },
        "externalURL": "http://cloudman-prometheus-alertmanager.cloudman:9093",
        "version": "4",
        "groupKey": "{}/{alertname=\"PodNotSchedulable\"}:{alertname=\"PodNotSchedulable\"}"
    }

    fixtures = ['initial_test_data.json']

    def _create_cluster_raw(self):
        url = reverse('clusterman:clusters-list')
        return self.client.post(url, self.CLUSTER_DATA, format='json')

    def _create_cluster(self):
        response = self._create_cluster_raw()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return response.data['id']

    def _update_cluster(self, cluster_id):
        url = reverse('clusterman:clusters-detail', args=[cluster_id])
        cluster_data = dict(self.CLUSTER_DATA)
        cluster_data['name'] = 'new_name'
        cluster_data['autoscale'] = False
        response = self.client.put(url, cluster_data, format='json')
        return response

    def _deactivate_autoscaling(self, cluster_id):
        url = reverse('clusterman:clusters-detail', args=[cluster_id])
        response = self.client.get(url)
        cluster_data = response.data
        cluster_data['autoscale'] = False
        return self.client.put(url, cluster_data, format='json')

    def _create_cluster_node(self, cluster_id):
        url = reverse('clusterman:node-list', args=[cluster_id])
        return self.client.post(url, self.NODE_DATA, format='json')

    def _count_cluster_nodes(self, cluster_id):
        url = reverse('clusterman:node-list', args=[cluster_id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response.data['count']

    def _get_cluster_node_vm_types(self, cluster_id):
        url = reverse('clusterman:node-list', args=[cluster_id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return [n['deployment']['application_config']['config_cloudlaunch']['vmType']
                for n in response.data['results']]

    def _signal_scaleup(self, cluster_id, data=SCALE_SIGNAL_DATA):
        url = reverse('clusterman:scaleupsignal-list', args=[cluster_id])
        response = self.client.post(url, data, format='json')
        return response

    def _signal_scaledown(self, cluster_id, data=SCALE_SIGNAL_DATA):
        url = reverse('clusterman:scaledownsignal-list', args=[cluster_id])
        response = self.client.post(url, data, format='json')
        return response

    def _create_autoscaler(self, cluster_id, data=AUTOSCALER_DATA):
        url = reverse('clusterman:autoscaler-list', args=[cluster_id])
        response = self.client.post(url, data, format='json')
        return response.data['id']

    def _count_nodes_in_scale_group(self, cluster_id, autoscaler_id):
        url = reverse('clusterman:node-list', args=[cluster_id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return len([n for n in response.data['results']
                    if n['autoscaler'] == int(autoscaler_id)])

    def test_scale_up_default(self):
        # create the parent cluster
        cluster_id = self._create_cluster()

        count = self._count_cluster_nodes(cluster_id)
        self.assertEqual(count, 0)

        # send autoscale signal
        self._signal_scaleup(cluster_id)

        # Ensure that node was created
        count = self._count_cluster_nodes(cluster_id)
        self.assertEqual(count, 1)

        # Ensure that the created node has the correct size
        vm_types = self._get_cluster_node_vm_types(cluster_id)
        self.assertEqual(len(vm_types), 1)
        self.assertTrue("m5.24xlarge" in vm_types)

    def test_scale_down_default(self):
        # create the parent cluster
        cluster_id = self._create_cluster()

        # send autoscale signal
        self._signal_scaleup(cluster_id)

        # Ensure that node was created
        count = self._count_cluster_nodes(cluster_id)
        self.assertEqual(count, 1)

        # send autoscale signal
        self._signal_scaledown(cluster_id)

        # Ensure that node was deleted
        count = self._count_cluster_nodes(cluster_id)
        self.assertEqual(count, 0)

    def test_scaling_while_deactivated(self):
        # create the parent cluster
        cluster_id = self._create_cluster()

        # send autoscale signal
        self._signal_scaleup(cluster_id)

        # Ensure that node was created
        count = self._count_cluster_nodes(cluster_id)
        self.assertEqual(count, 1)

        # deactivate autoscaling
        self._deactivate_autoscaling(cluster_id)

        # send autoscale signal
        self._signal_scaleup(cluster_id)

        # Ensure that scaling up doesn't occur
        count = self._count_cluster_nodes(cluster_id)
        self.assertEqual(count, 1)

        # send autoscale signal
        self._signal_scaledown(cluster_id)

        # Ensure that scaling up doesn't occur
        count = self._count_cluster_nodes(cluster_id)
        self.assertEqual(count, 1)

    def test_scaling_is_within_bounds(self):
        # create the parent cluster
        cluster_id = self._create_cluster()

        # manually create autoscaler
        self._create_autoscaler(cluster_id)

        count = self._count_cluster_nodes(cluster_id)
        self.assertEqual(count, 0)

        # send three autoscale signals
        self._signal_scaleup(cluster_id)
        self._signal_scaleup(cluster_id)
        self._signal_scaleup(cluster_id)

        # Ensure that only two nodes were created
        count = self._count_cluster_nodes(cluster_id)
        self.assertEqual(count, 2)

        # Make sure nodes do not shrink below mininimum
        self._signal_scaledown(cluster_id)
        self._signal_scaledown(cluster_id)
        self._signal_scaledown(cluster_id)

        # Ensure that manual node remains
        count = self._count_cluster_nodes(cluster_id)
        self.assertEqual(count, 1)

        # Ensure that the created node has the correct size
        vm_types = self._get_cluster_node_vm_types(cluster_id)
        self.assertEqual(len(vm_types), 1)
        self.assertTrue("m1.medium" in vm_types)

    def test_scaling_with_manual_nodes(self):
        # create the parent cluster
        cluster_id = self._create_cluster()
        self._create_cluster_node(cluster_id)

        count = self._count_cluster_nodes(cluster_id)
        self.assertEqual(count, 1)

        # send two autoscale signals
        self._signal_scaleup(cluster_id)
        self._signal_scaleup(cluster_id)

        # Ensure that two nodes were created
        count = self._count_cluster_nodes(cluster_id)
        self.assertEqual(count, 3)

        # Make sure manually added node is not removed
        self._signal_scaledown(cluster_id)
        self._signal_scaledown(cluster_id)
        self._signal_scaledown(cluster_id)

        # Ensure that manual node remains
        count = self._count_cluster_nodes(cluster_id)
        self.assertEqual(count, 1)

    def test_scaling_within_zone_group(self):
        # create the parent cluster
        cluster_id = self._create_cluster()

        # manually create autoscaler
        autoscaler_default_id = self._create_autoscaler(cluster_id)

        # create another autoscaler
        autoscaler_secondary_id = self._create_autoscaler(
            cluster_id, data=self.AUTOSCALER_DATA_SECOND_ZONE)

        # everything should be zero initially
        count = self._count_cluster_nodes(cluster_id)
        self.assertEqual(count, 0)

        # sending an autoscale signal should scale the default scaler
        self._signal_scaleup(cluster_id)
        count_default = self._count_nodes_in_scale_group(
            cluster_id, autoscaler_default_id)
        count_secondary = self._count_nodes_in_scale_group(
            cluster_id, autoscaler_secondary_id)
        self.assertEqual(count_default, 1)
        self.assertEqual(count_secondary, 0)

        # send another scale signal but affecting a different zone group
        self._signal_scaleup(cluster_id, data=self.SCALE_SIGNAL_DATA_SECOND_ZONE)
        count_default = self._count_nodes_in_scale_group(
            cluster_id, autoscaler_default_id)
        count_secondary = self._count_nodes_in_scale_group(
            cluster_id, autoscaler_secondary_id)
        self.assertEqual(count_default, 1)
        self.assertEqual(count_secondary, 1)
        count = self._count_cluster_nodes(cluster_id)
        self.assertEqual(count, 2)

        # should respect the second zone's scaling limits
        self._signal_scaleup(cluster_id, data=self.SCALE_SIGNAL_DATA_SECOND_ZONE)
        self._signal_scaleup(cluster_id, data=self.SCALE_SIGNAL_DATA_SECOND_ZONE)
        count_default = self._count_nodes_in_scale_group(
            cluster_id, autoscaler_default_id)
        count_secondary = self._count_nodes_in_scale_group(
            cluster_id, autoscaler_secondary_id)
        self.assertEqual(count_default, 1)
        self.assertEqual(count_secondary, 2)
        count = self._count_cluster_nodes(cluster_id)
        self.assertEqual(count, 3)

        # should affect only second zone
        self._signal_scaledown(cluster_id, data=self.SCALE_SIGNAL_DATA_SECOND_ZONE)
        self._signal_scaledown(cluster_id, data=self.SCALE_SIGNAL_DATA_SECOND_ZONE)

        count_default = self._count_nodes_in_scale_group(
            cluster_id, autoscaler_default_id)
        count_secondary = self._count_nodes_in_scale_group(
            cluster_id, autoscaler_secondary_id)
        self.assertEqual(count_default, 1)
        self.assertEqual(count_secondary, 0)

        # Ensure the total nodes are 1
        count = self._count_cluster_nodes(cluster_id)
        self.assertEqual(count, 1)

        # Ensure that the created node has the correct size
        vm_types = self._get_cluster_node_vm_types(cluster_id)
        self.assertEqual(len(vm_types), 1)
        self.assertTrue("m5.24xlarge")

    def _login_as_autoscaling_user(self, impersonate_user=None):
        if impersonate_user:
            call_command('create_autoscale_user', "--impersonate_account",
                         impersonate_user, "--username", "autoscaletestuser")
        else:
            call_command('create_autoscale_user', "--username", "autoscaletestuser")
        self.client.force_login(
            User.objects.get_or_create(username='autoscaletestuser')[0])

    def test_autoscaling_user_scale_up_permissions(self):
        # create the parent cluster
        cluster_id = self._create_cluster()
        self._login_as_autoscaling_user()
        count = self._count_cluster_nodes(cluster_id)
        self.assertEqual(count, 0)
        response = self._signal_scaleup(cluster_id)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        count = self._count_cluster_nodes(cluster_id)
        self.assertEqual(count, 1)

    def test_autoscaling_user_scale_down_permissions(self):
        # create the parent cluster
        cluster_id = self._create_cluster()
        self._login_as_autoscaling_user()
        self._signal_scaleup(cluster_id)
        count = self._count_cluster_nodes(cluster_id)
        self.assertEqual(count, 1)
        response = self._signal_scaledown(cluster_id)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        count = self._count_cluster_nodes(cluster_id)
        self.assertEqual(count, 0)

    def test_autoscaling_user_no_extra_permissions(self):
        # create a parent cluster
        cluster_id = self._create_cluster()

        self._login_as_autoscaling_user()

        # Should not be able to create a new cluster
        response = self._create_cluster_raw()
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

        # should not be able to change an existing cluster
        response = self._update_cluster(cluster_id)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_autoscale_up_signal_unauthorized(self):
        cluster_id = self._create_cluster()
        self._create_autoscaler(cluster_id)
        self.client.force_login(
            User.objects.get_or_create(username='notaclusteradmin', is_staff=False)[0])
        response = self._signal_scaleup(cluster_id)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_autoscale_down_signal_unauthorized(self):
        cluster_id = self._create_cluster()
        self._create_autoscaler(cluster_id)
        self.client.force_login(
            User.objects.get_or_create(username='notaclusteradmin', is_staff=False)[0])
        response = self._signal_scaledown(cluster_id)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_create_autoscale_user_impersonate(self):
        # create a parent cluster
        cluster_id = self._create_cluster()
        self._login_as_autoscaling_user(impersonate_user='clusteradmin')
        count = self._count_cluster_nodes(cluster_id)
        self.assertEqual(count, 0)
        response = self._signal_scaleup(cluster_id)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        count = self._count_cluster_nodes(cluster_id)
        self.assertEqual(count, 1)

    def test_create_autoscale_user_impersonate_no_perms(self):
        # create a parent cluster
        cluster_id = self._create_cluster()
        # create a non admin user
        self.client.force_login(
            User.objects.get_or_create(username='notaclusteradmin', is_staff=False)[0])
        # log back in as admin
        self.client.force_login(
            User.objects.get(username='clusteradmin'))
        # impersonate non admin user
        self._login_as_autoscaling_user(impersonate_user='notaclusteradmin')
        count = self._count_cluster_nodes(cluster_id)
        self.assertEqual(count, 0)
        response = self._signal_scaleup(cluster_id)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)
        count = self._count_cluster_nodes(cluster_id)
        self.assertEqual(count, 0)

    def test_scale_up_unschedulable(self):
        # create the parent cluster
        cluster_id = self._create_cluster()

        count = self._count_cluster_nodes(cluster_id)
        self.assertEqual(count, 0)

        # send autoscale signal with unschedulable pod
        self._signal_scaleup(cluster_id, data=self.SCALE_SIGNAL_DATA_POD_UNSCHEDULABLE)

        # Ensure that node was created
        count = self._count_cluster_nodes(cluster_id)
        self.assertEqual(count, 1)

        # Ensure that the created node has the correct size
        vm_types = self._get_cluster_node_vm_types(cluster_id)
        self.assertEqual(len(vm_types), 1)
        self.assertTrue("m5.24xlarge" in vm_types)

    def test_scale_up_allowed_vm_Types(self):
        # create the parent cluster
        cluster_id = self._create_cluster()

        # manually create autoscaler
        self._create_autoscaler(cluster_id, data=self.AUTOSCALER_DATA_ALLOWED_VM_TYPES)

        # send autoscale signal
        self._signal_scaleup(cluster_id, data=self.SCALE_SIGNAL_DATA_SECOND_ZONE)

        # Ensure that node was created
        count = self._count_cluster_nodes(cluster_id)
        self.assertEqual(count, 1)

        # Ensure that the created node has the correct size
        vm_types = self._get_cluster_node_vm_types(cluster_id)
        self.assertEqual(len(vm_types), 1)
        self.assertTrue("m5.24xlarge" not in vm_types)
