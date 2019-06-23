from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase


# Create your tests here.
class ProjManManServiceTestBase(APITestCase):

    def setUp(self):
        self.client.force_login(
            User.objects.get_or_create(username='admin')[0])

    def tearDown(self):
        self.client.logout()


class ProjectServiceTests(ProjManManServiceTestBase):

    PROJECT_DATA = {
        'name': 'GVL'
    }

    def test_crud_project(self):
        """
        Ensure we can register a new project
        """
        # create the object
        url = reverse('projects-list')
        response = self.client.post(url, self.PROJECT_DATA, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        # list existing objects
        url = reverse('projects-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertDictContainsSubset(self.PROJECT_DATA, response.data['results'][0])

        # check it exists
        url = reverse('projects-detail', args=[response.data['results'][0]['id']])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertDictContainsSubset(self.PROJECT_DATA, response.data)

        # delete the object
        url = reverse('projects-detail', args=[response.data['id']])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # check it no longer exists
        url = reverse('projects-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 0)
