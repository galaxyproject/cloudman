import os

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from .client_mocker import ClientMocker
from ..clients.helm_client import HelmClient

from helmsman import models as hm_models
from helmsman.api import NamespaceNotFoundException
from helmsman.api import HelmsManAPI, HMServiceContext


class CommandsTestCase(TestCase):

    TEST_DATA_PATH = os.path.join(os.path.dirname(__file__), 'data')
    INITIAL_HELMSMAN_DATA = os.path.join(
        TEST_DATA_PATH, 'helmsman_config.yaml')
    INITIAL_HELMSMAN_DATA_UPDATE = os.path.join(
        TEST_DATA_PATH, 'helmsman_config_update.yaml')

    def setUp(self):
        super().setUp()
        self.mock_client = ClientMocker(self)
        self.client.force_login(
            User.objects.get_or_create(username='admin', is_superuser=True)[0])

    def tearDown(self):
        self.client.logout()

    def test_helmsman_load_config_no_args(self):
        with self.assertRaisesRegex(CommandError, "required: config_file"):
            call_command('helmsman_load_config')

    def test_helmsman_load_config(self):
        call_command('helmsman_load_config', self.INITIAL_HELMSMAN_DATA)
        client = HelmClient()
        repos = client.repositories.list()
        for repo in repos:
            self.assertIn(repo.get('NAME'), ["stable", "cloudve", "jupyterhub"])
        template = hm_models.HMInstallTemplate.objects.get(name='dummy')
        self.assertEqual(template.summary, "dummy chart")
        releases = client.releases.list("default")
        for rel in releases:
            self.assertIn(rel.get('CHART'),
                          ["cloudlaunch-0.2.0", "galaxy-1.0.0"])

    def test_add_chart_no_namespace(self):
        with self.assertRaises(NamespaceNotFoundException):
            call_command("add_chart", "cloudve/galaxy", namespace="new")

    def test_helmsman_install_duplicate_template(self):
        call_command('helmsman_load_config', self.INITIAL_HELMSMAN_DATA)
        call_command('helmsman_load_config', self.INITIAL_HELMSMAN_DATA)

    def test_helmsman_load_config_template_registry(self):
        call_command('helmsman_load_config', self.INITIAL_HELMSMAN_DATA)
        template = hm_models.HMInstallTemplate.objects.get(name='terminalman')
        self.assertEqual(template.chart, "terminalman")
        self.assertIn("starting_dir", template.context)

    def test_update_install_template(self):
        call_command('helmsman_load_config', self.INITIAL_HELMSMAN_DATA)
        call_command('helmsman_load_config', self.INITIAL_HELMSMAN_DATA_UPDATE)
        # dummy template should be unchanged since upgrade = false
        template = hm_models.HMInstallTemplate.objects.get(name='dummy')
        self.assertEqual(template.display_name, "dummy")
        # another dummy template should be updated since upgrade was specified
        template = hm_models.HMInstallTemplate.objects.get(name='anotherdummy')
        self.assertEqual(template.chart_version, "4.0.0")

    def test_update_chart(self):
        call_command('helmsman_load_config', self.INITIAL_HELMSMAN_DATA)
        call_command('helmsman_load_config', self.INITIAL_HELMSMAN_DATA_UPDATE)
        helm_api = HelmsManAPI(HMServiceContext(
            user=User.objects.get_or_create(username='admin', is_superuser=True)[0]))
        chart = helm_api.charts.find("anotherdummy", "anotherdummy")
        # version should be unchanged since upgrade = false
        self.assertEqual(chart.chart_version, "2.0.0")
        # dummy chart should be updated since upgrade = true
        chart = helm_api.charts.find("dummy", "dummy")
        self.assertEqual(chart.chart_version, "2.0.0")
