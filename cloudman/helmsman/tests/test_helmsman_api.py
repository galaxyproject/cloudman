from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .client_mocker import ClientMocker

from helmsman.api import ChartExistsException
from helmsman.api import InstallTemplateExistsException
from helmsman.api import NamespaceExistsException


# Create your tests here.
class HelmsManServiceTestBase(APITestCase):

    def setUp(self):
        self.mock_client = ClientMocker(self)
        self.client.force_login(
            User.objects.get_or_create(username='admin', is_superuser=True)[0])


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

    def _create_chart(self):
        # create the object
        url = reverse('helmsman:charts-list')
        return self.client.post(url, self.CHART_DATA, format='json')

    def _list_chart(self):
        # list existing objects
        url = reverse('helmsman:charts-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertDictContainsSubset(self.CHART_DATA, response.data['results'][1])
        return response.data['results'][1]['id']

    def _check_chart_exists(self, chart_id):
        # check it exists
        url = reverse('helmsman:charts-detail', args=[chart_id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertDictContainsSubset(self.CHART_DATA, response.data)
        return response.data['id']

    def _delete_chart(self, chart_id):
        # delete the object
        url = reverse('helmsman:charts-detail', args=[chart_id])
        return self.client.delete(url)

    def _check_no_extra_charts_exist(self):
        # check it no longer exists
        url = reverse('helmsman:charts-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)

    def _check_no_charts_exist(self):
        # check it no longer exists
        url = reverse('helmsman:charts-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 0)

    def test_crud_chart(self):
        """
        Ensure we can register a new chart with cloudman.
        Only staff are allowed to directly manipulate charts.
        Other users must go through a project in projman.
        """
        response = self._create_chart()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED,
                         response.data)

        # create duplicate object
        with self.assertRaises(ChartExistsException):
            self._create_chart()

        chart_id = self._list_chart()
        # Assert that the originally created chart id is the same as the one
        # returned by list
        self.assertEquals(response.data['id'], chart_id)

        chart_id = self._check_chart_exists(chart_id)
        response = self._delete_chart(chart_id)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT, response.data)
        self._check_no_extra_charts_exist()

    def test_create_unauthorized(self):
        self.client.force_login(
            User.objects.get_or_create(username='chartnoauth', is_staff=False)[0])
        response = self._create_chart()
        self.assertEquals(response.status_code, 403, response.data)
        self._check_no_charts_exist()

    def test_list_unauthorized(self):
        self.client.force_login(
            User.objects.get_or_create(username='chartnoauth', is_staff=False)[0])
        self._check_no_charts_exist()

    def test_delete_unauthorized(self):
        self._create_chart()
        chart_id_then = self._list_chart()
        self.client.force_login(
            User.objects.get_or_create(username='chartnoauth', is_staff=False)[0])
        response = self._delete_chart(chart_id_then)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)
        self.client.force_login(
            User.objects.get(username='admin'))
        chart_id_now = self._list_chart()
        assert chart_id_now  # should still exist
        assert chart_id_then == chart_id_now  # should be the same chart
        response = self._delete_chart(chart_id_now)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT, response.data)
        self._check_no_extra_charts_exist()


class NamespaceServiceTests(HelmsManServiceTestBase):

    NAMESPACE_DATA = {
        'name': 'newnamespace',
        'status': 'Active',
        'age': '1d'
    }

    def _create_namespace(self):
        # create the object
        url = reverse('helmsman:namespaces-list')
        return self.client.post(url, self.NAMESPACE_DATA, format='json')

    def _list_namespace(self):
        # list existing objects
        url = reverse('helmsman:namespaces-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertDictContainsSubset(self.NAMESPACE_DATA, response.data['results'][1])
        return response.data['results'][1]['name']

    def _check_namespace_exists(self, ns_id):
        # check it exists
        url = reverse('helmsman:namespaces-detail', args=[ns_id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertDictContainsSubset(self.NAMESPACE_DATA, response.data)
        return response.data['name']

    def _delete_namespace(self, ns_id):
        # delete the object
        url = reverse('helmsman:namespaces-detail', args=[ns_id])
        return self.client.delete(url)

    def _check_no_extra_namespaces_exist(self):
        # check it no longer exists
        url = reverse('helmsman:namespaces-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)

    def _check_no_namespaces_exist(self):
        # check it no longer exists
        url = reverse('helmsman:namespaces-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 0)

    def test_crud_namespace(self):
        """
        Ensure we can register a new cluster with cloudman.
        """
        response = self._create_namespace()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED,
                         response.data)

        # create duplicate object
        with self.assertRaises(NamespaceExistsException):
            self._create_namespace()

        ns_id = self._list_namespace()
        # Assert that the originally created ns id is the same as the one
        # returned by list
        self.assertEquals(response.data['name'], ns_id)

        ns_id = self._check_namespace_exists(ns_id)
        response = self._delete_namespace(ns_id)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT, response.data)
        self._check_no_extra_namespaces_exist()

    def test_create_unauthorized(self):
        self.client.force_login(
            User.objects.get_or_create(username='nsnoauth', is_staff=False)[0])
        response = self._create_namespace()
        self.assertEquals(response.status_code, 403, response.data)
        self._check_no_namespaces_exist()

    def test_list_unauthorized(self):
        self.client.force_login(
            User.objects.get_or_create(username='nsnoauth', is_staff=False)[0])
        self._check_no_namespaces_exist()

    def test_delete_unauthorized(self):
        self._create_namespace()
        ns_id_then = self._list_namespace()
        self.client.force_login(
            User.objects.get_or_create(username='nsnoauth', is_staff=False)[0])
        response = self._delete_namespace(ns_id_then)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)
        self.client.force_login(
            User.objects.get(username='admin'))
        ns_id_now = self._list_namespace()
        assert ns_id_now  # should still exist
        assert ns_id_then == ns_id_now  # should be the same chart
        response = self._delete_namespace(ns_id_now)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT, response.data)
        self._check_no_extra_namespaces_exist()


class InstallTemplateServiceTests(HelmsManServiceTestBase):

    INSTALL_TEMPLATE_DATA = {
        'name': 'galaxy',
        'repo': 'galaxyproject',
        'chart': 'galaxy',
        'chart_version': '',
        'summary': 'Web-based data analysis platform',
        'description': 'A more detailed description',
        'display_name': 'Galaxy',
        'maintainers': 'Galaxy Team',
        'info_url': 'https://usegalaxy.org',
        'icon_url': 'https://usegalaxy.org/some_icon.png',
        'context': {'project': 'test'},
        'template': """ingress:
              enabled: true
              path: '{{context.project.access_path}}/galaxy'
            hub:
              baseUrl: '{{context.project.access_path}}/galaxy'
            proxy:
              secretToken: '{{random_alphanumeric(65)}}'"""
    }

    def _create_install_template(self):
        # create the object
        url = reverse('helmsman:install_templates-list')
        return self.client.post(url, self.INSTALL_TEMPLATE_DATA, format='json')

    def _list_install_templates(self):
        # list existing objects
        url = reverse('helmsman:install_templates-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertDictContainsSubset(self.INSTALL_TEMPLATE_DATA, response.data['results'][0])
        return response.data['results'][0]['name']

    def _check_install_template_exists(self, ns_id):
        # check it exists
        url = reverse('helmsman:install_templates-detail', args=[ns_id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertDictContainsSubset(self.INSTALL_TEMPLATE_DATA, response.data)
        return response.data['name']

    def _delete_install_template(self, ns_id):
        url = reverse('helmsman:install_templates-detail', args=[ns_id])
        return self.client.delete(url)

    def _check_no_install_templates_exist(self):
        url = reverse('helmsman:install_templates-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 0)

    def test_crud_install_template(self):
        response = self._create_install_template()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED,
                         response.data)

        obj_id = self._list_install_templates()
        # Assert that the originally created obj id is the same as the one
        # returned by list
        self.assertEquals(response.data['name'], obj_id)

        # create duplicate object
        with self.assertRaises(InstallTemplateExistsException):
            self._create_install_template()

        obj_id = self._check_install_template_exists(obj_id)
        response = self._delete_install_template(obj_id)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT, response.data)
        self._check_no_install_templates_exist()


    def test_create_unauthorized(self):
        self.client.force_login(
            User.objects.get_or_create(username='nsnoauth', is_staff=False)[0])
        response = self._create_install_template()
        self.assertEquals(response.status_code, 403, response.data)
        self._check_no_install_templates_exist()

    def test_list_unauthorized(self):
        self.client.force_login(
            User.objects.get_or_create(username='nsnoauth', is_staff=False)[0])
        self._check_no_install_templates_exist()

    def test_delete_unauthorized(self):
        self._create_install_template()
        obj_id_then = self._list_install_templates()
        self.client.force_login(
            User.objects.get_or_create(username='nsnoauth', is_staff=False)[0])
        response = self._delete_install_template(obj_id_then)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)
        self.client.force_login(
            User.objects.get(username='admin'))
        obj_id_now = self._list_install_templates()
        assert obj_id_now  # should still exist
        assert obj_id_then == obj_id_now  # should be the same chart
        response = self._delete_install_template(obj_id_now)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT, response.data)
        self._check_no_install_templates_exist()
