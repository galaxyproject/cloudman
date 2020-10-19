"""HelmsMan Service API."""
import jsonmerge
import jinja2
import yaml

from ansible.plugins.filter import ipaddr

from django.apps import apps
from django.db import IntegrityError
from django.db import transaction

from django.contrib.auth.models import User

from rest_framework.exceptions import PermissionDenied

from clusterman.clients.kube_client import KubeClient

from . import models

from .clients.helm_client import HelmClient
from .clients.helm_client import HelmValueHandling


class HelmsmanException(Exception):
    pass


class ChartExistsException(HelmsmanException):
    pass


class NamespaceNotFoundException(HelmsmanException):
    pass


class NamespaceExistsException(HelmsmanException):
    pass


class ChartNotFoundException(HelmsmanException):
    pass


class InstallTemplateExistsException(HelmsmanException):
    pass


class InstallTemplateNotFoundException(HelmsmanException):
    pass


class HMServiceContext(object):
    """
    A class to contain contextual information when processing a
    service request, such as the current user. A ServiceContext object
    must be passed in when creating a service.
    """

    def __init__(self, user):
        self._user = user

    @property
    def user(self):
        return self._user

    @classmethod
    def from_request(cls, request):
        # Construct and return an instance of CMServiceContext
        return cls(user=request.user)


class HelmsManService(object):
    """Marker interface for HelmsMan services"""
    def __init__(self, context):
        self._context = context

    @property
    def context(self):
        """
        Returns the currently associated service context.
        """
        return self._context

    def has_permissions(self, scopes, obj=None):
        if not isinstance(scopes, list):
            scope = [scopes]
        return self.context.user.has_perms(scope, obj)

    def check_permissions(self, scopes, obj=None):
        if not self.has_permissions(scopes, obj):
            self.raise_no_permissions(scopes)

    def raise_no_permissions(self, scopes):
        raise PermissionDenied(
            "Object does not exist or you do not have permissions to "
            "perform '%s'" % (scopes,))


class HelmsManAPI(HelmsManService):

    def __init__(self, context):
        super(HelmsManAPI, self).__init__(context)
        self._repo_svc = HMChartRepoService(context)
        self._chart_svc = HMChartService(context)
        self._namespace_svc = HMNamespaceService(context)
        self._templates_svc = HMInstallTemplateService(context)

    @classmethod
    def from_request(cls, request):
        context = HMServiceContext.from_request(request)
        return cls(context)

    @property
    def repositories(self):
        return self._repo_svc

    @property
    def charts(self):
        return self._chart_svc

    @property
    def namespaces(self):
        return self._namespace_svc

    @property
    def templates(self):
        return self._templates_svc


class HMNamespaceService(HelmsManService):

    def __init__(self, context):
        super(HMNamespaceService, self).__init__(context)

    def list(self):
        return [KubeNamespace(self, **namespace)
                for namespace in KubeClient().namespaces.list()
                if self.has_permissions('helmsman.view_namespace', namespace)]

    def get(self, namespace):
        namespaces = (n for n in self.list() if n.name == namespace)
        ns = next(namespaces, None)
        self.check_permissions('helmsman.view_chart', ns)
        return ns

    def create(self, namespace):
        self.check_permissions('helmsman.add_namespace')
        client = KubeClient()
        existing = self.get(namespace)
        if existing:
            raise NamespaceExistsException(
                f"Namespace '{namespace}' already exists.")
        else:
            client.namespaces.create(namespace)
        return self.get(namespace)

    def delete(self, namespace):
        self.check_permissions('helmsman.delete_namespace')
        client = KubeClient()
        existing = self.get(namespace)
        if not existing:
            raise NamespaceNotFoundException(
                f"Namespace {namespace} cannot be found.")
        else:
            client.namespaces.delete(namespace)


class HMChartRepoService(HelmsManService):

    def __init__(self, context):
        super(HMChartRepoService, self).__init__(context)

    def list(self):
        return []

    def get(self, cluster_id):
        return {}

    def create(self, name, cluster_type, connection_settings):
        raise NotImplementedError()

    def delete(self, cluster_id):
        raise NotImplementedError()


