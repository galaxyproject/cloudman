"""HelmsMan Service API."""
import jsonmerge
import yaml

from django.contrib.auth.models import User

from rest_framework.exceptions import PermissionDenied

from clusterman.clients.kube_client import KubeClient

from . import models

from .clients.helm_client import HelmClient
from .clients.helm_client import HelmValueHandling

from .clients.jinja_client import JinjaClient


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
                    release.get("NAMESPACE"), release.get("NAME"), get_all=True)
            )
            for release in releases
        )
        return [c for c in charts if self.has_permissions('helmsman.view_chart', c)]

    def get(self, chart_id):
        charts = (c for c in self.list() if c.id == chart_id)
        chart = next(charts, None)
        self.check_permissions('helmsman.view_chart', chart)
        return chart

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

    def create(self, repo_name, chart_name, namespace,
               release_name=None, version=None, values=None,
               extra_values=None):
        self.check_permissions('helmsman.add_chart')
        client = HelmClient()
        existing_release = [
            r for r in client.releases.list(namespace)
            if chart_name == client.releases.parse_chart_name(r.get('CHART'))
        ]
        if existing_release:
            raise ChartExistsException(
                f"Chart {repo_name}/{chart_name} already installed in namespace {namespace}.")
        else:
            client.repositories.update()
            client.releases.create(f"{repo_name}/{chart_name}", namespace,
                                   release_name=release_name, version=version,
                                   values=values, extra_values=extra_values)
        return self._get_from_namespace(namespace, chart_name)

    def update(self, chart, values):
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
            value_handling=HelmValueHandling.REUSE)
        chart.values = jsonmerge.merge(chart.values, cur_vals)
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
        # Remap the returned django model's delete method to the API method
        # This is just a lazy alternative to writing an actual wrapper around
        # the django object.
        template.original_delete = template.delete
        template.delete = lambda: self.delete(template)
        return template

    def create(self, name, repo, chart, chart_version,
               context, macros, values):
        self.check_permissions('helmsman.add_template')
        obj = models.HMInstallTemplate.objects.create(
            name=name, repo=repo, chart=chart,
            chart_version=chart_version,
            context=context, macros=macros, values=values)
        template = self.to_api_object(obj)
        return template

    def get(self, name):
        obj = models.HMInstallTemplate.objects.get(name=name)
        self.check_permissions('helmsman.view_template', obj)
        return self.to_api_object(obj)

    def delete(self, template):
        if template:
            self.check_permissions('helmsman.delete_template', template)
            template.original_delete()

    def render_values(self, name, **context):
        template = self.get(name)
        self.check_permissions('helmsman.render_template', template)
        admin = User.objects.filter(is_superuser=True).first()
        client = JinjaClient()
        if not context:
            context = {}
        if yaml.safe_load(template.context):
            context.update(yaml.safe_load(template.context))
        return client.templates.render(template.macros,
                                       template.values,
                                       **context)

    def install(self, install_template, namespace,
                release_name=None, values=None, **context):
        self.check_permissions('helmsman.add_chart')
        template = self.get(install_template)
        default_values = yaml.safe_load(self.render_values(install_template, **context))
        admin = User.objects.filter(is_superuser=True).first()
        client = HelmsManAPI(HMServiceContext(user=admin))
        return client.charts.create(repo_name=template.repo,
                                    chart_name=template.chart,
                                    namespace=namespace,
                                    release_name=release_name,
                                    version=template.chart_version,
                                    values=default_values,
                                    extra_values=values)

    def list(self):
        return list(map(
            self.to_api_object,
            (tmpl for tmpl in models.HMInstallTemplate.objects.all()
             if self.has_permissions('helmsman.view_template', tmpl))))

    def find(self, name):
        try:
            obj = models.HMInstallTemplate.objects.get(name=name)
            if self.has_permissions('helmsman.view_template', obj):
                return self.to_api_object(obj)
            else:
                return None
        except models.HMInstallTemplate.DoesNotExist:
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
