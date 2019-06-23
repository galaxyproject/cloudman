from django.urls import reverse
from rest_framework import status
from helmsman.tests import HelmsManServiceTestBase


# Create your tests here.
class ProjManManServiceTestBase(HelmsManServiceTestBase):
    pass


class ProjectServiceTests(ProjManManServiceTestBase):

    PROJECT_DATA = {
        'name': 'GVL'
    }

    def test_crud_project(self):
        """
        Ensure we can register a new project
        """
        # create the object
        url = reverse('projman:projects-list')
        response = self.client.post(url, self.PROJECT_DATA, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        # list existing objects
        url = reverse('projman:projects-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertDictContainsSubset(self.PROJECT_DATA, response.data['results'][0])

        # check it exists
        url = reverse('projman:projects-detail', args=[response.data['results'][0]['id']])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertDictContainsSubset(self.PROJECT_DATA, response.data)

        # delete the object
        url = reverse('projman:projects-detail', args=[response.data['id']])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # check it no longer exists
        url = reverse('projman:projects-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 0)


class ProjectChartServiceTests(ProjManManServiceTestBase):

    PROJECT_DATA = {
        'name': 'GVL'
    }

    CHART_DATA = {
        'name': 'galaxy',
        'display_name': 'Galaxy',
        'chart_version': '3.0.0',
        'state': "DEPLOYED",
        'values': {
            'hello': 'world'
        }
    }

    def test_crud_project_chart(self):
        """
        Ensure we can register a new project
        """
        # create the parent project
        url = reverse('projman:projects-list')
        response = self.client.post(url, self.PROJECT_DATA, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        project_id = response.data['id']

        # create the project chart
        url = reverse('projman:chart-list', args=[project_id])
        response = self.client.post(url, self.CHART_DATA, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        # list existing objects
        url = reverse('projman:chart-list', args=[project_id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertDictContainsSubset(self.PROJECT_DATA, response.data['results'][0]['project'])
        self.assertDictContainsSubset(self.CHART_DATA, response.data['results'][0])

        # check it exists
        url = reverse('projman:chart-detail', args=[project_id, response.data['results'][0]['id']])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertDictContainsSubset(self.PROJECT_DATA, response.data['project'])
        self.assertDictContainsSubset(self.CHART_DATA, response.data)

        # delete the object
        url = reverse('projman:chart-detail', args=[project_id, response.data['id']])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # check it no longer exists
        url = reverse('projman:chart-list', args=[project_id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 0)
