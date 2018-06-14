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
        raise Exception("Not implemented")

    def delete(self, cluster_id):
        raise Exception("Not implemented")


class HMChartService(HelmsManService):

    def __init__(self, context):
        super(HMChartService, self).__init__(context)

    def list(self):
        return [
            self.get('galaxy')
        ]

    def _get_galaxy_release(self):
        releases = HelmClient().releases.list()
        for release in releases:
            if "galaxy" in release.get("CHART", ""):
                return release
        return {}

    def get(self, chart_id):
        if not chart_id == 'galaxy':
            raise ObjectDoesNotExist('Chart: %s does not exist' % chart_id)
        file_path = os.path.join(os.path.dirname(__file__),
                                 './schemas/galaxy.json')
        with open(file_path) as f:
            schema = json.load(f)
        galaxy_rel = self._get_galaxy_release()
        if galaxy_rel:
            # Get entire chart state, including chart default values
            val = HelmClient().releases.get_values(galaxy_rel.get("NAME"),
                                                   get_all=True)
            config = val.get('galaxy_conf')
        else:
            config = {}
        return {
            'id': 'galaxy',
            'name': 'Galaxy',
            'access_address': '/galaxy',
            'schema': schema,
            'config': config
            }

    def create(self, name, instance_type):
        raise Exception("Not implemented")

    def update(self, chart, config_updates):
        galaxy_rel = self._get_galaxy_release()
        # 1. Retrieve chart's current user-defined values
        cur_vals = HelmClient().releases.get_values(galaxy_rel.get("NAME"))
        # 2. Add the latest differences on top
        if cur_vals:
            cur_vals.get('galaxy_conf').update(config_updates)
        else:
            cur_vals = {'galaxy_conf': config_updates}
        # 3. Apply the updated config to the chart
        HelmClient().releases.update(galaxy_rel.get("NAME"),
                                     "galaxyproject/galaxy-stable",
                                     cur_vals)
        chart.get('config', {}).update(cur_vals.get('galaxy_conf'))
        return chart

    def delete(self, node_id):
        raise Exception("Not implemented")
