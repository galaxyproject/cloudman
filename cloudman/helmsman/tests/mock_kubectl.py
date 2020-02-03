import argparse
import csv
from io import StringIO


class MockKubeCtl(object):
    """
    A mock version of the kubectl binary. Maintains an in-memory database
    to simulate kubectl commands.
    """

    def __init__(self):
        self.namespace_info = {
            'NAME': 'default',
            'STATUS': 'Active',
            'AGE': '2d1h'
        }
        self.namespace_database = {'default': self.namespace_info}
        self.namespace_list_field_names = ["NAME", "STATUS", "AGE"]
        self.parser = self._create_parser()

    def _create_parser(self):
        parser = argparse.ArgumentParser(prog='kubectl')
        subparsers = parser.add_subparsers(help='Available Commands')

        # kubectl get namespaces
        parser_get = subparsers.add_parser('get', help='list')
        subparsers_get = parser_get.add_subparsers(help='Resources to get')
        parser_list_ns = subparsers_get.add_parser(
            'namespaces', help='List namespaces')
        parser_list_ns.set_defaults(func=self._kubectl_get_namespaces)

        # kubectl create namespace
        parser_create = subparsers.add_parser('create', help='create')
        subparsers_create = parser_create.add_subparsers(
            help='Resources to create')
        parser_create_ns = subparsers_create.add_parser('namespace',
                                            help='create a namespace')
        parser_create_ns.add_argument(
            'namespace', type=str, help='namespace name')
        parser_create_ns.set_defaults(func=self._kubectl_create_namespace)

        # Kubectl delete namespace
        parser_delete = subparsers.add_parser('delete', help='delete')
        subparsers_delete = parser_delete.add_subparsers(
            help='Resources to create')
        parser_delete_ns = subparsers_delete.add_parser(
            'namespace', help='delete a namespace')
        parser_delete_ns.add_argument(
            'namespace', type=str, help='namespace name')
        parser_delete_ns.set_defaults(func=self._kubectl_delete_namespace)

        return parser

    def run_command(self, command):
        # evaluate command
        args = self.parser.parse_args(command[1:])
        return args.func(args)

    def _kubectl_get_namespaces(self, args):
        # pretend to succeed
        with StringIO() as output:
            writer = csv.DictWriter(output,
                                    fieldnames=self.namespace_list_field_names,
                                    delimiter=" ", extrasaction='ignore')
            writer.writeheader()
            for release in self.namespace_database.values():
                # Write data about the latest revision for each chart
                writer.writerow(release)
            return output.getvalue()

    def _kubectl_create_namespace(self, args):
        name = args.namespace
        details = {
            'NAME': name,
            'STATUS': 'Active',
            'AGE': '1d',
        }
        self.namespace_database[name] = details
        return details

    def _kubectl_delete_namespace(self, args):
        name = args.namespace
        details = self.namespace_database.get(name)
        if not details:
            return 'Error: namespace: "%s" not found' % name
        self.namespace_database.pop(name, None)
