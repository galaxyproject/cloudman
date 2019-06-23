"""DRF serializers for the CloudMan Create API endpoints."""

from rest_framework import serializers
from cloudlaunch import serializers as cl_serializers
from helmsman import serializers as helmsman_serializers
from .api import ProjManAPI
from rest_framework.exceptions import ValidationError


class PMProjectSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    name = serializers.CharField()

    def create(self, valid_data):
        return ProjManAPI.from_request(self.context['request']).projects.create(
            valid_data.get('name'))


class PMProjectChartSerializer(helmsman_serializers.HMChartSerializer):
    project = PMProjectSerializer()

    class Meta:
        exclude = ('namespace', )

    def create(self, valid_data):
        project_id = self.context['view'].kwargs.get("project_pk")
        project = ProjManAPI.from_request(self.context['request']).projects.get(project_id)
        if not project:
            raise ValidationError("Specified project id: %s does not exist"
                                  % project_id)
        return project.charts.create(
            valid_data.get('repo_name', 'cloudve'), valid_data.get('name'),
            valid_data.get('release_name'), valid_data.get('chart_version'),
            valid_data.get('values'))
