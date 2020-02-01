"""DRF serializers for the CloudMan Create API endpoints."""

from rest_framework import serializers
from .api import HelmsManAPI


class HMChartRepoSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    name = serializers.CharField()


class HMChartSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    name = serializers.CharField()
    display_name = serializers.CharField(read_only=True)
    chart_version = serializers.CharField(allow_blank=True, required=False)
    revision = serializers.IntegerField(allow_null=True, required=False)
    app_version = serializers.CharField(read_only=True)
    namespace = serializers.CharField()
    state = serializers.CharField(allow_blank=True, read_only=False, required=False)
    updated = serializers.CharField(read_only=True)
    access_address = serializers.CharField(read_only=True)
    values = serializers.DictField()
    repo = HMChartRepoSerializer(read_only=True)
    repo_name = serializers.CharField(write_only=True, allow_blank=True, required=False)

    def create(self, valid_data):
        return HelmsManAPI.from_request(self.context['request']).charts.create(
            valid_data.get('repo_name', 'cloudve'), valid_data.get('name'),
            valid_data.get('namespace'), valid_data.get('release_name'),
            valid_data.get('chart_version'), valid_data.get('values'))

    def update(self, chart, validated_data):
        if validated_data.get('state') == "rollback":
            return (HelmsManAPI.from_request(self.context['request']).charts
                    .rollback(chart))
        return HelmsManAPI.from_request(self.context['request']).charts.update(
            chart, validated_data.get('values'))


class HMNamespaceSerializer(serializers.Serializer):
    name = serializers.CharField()
    status = serializers.CharField(allow_blank=True)
    age = serializers.CharField(allow_blank=True)

    def create(self, valid_data):
        return HelmsManAPI.from_request(self.context['request']
                                        ).namespaces.create(
                                            valid_data.get('name'))

    def delete(self, valid_data):
        return HelmsManAPI.from_request(self.context['request']
                                        ).namespaces.delete(
                                            valid_data.get('name'))
