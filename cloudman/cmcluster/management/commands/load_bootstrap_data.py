import argparse
import base64
import json
from django.core.management.base import BaseCommand, CommandError
from djcloudbridge import models as cb_models
from cloudlaunch import models as cl_models


class Command(BaseCommand):
    help = 'Loads cloudman bootstrap data in base64 format. The bootstrap' \
           'data should contain cloud connection and credentials info for' \
           'the admin user'

    def add_arguments(self, parser):
        parser.add_argument('filename', type=argparse.FileType('r'))

    def handle(self, *args, **options):
        data = options['filename'].read()
        decoded_data = base64.b64decode(data).decode('utf-8')
        self.import_bootstrap_data(json.loads(decoded_data))

    @staticmethod
    def import_bootstrap_data(json_data):
        config = json_data.get('target_config')
        target = config.get('target')
        image = config.get('image')
        zone = target.get('target_zone')
        region = zone.get('region')
        cloud = zone.get('cloud')
        credentials = config.get('credentials')

        cloud_type = cloud.pop('resourcetype')
        if cloud_type == 'AWSCloud':
            cloud_model = cb_models.AWSCloud
            region_model = cb_models.AWSRegion
            credentials_model = cb_models.AWSCredentials
        elif cloud_type == 'AzureCloud':
            cloud_model = cb_models.AzureCloud
            region_model = cb_models.AzureRegion
            credentials_model = cb_models.AzureCredentials
        elif cloud_type == 'GCPCloud':
            cloud_model = cb_models.GCPCloud
            region_model = cb_models.GCPRegion
            credentials_model = cb_models.GCPCredentials
        elif cloud_type == 'OpenStackCloud':
            cloud_model = cb_models.OpenStackCloud
            region_model = cb_models.OpenStackRegion
            credentials_model = cb_models.OpenStackCredentials

        # create cloud
        cloud_id = cloud.pop('id')
        cloud_obj, _ = cloud_model.objects.get_or_create(
            id=cloud_id, defaults={**cloud})

        # create region
        region_id = region.pop('region_id')
        region['cloud'] = cloud_obj
        region_obj, _ = region_model.objects.get_or_create(
            region_id=region_id, defaults={**region})

        # create zone
        zone_id = zone.pop('zone_id')
        zone.pop('cloud')
        zone.pop('region')
        zone_obj, _ = cb_models.Zone.objects.get_or_create(
            region=region_obj, zone_id=zone_id, defaults={**zone})

        # create credentials and link to admin user
        credentials.pop('id', None)
        name = credentials.pop('name')
        credentials_model.objects.get_or_create(user_profile_id="admin",
                                                name=name,
                                                defaults={**credentials})

        # create image
        name = image.pop('name')
        image_obj, _ = cl_models.Image.objects.get_or_create(
            name=name, defaults={**image, "region": region_obj})

        # connect rancher app as target
        version = cl_models.ApplicationVersion.objects.filter(
            application='cm_rancher_kubernetes_plugin').first()
        target = cl_models.CloudDeploymentTarget.objects.filter(
            target_zone=zone_obj).first()
        cl_models.ApplicationVersionCloudConfig.objects.create(
            application_version=version, target=target, image=image_obj)
