"""DRF serializers for the CloudMan Create API endpoints."""

from rest_framework import serializers
from .api import HelmsManAPI


class HMInstallTemplateSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    name = serializers.CharField()
    repo = serializers.SlugField()
    chart = serializers.SlugField()
    chart_version = serializers.CharField(allow_blank=True, required=False)
    template = serializers.CharField()
    context = serializers.DictField(required=False)
    display_name = serializers.CharField(allow_blank=True, required=False)
    summary = serializers.CharField(allow_blank=True, required=False)
    description = serializers.CharField(allow_blank=True, required=False)
    maintainers = serializers.CharField(allow_blank=True, required=False)
    info_url = serializers.CharField(allow_blank=True, required=False)
    icon_url = serializers.CharField(allow_blank=True, required=False)
    screenshot_url = serializers.CharField(allow_blank=True, required=False)

    def create(self, valid_data):
        return HelmsManAPI.from_request(
            self.context['request']).templates.create(
                name=valid_data.get('name'),
                repo=valid_data.get('repo'),
                chart=valid_data.get('chart'),
                chart_version=valid_data.get('chart_version'),
                template=valid_data.get('template'),
                context=valid_data.get('context'),
                display_name=valid_data.get('display_name'),
                summary=valid_data.get('summary'),
                description=valid_data.get('description'),
                maintainers=valid_data.get('maintainers'),
                info_url=valid_data.get('info_url'),
                icon_url=valid_data.get('icon_url'),
                screenshot_url=valid_data.get('screenshot_url'))

    def render_values(self, valid_data):
        return HelmsManAPI.from_request(self.context['request']
                                        ).templates.render_values(
                                            valid_data.get('name'),
                                            **valid_data)

    def delete(self, valid_data):
        return HelmsManAPI.from_request(self.context['request']
                                        ).templates.delete(
                                            valid_data.get('name'))


class HMChartRepoSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    name = serializers.CharField()


class HMChartSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    name = serializers.CharField(required=False)
    display_name = serializers.CharField(read_only=True)
    chart_version = serializers.CharField(allow_blank=True, required=False)
    revision = serializers.IntegerField(allow_null=True, required=False)
    app_version = serializers.CharField(read_only=True)
    namespace = serializers.CharField()
    state = serializers.CharField(allow_blank=True, read_only=False, required=False)
    updated = serializers.CharField(read_only=True)
    access_address = serializers.CharField(read_only=True)
    values = serializers.DictField(required=False)
    repo = HMChartRepoSerializer(read_only=True)
    repo_name = serializers.CharField(write_only=True, allow_blank=True, required=False)
    install_template = HMInstallTemplateSerializer(read_only=True, required=False)
    use_install_template = serializers.CharField(write_only=True, allow_blank=True, required=False)

    def create(self, valid_data):
        return HelmsManAPI.from_request(self.context['request']).charts.create(
            valid_data.get('repo_name'), valid_data.get('name'),
            valid_data.get('namespace'), valid_data.get('release_name'),
            valid_data.get('chart_version'), valid_data.get('values'))

    def update(self, chart, validated_data):
        if validated_data.get('state') == "rollback":
            return (HelmsManAPI.from_request(self.context['request']).charts
                    .rollback(chart))
        return HelmsManAPI.from_request(self.context['request']).charts.update(
            chart, validated_data.get('values'), version=validated_data.get('chart_version'))


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
