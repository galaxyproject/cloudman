from io import StringIO
import os
from unittest.mock import patch
from unittest.mock import PropertyMock

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from djcloudbridge import models as cb_models
from clusterman import models as cm_models


TEST_DATA_PATH = os.path.join(os.path.dirname(__file__), 'data')


def load_kube_config():
    kube_config_path = os.path.join(TEST_DATA_PATH, 'kube_config.yaml')
    with open(kube_config_path) as f:
        return f.read()


class ClusterCommandTestCase(TestCase):

    INITIAL_CLUSTER_DATA = os.path.join(
        TEST_DATA_PATH, 'initial_cluster_data.yaml')

    def setUp(self):
        super().setUp()
        self.patcher = patch('clusterman.cluster_templates.CMRancherTemplate.fetch_kube_config',
                             new_callable=PropertyMock,
                             return_value=load_kube_config)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.client.force_login(
            User.objects.get_or_create(username='admin', is_superuser=True)[0])

    def tearDown(self):
        self.client.logout()

    def test_import_cloud_data_no_args(self):
        with self.assertRaisesRegex(CommandError, "required: filename"):
            call_command('import_cloud_data')

    def test_import_cloud_data(self):
        call_command('import_cloud_data', self.INITIAL_CLUSTER_DATA)
        zone_obj = cb_models.Zone.objects.get(
            region__cloud__id='aws', region__region_id='amazon-us-east',
            zone_id='default')
        self.assertEquals(zone_obj.name, 'us-east1')

    def test_create_cluster_no_args(self):
        with self.assertRaisesRegex(
                CommandError, "required: name, cluster_type, settings_file"):
            call_command('create_cluster')

    def test_create_cluster(self):
        call_command('create_cluster', 'test_cluster', 'KUBE_RANCHER', self.INITIAL_CLUSTER_DATA)
        cluster = cm_models.CMCluster.objects.get(name='test_cluster')
        self.assertEquals(cluster.cluster_type, 'KUBE_RANCHER')


class CreateAutoScaleUserCommandTestCase(TestCase):

    def test_create_autoscale_user_no_args(self):
        call_command('create_autoscale_user')
        self.assertTrue(User.objects.get(username='autoscaleuser'))

    def test_create_autoscale_user(self):
        call_command('create_autoscale_user', "--username", "testautoscale",
                     "--password", "hello")
        user = User.objects.get(username='testautoscale')
        self.assertEquals(user.username, "testautoscale")
        self.assertTrue(self.client.login(username="testautoscale", password="hello"))

    def test_create_autoscale_user_existing(self):
        out = StringIO()
        call_command('create_autoscale_user', "--username", "testautoscale2",
                     "--password", "hello", stdout=out)
        self.assertIn("created successfully", out.getvalue())
        out = StringIO()
        call_command('create_autoscale_user', "--username", "testautoscale2",
                     "--password", "hello", stdout=out)
        self.assertIn("already exists", out.getvalue())

    def test_create_autoscale_does_not_clobber_existing(self):
        User.objects.create_user(username="hello", password="world")
        call_command('create_autoscale_user', "--username", "hello",
                     "--password", "overwrite")
        # Password should remain unchanged
        self.assertTrue(self.client.login(username="hello", password="world"))
