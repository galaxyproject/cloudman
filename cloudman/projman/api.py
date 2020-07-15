"""ProjMan Service API."""
import base64

from django.contrib.auth.models import User
from django.template.defaultfilters import slugify

from . import models
from clusterman.clients.kube_client import KubeClient
from helmsman.api import HelmsManAPI, HMServiceContext
from helmsman.api import NamespaceExistsException
from rest_framework.exceptions import PermissionDenied


class PMServiceContext(object):
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
        # Construct and return an instance of PMServiceContext
        return cls(user=request.user)


class PMService(object):
    """Marker interface for ProjMan services"""
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

    def _get_helmsman_api(self):
        admin = User.objects.filter(is_superuser=True).first()
        return HelmsManAPI(HMServiceContext(user=admin))


class ProjManAPI(PMService):

    def __init__(self, context):
        super(ProjManAPI, self).__init__(context)
        self._projects = PMProjectService(context)

    @classmethod
    def from_request(cls, request):
        context = PMServiceContext.from_request(request)
        return cls(context)

    @property
    def projects(self):
        return self._projects


class PMProjectService(PMService):

    def __init__(self, context):
        super(PMProjectService, self).__init__(context)

    def to_api_object(self, project):
        # Remap the returned django model's delete method to the API method
        # This is just a lazy alternative to writing an actual wrapper around
        # the django object.
        project.delete = lambda: self.delete(project.id)
        return self.add_child_services(project)

    def add_child_services(self, project):
        project.service = self
        project.charts = PMProjectChartService(self.context, project)
        return project

    def list(self):
        return list(map(
            self.to_api_object,
            (proj for proj in models.CMProject.objects.all()
             if self.has_permissions('projman.view_project', proj))))

    def get(self, project_id):
        obj = models.CMProject.objects.get(id=project_id)
        self.check_permissions('projman.view_project', obj)
        return self.to_api_object(obj)

    def _init_default_project_charts(self, project):
        # TODO: We should add a notion of project templates
        # in addition to install templates.
        # That way, we can define a project with pre-installed
        # charts
        client = self._get_helmsman_api()
        chart_template = client.templates.find(name='projman')
        if chart_template:
            project.charts.create(chart_template.name)
        else:
            client.charts.create("cloudve", "projman", project.namespace)

    def create(self, name):
        self.check_permissions('projman.add_project')
        client = self._get_helmsman_api()
        namespace = slugify(name)
        if client.namespaces.get(namespace):
            message = (
                f"The project namespace '{namespace}' could not be created. "
                f"A namespace by the same name already exists.")
            raise NamespaceExistsException(message)
        obj = models.CMProject.objects.create(
            name=name, namespace=namespace, owner=self.context.user)
        client.namespaces.create(namespace)
        project = self.to_api_object(obj)
        self._init_default_project_charts(project)
        return project

    def delete(self, project_id):
        obj = models.CMProject.objects.get(id=project_id)
        if obj:
            self.check_permissions('projman.delete_project', obj)
            obj.delete()
            admin = User.objects.filter(is_superuser=True).first()
            client = HelmsManAPI(HMServiceContext(user=admin))
            if client.namespaces.get(obj.namespace):
                client.namespaces.delete(obj.namespace)
        else:
            self.raise_no_permissions('projman.delete_project')

    def find(self, name):
        try:
            obj = models.CMProject.objects.get(name=name)
            if self.has_permissions('projman.view_project', obj):
                return self.to_api_object(obj)
            else:
                return None
        except models.CMProject.DoesNotExist:
            return None


class PMProjectChartService(PMService):

    def __init__(self, context, project):
        super(PMProjectChartService, self).__init__(context)
        self.project = project

    def _to_proj_chart(self, chart):
        chart.project = self.project
        # Remap the helm API's delete method to the project chart API method
        # This is just a lazy alternative to writing an actual wrapper around
        # the HelmChart object.
        chart.delete = lambda: self.delete(chart.id)
        return chart

    def find(self, name):
        matches = [self._to_proj_chart(chart) for chart
                   in self.list() if chart.name == name]
        if matches:
            return matches[0]
        else:
            return None

    def list(self):
        return [self._to_proj_chart(chart) for chart
                in self._get_helmsman_api().charts.list(self.project.namespace)
                if self.has_permissions('projman.view_chart', self._to_proj_chart(chart))]

    def get(self, chart_id):
        chart = self._get_helmsman_api().charts.get(chart_id)
        self.check_permissions('projman.view_chart', self._to_proj_chart(chart))
        return (self._to_proj_chart(chart)
                if chart and chart.namespace == self.project.namespace else None)

    def _get_project_oidc_secret(self):
        try:
            secret = KubeClient().secrets.get(f"{self.project.namespace}-projman-secrets",
                                              namespace=self.project.namespace)
            return base64.b64decode(secret.get('data').get('oidc-client-secret')).decode('utf-8')
        except Exception:
            return None

    def create(self, template_name, release_name=None,
               values=None, context=None):
        self.check_permissions('projman.add_chart')
        template = self._get_helmsman_api().templates.get(template_name)
        if not context:
            context = {}
        context.update({'project': {
            'name': self.project.name,
            'namespace': self.project.namespace,
            'access_path': f"/{self.project.namespace}",
            'oidc_client_id': f"projman-{self.project.namespace}",
            'oidc_client_secret': self._get_project_oidc_secret()
        }})
        return self._to_proj_chart(
            template.install(self.project.namespace, release_name,
                             values, context=context))

    def update(self, chart, values):
        self.check_permissions('projman.change_chart', chart)
        updated_chart = self._get_helmsman_api().charts.update(chart, values)
        return self._to_proj_chart(updated_chart)

    def rollback(self, chart, revision=None):
        self.check_permissions('projman.change_chart', chart)
        updated_chart = self._get_helmsman_api().charts.rollback(chart,
                                                                 revision)
        return self._to_proj_chart(updated_chart)

    def delete(self, chart_id):
        obj = self.get(chart_id)
        if obj:
            self.check_permissions('projman.delete_chart', obj)
            self._get_helmsman_api().charts.delete(obj)
        else:
            self.raise_no_permissions('projman.delete_chart')
