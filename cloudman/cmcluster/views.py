"""CloudMan Create views."""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from djcloudbridge import drf_helpers
from . import serializers
from .api import CloudManAPI


class CloudManAPIView(APIView):
    """List Cloudman API endpoints"""

    def get(self, request, format=None):
        """Return available clusters."""
        response = {'url': request.build_absolute_uri('clusters')}
        return Response(response)


class ClusterViewSet(drf_helpers.CustomModelViewSet):
    """Returns list of clusters managed by CloudMan."""

    permission_classes = (IsAuthenticated,)
    # Required for the Browsable API renderer to have a nice form.
    serializer_class = serializers.CMClusterSerializer

    def list_objects(self):
        """Get a list of all registered clusters."""
        return CloudManAPI(self.request).clusters.list()

    def get_object(self):
        """Get info about a specific cloud."""
        return CloudManAPI(self.request).clusters.get(self.kwargs["pk"])


class ClusterNodeViewSet(drf_helpers.CustomModelViewSet):
    """
    Returns a list of nodes currently registered with CloudMan.
    """
    permission_classes = (IsAuthenticated,)
    # Required for the Browsable API renderer to have a nice form.
    serializer_class = serializers.CMClusterNodeSerializer

    def list_objects(self):
        cluster = CloudManAPI(self.request).clusters.get(self.kwargs["cluster_pk"])
        if cluster:
            return cluster.nodes.list()
        else:
            return []

    def get_object(self):
        cluster = CloudManAPI(self.request).clusters.get(self.kwargs["cluster_pk"])
        if cluster:
            return cluster.nodes.get(self.kwargs["pk"])
        else:
            return None
