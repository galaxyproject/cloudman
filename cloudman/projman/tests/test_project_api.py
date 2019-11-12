from django.urls import reverse
from django.contrib.auth.models import User
from rest_framework import status
from helmsman.tests import HelmsManServiceTestBase


# Create your tests here.
class ProjManManServiceTestBase(HelmsManServiceTestBase):

    def setUp(self):
        super().setUp()
        self.client.force_login(
            User.objects.get_or_create(username='projadmin', is_staff=True)[0])


class ProjectServiceTests(ProjManManServiceTestBase):

    PROJECT_DATA = {
        'name': 'GVL'
    }

    def _create_project(self):
        # create the object
        url = reverse('projman:projects-list')
        return self.client.post(url, self.PROJECT_DATA, format='json')

    def _list_project(self):
        # list existing objects
        url = reverse('projman:projects-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertDictContainsSubset(self.PROJECT_DATA, response.data['results'][0])
        return response.data['results'][0]['id']

    def _check_project_exists(self, project_id):
        # check it exists
        url = reverse('projman:projects-detail', args=[project_id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertDictContainsSubset(self.PROJECT_DATA, response.data)
        return response.data['id']

    def _delete_project(self, project_id):
        # delete the object
        url = reverse('projman:projects-detail', args=[project_id])
        return self.client.delete(url)

    def _check_no_projects_exist(self):
        # check it no longer exists
        url = reverse('projman:projects-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 0)

    def test_crud_project(self):
        """
        Ensure we can register a new project
        """
        response = self._create_project()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        project_id = self._list_project()
        # Assert that the originally created project id is the same as the one
        # returned by list
        self.assertEquals(response.data['id'], project_id)
        project_id = self._check_project_exists(project_id)
        response = self._delete_project(project_id)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT, response.data)
        self._check_no_projects_exist()

    def test_create_unauthorized(self):
        self.client.force_login(
            User.objects.get_or_create(username='projadminnoauth', is_staff=False)[0])
        response = self._create_project()
        self.assertEquals(response.status_code, 403, response.data)
        self._check_no_projects_exist()

    def test_list_unauthorized(self):
        self.client.force_login(
            User.objects.get_or_create(username='projadminnoauth', is_staff=False)[0])
        self._check_no_projects_exist()

    def test_delete_unauthorized(self):
        self._create_project()
        project_id_then = self._list_project()
        self.client.force_login(
            User.objects.get_or_create(username='projadminnoauth', is_staff=False)[0])
        response = self._delete_project(project_id_then)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)
        self.client.force_login(
            User.objects.get(username='projadmin'))
        project_id_now = self._list_project()
        assert project_id_now  # should still exist
        assert project_id_then == project_id_now  # should be the same project

    def test_can_view_shared_project(self):
        self._create_project()
        project_id_then = self._list_project()
        self.client.force_login(
            User.objects.get_or_create(username='notaprojadmin', is_staff=False)[0])
        project_id_now = self._list_project()
        assert project_id_now  # should be visible
        assert project_id_then == project_id_now  # should be the same project


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

    def _create_project(self):
        url = reverse('projman:projects-list')
        response = self.client.post(url, self.PROJECT_DATA, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return response.data['id']

    def _create_project_chart(self, project_id):
        url = reverse('projman:chart-list', args=[project_id])
        return self.client.post(url, self.CHART_DATA, format='json')

    def _list_project_chart(self, project_id):
        url = reverse('projman:chart-list', args=[project_id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertDictContainsSubset(self.PROJECT_DATA, response.data['results'][0]['project'])
        self.assertDictContainsSubset(self.CHART_DATA, response.data['results'][0])
        return response.data['results'][0]['id']

    def _check_project_chart_exists(self, project_id, chart_id):
        url = reverse('projman:chart-detail', args=[project_id, chart_id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertDictContainsSubset(self.PROJECT_DATA, response.data['project'])
        self.assertDictContainsSubset(self.CHART_DATA, response.data)
        return response.data['id']

    def _delete_project_chart(self, project_id, chart_id):
        url = reverse('projman:chart-detail', args=[project_id, chart_id])
        return self.client.delete(url)

    def _check_no_project_charts_exist(self, project_id):
        url = reverse('projman:chart-list', args=[project_id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 0)

    def _update_project_chart(self, project_id, chart_id):
        url = reverse('projman:chart-detail', args=[project_id, chart_id])
        response = self.client.get(url)
        chart = response.data
        chart['values']['hello'] = 'anotherworld'
        chart['values']['new_value'] = 'anothervalue'
        response = self.client.put(url, chart, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.data['id']

    def _check_project_chart_update(self, project_id, chart_id):
        url = reverse('projman:chart-detail', args=[project_id, chart_id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['values']['hello'], 'anotherworld')
        self.assertEqual(response.data['values']['new_value'], 'anothervalue')

    def _check_project_chart_reuse_values(self, project_id, chart_id):
        url = reverse('projman:chart-detail', args=[project_id, chart_id])
        response = self.client.get(url)
        chart = response.data
        chart['values']['new_value'] = 'anothervalue2'
        response = self.client.put(url, chart, format='json')

        url = reverse('projman:chart-detail', args=[project_id, chart_id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['values']['hello'], 'anotherworld')
        self.assertEqual(response.data['values']['new_value'], 'anothervalue2')

    def test_crud_project_chart(self):
        """
        Ensure we can register a new project
        """
        # create the parent project
        project_id = self._create_project()
        # create the project chart
        response = self._create_project_chart(project_id)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        # list existing objects
        chart_id = self._list_project_chart(project_id)
        # check it exists
        chart_id = self._check_project_chart_exists(project_id, chart_id)
        # Update chart
        self._update_project_chart(project_id, chart_id)
        # check update worked
        self._check_project_chart_update(project_id, chart_id)
        # check reusing values works
        self._check_project_chart_reuse_values(project_id, chart_id)
        # delete the object
        response = self._delete_project_chart(project_id, chart_id)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        # check it no longer exists
        self._check_no_project_charts_exist(project_id)

    def test_chart_create_unauthorized(self):
        project_id = self._create_project()
        self.client.force_login(
            User.objects.get_or_create(username='projadminnoauth', is_staff=False)[0])
        response = self._create_project_chart(project_id)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)
        self._check_no_project_charts_exist(project_id)

    def test_chart_delete_unauthorized(self):
        project_id = self._create_project()
        self._create_project_chart(project_id)
        chart_id_then = self._list_project_chart(project_id)
        self.client.force_login(
            User.objects.get_or_create(username='projadminnoauth', is_staff=False)[0])
        response = self._delete_project_chart(project_id, chart_id_then)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)
        self.client.force_login(
            User.objects.get(username='projadmin'))
        chart_id_now = self._list_project_chart(project_id)
        assert chart_id_now  # should still exist
        assert chart_id_then == chart_id_now  # should be the same chart

    def test_can_view_shared_chart(self):
        project_id = self._create_project()
        self._create_project_chart(project_id)
        chart_id_then = self._list_project_chart(project_id)
        self.client.force_login(
            User.objects.get_or_create(username='anotherprojadmin', is_staff=True)[0])
        chart_id_now = self._list_project_chart(project_id)
        assert chart_id_now  # should be visible
        assert chart_id_then == chart_id_now  # should be the same chart
