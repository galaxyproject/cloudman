from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from djcloudbridge import drf_helpers
from . import serializers
from .api import HelmsManAPI


class HelmsManAPIView(APIView):
    """List Helmsman API endpoints"""

    def get(self, request, format=None):
        """Return available charts."""
        response = {'repositories': request.build_absolute_uri('repositories'),
                    'charts': request.build_absolute_uri('charts')}
        return Response(response)


class ChartRepoViewSet(drf_helpers.CustomModelViewSet):
    """Returns list of repositories managed by CloudMan."""

    permission_classes = (IsAuthenticated,)
    # Required for the Browsable API renderer to have a nice form.
    serializer_class = serializers.HMChartRepoSerializer

    def list_objects(self):
        """Get a list of all registered repository."""
        return HelmsManAPI(self.request).repositories.list()

    def get_object(self):
        """Get info about a specific repository."""
        return HelmsManAPI(self.request).repositories.get(self.kwargs["pk"])


class ChartViewSet(drf_helpers.CustomModelViewSet):
    """Returns list of charts managed by CloudMan."""

    permission_classes = (IsAuthenticated,)
    # Required for the Browsable API renderer to have a nice form.
    serializer_class = serializers.HMChartSerializer

    def list_objects(self):
        """Get a list of all registered charts."""
        return HelmsManAPI(self.request).charts.list()

    def get_object(self):
        """Get info about a specific chart."""
        return HelmsManAPI(self.request).charts.get(self.kwargs["pk"])
