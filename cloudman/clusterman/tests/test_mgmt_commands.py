from io import StringIO
import os

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import transaction
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
        TEST_DATA_PATH, 'initial_cluster_data_aws.yaml')
    INITIAL_CLUSTER_DATA_AZURE = os.path.join(
        TEST_DATA_PATH, 'initial_cluster_data_azure.yaml')
    INITIAL_CLUSTER_DATA_GCP = os.path.join(
        TEST_DATA_PATH, 'initial_cluster_data_gcp.yaml')
    INITIAL_CLUSTER_DATA_OPENSTACK = os.path.join(
        TEST_DATA_PATH, 'initial_cluster_data_openstack.yaml')

    def setUp(self):
        super().setUp()
        self.client.force_login(
            User.objects.get_or_create(username='admin', is_superuser=True)[0])

    def test_import_cloud_data_no_args(self):
        with self.assertRaisesRegex(CommandError, "required: filename"):
            call_command('import_cloud_data')

    def test_import_cloud_data_aws(self):
        call_command('import_cloud_data', self.INITIAL_CLUSTER_DATA)
        zone_obj = cb_models.Zone.objects.get(
            region__cloud__id='aws', region__region_id='amazon-us-east',
            zone_id='default')
        self.assertEquals(zone_obj.name, 'us-east1')

    def test_import_cloud_data_azure(self):
        call_command('import_cloud_data', self.INITIAL_CLUSTER_DATA_AZURE)
        zone_obj = cb_models.Zone.objects.get(
            region__cloud__id='azure', region__region_id='azure-us-east',
            zone_id='default')
        self.assertEquals(zone_obj.name, 'us-east1')

    def test_import_cloud_data_gcp(self):
        call_command('import_cloud_data', self.INITIAL_CLUSTER_DATA_GCP)
        zone_obj = cb_models.Zone.objects.get(
            region__cloud__id='gcp', region__region_id='gcp-us-east',
            zone_id='default')
        self.assertEquals(zone_obj.name, 'us-east1')

    def test_import_cloud_data_openstack(self):
        call_command('import_cloud_data', self.INITIAL_CLUSTER_DATA_OPENSTACK)
        zone_obj = cb_models.Zone.objects.get(
            region__cloud__id='openstack', region__region_id='melbourne',
            zone_id='default')
        self.assertEquals(zone_obj.name, 'melbourne')

    def test_create_cluster_no_args(self):
        with self.assertRaisesRegex(
                CommandError, "required: name, cluster_type, settings_file"):
            call_command('create_cluster')

    def test_create_cluster(self):
        call_command('create_cluster', 'test_cluster', 'KUBE_RANCHER', self.INITIAL_CLUSTER_DATA)
        cluster = cm_models.CMCluster.objects.get(name='test_cluster')
        self.assertEquals(cluster.cluster_type, 'KUBE_RANCHER')

    def test_create_cluster_existing(self):
        with transaction.atomic():
            call_command('create_cluster', 'test_cluster', 'KUBE_RANCHER', self.INITIAL_CLUSTER_DATA)
        self.assertEqual(cm_models.CMCluster.objects.all().count(), 1)
        with transaction.atomic():
            call_command('create_cluster', 'test_cluster', 'KUBE_RANCHER', self.INITIAL_CLUSTER_DATA)
        self.assertEqual(cm_models.CMCluster.objects.all().count(), 1)


class CreateAutoScaleUserCommandTestCase(TestCase):

    def setUp(self):
        self.client.force_login(
            User.objects.get_or_create(username='admin', is_superuser=True)[0])

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

    def test_create_autoscale_user_does_not_clobber_existing(self):
        User.objects.create_user(username="hello", password="world")
        call_command('create_autoscale_user', "--username", "hello",
                     "--password", "overwrite")
        # Password should remain unchanged
        self.assertTrue(self.client.login(username="hello", password="world"))

    def test_create_autoscale_user_with_impersonate(self):
        out = StringIO()
        call_command('create_autoscale_user', "--username", "hello",
                     "--password", "overwrite", "--impersonate_account", "admin",
                     stdout=out)
        self.assertIn("created successfully", out.getvalue())

    def test_create_autoscale_user_with_non_existent_impersonate(self):
        out = StringIO()
        call_command('create_autoscale_user', "--username", "hello",
                     "--password", "overwrite", "--impersonate_account", "non_existent",
                     stdout=out)
        self.assertNotIn("created successfully", out.getvalue())
