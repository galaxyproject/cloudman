import argparse
import csv
from io import StringIO
import uuid
import yaml


class MockHelm(object):
    """
    A mock version of the helm binary. Maintains an in-memory database
    to simulate helm commands.
    """

    def __init__(self):
        self.revision_history = [
            {
                'NAME': 'turbulent-markhor',
                'REVISION': 12,
                'UPDATED': 'Fri Apr 19 05:33:37 2019',
                'STATUS': 'DEPLOYED',
                'CHART': 'cloudlaunch-0.2.0',
                'APP VERSION': '2.0.2',
                'NAMESPACE': 'default',
                'VALUES': {
                    'foo': 'bar'
                }
            }
        ]
        self.chart_database = {
            'turbulent-markhor': self.revision_history
        }
        self.installed_repos = {
            'stable': {
                'NAME': 'stable',
                'URL': 'https://kubernetes-charts.storage.googleapis.com'
            }
        }
        self.chart_list_field_names = ["NAME", "REVISION", "UPDATED", "STATUS",
                                       "CHART", "APP VERSION", "NAMESPACE"]
        self.chart_history_field_names = ["REVISION", "UPDATED", "STATUS",
                                          "CHART", "APP VERSION",
                                          "DESCRIPTION"]
        self.repo_list_field_names = ["NAME", "URL"]
        self.parser = self._create_parser()

    def _create_parser(self):
        parser = argparse.ArgumentParser(prog='helm')

        subparsers = parser.add_subparsers(help='Available Commands')

        # Helm list
        parser_list = subparsers.add_parser('list', help='list releases')
        parser_list.add_argument('--all-namespaces', action='store_true',
                                 help='list releases from all namespaces')
        parser_list.add_argument('--namespace', type=str, help='namespace')
        parser_list.set_defaults(func=self._helm_list)

        # Helm install
        parser_inst = subparsers.add_parser('install', help='install a chart')
        parser_inst.add_argument(
            'name', type=str, help='release name', nargs='?')
        parser_inst.add_argument(
            'chart', type=str, help='chart name')
        parser_inst.add_argument(
            '--generate-name', action='store_true', help='generate random name')
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
        parser_upgrade.add_argument(
            '--namespace', type=str, help='namespace of release')
        parser_upgrade.set_defaults(func=self._helm_upgrade)

        # Helm rollback
        parser_rollback = subparsers.add_parser('rollback', help='rolls back a release to a previous revision')
        parser_rollback.add_argument(
            'release', type=str, help='release name')
        parser_rollback.add_argument(
            'revision', type=int, help='revision number')
        parser_rollback.add_argument(
            '--namespace', type=str, help='namespace of release')
        parser_rollback.set_defaults(func=self._helm_rollback)

        # Helm history
        parser_history = subparsers.add_parser('history', help='prints historical revisions for a given release')
        parser_history.add_argument(
            'release', type=str, help='release name')
        parser_history.add_argument('--namespace', type=str, help='namespace')
        parser_history.set_defaults(func=self._helm_history)

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
        p_get_values.add_argument(
            '--namespace', type=str, help='namespace of release')
        p_get_values.set_defaults(func=self._helm_get_values)


        p_get_manifest = subparser_get.add_parser(
            'manifest', help='download manifest for a release')
        p_get_manifest.set_defaults(func=self._helm_get_manifest)

        # Helm delete
        parser_delete = subparsers.add_parser('delete', help='delete a release')
        parser_delete.add_argument('release', type=str, help='release name')
        parser_delete.add_argument('--namespace', type=str, help='namespace')
        parser_delete.set_defaults(func=self._helm_delete)

        return parser

    def run_command(self, command):
        # evaluate command
        args = self.parser.parse_args(command[1:])
        return args.func(args)

    def _helm_list(self, args):
        # pretend to succeed
        with StringIO() as output:
            writer = csv.DictWriter(output,
                                    fieldnames=self.chart_list_field_names,
                                    delimiter="\t", extrasaction='ignore')
            writer.writeheader()
            for release in self.chart_database.values():
                last = release[-1]
                if args.namespace and last.get("NAMESPACE"):
                    if args.namespace == last.get("NAMESPACE"):
                        # Write data about the latest revision for each chart
                        writer.writerow(last)
                else:
                    writer.writerow(last)
            return output.getvalue()

    def _helm_install(self, args):
        repo_name, chart_name = args.chart.split('/')
        release_name = '%s-%s' % (chart_name, uuid.uuid4().hex[:6])
        revision = {
            'NAME': release_name,
            'REVISION': 1,
            'UPDATED': 'Fri Apr 19 05:33:37 2019',
            'STATUS': 'DEPLOYED',
            'CHART': '%s-%s' % (chart_name, args.version or "1.0.0"),
            'APP VERSION': '2.0.2',
            'NAMESPACE': args.namespace,
            'DESCRIPTION': 'Initial Install',
            'VALUES': {}
        }
        if args.values:
            with open(args.values, 'r') as f:
                values = yaml.safe_load(f)
                revision['VALUES'] = values
        self.chart_database[release_name] = [revision]
        return revision

    def _helm_upgrade(self, args):
        revisions = self.chart_database.get(args.release)
        if not revisions:
            return 'Error: "%s" has no deployed releases' % args.release
        latest_release = revisions[-1]
        new_release = dict(latest_release)
        new_release['REVISION'] += 1
        new_release['DESCRIPTION'] = 'Upgraded successfully'
        if args.values:
            with open(args.values, 'r') as f:
                values = yaml.safe_load(f)
                new_release['VALUES'] = values
        revisions.append(new_release)
        return new_release

    def _helm_rollback(self, args):
        revisions = self.chart_database.get(args.release)
        if not revisions:
            return 'Error: "%s" has no deployed releases' % args.release
        latest_revision = revisions[-1]
        if args.revision:
            matches = [r for r in revisions if r['REVISION'] == args.revision]
            if not matches:
                return 'Error: "%s" has no matching revision %s' % (args.release, args.revision)
            rollback_revision = matches[0]
        else:
            rollback_revision = revisions[-1]
        new_revision = dict(rollback_revision)
        new_revision['REVISION'] = latest_revision['REVISION'] + 1
        new_revision['DESCRIPTION'] = 'Rolled back to %s' % args.revision
        revisions.append(new_revision)
        return new_revision

    def _helm_history(self, args):
        revisions = self.chart_database.get(args.release)
        if not revisions:
            return 'Error: "%s" has no deployed releases' % args.release
        # pretend to succeed
        with StringIO() as output:
            writer = csv.DictWriter(output,
                                    fieldnames=self.chart_history_field_names,
                                    delimiter="\t", extrasaction='ignore')
            writer.writeheader()
            writer.writerows(revisions)
            return output.getvalue()

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
            writer = csv.DictWriter(output,
                                    fieldnames=self.repo_list_field_names,
                                    delimiter="\t", extrasaction='ignore')
            writer.writeheader()
            for val in self.installed_repos.values():
                writer.writerow(val)
            return output.getvalue()

    def _helm_get_values(self, args):
        revisions = self.chart_database.get(args.release)
        if not revisions:
            return 'Error: release: "%s" not found' % args.release
        latest_release = revisions[-1]
        with StringIO() as output:
            yaml.safe_dump(latest_release.get('VALUES'), output, allow_unicode=True)
            return output.getvalue()

    def _helm_get_manifest(self, args):
        # pretend to succeed
        pass

    def _helm_delete(self, args):
        revisions = self.chart_database.get(args.release)
        if not revisions:
            return 'Error: release: "%s" not found' % args.release
        self.chart_database.pop(args.release, None)

