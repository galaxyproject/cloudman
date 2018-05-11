import json
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase, APILiveServerTestCase
from unittest.mock import patch
from unittest.mock import PropertyMock


# Create your tests here.
class CMCloudServiceTests(APITestCase):

    # TODO: Check that attempting to create an existing
    # object raises exception
    # TODO: Add test for updating objects
    CLUSTER_DATA = {'name': 'testcluster1',
                    'cluster_type': 'KUBE_RANCHER',
                    'connection_settings': {
                        'target_cloud': 'amazon-us-east-n-virginia'
                        }
                    }

    def setUp(self):
        self.client.force_login(
            User.objects.get_or_create(username='test_user')[0])

    def tearDown(self):
        self.client.logout()

    def test_crud_cluster(self):
        """
        Ensure we can register a new cluster with cloudman.
        """
        # create the object
        url = reverse('clusters-list')
        response = self.client.post(url, self.CLUSTER_DATA, format='json')
        print(response.data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # check it exists
        url = reverse('clusters-detail', args=[response.data['id']])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertDictContainsSubset(self.CLUSTER_DATA,
                                      response.data)

        # delete the object
        url = reverse('clusters-detail', args=[response.data['id']])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # check it no longer exists
        url = reverse('clusters-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class CMClusterNodeServiceTests(APILiveServerTestCase):

    CLUSTER_DATA = {'name': 'testcluster2',
                    'cluster_type': 'KUBE_RANCHER',
                    'connection_settings': {
                        'target_cloud': 'amazon-us-east-n-virginia'
                        }
                    }

    NODE_DATA = {'name': 'testvm1',
                 'instance_type': 'm1.medium'
                 }

    fixtures = ['initial_test_data.json']

    def setUp(self):
        cloudlaunch_url = f'{self.live_server_url}/cloudlaunch/api/v1'
        self.patcher = patch('cmcluster.api.CMServiceContext.cloudlaunch_url',
                             new_callable=PropertyMock,
                             return_value=cloudlaunch_url)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.client.force_login(
            User.objects.get_or_create(username='test_user')[0])

    def tearDown(self):
        self.client.logout()

    def test_crud_cluster_node(self):
        """
        Ensure we can register a new node with cloudman.
        """
        # create the object
        url = reverse('clusters-list')
        response = self.client.post(url, self.CLUSTER_DATA, format='json')
        cluster_id = response.data['id']

        url = reverse('node-list', args=[cluster_id])
        response = self.client.post(url, self.NODE_DATA, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # check it exists
        url = reverse('node-detail', args=[cluster_id, response.data['id']])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertDictContainsSubset({'vmType': 'm1.medium'},
                                      (response.data.get('deployment')
                                       .get('application_config')
                                       .get('config_cloudlaunch')))

        # delete the object
        url = reverse('node-detail', args=[cluster_id, response.data['id']])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # check it no longer exists
        url = reverse('node-list', args=[cluster_id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