class HMChartService(HelmsManService):

    def __init__(self, context):
        super(HMChartService, self).__init__(context)

    def list(self, namespace=None):
        client = HelmClient()
        releases = client.releases.list(namespace)
        charts = (
            HelmChart(
                self,
                id=release.get('NAME'),
                name=client.releases.parse_chart_name(release.get('CHART')),
                namespace=release.get("NAMESPACE"),
                chart_version=client.releases.parse_chart_version(release.get('CHART')),
                revision=release.get("REVISION"),
                app_version=release.get("APP VERSION"),
                state=release.get("STATUS"),
                updated=release.get("UPDATED"),
                values=HelmClient().releases.get_values(
                    release.get("NAMESPACE"), release.get("NAME"), get_all=True),
                install_template=self._find_closest_install_template(
                    client.releases.parse_chart_name(release.get('CHART')))
            )
            for release in releases
        )
        return [c for c in charts if self.has_permissions('helmsman.view_chart', c)]

    def get(self, chart_id):
        charts = (c for c in self.list() if c.id == chart_id)
        chart = next(charts, None)
        self.check_permissions('helmsman.view_chart', chart)
        return chart

    def _find_closest_install_template(self, chart_name):
        client = HelmsManAPI(self.context)
        return client.templates.find(chart_name=chart_name)

    def _get_from_namespace(self, namespace, chart_name):
        matches = [c for c in self.list(namespace) if c.name == chart_name]
        if matches:
            return matches[0]
        else:
            return None

    def _find_repo_for_chart(self, chart):
        # We use a best guess because helm does not track which repository a chart
        # was installed from: https://github.com/helm/helm/issues/4256
        # So just return the first matching repo
        repos = HelmClient().repo_charts.find(
            name=chart.name, version=chart.chart_version)
        if repos:
            fullname = repos[0].get('NAME')
            return fullname.split("/")[0]
        else:
            return None

    def find(self, namespace, chart_name):
        client = HelmClient()
        existing_chart = [
            r for r in client.releases.list(namespace)
            if chart_name == client.releases.parse_chart_name(r.get('CHART'))
        ]
        return existing_chart[0] if existing_chart else None

    def create(self, repo_name, chart_name, namespace,
               release_name=None, version=None, values=None):
        self.check_permissions('helmsman.add_chart')
        client = HelmClient()
        existing_chart = self.find(namespace, chart_name)
        if existing_chart:
            raise ChartExistsException(
                f"Chart {repo_name}/{chart_name} already installed in namespace {namespace}.")
        else:
            client.repositories.update()
            client.releases.create(f"{repo_name}/{chart_name}", namespace,
                                   release_name=release_name, version=version,
                                   values=values)
        return self._get_from_namespace(namespace, chart_name)

    def update(self, chart, values, version=None):
        self.check_permissions('helmsman.change_chart', chart)
        # 1. Retrieve chart's current user-defined values
        cur_vals = HelmClient().releases.get_values(chart.namespace, chart.id, get_all=False)
        # 2. Deep merge the latest differences on top
        if cur_vals:
            cur_vals = jsonmerge.merge(cur_vals, values)
        else:
            cur_vals = values
        # 3. Guess which repo the chart came from
        repo_name = self._find_repo_for_chart(chart)
        if not repo_name:
            raise ChartNotFoundException(
                "Could not find chart: %s, version: %s in any repository" %
                (chart.name, chart.chart_version))
        # 4. Apply the updated config to the chart
        HelmClient().releases.update(
            chart.namespace, chart.id, "%s/%s" % (repo_name, chart.name), values=cur_vals,
            value_handling=HelmValueHandling.REUSE, version=version)
        chart.values = jsonmerge.merge(chart.values, cur_vals)
        chart.chart_version = version
        return chart

    def rollback(self, chart, revision=None):
        self.check_permissions('helmsman.change_chart', chart)
        # Roll back to immediately preceding revision if revision=None
        HelmClient().releases.rollback(chart.namespace, chart.id, revision)
        return self.get(chart.id)

    def delete(self, chart):
        self.check_permissions('helmsman.delete_chart', chart)
        HelmClient().releases.delete(chart.namespace, chart.id)


