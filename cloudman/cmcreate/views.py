"""CloudMan Create views."""
from rest_framework.views import APIView
from rest_framework.response import Response


class InfrastructureView(APIView):
    """List kinds of available infrastructures."""

    def get(self, request, format=None):
        """Return available infrastructures."""
        # We only support cloud infrastructures for the time being
        response = {'url': request.build_absolute_uri('clouds')}
        return Response(response)


class VMViewSet(APIView):
    """Interactions with virtual machine resource."""

    def get(self, request, format=None):
        """Return available VMs."""
        print("In VMViewSet")
        return Response("VMViewSet")
