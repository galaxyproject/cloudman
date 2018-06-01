"""DRF serializers for the CloudMan Create API endpoints."""

from rest_framework import serializers
from .api import HelmsManAPI


class HMChartRepoSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    name = serializers.CharField()


class HMChartSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    name = serializers.CharField()
    access_address = serializers.CharField()
    schema = serializers.DictField()
    config = serializers.DictField()
    repo = HMChartRepoSerializer(read_only=True)

    def create(self, valid_data):
        return HelmsManAPI(self.context['request']).charts.create(
            valid_data.get('name'), valid_data.get('config'),
            valid_data.get('schema'))

    def update(self, chart, validated_data):
        chart.get('config', {}).update(validated_data.get('config'))
        return chart