class HMInstallTemplateService(HelmsManService):

    def __init__(self, context):
        super(HMInstallTemplateService, self).__init__(context)

    def to_api_object(self, template):
        return HelmInstallTemplate(self, template)

    def create(self, name, repo, chart, chart_version=None,
               template=None, context=None, **kwargs):
        self.check_permissions('helmsman.add_install_template')
        try:
            with transaction.atomic():
                obj = models.HMInstallTemplate.objects.create(
                    name=name, repo=repo, chart=chart,
                    chart_version=chart_version,
                    template=template, context=context, **kwargs)
            install_template = self.to_api_object(obj)
            return install_template
        except IntegrityError as e:
            raise InstallTemplateExistsException(
                "Install template '%s' already exists" % name) from e

    def get(self, name):
        try:
            obj = models.HMInstallTemplate.objects.get(name=name)
        except models.HMInstallTemplate.DoesNotExist as e:
            raise InstallTemplateNotFoundException("Could not find install template '%s'" % name)
        self.check_permissions('helmsman.view_install_template', obj)
        return self.to_api_object(obj)

    def delete(self, template):
        if template:
            self.check_permissions('helmsman.delete_install_template', template)
            template_name = template.name if isinstance(template, HelmInstallTemplate) else template
            models.HMInstallTemplate.objects.filter(name=template_name).delete()

    def list(self):
        return list(map(
            self.to_api_object,
            (tmpl for tmpl in models.HMInstallTemplate.objects.all()
             if self.has_permissions('helmsman.view_install_template', tmpl))))

    def find(self, name=None, chart_name=None):
        search_terms = {'name': name, 'chart': chart_name}
        matches = list(models.HMInstallTemplate.objects.filter(
            **{k: v for k, v in search_terms.items() if v}))
        if matches:
            if self.has_permissions('helmsman.view_install_template', matches[0]):
                return self.to_api_object(matches[0])
        return None


class HelmsManResource(object):
    """Marker interface for HelmsMan resources"""
    def __init__(self, service):
        self.service = service

    def delete(self):
        raise NotImplementedError()


class HelmChart(HelmsManResource):

    def __init__(self, service, id, name, namespace, **kwargs):
        super().__init__(service)
        self.id = id
        self.name = name
        self.namespace = namespace
        self.display_name = self.name.title()
        self.chart_version = kwargs.get('chart_version')
        self.revision = kwargs.get('revision')
        self.app_version = kwargs.get('app_version')
        self.state = kwargs.get('state')
        self.updated = kwargs.get('updated')
        self.access_address = '/%s/' % name
        self.values = kwargs.get('values') or {}
        self.install_template = kwargs.get('install_template')

    def delete(self):
        self.service.delete(self)


class KubeNamespace(HelmsManResource):

    def __init__(self, service, **kwargs):
        super().__init__(service)
        self.name = kwargs.get('NAME')
        self.status = kwargs.get('STATUS')
        self.age = kwargs.get('AGE')

    def delete(self):
        self.service.delete(self.name)


class HelmInstallTemplate(HelmsManResource):

    def __init__(self, service, template_obj):
        super().__init__(service)
        self.template_obj = template_obj

    @property
    def name(self):
        return self.template_obj.name

    @property
    def repo(self):
        return self.template_obj.repo

    @property
    def chart(self):
        return self.template_obj.chart

    @property
    def chart_version(self):
        return self.template_obj.chart_version

    @property
    def template(self):
        return self.template_obj.template

    @property
    def context(self):
        if self.template_obj.context:
            return yaml.safe_load(self.template_obj.context)
        else:
            return {}

    @property
    def display_name(self):
        return self.template_obj.display_name or self.template_obj.name.title()

    @property
    def summary(self):
        return self.template_obj.summary

    @property
    def description(self):
        return self.template_obj.description

    @property
    def maintainers(self):
        return self.template_obj.maintainers

    @property
    def info_url(self):
        return self.template_obj.info_url

    @property
    def icon_url(self):
        return self.template_obj.icon_url

    @property
    def screenshot_url(self):
        return self.template_obj.screenshot_url

    def render_values(self, context):
        if not context:
            context = {}
        default_context = self.context or {}
        context.update(default_context)
        jinja2_env = self._get_jinja2_env()
        tmpl = jinja2_env.from_string(
            "\n".join([apps.get_app_config('helmsman').default_macros,
                       self.template or '']))
        return tmpl.render({"context": context})

    @staticmethod
    def _get_jinja2_env():
        env = jinja2.Environment(loader=jinja2.BaseLoader)
        f = ipaddr.FilterModule()
        env.filters.update(f.filters())
        return env

    def install(self, namespace, release_name=None, values=None,
                context=None):
        default_values = yaml.safe_load(
            self.render_values(context or {}))
        admin = User.objects.filter(is_superuser=True).first()
        client = HelmsManAPI(HMServiceContext(user=admin))
        return client.charts.create(repo_name=self.repo,
                                    chart_name=self.chart,
                                    namespace=namespace,
                                    release_name=release_name,
                                    version=self.chart_version,
                                    values=[default_values, values or {}])

    def delete(self):
        self.service.delete(self.name)
