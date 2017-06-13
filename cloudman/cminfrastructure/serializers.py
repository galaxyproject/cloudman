"""DRF serializers for the CloudMan Create API endpoints."""

from rest_framework import serializers
from cloudbridge.cloud.factory import CloudProviderFactory

from .api import CMInfrastructureAPI
from .drf_helpers import CustomHyperlinkedIdentityField


class CMCloudSerializer(serializers.Serializer):
    cloud_id = serializers.CharField(read_only=True)
    name = serializers.CharField()
    cloud_type = serializers.ChoiceField(
        choices=[p for p in CloudProviderFactory().list_providers()])
    nodes = CustomHyperlinkedIdentityField(view_name='nodes-list',
                                           lookup_field='cloud_id',
                                           lookup_url_kwarg='cloud_pk')

    def create(self, valid_data):
        return CMInfrastructureAPI().clouds.create(
            valid_data.get('name'), valid_data.get('cloud_type'))


class CMCloudNodeSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    cloud_id = serializers.CharField(read_only=True)
    name = serializers.CharField()
    instance_type = serializers.CharField()

    def create(self, valid_data):
        cloud_id = self.context['view'].kwargs.get("cloud_pk")
        return CMInfrastructureAPI().clouds.get(cloud_id).nodes.create(
            valid_data.get('name'), valid_data.get('instance_type'))
