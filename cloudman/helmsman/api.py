"""CloudMan Service API."""
import json
import os
from django.core.exceptions import ObjectDoesNotExist


class HelmsManAPI(object):

    def __init__(self, request):
        self._repositories = HMChartRepoService(self)
        self._charts = HMChartService(self)

    @property
    def repositories(self):
        return self._repositories

    @property
    def charts(self):
        return self._charts


class HMChartRepoService(object):

    def __init__(self, api):
        self.api = api

    def list(self):
        return []

    def get(self, cluster_id):
        return {}

    def create(self, name, cluster_type, connection_settings):
        raise Exception("Not implemented")

    def delete(self, cluster_id):
        raise Exception("Not implemented")


class HMChartService(object):

    def __init__(self, api):
        self.api = api

    def list(self):
        return [
            self.get('galaxy')
        ]

    def get(self, chart_id):
        if not chart_id == 'galaxy':
            raise ObjectDoesNotExist('Chart: %s does not exist' % chart_id)
        file_path = os.path.join(os.path.dirname(__file__),
                                 './schemas/galaxy.json')
        with open(file_path) as f:
            config = json.load(f)
        return {
            'id': 'galaxy',
            'name': 'Galaxy',
            'access_address': '/galaxy',
            'config': config
        }

    def create(self, name, instance_type):
        raise Exception("Not implemented")

    def delete(self, node_id):
        raise Exception("Not implemented")
