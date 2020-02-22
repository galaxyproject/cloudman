"""CloudMan Create views."""
from django.contrib.auth.models import User

from rest_framework.authentication import SessionAuthentication, BasicAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework import viewsets, mixins

from djcloudbridge import drf_helpers
from . import serializers
from .api import CloudManAPI
from .api import CMServiceContext



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

    def perform_create(self, serializer):
        # first, check whether the current user has permissions to
        # autoscale
        cmapi = CloudManAPI.from_request(self.request)
        cmapi.check_permissions('autoscalers.can_autoscale')
        # If so, the remaining actions must be carried out as the admin user
        # since we must use cloud credentials from the admin profile.
        zone_name = serializer.validated_data.get(
            'commonLabels', {}).get('availability_zone')
        # TODO: This is brittle because it assumes the first superuser
        # found has cloud credentials. Instead, we could globally store
        # which admin account the autoscale user should impersonate.
        admin = User.objects.filter(is_superuser=True).first()
        cmapi = CloudManAPI(CMServiceContext(user=admin))
        cluster = cmapi.clusters.get(self.kwargs["cluster_pk"])
        if cluster:
            return cluster.scaleup(zone_name=zone_name)
        else:
            return None


class ClusterScaleDownSignalViewSet(CustomCreateOnlyModelViewSet):
    """
    Reads and updates AutoScaler fields
    Accepts GET, PUT, PATCH methods.
    """
    serializer_class = serializers.PrometheusWebHookSerializer
    permission_classes = (IsAuthenticated,)
    authentication_classes = [SessionAuthentication, BasicAuthentication]

    def perform_create(self, serializer):
        # first, check whether the current user has permissions to
        # autoscale
        cmapi = CloudManAPI.from_request(self.request)
        cmapi.check_permissions('autoscalers.can_autoscale')
        # If so, the remaining actions must be carried out as the admin user
        # since we must use cloud credentials from the admin profile.
        zone_name = serializer.validated_data.get(
            'commonLabels', {}).get('availability_zone')
        # TODO: This is brittle because it assumes the first superuser
        # found has cloud credentials. Instead, we could globally store
        # which admin account the autoscale user should impersonate.
        admin = User.objects.filter(is_superuser=True).first()
        cmapi = CloudManAPI(CMServiceContext(user=admin))
        cluster = cmapi.clusters.get(self.kwargs["cluster_pk"])
        if cluster:
            return cluster.scaledown(zone_name=zone_name)
        else:
            return None
