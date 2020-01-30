"""ProjMan Service API."""
from django.contrib.auth.models import User

from . import models
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
             if self.has_permissions('projects.view_project', proj))))

    def get(self, project_id):
        obj = models.CMProject.objects.get(id=project_id)
        self.check_permissions('projects.view_project', obj)
        return self.to_api_object(obj)

    def create(self, name):
        self.check_permissions('projects.add_project')
        admin = User.objects.filter(is_superuser=True).first()
        client = HelmsManAPI(HMServiceContext(user=admin))
        if client.namespaces.get(name) and name != 'default':
            message = (f"The project '{name}' could not be created. "
                       f"A namespace by the same name already exists.")
            raise NamespaceExistsException(message)
        obj = models.CMProject.objects.create(
            name=name, owner=self.context.user)
        if name != 'default':
            client.namespaces.create(name)
        project = self.to_api_object(obj)
        return project

    def delete(self, project_id):
        obj = models.CMProject.objects.get(id=project_id)
        if obj:
            self.check_permissions('projects.delete_project', obj)
            obj.delete()
            admin = User.objects.filter(is_superuser=True).first()
            client = HelmsManAPI(HMServiceContext(user=admin))
            if client.namespaces.get(obj.name) and obj.name != "default":
                client.namespaces.delete(obj.name)
        else:
            self.raise_no_permissions('projects.delete_project')

    def find(self, name):
        try:
            obj = models.CMProject.objects.get(name=name)
            if self.has_permissions('projects.view_project', obj):
                return self.to_api_object(obj)
            else:
                return None
        except models.CMProject.DoesNotExist:
            return None


class PMProjectChartService(PMService):

    def __init__(self, context, project):
        super(PMProjectChartService, self).__init__(context)
        self.project = project

    def _get_helmsman_api(self):
        return HelmsManAPI(HMServiceContext(user=self.context.user))

    def _to_proj_chart(self, chart):
        chart.project = self.project
        # Remap the helm API's delete method to the project chart API method
        # This is just a lazy alternative to writing an actual wrapper around
        # the HelmChart object.
        chart.delete = lambda: self.delete(chart.id)
        return chart

    def list(self):
        return [self._to_proj_chart(chart) for chart
                in self._get_helmsman_api().charts.list()
                if chart.namespace == self.project.name and
                self.has_permissions('charts.view_chart', chart)]

    def get(self, chart_id):
        chart = self._get_helmsman_api().charts.get(chart_id)
        self.check_permissions('charts.view_chart', chart)
        return (self._to_proj_chart(chart)
                if chart and chart.namespace == self.project.name else None)

    def create(self, repo_name, chart_name, release_name=None, version=None,
               values=None):
        self.check_permissions('charts.add_chart')
        return self._to_proj_chart(self._get_helmsman_api().charts.create(
            repo_name, chart_name, self.project.name, release_name, version,
            values))

    def update(self, chart, values):
        self.check_permissions('charts.change_chart', chart)
        updated_chart = self._get_helmsman_api().charts.update(chart, values)
        return self._to_proj_chart(updated_chart)

    def rollback(self, chart, revision=None):
        self.check_permissions('charts.change_chart', chart)
        updated_chart = self._get_helmsman_api().charts.rollback(chart, revision)
        return self._to_proj_chart(updated_chart)

    def delete(self, chart_id):
        obj = self.get(chart_id)
        if obj:
            self.check_permissions('charts.delete_chart', obj)
            self._get_helmsman_api().charts.delete(obj)
        else:
            self.raise_no_permissions('charts.delete_chart')
