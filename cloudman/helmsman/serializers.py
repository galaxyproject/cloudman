"""DRF serializers for the CloudMan Create API endpoints."""

from rest_framework import serializers
from .api import HelmsManAPI


class HMChartRepoSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    name = serializers.CharField()


class HMChartSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    display_name = serializers.CharField(read_only=True)
    chart_version = serializers.CharField(read_only=True)
    app_version = serializers.CharField(read_only=True)
    project = serializers.CharField(read_only=True)
    state = serializers.CharField(read_only=True)
    updated = serializers.CharField(read_only=True)
    access_address = serializers.CharField(read_only=True)
    values = serializers.DictField()
    repo = HMChartRepoSerializer(read_only=True)

    def create(self, valid_data):
        return HelmsManAPI(request=self.context['request']).charts.create(
            valid_data.get('name'), valid_data.get('values'))

    def update(self, chart, validated_data):
        if validated_data.get('state') == "rollback":
            return (HelmsManAPI(request=self.context['request']).charts
                    .rollback(chart))
        return HelmsManAPI(request=self.context['request']).charts.update(
            chart, validated_data.get('values'))
