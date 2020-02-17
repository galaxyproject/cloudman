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
    vm_type = serializers.CharField(write_only=True)
    deployment = cl_serializers.DeploymentSerializer(read_only=True)

    def create(self, valid_data):
        cluster_id = self.context['view'].kwargs.get("cluster_pk")
        cluster = CloudManAPI.from_request(self.context['request']).clusters.get(cluster_id)
        if not cluster:
            raise ValidationError("Specified cluster id: %s does not exist"
                                  % cluster_id)
        return cluster.nodes.create(valid_data.get('vm_type'))


class CMClusterAutoScalerSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    name = serializers.CharField(allow_blank=True)
    cluster = CMClusterSerializer(read_only=True)
    vm_type = serializers.CharField()
    zone_id = serializers.CharField()
    min_nodes = serializers.IntegerField(min_value=0, allow_null=True,
                                         required=False)
    max_nodes = serializers.IntegerField(min_value=1, max_value=5000,
                                         allow_null=True, required=False)

    def create(self, valid_data):
        cluster_id = self.context['view'].kwargs.get("cluster_pk")
        cluster = CloudManAPI.from_request(self.context['request']).clusters.get(cluster_id)
        if not cluster:
            raise ValidationError("Specified cluster id: %s does not exist"
                                  % cluster_id)
        return cluster.autoscalers.create(valid_data.get('vm_type'),
                                          name=valid_data.get('name'),
                                          zone_id=valid_data.get('zone_id'))


# xref: https://prometheus.io/docs/alerting/configuration/#webhook_config
class PrometheusAlertSerializer(serializers.Serializer):
    status = serializers.CharField(allow_blank=True)
    labels = serializers.DictField(required=False)
    annotations = serializers.DictField(required=False)
    startsAt = serializers.CharField(allow_blank=True)
    endsAt = serializers.CharField(allow_blank=True)
    generatorURL = serializers.CharField(allow_blank=True)


# xref: https://prometheus.io/docs/alerting/configuration/#webhook_config
class PrometheusWebHookSerializer(serializers.Serializer):
    version = serializers.CharField()
    groupKey = serializers.CharField(allow_blank=True)
    receiver = serializers.CharField(allow_blank=True)
    groupLabels = serializers.DictField(required=False)
    commonLabels = serializers.DictField(required=False)
    commonAnnotations = serializers.DictField(required=False)
    externalURL = serializers.CharField(allow_blank=True)
    alerts = serializers.ListField(child=PrometheusAlertSerializer(),
                                   allow_empty=True, required=False)

    def create(self, valid_data):
        cluster_id = self.context['view'].kwargs.get("cluster_pk")
        cluster = CloudManAPI.from_request(self.context['request']).clusters.get(cluster_id)
        if not cluster:
            raise ValidationError("Specified cluster id: %s does not exist"
                                  % cluster_id)
        return cluster.nodes.create(valid_data.get('vm_type'))
