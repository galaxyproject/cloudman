"""CloudMan Service API."""


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
        return []

    def get(self, node_id):
        return {}

    def create(self, name, instance_type):
        raise Exception("Not implemented")

    def delete(self, node_id):
        raise Exception("Not implemented")
