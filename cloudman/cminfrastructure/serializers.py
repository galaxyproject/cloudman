"""DRF serializers for the CloudMan Create API endpoints."""

from rest_framework import serializers
from cloudbridge.cloud.factory import CloudProviderFactory

from .api import CMInfrastructureAPI
from .drf_helpers import CustomHyperlinkedIdentityField


class AWSSerializer(serializers.Serializer):

    ec2_region_name = serializers.CharField()
    ec2_region_endpoint = serializers.CharField()
    ec2_conn_path = serializers.CharField()
    ec2_is_secure = serializers.CharField()
    ec2_port = serializers.CharField()
    s3_host = serializers.CharField()
    s3_conn_path = serializers.CharField()
    s3_is_secure = serializers.CharField()
    s3_port = serializers.CharField()
    s3_port = serializers.CharField()

    aws_access_key = serializers.CharField()
    secret_key = serializers.CharField(
        style={'input_type': 'password'},
        write_only=True,
        required=False)


class OpenStackSerializer(serializers.Serializer):

    username = serializers.CharField()
    project_name = serializers.CharField()
    auth_url = serializers.CharField()
    region_name = serializers.CharField()
    identity_api_version = serializers.CharField()
    project_domain_name = serializers.CharField()
    user_domain_name = serializers.CharField()

    password = serializers.CharField(
        style={'input_type': 'password'},
        write_only=True,
        required=False)


class CMCloudSerializer(serializers.Serializer):
    cloud_id = serializers.CharField(read_only=True)
    name = serializers.CharField()
    provider_id = serializers.ChoiceField(
        choices=[p for p in CloudProviderFactory().list_providers()])
    nodes = CustomHyperlinkedIdentityField(view_name='nodes-list',
                                           lookup_field='cloud_id',
                                           lookup_url_kwarg='cloud_pk')

    # serializer relations for each known provider_ids
    aws = AWSSerializer(source='*')
    openstack = OpenStackSerializer(source='*')

    def create(self, valid_data):
        return CMInfrastructureAPI().clouds.create(
            valid_data.get('name'), valid_data.get('provider_id'),
            valid_data.get('provider_settings'))


class CMCloudNodeSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    cloud_id = serializers.CharField(read_only=True)
    name = serializers.CharField()
    instance_type = serializers.CharField()

    def create(self, valid_data):
        cloud_id = self.context['view'].kwargs.get("cloud_pk")
        return CMInfrastructureAPI().clouds.get(cloud_id).nodes.create(
            valid_data.get('name'), valid_data.get('instance_type'))
