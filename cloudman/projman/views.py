"""ProjMan Create views."""
from rest_framework.views import APIView
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from djcloudbridge import drf_helpers
from . import serializers
from .api import ProjManAPI


class ProjManAPIView(APIView):
    """List ProjMan API endpoints"""

    def get(self, request, format=None):
        """Return available clusters."""
        response = {'url': request.build_absolute_uri('projects')}
        return Response(response)


class ProjectViewSet(drf_helpers.CustomModelViewSet):
    """Returns list of projects managed by ProjMan."""

    permission_classes = (IsAuthenticated,)
    # Required for the Browsable API renderer to have a nice form.
    serializer_class = serializers.PMProjectSerializer

    def list_objects(self):
        """Get a list of all registered projects."""
        return ProjManAPI.from_request(self.request).projects.list()

    def get_object(self):
        """Get info about a specific project."""
        return ProjManAPI.from_request(self.request).projects.get(
            self.kwargs["pk"])


class ProjectChartViewSet(drf_helpers.CustomModelViewSet):
    """
    Returns a list of charts belonging to a project.
    """
    permission_classes = (IsAuthenticated,)
    # Required for the Browsable API renderer to have a nice form.
    serializer_class = serializers.PMProjectChartSerializer

    def list_objects(self):
        try:
            project = ProjManAPI.from_request(self.request).projects.get(
                self.kwargs["project_pk"])
        except PermissionDenied:
            project = None
        if project:
            return project.charts.list()
        else:
            return []

    def get_object(self):
        project = ProjManAPI.from_request(self.request).projects.get(
            self.kwargs["project_pk"])
        if project:
            return project.charts.get(self.kwargs["pk"])
        else:
            return None
