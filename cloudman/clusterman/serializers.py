"""DRF serializers for the CloudMan Create API endpoints."""

from rest_framework import serializers
from cloudlaunch import serializers as cl_serializers
from djcloudbridge.drf_helpers import CustomHyperlinkedIdentityField
from .api import CloudManAPI
from rest_framework.exceptions import ValidationError


class CMClusterSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    name = serializers.CharField()
    cluster_type = serializers.CharField()
    connection_settings = serializers.DictField(write_only=True)
    nodes = CustomHyperlinkedIdentityField(view_name='node-list',
                                           lookup_field='cluster_id',
                                           lookup_url_kwarg='cluster_pk')

    def create(self, valid_data):
        return CloudManAPI.from_request(self.context['request']).clusters.create(
            valid_data.get('name'), valid_data.get('cluster_type'),
            valid_data.get('connection_settings'))


class CMClusterNodeSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    cluster = CMClusterSerializer(read_only=True)
    instance_type = serializers.CharField(write_only=True)
    deployment = cl_serializers.DeploymentSerializer(read_only=True)

    def create(self, valid_data):
        cluster_id = self.context['view'].kwargs.get("cluster_pk")
        cluster = CloudManAPI.from_request(self.context['request']).clusters.get(cluster_id)
        if not cluster:
            raise ValidationError("Specified cluster id: %s does not exist"
                                  % cluster_id)
        return cluster.nodes.create(valid_data.get('instance_type'))


class CMClusterAutoScalerSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    name = serializers.CharField(allow_blank=True)
    cluster = CMClusterSerializer(read_only=True)
    instance_type = serializers.CharField()
    zone_id = serializers.CharField()

    def create(self, valid_data):
        cluster_id = self.context['view'].kwargs.get("cluster_pk")
        cluster = CloudManAPI.from_request(self.context['request']).clusters.get(cluster_id)
        if not cluster:
            raise ValidationError("Specified cluster id: %s does not exist"
                                  % cluster_id)
        return cluster.autoscalers.create(valid_data.get('instance_type'),
                                          name=valid_data.get('name'),
                                          zone_id=valid_data.get('zone_id'))

