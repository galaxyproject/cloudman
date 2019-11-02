"""ProjMan Service API."""
import uuid
from . import models
from helmsman.api import HelmsManAPI, HMServiceContext


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
            raise PermissionError(
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

    def add_child_services(self, project):
        project.service = self
        project.charts = PMProjectChartService(self.context, project)
        return project

    def list(self):
        return list(map(
            self.add_child_services,
            (proj for proj in models.CMProject.objects.all()
             if self.has_permissions('projects.view_project', proj))))

    def get(self, project_id):
        obj = models.CMProject.objects.get(id=project_id)
        self.check_permissions('projects.view_project', obj)
        return self.add_child_services(obj)

    def create(self, name):
        self.check_permissions('projects.create_project')
        obj = models.CMProject.objects.create(
            name=name, owner=self.context.user)
        project = self.add_child_services(obj)
        return project

    def delete(self, project_id):
        obj = models.CMProject.objects.get(id=project_id)
        self.check_permissions('projects.delete_project', obj)
        if obj:
            obj.delete()

    def find(self, name):
        try:
            obj = models.CMProject.objects.get(name=name)
            if self.has_permissions('projects.view_project', obj):
                return self.add_child_services(obj)
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
        return chart

    def list(self):
        return [self._to_proj_chart(chart) for chart
                in self._get_helmsman_api().charts.list()
                if chart.namespace == self.project.name]

    def get(self, chart_id):
        chart = self._get_helmsman_api().charts.get(chart_id)
        return (self._to_proj_chart(chart)
                if chart and chart.namespace == self.project.name else None)

    def create(self, repo_name, chart_name, release_name=None, version=None,
               values=None):
        return self._to_proj_chart(self._get_helmsman_api().charts.create(
            repo_name, chart_name, self.project.name, release_name, version,
            values))

    def delete(self, chart_id):
        obj = self.get(chart_id)
        if obj:
            obj.delete()
