"""A wrapper around the helm commandline client"""
import shutil
from . import helpers


class HelmService(object):
    """Marker interface for CloudMan services"""
    def __init__(self, api):
        self._api = api

    def api(self):
        return self._api


class HelmAPI(HelmService):

    def __init__(self):
        self._check_environment()
        super(HelmAPI, self).__init__(self)
        self._release_svc = HelmReleaseService(self)
        self._repo_svc = HelmRepositoryService(self)
        self._chart_svc = HelmChartService(self)

    def _check_environment(self):
        if not shutil.which("helm"):
            raise Exception("Could not find helm executable in path")

    @property
    def releases(self):
        return self._release_svc

    @property
    def repositories(self):
        return self._repo_svc

    @property
    def charts(self):
        return self._chart_svc


class HelmReleaseService(HelmService):

    def __init__(self, api):
        super(HelmReleaseService, self).__init__(api)

    def list(self):
        output = helpers.run_list_command(["helm", "list"])
        print(output)
        return output

    def get(self, release_name):
        return {}

    def create(self, chart_name):
        raise Exception("Not implemented")

    def delete(self, release_name):
        raise Exception("Not implemented")


class HelmRepositoryService(HelmService):

    def __init__(self, api):
        super(HelmRepositoryService, self).__init__(api)

    def list(self):
        output = helpers.run_list_command(["helm", "repo", "list"])
        print(output)
        return output

    def get(self, release_name):
        return {}

    def create(self, chart_name):
        raise Exception("Not implemented")

    def delete(self, release_name):
        raise Exception("Not implemented")


class HelmChartService(HelmService):

    def __init__(self, api):
        super(HelmChartService, self).__init__(api)

    def list(self):
        return []

    def get(self, release_name):
        return {}

    def create(self, chart_name):
        raise Exception("Not implemented")

    def delete(self, release_name):
        raise Exception("Not implemented")