"""CloudMan Service API."""
import json
import os
from .helm.client import HelmClient, HelmValueHandling
from django.core.exceptions import ObjectDoesNotExist


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
    """Marker interface for CloudMan services"""
    def __init__(self, context):
        self._context = context

    @property
    def context(self):
        """
        Returns the currently associated service context.
        """
        return self._context


class HelmsManAPI(HelmsManService):

    def __init__(self, request=None):
        context = HMServiceContext.from_request(request)
        super(HelmsManAPI, self).__init__(context)
        self._repo_svc = HMChartRepoService(context)
        self._chart_svc = HMChartService(context)

    @property
    def repositories(self):
        return self._repo_svc

    @property
    def charts(self):
        return self._chart_svc


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

    def list(self):
        client = HelmClient()
        releases = client.releases.list()
        return [
            {
                'id': release.get('NAME'),
                'name': client.releases.parse_chart_name(
                    release.get('CHART')),
                'display_name': client.releases.parse_chart_name(
                    release.get('CHART')).title(),
                'chart_version': client.releases.parse_chart_version(
                    release.get('CHART')),
                'app_version': release.get("APP VERSION"),
                'project': release.get("NAMESPACE"),
                'state': release.get("STATUS"),
                'updated': release.get("UPDATED"),
                'access_address': '/%s/' % client.releases.parse_chart_name(
                    release.get('CHART')),
                'values': HelmClient().releases.get_values(
                    release.get("NAME"), get_all=True)
            }
            for release in releases
        ]

    def get(self, chart_id):
        charts = (c for c in self.list() if c.get('id') == chart_id)
        return next(charts, {})

    def create(self, name, values):
        raise NotImplementedError()

    def update(self, chart, values):
        # 1. Retrieve chart's current user-defined values
        cur_vals = HelmClient().releases.get_values(chart.get("id"))
        # 2. Add the latest differences on top
        if cur_vals:
            cur_vals.update(values)
        else:
            cur_vals = values
        # 3. Apply the updated config to the chart
        HelmClient().releases.update(chart.get("id"),
                                     "cloudve/%s" % chart.get("name"),
                                     cur_vals)
        chart.get('values', {}).update(cur_vals)
        return chart

    def rollback(self, chart, revision=None):
        # Roll back to immediately preceding revision if revision=None
        HelmClient().releases.rollback(chart.get("id"), revision)
        return self.get(chart.get("id"))

    def delete(self, chart_id):
        raise NotImplementedError()
