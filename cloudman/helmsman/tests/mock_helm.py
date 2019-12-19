import argparse
import csv
from io import StringIO
from unittest.mock import patch
import uuid
import yaml


class MockHelm(object):

    """ Mocks all calls to the helm command"""
    def __init__(self, testcase):
        self.patch1 = patch(
            'helmsman.helm.client.HelmClient._check_environment',
            return_value=True)
        self.patch2 = patch('helmsman.helm.helpers.run_command',
                            self.mock_run_command)
        self.patch1.start()
        self.patch2.start()
        testcase.addCleanup(self.patch2.stop)
        testcase.addCleanup(self.patch1.stop)
        self.chart_list_field_name = ["NAME", "REVISION", "UPDATED", "STATUS",
                                      "CHART", "APP VERSION", "NAMESPACE"]
        self.installed_charts = [
            {
                'NAME': 'turbulent-markhor',
                'REVISION': 12,
                'UPDATED': 'Fri Apr 19 05:33:37 2019',
                'STATUS': 'DEPLOYED',
                'CHART': 'cloudlaunch-0.2.0',
                'APP VERSION': '2.0.2',
                'NAMESPACE': 'cloudlaunch',
                'VALUES': {
                    'foo': 'bar'
                }
            }
        ]
        self.repo_list_field_name = ["NAME", "URL"]
        self.installed_repos = {
            'stable': {
                'NAME': 'stable',
                'URL': 'https://kubernetes-charts.storage.googleapis.com'
            }
        }

    def _parse_helm_command(self, command):
        parser = argparse.ArgumentParser(prog='helm')
        subparsers = parser.add_subparsers(help='Available Commands')

        # Helm init
        parser_init = subparsers.add_parser('init', help='init Helm')
        parser_init.add_argument(
            '--service-account', type=str, help='service account', default=None)
        parser_init.add_argument(
            '--wait', help='wait till initialized', action='store_true')
        parser_init.set_defaults(func=self._helm_init)

        # Helm list
        parser_list = subparsers.add_parser('list', help='list releases')
        parser_list.set_defaults(func=self._helm_list)

        # Helm install
        parser_inst = subparsers.add_parser('install', help='install a chart')
        parser_inst.add_argument(
            'chart', type=str, help='chart name')
        parser_inst.add_argument('--namespace', type=str, help='namespace')
        parser_inst.add_argument('--version', type=str, help='version')
        parser_inst.add_argument(
            '-f', '--values', type=str, help='value files')
        parser_inst.set_defaults(func=self._helm_install)

        # Helm upgrade
        parser_upgrade = subparsers.add_parser('upgrade', help='upgrade a chart')
        parser_upgrade.add_argument(
            'release', type=str, help='release name')
        parser_upgrade.add_argument(
            'chart', type=str, help='chart name')
        parser_upgrade.add_argument(
            '--reuse-values', action='store_true',
            help="reuse the last release's values and merge in any overrides")
        parser_upgrade.add_argument(
            '-f', '--values', type=str, help='value files')
        parser_upgrade.set_defaults(func=self._helm_upgrade)

        # Helm repo commands
        parser_repo = subparsers.add_parser('repo', help='repo commands')
        subparser_repo = parser_repo.add_subparsers()
        p_repo_update = subparser_repo.add_parser('update', help='update repo')
        p_repo_update.set_defaults(func=self._helm_repo_update)
        p_repo_add = subparser_repo.add_parser('add', help='install repo')
        p_repo_add.add_argument('name', type=str, help='repo name')
        p_repo_add.add_argument('url', type=str, help='repo url')
        p_repo_add.set_defaults(func=self._helm_repo_add)
        p_repo_list = subparser_repo.add_parser('list', help='list repos')
        p_repo_list.set_defaults(func=self._helm_repo_list)

        # Helm get
        parser_get = subparsers.add_parser(
            'get', help='download a named release')
        subparser_get = parser_get.add_subparsers()

        p_get_values = subparser_get.add_parser(
            'values', help='download values for a release')
        p_get_values.add_argument(
            'release', type=str, help='release name')
        p_get_values.add_argument(
            '--all', action='store_true', help='dump all values')
        p_get_values.set_defaults(func=self._helm_get_values)

        p_get_manifest = subparser_get.add_parser(
            'manifest', help='download manifest for a release')
        p_get_manifest.set_defaults(func=self._helm_get_manifest)

        # Helm delete
        parser_list = subparsers.add_parser('delete', help='delete a release')
        parser_list.add_argument('release', type=str, help='release name')
        parser_list.set_defaults(func=self._helm_delete)

        # evaluate command
        args = parser.parse_args(command)
        return args.func(args)

    def _helm_init(self, args):
        # pretend to succeed
        pass

    def _helm_list(self, args):
        # pretend to succeed
        with StringIO() as output:
            writer = csv.DictWriter(output, fieldnames=self.chart_list_field_name,
                                    delimiter="\t", extrasaction='ignore')
            writer.writeheader()
            writer.writerows(self.installed_charts)
            return output.getvalue()

    def _helm_install(self, args):
        repo_name, chart_name = args.chart.split('/')
        chart = {
            'NAME': '%s-%s' % (chart_name, uuid.uuid4().hex[:6]),
            'REVISION': 1,
            'UPDATED': 'Fri Apr 19 05:33:37 2019',
            'STATUS': 'DEPLOYED',
            'CHART': '%s-%s' % (chart_name, args.version or "1.0.0"),
            'APP VERSION': '2.0.2',
            'NAMESPACE': args.namespace,
            'VALUES': {}
        }
        if args.values:
            with open(args.values, 'r') as f:
                values = yaml.safe_load(f)
                chart['VALUES'] = values
        self.installed_charts.append(chart)
        return chart

    def _helm_upgrade(self, args):
        matches = [chart for chart in self.installed_charts
                   if chart.get('NAME') == args.release]
        if not matches:
            return 'Error: "%s" has no deployed releases' % args.release
        release = matches[0]
        if args.values:
            with open(args.values, 'r') as f:
                values = yaml.safe_load(f)
                release['VALUES'] = values
        return release

    def _helm_repo_update(self, args):
        # pretend to succeed
        pass

    def _helm_repo_add(self, args):
        repo = {
            'NAME': args.name,
            'URL': args.url
        }
        self.installed_repos[args.name] = repo
        return '"%s" has been added to your repositories' % args.name

    def _helm_repo_list(self, args):
        with StringIO() as output:
            writer = csv.DictWriter(output, fieldnames=self.repo_list_field_name,
                                    delimiter="\t", extrasaction='ignore')
            writer.writeheader()
            for val in self.installed_repos.values():
                writer.writerow(val)
            return output.getvalue()

    def _helm_get_values(self, args):
        matches = [chart for chart in self.installed_charts
                   if chart.get('NAME') == args.release]
        if matches:
            chart = matches[0]
            with StringIO() as output:
                yaml.safe_dump(chart.get('VALUES'), output, allow_unicode=True)
                return output.getvalue()
        else:
            return 'Error: release: "%s" not found' % args.release

    def _helm_get_manifest(self, args):
        # pretend to succeed
        pass

    def _helm_delete(self, args):
        matches = [chart for chart in self.installed_charts
                   if chart.get('NAME') == args.release]
        if matches:
            self.installed_charts.remove(matches[0])
        else:
            return 'Error: release: "%s" not found' % args.release

    def mock_run_command(self, command, shell=False):
        if isinstance(command, list):
            prog = command[0]
        else:
            prog = command or ""

        if prog.startswith("helm"):
            return self._parse_helm_command(command[1:])
        elif prog.startswith("kubectl create"):
            # pretend to succeed
            pass
        else:
            raise Exception("Unrecognised command: {0}".format(prog))
