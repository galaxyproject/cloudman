"""A wrapper around the helm commandline client"""
import shutil
import tempfile
import yaml
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
        self._namespace_svc = KubeCtlNamespaceService(self)

    def _check_environment(self):
        if not shutil.which("helm"):
            raise Exception("Could not find helm executable in path")
        if not shutil.which("kubectl"):
            raise Exception("Could not find kubectl executable in path")

    @property
    def releases(self):
        return self._release_svc

    @property
    def repositories(self):
        return self._repo_svc

    @property
    def charts(self):
        return self._chart_svc

    @property
    def namespaces(self):
        return self._namespace_svc


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

    def _set_values_and_run_command(self, cmd, values):
        """
        Handles helm values by writing values to a temporary file,
        after which the command is run. The temporary file is cleaned
        up on exit from this method. This allows special values like braces
        to be handled without complex escaping, which the helm --set flag
        can't handle.
        """
        with tempfile.NamedTemporaryFile(mode="w", prefix="helmsman") as f:
            yaml.dump(values, stream=f, default_flow_style=False)
            cmd += ["-f", f.name]
            return helpers.run_command(cmd)

    def create(self, chart, namespace, release_name=None,
               version=None, values=None):
        cmd = ["helm", "install"]

        if release_name:
            cmd += [release_name, chart]
        else:
            cmd += [chart, "--generate-name"]
        if namespace:
            cmd += ["--namespace", namespace]
        if version:
            cmd += ["--version", version]
        return self._set_values_and_run_command(cmd, values)

    def update(self, release_name, chart, values=None,
               value_handling=HelmValueHandling.REUSE):
        """
        The chart argument can be either: a chart reference('stable/mariadb'),
        a path to a chart directory, a packaged chart, or a fully qualified
        URL. For chart references, the latest version will be specified unless
        the '--version' flag is set.
        """
        cmd = ["helm", "upgrade", release_name, chart]

        if value_handling == value_handling.RESET:
            cmd += ["--reset-values"]
        elif value_handling == value_handling.REUSE:
            cmd += ["--reuse-values"]
        else:  # value_handling.DEFAULT
            pass
        return self._set_values_and_run_command(cmd, values)

    def history(self, release_name):
        data = helpers.run_list_command(["helm", "history", release_name])
        return data

    def rollback(self, release_name, revision=None):
        if not revision:
            history = self.history(release_name)
            if history and len(history) > 1:
                # Rollback to previous
                revision = history[-2].get('REVISION')
            else:
                return
        return helpers.run_command(["helm", "rollback",
                                    release_name, revision])

    def delete(self, release_name):
        return helpers.run_command(["helm", "delete", release_name])

    def get_values(self, release_name, get_all=True):
        """
        get_all=True will also dump chart default values.
        get_all=False will only return user overridden values.
        """
        cmd = ["helm", "get", "values", release_name]
        if get_all:
            cmd += ["--all"]
        return yaml.safe_load(helpers.run_command(cmd))

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


class KubeCtlNamespaceService(HelmService):

    def __init__(self, client):
        super(KubeCtlNamespaceService, self).__init__(client)

    def list(self):
        data = helpers.run_list_command(["kubectl", "get", "namespaces"],
                                        delimiter=" ")
        return data

    def list_names(self):
        data = self.list()
        output = []
        for each in data:
            output.append(each.get('NAME'))
        return output

    def create(self, namespace_name):
        return helpers.run_command(["kubectl", "create",
                                    "namespace", namespace_name])

    def create_if_not_exists(self, namespace_name):
        if namespace_name not in self.list_names():
            return self.create(namespace_name)

    def delete(self, namespace_name):
        return helpers.run_command(["kubectl", "delete",
                                    "namespace", namespace_name])
