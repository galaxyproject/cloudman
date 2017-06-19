from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from cminfrastructure.api import CMInfrastructureAPI


# Create your tests here.
class CMCloudServiceTests(APITestCase):

    # TODO: Check that attempting to create an existing
    # object raises exception
    # TODO: Add test for updating objects
    CLOUD_DATA = {'name': 'testcloud1',
                  'provider_id': 'aws',
                  'provider_config': {'access_key': 'dummy',
                                      'secret_key': 'dummy'}
                  }

    def setUp(self):
        self.client.force_login(
            User.objects.get_or_create(username='testuser')[0])

    def tearDown(self):
        self.client.logout()

    def test_crud_cloud(self):
        """
        Ensure we can register a new cloud with cloudman.
        """
        # create the object
        url = reverse('cloud-list')
        response = self.client.post(url, self.CLOUD_DATA, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # check it exists
        url = reverse('cloud-detail', args=[response.data['cloud_id']])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertDictContainsSubset(self.CLOUD_DATA,
                                      response.data)

        # delete the object
        url = reverse('cloud-detail', args=[response.data['cloud_id']])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # check it no longer exists
        url = reverse('cloud-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class CMCloudNodeServiceTests(APITestCase):

    CLOUD_DATA = {'name': 'testcloud2',
                  'provider_id': 'openstack',
                  'provider_config': {'access_key': 'dummy',
                                      'secret_key': 'dummy'}
                  }

    NODE_DATA = {'name': 'testvm1',
                 'instance_type': 'm1.medium'
                 }

    def setUp(self):
        self.client.force_login(
            User.objects.get_or_create(username='testuser')[0])

    def tearDown(self):
        self.client.logout()

    def test_crud_cloud_node(self):
        """
        Ensure we can register a new node with cloudman.
        """
        # create the object
        url = reverse('cloud-list')
        response = self.client.post(url, self.CLOUD_DATA, format='json')
        cloud_id = response.data['cloud_id']
        url = reverse('node-list', args=[cloud_id])
        response = self.client.post(url, self.NODE_DATA, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # check it exists
        url = reverse('node-detail', args=[cloud_id, response.data['id']])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertDictContainsSubset(self.NODE_DATA,
                                      response.data)

        # delete the object
        url = reverse('node-detail', args=[cloud_id, response.data['id']])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # check it no longer exists
        url = reverse('node-list', args=[cloud_id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class CMNodeTaskServiceTests(APITestCase):

    CLOUD_DATA = {'name': 'testcloud2',
                  'provider_id': 'openstack',
                  'provider_config': {'access_key': 'dummy',
                                      'secret_key': 'dummy'}
                  }

    NODE_DATA = {'name': 'testvm1',
                 'instance_type': 'm1.medium'
                 }

    TASK_DATA = {'task_type': 'create_node',
                 'task_params': None
                 }

    def setUp(self):
        self.client.force_login(
            User.objects.get_or_create(username='testuser')[0])
        # Make sure tasks execute synchronously during tests
        import cloudman.celery as celery
        celery.app.conf.task_always_eager = True

    def tearDown(self):
        self.client.logout()

    def test_crud_cloud_node(self):
        """
        Ensure we can register a new node with cloudman.
        """
        # create the object
        url = reverse('cloud-list')
        response = self.client.post(url, self.CLOUD_DATA, format='json')
        cloud_id = response.data['cloud_id']

        url = reverse('node-list', args=[cloud_id])
        response = self.client.post(url, self.NODE_DATA, format='json')
        node_id = response.data['id']

        url = reverse('nodetask-list', args=[cloud_id, node_id])

        # Creating a node should have spawned a create task
        response = self.client.get(url, format='json')
        self.assertEqual(len(response.data), 1, "Creating a node"
                         "should have spawned a task")

        # Attempting to create the task again should create a task
        response = self.client.post(url, self.TASK_DATA, format='json')
        task_id = response.data['task_id']
        response = self.client.get(url, self.TASK_DATA, format='json')
        self.assertEqual(len(response.data), 2, "New task should have"
                         "been created")
        # However, that created task should fail
        url = reverse('nodetask-detail', args=[cloud_id, node_id, task_id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertDictContainsSubset(self.TASK_DATA,
                                      response.data)
        self.assertEqual(response.data['status'], "FAILED", "Attempting to create"
                         " a node twice should have failed")

        # delete the object
        url = reverse('nodetask-detail', args=[cloud_id, node_id, task_id])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # check it no longer exists
        url = reverse('nodetask-list', args=[cloud_id, node_id])
        response = self.client.get(url)
        self.assertEqual(len(response.data), 1, "There should be only one task"
                         " remaining")
