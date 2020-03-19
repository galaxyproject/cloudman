"""DRF serializers for the CloudMan Create API endpoints."""

from rest_framework import serializers
from djcloudbridge import serializers as dj_serializers
from helmsman import serializers as helmsman_serializers
from .api import ProjManAPI
from rest_framework.exceptions import ValidationError


class PMProjectSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    name = serializers.CharField()
    namespace = serializers.CharField(read_only=True)
    permissions = serializers.SerializerMethodField()

    def get_permissions(self, project):
        """
        Implementation of permissions field
        """
        user = self.context['view'].request.user
        return {
            'change_project': user.has_perm('projman.change_project', project),
            'delete_project': user.has_perm('projman.delete_project', project)
        }

    def create(self, valid_data):
        return ProjManAPI.from_request(self.context['request']).projects.create(
            valid_data.get('name'))


class PMProjectChartSerializer(helmsman_serializers.HMChartSerializer):
    # remove the inherited field
    namespace = None
    project = PMProjectSerializer(read_only=True)
    permissions = serializers.SerializerMethodField()

    def get_permissions(self, chart):
        """
        Implementation of permissions field
        """
        user = self.context['view'].request.user
        return {
            'change_chart': user.has_perm('projman.change_chart', chart),
            'delete_chart': user.has_perm('projman.delete_chart', chart)
        }

    def create(self, valid_data):
        project_id = self.context['view'].kwargs.get("project_pk")
        project = ProjManAPI.from_request(self.context['request']).projects.get(project_id)
        if not project:
            raise ValidationError("Specified project id: %s does not exist"
                                  % project_id)
        return project.charts.create(
            valid_data.get('repo_name'), valid_data.get('name'),
            valid_data.get('release_name'), valid_data.get('version'),
            valid_data.get('values'))

    def update(self, chart, validated_data):
        project_id = self.context['view'].kwargs.get("project_pk")
        project = ProjManAPI.from_request(self.context['request']).projects.get(project_id)
        if not project:
            raise ValidationError("Specified project id: %s does not exist"
                                  % project_id)
        if validated_data.get('state') == "rollback":
            return project.charts.rollback(chart)
        else:
            return project.charts.update(chart, validated_data.get("values"))


class UserSerializer(dj_serializers.UserDetailsSerializer):
    permissions = serializers.SerializerMethodField()

    def get_permissions(self, user_obj):
        return {
            'is_admin': user_obj.is_staff
        }

    class Meta(dj_serializers.UserDetailsSerializer.Meta):
        fields = dj_serializers.UserDetailsSerializer.Meta.fields + ('permissions',)
