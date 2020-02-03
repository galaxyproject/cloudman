from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .client_mocker import ClientMocker

from helmsman.api import ChartExistsException


# Create your tests here.
class HelmsManServiceTestBase(APITestCase):

    def setUp(self):
        self.mock_client = ClientMocker(self)
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
        url = reverse('helmsman:repositories-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class ChartServiceTests(HelmsManServiceTestBase):

    CHART_DATA = {
        'name': 'galaxy',
        'display_name': 'Galaxy',
        'chart_version': '3.0.0',
        'namespace': 'gvl',
        'state': "DEPLOYED",
        'values': {
            'hello': 'world'
        }
    }

    def test_crud_chart(self):
        """
        Ensure we can register a new cluster with cloudman.
        """
        # create the object
        url = reverse('helmsman:charts-list')
        response = self.client.post(url, self.CHART_DATA, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED,
                         response.data)
        # create duplicate object
        with self.assertRaises(ChartExistsException):
            self.client.post(url, self.CHART_DATA, format='json')
        # list existing objects
        url = reverse('helmsman:charts-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertDictContainsSubset(self.CHART_DATA, response.data['results'][1])

        # check it exists
        url = reverse('helmsman:charts-detail', args=[response.data['results'][1]['id']])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertDictContainsSubset(self.CHART_DATA, response.data)

        # delete the object
        url = reverse('helmsman:charts-detail', args=[response.data['id']])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # check it no longer exists
        url = reverse('helmsman:charts-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)


class NamespaceServiceTests(HelmsManServiceTestBase):

    NAMESPACE_DATA = {
        'name': 'newnamespace',
        'status': 'Active',
        'age': '1d'
    }

    def test_crud_namespace(self):
        """
        Ensure we can register a new cluster with cloudman.
        """
        # create the object
        url = reverse('helmsman:namespaces-list')
        response = self.client.post(url, self.NAMESPACE_DATA, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        # list existing objects
        url = reverse('helmsman:namespaces-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertDictContainsSubset(self.NAMESPACE_DATA, response.data['results'][1])

        # check it exists
        url = reverse('helmsman:namespaces-detail', args=[response.data['results'][1]['name']])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertDictContainsSubset(self.NAMESPACE_DATA, response.data)

        # delete the object
        url = reverse('helmsman:namespaces-detail', args=[response.data['name']])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # check it no longer exists
        url = reverse('helmsman:namespaces-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
