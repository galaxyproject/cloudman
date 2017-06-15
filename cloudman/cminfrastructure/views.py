"""CloudMan Create views."""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from cminfrastructure import drf_helpers
from cminfrastructure import serializers
from .api import CMInfrastructureAPI


class InfrastructureView(APIView):
    """List kinds of available infrastructures."""

    def get(self, request, format=None):
        """Return available infrastructures."""
        # We only support cloud infrastructures for the time being
        response = {'url': request.build_absolute_uri('clouds')}
        return Response(response)


class CloudViewSet(drf_helpers.CustomModelViewSet):
    """Returns list of clouds currently registered with CloudMan."""

    permission_classes = (IsAuthenticated,)
    # Required for the Browsable API renderer to have a nice form.
    serializer_class = serializers.CMCloudSerializer

    def list_objects(self):
        """Get a list of all registered clouds."""
        return CMInfrastructureAPI().clouds.list()

    def get_object(self):
        """Get info about a specific cloud."""
        return CMInfrastructureAPI().clouds.get(self.kwargs["pk"])


class CloudNodeViewSet(drf_helpers.CustomModelViewSet):
    """
    Returns list of clouds currently registered with CloudMan.
    """
    permission_classes = (IsAuthenticated,)
    # Required for the Browsable API renderer to have a nice form.
    serializer_class = serializers.CMCloudNodeSerializer

    def list_objects(self):
        cloud = CMInfrastructureAPI().clouds.get(self.kwargs["cloud_pk"])
        if cloud:
            return cloud.nodes.list()
        else:
            return []

    def get_object(self):
        provider = view_helpers.get_cloud_provider(self)
        obj = provider.compute.images.get(self.kwargs["pk"])
        return obj
