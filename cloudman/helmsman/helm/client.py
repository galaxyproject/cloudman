"""A wrapper around the helm commandline client"""
import shutil
from . import helpers
from enum import Enum


class HelmService(object):
    """Marker interface for CloudMan services"""
    def __init__(self, client):
        self._client = client

    def client(self):
        return self._client


class HelmClient(HelmService):

    def __init__(self):
        self._check_environment()
        super(HelmClient, self).__init__(self)
        self._release_svc = HelmReleaseService(self)
        self._repo_svc = HelmRepositoryService(self)
        self._chart_svc = HelmChartService(self)

    def _check_environment(self):
        if not shutil.which("helm"):
            raise Exception("Could not find helm executable in path")

    def helm_init(self, upgrade=False, wait=False):
        cmd = ["helm", "init"]
        if upgrade:
            cmd += ["--upgrade"]
        if wait:
            cmd += ["--wait"]
        return helpers.run_command(cmd)

    @property
    def releases(self):
        return self._release_svc

    @property
    def repositories(self):
        return self._repo_svc

    @property
    def charts(self):
        return self._chart_svc


class HelmValueHandling(Enum):
    RESET = 0  # equivalent to --reset-values
    REUSE = 1  # equivalent to --reuse-values
    DEFAULT = 2  # uses only values passed in


class HelmReleaseService(HelmService):

    def __init__(self, client):
        super(HelmReleaseService, self).__init__(client)

    def list(self):
        data = helpers.run_list_command(["helm", "list"])
        return data

    def get(self, release_name):
        return {}

    def create(self, chart, namespace, release_name=None,
               values=None, version=None):
        cmd = ["helm", "install", chart]

        if namespace:
            cmd += ["--namespace", namespace]
        if release_name:
            cmd += ["--name", release_name]
        if version:
            cmd += ["--version", version]
        if values:
            for key, val in helpers.flatten_dict(values).items():
                cmd += ["--set", f"{key}={val}"]
        return helpers.run_command(cmd)

    def update(self, release_name, chart, values=None,
               value_handling=HelmValueHandling.DEFAULT):
        """
        The chart argument can be either: a chart reference('stable/mariadb'),
        a path to a chart directory, a packaged chart, or a fully qualified
        URL. For chart references, the latest version will be specified unless
        the '--version' flag is set.
        """
        cmd = ["helm", "upgrade", release_name, chart]

        if values:
            for key, val in helpers.flatten_dict(values).items():
                cmd += ["--set", f"{key}={val}"]

        if value_handling == value_handling.RESET:
            cmd += ["--reset-values"]
        elif value_handling == value_handling.REUSE:
            cmd += ["--reuse-values"]
        else:  # value_handling.DEFAULT
            pass

        return helpers.run_command(cmd)

    def delete(self, release_name):
        return helpers.run_command(["helm", "delete", release_name])


class HelmRepositoryService(HelmService):

    def __init__(self, client):
        super(HelmRepositoryService, self).__init__(client)

    def list(self):
        data = helpers.run_list_command(["helm", "repo", "list"])
        return data

    def update(self):
        return helpers.run_command(["helm", "repo", "update"])

    def create(self, repo_name, url):
        return helpers.run_command(["helm", "repo", "add", repo_name, url])

    def delete(self, repo_name):
        return helpers.run_command(["helm", "repo", "remove", repo_name])


class HelmChartService(HelmService):

    def __init__(self, client):
        super(HelmChartService, self).__init__(client)

    def list(self, chart_name=None):
        data = helpers.run_list_command(["helm", "search"] +
                                        [chart_name] if chart_name else [])
        return data

    def get(self, chart_name):
        return {}

    def create(self, chart_name):
        raise Exception("Not implemented")

    def delete(self, release_name):
        raise Exception("Not implemented")
