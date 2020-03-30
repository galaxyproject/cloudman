"""DRF serializers for the CloudMan Create API endpoints."""

from rest_framework import serializers
from rest_framework import status
from rest_framework.exceptions import ValidationError

from cloudlaunch import serializers as cl_serializers
from djcloudbridge import models as cb_models
from djcloudbridge.drf_helpers import CustomHyperlinkedIdentityField

from .api import CloudManAPI
from .exceptions import CMDuplicateNameException


class CMClusterSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    name = serializers.CharField()
    cluster_type = serializers.CharField()
    connection_settings = serializers.DictField(write_only=True, required=False)
    default_vm_type = serializers.CharField(read_only=True)
    default_zone = cl_serializers.DeploymentZoneSerializer(read_only=True)
    autoscale = serializers.BooleanField(required=False, initial=True, default=True)
    nodes = CustomHyperlinkedIdentityField(view_name='node-list',
                                           lookup_field='cluster_id',
                                           lookup_url_kwarg='cluster_pk')

    def create(self, valid_data):
        try:
            cmapi = CloudManAPI.from_request(self.context['request'])
            return cmapi.clusters.create(
                valid_data.get('name'), valid_data.get('cluster_type'),
                valid_data.get('connection_settings'),
                autoscale=valid_data.get('autoscale'))
        except CMDuplicateNameException as e:
            raise ValidationError(detail=str(e))

    def update(self, instance, valid_data):
        instance.name = valid_data.get('name') or instance.name
        instance.autoscale = valid_data.get('autoscale')
        return CloudManAPI.from_request(
            self.context['request']).clusters.update(instance)


class CMClusterNodeSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    cluster = CMClusterSerializer(read_only=True)
    vm_type = serializers.CharField(write_only=True)
    deployment = cl_serializers.DeploymentSerializer(read_only=True)
    autoscaler = serializers.PrimaryKeyRelatedField(read_only=True)

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
    zone = serializers.PrimaryKeyRelatedField(queryset=cb_models.Zone.objects.all())
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
                                          zone=valid_data.get('zone'),
                                          min_nodes=valid_data.get('min_nodes'),
                                          max_nodes=valid_data.get('max_nodes'))

    def update(self, instance, valid_data):
        cluster_id = self.context['view'].kwargs.get("cluster_pk")
        cluster = CloudManAPI.from_request(self.context['request']).clusters.get(cluster_id)
        instance.name = valid_data.get('name') or instance.name
        instance.vm_type = valid_data.get('vm_type') or instance.vm_type
        instance.min_nodes = (instance.min_nodes if valid_data.get('min_nodes') is None
                              else valid_data.get('min_nodes'))
        instance.max_nodes = (instance.max_nodes if valid_data.get('max_nodes') is None
                              else valid_data.get('max_nodes'))
        instance.zone = valid_data.get('zone') or instance.zone
        return cluster.autoscalers.update(instance)


# xref: https://prometheus.io/docs/alerting/configuration/#webhook_config
class PrometheusAlertSerializer(serializers.Serializer):
    status = serializers.CharField(allow_blank=True, required=False)
    labels = serializers.DictField(required=False)
    annotations = serializers.DictField(required=False)
    startsAt = serializers.CharField(allow_blank=True, required=False)
    endsAt = serializers.CharField(allow_blank=True, required=False)
    generatorURL = serializers.CharField(allow_blank=True, required=False)


# xref: https://prometheus.io/docs/alerting/configuration/#webhook_config
class PrometheusWebHookSerializer(serializers.Serializer):
    version = serializers.CharField()
    groupKey = serializers.CharField(allow_blank=True, required=False)
    receiver = serializers.CharField(allow_blank=True, required=False)
    groupLabels = serializers.DictField(required=False)
    commonLabels = serializers.DictField(required=False)
    commonAnnotations = serializers.DictField(required=False)
    externalURL = serializers.CharField(allow_blank=True, required=False)
    alerts = serializers.ListField(child=PrometheusAlertSerializer(),
                                   allow_empty=True, required=False)
