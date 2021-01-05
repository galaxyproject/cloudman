import argparse
import base64
import json
import yaml
from django.core.management.base import BaseCommand, CommandError
from djcloudbridge import models as cb_models
from cloudlaunch import models as cl_models


class Command(BaseCommand):
    help = 'Loads initial cloud data in base64 format. The cloud ' \
           'data should contain cloud connection and credentials info for' \
           'the admin user'

    def add_arguments(self, parser):
        parser.add_argument('filename', type=argparse.FileType('r'))
        parser.add_argument('--format', required=False, default="yaml",
                            choices=['yaml', 'json', 'base64yaml'],
                            help='Format that the data is encoded in')

    def handle(self, *args, **options):
        data = options['filename'].read()
        format = options['format']
        if format == "base64yaml":
            # Pad data: https://gist.github.com/perrygeo/ee7c65bb1541ff6ac770
            data = base64.b64decode(data + "===").decode('utf-8')

        if format == "json":
            decoded_data = json.loads(data)
        elif format == "yaml" or format == "base64yaml":
            decoded_data = yaml.safe_load(data)
        self.load_cloud_data(decoded_data)

    @staticmethod
    def load_cloud_data(json_data):
        config = json_data.get('cloud_config')
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
            credentials['gcp_service_creds_dict'] = json.dumps(
                credentials['gcp_service_creds_dict'])
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
        region.pop('resourcetype', None)
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
        if credentials:
            credentials.pop('id', None)
            name = credentials.pop('name', 'default')
            cloud_id = credentials.pop('cloud_id', cloud_id)
            credentials.pop('default', None)
            credentials_model.objects.get_or_create(user_profile_id="admin",
                                                    name=name,
                                                    cloud_id=cloud_id,
                                                    default=True,
                                                    defaults={**credentials})

        # create image
        name = image.pop('name')
        image_obj, _ = cl_models.Image.objects.get_or_create(
            name=name, defaults={**image, "region": region_obj})

        # connect rke app as target
        version = cl_models.ApplicationVersion.objects.filter(
            application='cm_rke_kubernetes_plugin').first()
        target = cl_models.CloudDeploymentTarget.objects.filter(
            target_zone=zone_obj).first()
        cl_models.ApplicationVersionCloudConfig.objects.get_or_create(
            application_version=version, target=target, image=image_obj)
