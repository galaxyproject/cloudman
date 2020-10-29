import os

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from helmsman.api import HelmsManAPI, HMServiceContext, NamespaceExistsException
from helmsman.tests.client_mocker import ClientMocker

from projman import models as pm_models
from projman.api import ProjManAPI, PMServiceContext


class CommandsTestCase(TestCase):

    TEST_DATA_PATH = os.path.join(os.path.dirname(__file__), 'data')
    INITIAL_HELMSMAN_DATA = os.path.join(
        TEST_DATA_PATH, 'helmsman_config.yaml')
    INITIAL_PROJECT_DATA = os.path.join(
        TEST_DATA_PATH, 'projman_config.yaml')
    INITIAL_PROJECT_DATA_UPDATE = os.path.join(
        TEST_DATA_PATH, 'projman_config_update.yaml')

    def setUp(self):
        super().setUp()
        self.mock_client = ClientMocker(self)
        self.client.force_login(
            User.objects.get_or_create(username='admin', is_superuser=True)[0])

    def tearDown(self):
        self.client.logout()

    def test_projman_load_config_no_args(self):
        with self.assertRaisesRegex(CommandError, "required: config_file"):
            call_command('projman_load_config')

    def test_projman_load_config(self):
        call_command('helmsman_load_config', self.INITIAL_HELMSMAN_DATA)
        call_command('projman_load_config', self.INITIAL_PROJECT_DATA)
        project1 = pm_models.CMProject.objects.get(name='first')
        project2 = pm_models.CMProject.objects.get(name='second')
        self.assertEquals(project1.name, 'first')
        self.assertEquals(project1.owner.username, 'admin')
        self.assertEquals(project2.name, 'second')
        self.assertEquals(project2.owner.username, 'admin')
        admin = User.objects.filter(is_superuser=True).first()
        client = HelmsManAPI(HMServiceContext(user=admin))
        self.assertEquals(client.namespaces.get(project2.name).name, 'second')
        # Test error for default namespace
        with self.assertRaises(NamespaceExistsException):
            call_command("projman_create_project", "default")
        client.namespaces.delete(project1.name)
        client.namespaces.delete(project2.name)

    def test_projman_update_config(self):
        call_command('helmsman_load_config', self.INITIAL_HELMSMAN_DATA)
        call_command('projman_load_config', self.INITIAL_PROJECT_DATA)
        call_command('projman_load_config', self.INITIAL_PROJECT_DATA_UPDATE)
        projman_api = ProjManAPI(PMServiceContext(
            user=User.objects.get_or_create(username='admin', is_superuser=True)[0]))
        proj1 = projman_api.projects.find("first")
        chart1 = proj1.charts.find("galaxy")
        # should be unchanged since upgrade = false
        self.assertEqual(chart1.values['postgresql']['persistence']['storageClass'],
                         "ebs-provisioner")
        # should be updated since upgrade = true
        proj2 = projman_api.projects.find("second")
        chart2 = proj2.charts.find("galaxy")
        self.assertEqual(chart2.values['postgresql']['persistence']['storageClass'],
                         "updated-provisioner")

    def test_projman_context_update_by_release_name(self):
        call_command('helmsman_load_config', self.INITIAL_HELMSMAN_DATA)
        call_command('projman_load_config', self.INITIAL_PROJECT_DATA)
        projman_api = ProjManAPI(PMServiceContext(
            user=User.objects.get_or_create(username='admin', is_superuser=True)[0]))
        proj = projman_api.projects.find("second")
        chart = proj.charts.get("jup")
        self.assertEqual(chart.values['greeting'], "hello")
        call_command('projman_load_config', self.INITIAL_PROJECT_DATA_UPDATE)
        chart = proj.charts.get("jup")
        self.assertEqual(chart.values['greeting'], "world")
