"""DRF serializers for the CloudMan Create API endpoints."""

from rest_framework import serializers
from cloudbridge.cloud.factory import CloudProviderFactory

from .api import CMInfrastructureAPI
from .drf_helpers import CustomHyperlinkedIdentityField


class CMCloudSerializer(serializers.Serializer):
    cloud_id = serializers.CharField(read_only=True)
    name = serializers.CharField()
    provider_id = serializers.ChoiceField(
        choices=[p for p in CloudProviderFactory().list_providers()])
    provider_config = serializers.DictField()
    nodes = CustomHyperlinkedIdentityField(view_name='node-list',
                                           lookup_field='cloud_id',
                                           lookup_url_kwarg='cloud_pk')

    def create(self, valid_data):
        return CMInfrastructureAPI().clouds.create(
            valid_data.get('name'), valid_data.get('provider_id'),
            valid_data.get('provider_config'))


class CMCloudNodeSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    cloud_id = serializers.CharField(read_only=True)
    name = serializers.CharField()
    instance_type = serializers.CharField()

    def create(self, valid_data):
        cloud_id = self.context['view'].kwargs.get("cloud_pk")
        return CMInfrastructureAPI().clouds.get(cloud_id).nodes.create(
            valid_data.get('name'), valid_data.get('instance_type'))


class CMCloudNodeTaskSerializer(serializers.Serializer):
    task_id = serializers.CharField(read_only=True)
    cloud_id = serializers.CharField(read_only=True)
    node_id = serializers.CharField(read_only=True)
    task_type = serializers.CharField()
    task_params = serializers.DictField(required=False, allow_null=True)
    status = serializers.CharField(read_only=True)
    message = serializers.CharField(read_only=True)
    stack_trace = serializers.CharField(read_only=True)

    def create(self, valid_data):
        cloud_id = self.context['view'].kwargs.get("cloud_pk")
        node_id = self.context['view'].kwargs.get("node_pk")
        cloud = CMInfrastructureAPI().clouds.get(cloud_id)
        node = cloud.nodes.get(node_id)
        return node.tasks.create(valid_data.get('task_type'),
                                 valid_data.get('task_params'))
