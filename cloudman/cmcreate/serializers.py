"""DRF serializers for the CloudMan Create API endpoints."""

from rest_framework import serializers


class VMSerializer(serializers.Serializer):
    """A serializer for a virtual machine resource."""

    id = serializers.CharField()
    name = serializers.CharField()
