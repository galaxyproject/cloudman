"""CloudMan Create views."""
from django.contrib.auth.models import User

from rest_framework.authentication import SessionAuthentication, BasicAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework import viewsets, mixins

from djcloudbridge import drf_helpers
from . import serializers
from .api import CloudManAPI
from .api import CMServiceContext
from .models import GlobalSettings


class ClusterViewSet(drf_helpers.CustomModelViewSet):
    """Returns list of clusters managed by CloudMan."""

    permission_classes = (IsAuthenticated,)
    # Required for the Browsable API renderer to have a nice form.
    serializer_class = serializers.CMClusterSerializer

    def list_objects(self):
        """Get a list of all registered clusters."""
        return CloudManAPI.from_request(self.request).clusters.list()

    def get_object(self):
        """Get info about a specific cloud."""
        return CloudManAPI.from_request(self.request).clusters.get(
            self.kwargs["pk"])


class ClusterNodeViewSet(drf_helpers.CustomModelViewSet):
    """
    Returns a list of nodes currently registered with CloudMan.
    """
    permission_classes = (IsAuthenticated,)
    # Required for the Browsable API renderer to have a nice form.
    serializer_class = serializers.CMClusterNodeSerializer

    def list_objects(self):
        cluster = CloudManAPI.from_request(self.request).clusters.get(
            self.kwargs["cluster_pk"])
        if cluster:
            return cluster.nodes.list()
        else:
            return []

    def get_object(self):
        cluster = CloudManAPI.from_request(self.request).clusters.get(
            self.kwargs["cluster_pk"])
        if cluster:
            return cluster.nodes.get(self.kwargs["pk"])
        else:
            return None


class ClusterAutoScalerViewSet(drf_helpers.CustomModelViewSet):
    """
    Returns a list of autoscalers currently registered with CloudMan.
    """
    permission_classes = (IsAuthenticated,)
    # Required for the Browsable API renderer to have a nice form.
    serializer_class = serializers.CMClusterAutoScalerSerializer

    def list_objects(self):
        cluster = CloudManAPI.from_request(self.request).clusters.get(
            self.kwargs["cluster_pk"])
        if cluster:
            return cluster.autoscalers.list()
        else:
            return []

    def get_object(self):
        cluster = CloudManAPI.from_request(self.request).clusters.get(
            self.kwargs["cluster_pk"])
        if cluster:
            return cluster.autoscalers.get(self.kwargs["pk"])
        else:
            return None


class CustomCreateOnlyModelViewSet(drf_helpers.CustomNonModelObjectMixin,
                                   mixins.CreateModelMixin,
                                   viewsets.GenericViewSet):
    pass


class ClusterScaleUpSignalViewSet(CustomCreateOnlyModelViewSet):
    """
    Reads and updates AutoScaler fields
    Accepts GET, PUT, PATCH methods.
    """
    serializer_class = serializers.PrometheusWebHookSerializer
    permission_classes = (IsAuthenticated,)
    authentication_classes = [SessionAuthentication, BasicAuthentication]

    def _process_alert(self, alert):
        labels = {}
        zone_name = alert.get('labels', {}).get('availability_zone')
        if zone_name:
            labels['availability_zone'] = zone_name

        vcpus = float(alert.get('annotations', {}).get('cpus') or 0)
        if vcpus:
            labels['min_vcpus'] = vcpus

        ram = float(alert.get('annotations', {}).get('memory') or 0) / 1024 / 1024 / 1024
        if ram:
            labels['min_ram'] = ram

        scaling_group = alert.get('labels', {}).get(
            'label_usegalaxy_org_cm_autoscaling_group')
        if scaling_group:
            labels['usegalaxy.org/cm_autoscaling_group'] = scaling_group

        impersonate = (User.objects.filter(
            username=GlobalSettings().settings.autoscale_impersonate).first()
                       or User.objects.filter(is_superuser=True).first())
        cmapi = CloudManAPI(CMServiceContext(user=impersonate))
        cluster = cmapi.clusters.get(self.kwargs["cluster_pk"])
        if cluster:
            return cluster.scaleup(labels=labels)
        else:
            return None

    def perform_create(self, serializer):
        # first, check whether the current user has permissions to
        # autoscale
        cmapi = CloudManAPI.from_request(self.request)
        cmapi.check_permissions('autoscalers.can_autoscale')
        # If so, the remaining actions must be carried out as an impersonated user
        # whose profile contains the relevant cloud credentials, usually an admin

        alerts = serializer.validated_data.get('alerts', [])

        # pick only one alert per scaling group
        alerts_per_group = {}
        for alert in alerts:
            scaling_group = alert.get('labels', {}).get(
                'label_usegalaxy_org_cm_autoscaling_group')
            if scaling_group not in alerts_per_group:
                alerts_per_group[scaling_group] = alert

        # dispatch scale up signal for each alert
        for alert in alerts_per_group.values():
            self._process_alert(alert)


class ClusterScaleDownSignalViewSet(CustomCreateOnlyModelViewSet):
    """
    Reads and updates AutoScaler fields
    Accepts GET, PUT, PATCH methods.
    """
    serializer_class = serializers.PrometheusWebHookSerializer
    permission_classes = (IsAuthenticated,)
    authentication_classes = [SessionAuthentication, BasicAuthentication]

    def _process_alert(self, alert):
        labels = {}
        zone_name = alert.get('labels', {}).get('availability_zone')
        if zone_name:
            labels['availability_zone'] = zone_name

        node_name = alert.get('labels', {}).get(
            'label_usegalaxy_org_cm_node_name')
        if node_name:
            labels['usegalaxy.org/cm_node_name'] = node_name

        scaling_group = alert.get('labels', {}).get(
            'label_usegalaxy_org_cm_autoscaling_group')
        if scaling_group:
            labels['usegalaxy.org/cm_autoscaling_group'] = scaling_group

        impersonate = (User.objects.filter(
            username=GlobalSettings().settings.autoscale_impersonate).first()
                       or User.objects.filter(is_superuser=True).first())
        cmapi = CloudManAPI(CMServiceContext(user=impersonate))
        cluster = cmapi.clusters.get(self.kwargs["cluster_pk"])
        if cluster:
            return cluster.scaledown(labels=labels)
        else:
            return None

    def perform_create(self, serializer):
        # first, check whether the current user has permissions to
        # autoscale
        print(f"Scale down signal received...")
        cmapi = CloudManAPI.from_request(self.request)
        cmapi.check_permissions('autoscalers.can_autoscale')
        # If so, the remaining actions must be carried out as an impersonated user
        # whose profile contains the relevant cloud credentials, usually an admin

        alerts = serializer.validated_data.get('alerts', [])

        # pick only one alert per scaling group
        alerts_per_group = {}
        for alert in alerts:
            scaling_group = alert.get('labels', {}).get(
                'label_usegalaxy_org_cm_autoscaling_group')
            if scaling_group not in alerts_per_group:
                alerts_per_group[scaling_group] = alert

        # dispatch scale down signal for each alert
        for alert in alerts_per_group.values():
            self._process_alert(alert)
