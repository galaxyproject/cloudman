"""A wrapper around the helm commandline client"""
import contextlib
import shutil

from enum import Enum

from clusterman.clients import helpers

from helmsman import helpers as hm_helpers


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
        self._repo_chart_svc = HelmRepoChartService(self)

    @staticmethod
    def _check_environment():
        if not shutil.which("helm"):
            raise Exception("Could not find helm executable in path")

    @property
    def releases(self):
        return self._release_svc

    @property
    def repositories(self):
        return self._repo_svc

    @property
    def repo_charts(self):
        return self._repo_chart_svc


class HelmValueHandling(Enum):
    RESET = 0  # equivalent to --reset-values
    REUSE = 1  # equivalent to --reuse-values
    DEFAULT = 2  # uses only values passed in


class HelmReleaseService(HelmService):

    def __init__(self, client):
        super(HelmReleaseService, self).__init__(client)

    def list(self, namespace=None):
        cmd = ["helm", "list"]
        if namespace:
            cmd += ["--namespace", namespace]
        else:
            cmd += ["--all-namespaces"]
        data = helpers.run_list_command(cmd)
        return data

    def get(self, namespace, release_name):
        return {}

    def _set_values_and_run_command(self, cmd, values_list):
        """
        Handles helm values by writing values to a temporary file,
        after which the command is run. The temporary file is cleaned
        up on exit from this method. This allows special values like braces
        to be handled without complex escaping, which the helm --set flag
        can't handle.

        The values can be a list of values files, in which case they will
        all be written to multiple temp files and passed to helm.
        """
        if not isinstance(values_list, list):
            values_list = [values_list]
        # contextlib.exitstack allows multiple temp files to be cleaned up
        # on exit. ref: https://stackoverflow.com/a/19412700
        with contextlib.ExitStack() as stack:
            files = [stack.enter_context(hm_helpers.TempValuesFile(values))
                     for values in values_list]
            for file in files:
                cmd += ["-f", file.name]
            return helpers.run_command(cmd)

    def create(self, chart, namespace, release_name=None,
               version=None, values=None):
        cmd = ["helm", "install", "--namespace", namespace]

        if release_name:
            cmd += [release_name, chart]
        else:
            cmd += [chart, "--generate-name"]
        if version:
            cmd += ["--version", version]
        return self._set_values_and_run_command(cmd, values)

    def update(self, namespace, release_name, chart, values=None,
               value_handling=HelmValueHandling.REUSE, version=None):
        """
        The chart argument can be either: a chart reference('stable/mariadb'),
        a path to a chart directory, a packaged chart, or a fully qualified
        URL. For chart references, the latest version will be specified unless
        the '--version' flag is set.
        """
        cmd = ["helm", "upgrade", "--namespace", namespace,
               release_name, chart]
        if value_handling == value_handling.RESET:
            cmd += ["--reset-values"]
        elif value_handling == value_handling.REUSE:
            cmd += ["--reuse-values"]
        else:  # value_handling.DEFAULT
            pass
        if version:
            cmd += ["--version", version]
        return self._set_values_and_run_command(cmd, values)

    def history(self, namespace, release_name):
        data = helpers.run_list_command(
            ["helm", "history", "--namespace", namespace, release_name])
        return data

    def rollback(self, namespace, release_name, revision=None):
        if not revision:
            history = self.history(namespace, release_name)
            if history and len(history) > 1:
                # Rollback to previous
                revision = history[-2].get('REVISION')
            else:
                return
        return helpers.run_command(
            ["helm", "rollback", "--namespace", namespace,
             release_name, revision])

    def delete(self, namespace, release_name):
        return helpers.run_command(
            ["helm", "delete", "--namespace", namespace, release_name])

    def get_values(self, namespace, release_name, get_all=True):
        """
        get_all=True will also dump chart default values.
        get_all=False will only return user overridden values.
        """
        cmd = ["helm", "get", "values", "-o", "yaml",
               "--namespace", namespace, release_name]
        if get_all:
            cmd += ["--all"]
        return helpers.run_yaml_command(cmd)

    @staticmethod
    def parse_chart_name(name):
        """
        Parses a chart name-version string such as galaxy-cvmfs-csi-1.0.0 and
        returns the name portion (e.g. galaxy-cvmfs-csi) only
        """
        return name.rpartition("-")[0] if name else name

    @staticmethod
    def parse_chart_version(name):
        """
        Parses a chart name-version string such as galaxy-cvmfs-csi-1.0.0 and
        returns the version portion (e.g. 1.0.0) only
        """
        return name.rpartition("-")[2] if name else name


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


class HelmRepoChartService(HelmService):

    def __init__(self, client):
        super(HelmRepoChartService, self).__init__(client)

    def list(self, chart_name=None, chart_version=None, search_hub=False):
        # Perform exact match if chart_name specified.
        # https://github.com/helm/helm/issues/3890
        data = helpers.run_list_command(
            ["helm", "search", "hub" if search_hub else "repo"] +
            ["--regexp", "%s\\v" % chart_name] if chart_name else [] +
            ["--version", chart_version] if chart_version else [])
        return data

    def get(self, chart_name):
        return {}

    def find(self, name, version, search_hub=False):
        return self.list(chart_name=name, chart_version=version, search_hub=search_hub)

    def create(self, chart_name):
        raise Exception("Not implemented")

    def delete(self, release_name):
        raise Exception("Not implemented")
