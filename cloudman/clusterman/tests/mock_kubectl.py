import argparse
import copy
import csv
import yaml

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
        # Response template for kubectl commands returning yaml lists
        self.list_template = {
            "apiVersion": "v1",
            "items": [],
            "kind": "List",
        }
        self.request_counter = 0
        self.nodes = [
            {
                "apiVersion": "v1",
                "kind": "Node",
                "metadata": {
                    "labels": {
                        "kubernetes.io/hostname": "docker-desktop",
                        "node-role.kubernetes.io/master": ""
                    },
                    "name": "docker-desktop",
                    "resourceVersion": "3932510",
                    "selfLink": "/api/v1/nodes/docker-desktop",
                    "uid": "166c6e35-76b7-4f28-a1a0-590dd3e05662"
                },
                "spec": {},
                "status": {
                    "addresses": [
                        {
                            "address": "10.1.1.1",
                            "type": "InternalIP"
                        },
                        {
                            "address": None,
                            "type": "ExternalIP"
                        },
                        {
                            "address": "docker-desktop",
                            "type": "Hostname"
                        }
                    ],
                }
            }
        ]
        self.pods = [
            {
                "apiVersion": "v1",
                "kind": "Pod",
                "metadata": {
                    "annotations": {
                        "cni.projectcalico.org/podIP": "10.42.49.236/32"
                    },
                    "creationTimestamp": "2020-03-29T09:56:06Z",
                    "generateName": "galaxy-1584807903-galaxy-metrics-1585475760-",
                    "labels": {
                        "controller-uid": "fb4cf4bb-5df5-47bb-b0b8-741540cdedcc",
                        "job-name": "galaxy-1584807903-galaxy-metrics-1585475760"
                    },
                    "name": "galaxy-1584807903-galaxy-metrics-1585475760-9wtb6",
                    "namespace": "initial",
                    "ownerReferences": [
                        {
                            "apiVersion": "batch/v1",
                            "kind": "Job",
                            "name": "galaxy-1584807903-galaxy-metrics-1585475760",
                            "uid": "fb4cf4bb-5df5-47bb-b0b8-741540cdedcc"
                        }
                    ],
                    "resourceVersion": "2583982",
                    "selfLink": "/api/v1/namespaces/initial/pods/galaxy-1584807903-galaxy-metrics-1585475760-9wtb6",
                    "uid": "fc99cc5c-db80-4493-85c9-7eaffbe980e3"
                },
                "spec": {
                    "containers": [
                        {
                            "image": "cloudve/galaxy-metrics-scraper:latest",
                            "imagePullPolicy": "IfNotPresent",
                            "name": "galaxy-metrics-scraper",
                        }
                    ],
                    "nodeName": "ip-10-0-24-156.ec2.internal",
                    "terminationGracePeriodSeconds": 30
                }
            }
        ]
        self.secrets = [
            {
                'apiVersion': 'v1',
                'data': {'POSTGRES_DATABASE': 'cm9vdA==',
                         'POSTGRES_HOST': 'a2V5Y2xvYWstcG9zdGdyZXNxbA==',
                         'POSTGRES_SUPERUSER': 'dHJ1ZQ==',
                         'oidc-client-secret': 'ZXhhbXBsZS1rZXljbG9hay1DTmY3eVhwY1M3UXZLM0JLZ0plejBTbV9xYTBXRG1aRnpFSzlhcXRmdlZJPQ=='},
                'kind': 'Secret',
                'metadata': {'creationTimestamp': '2020-07-10T15:55:57Z',
                             'labels': {'app': 'keycloak'},
                             'name': 'gvl-projman-secret',
                             'namespace': 'default',
                             'resourceVersion': '4664946',
                             'selfLink': '/api/v1/namespaces/default/secrets/keycloak-db-secret',
                             'uid': '48ae55dc-2bed-4bee-9720-28ae725e47f0'},
                'type': 'Opaque'
            }
        ]
        self.parser = self._create_parser()

    def _create_parser(self):
        parser = argparse.ArgumentParser(prog='kubectl')
        subparsers = parser.add_subparsers(help='Available Commands')

        # kubectl get
        parser_get = subparsers.add_parser('get', help='list')
        subparsers_get = parser_get.add_subparsers(help='Resources to get')
        # kubectl get namespaces
        parser_list_ns = subparsers_get.add_parser(
            'namespaces', help='List namespaces')
        parser_list_ns.set_defaults(func=self._kubectl_get_namespaces)
        # kubectl get nodes
        parser_list_nodes = subparsers_get.add_parser(
            'nodes', help='List Nodes')
        parser_list_nodes.add_argument('-o', choices=['yaml'], default="yaml")
        parser_list_nodes.set_defaults(func=self._kubectl_get_nodes)
        # kubectl get pods
        parser_list_pods = subparsers_get.add_parser(
            'pods', help='List Pods')
        parser_list_pods.add_argument(
            '--all-namespaces', action='store_true')
        parser_list_pods.add_argument(
            '--selector', type=str)
        parser_list_pods.add_argument(
            '--field-selector', type=str)
        parser_list_pods.add_argument('-o', choices=['yaml'], default="yaml")
        parser_list_pods.set_defaults(func=self._kubectl_get_pods)
        # kubectl get secrets
        parser_list_secrets = subparsers_get.add_parser(
            'secrets', help='List secrets')
        parser_list_secrets.add_argument('-o', choices=['yaml'], default="yaml")
        parser_list_secrets.add_argument('-n', "--namespace", default=None)
        parser_list_secrets.add_argument('name', default=None)
        parser_list_secrets.set_defaults(func=self._kubectl_get_secrets)

        # kubectl create
        parser_create = subparsers.add_parser('create', help='create')
        subparsers_create = parser_create.add_subparsers(
            help='Resources to create')
        # kubectl create namespace
        parser_create_ns = subparsers_create.add_parser('namespace',
                                                        help='create a namespace')
        parser_create_ns.add_argument(
            'namespace', type=str, help='namespace name')
        parser_create_ns.set_defaults(func=self._kubectl_create_namespace)

        # kubectl delete
        parser_delete = subparsers.add_parser('delete', help='delete')
        subparsers_delete = parser_delete.add_subparsers(
            help='Resources to create')
        # Kubectl delete namespace
        parser_delete_ns = subparsers_delete.add_parser(
            'namespace', help='delete a namespace')
        parser_delete_ns.add_argument(
            'namespace', type=str, help='namespace name')
        parser_delete_ns.set_defaults(func=self._kubectl_delete_namespace)
        # Kubectl delete node
        parser_delete_node = subparsers_delete.add_parser(
            'node', help='delete a node')
        parser_delete_node.add_argument(
            'node', type=str, help='node name')
        parser_delete_node.set_defaults(func=self._kubectl_delete_node)

        # kubectl cordon
        parser_cordon = subparsers.add_parser('cordon', help='cordon node')
        parser_cordon.add_argument(
            'node_name', type=str, help='node to cordon')
        parser_cordon.set_defaults(func=self._kubectl_cordon)

        def str2bool(v):
            if isinstance(v, bool):
                return v
            elif str(v).lower() in ('true',):
                return True
            elif str(v).lower() in ('false',):
                return False
            else:
                raise argparse.ArgumentTypeError('Boolean value expected.')

        # kubectl drain
        parser_drain = subparsers.add_parser('drain', help='drain node')
        parser_drain.add_argument(
            'node_name', type=str, help='node to cordon')
        parser_drain.add_argument(
            '--timeout', type=str, help='time to wait before giving up. e.g. 10s')
        parser_drain.add_argument(
            '--force', type=str2bool, default=False, help='continue even with unmanaged pods')
        parser_drain.add_argument(
            '--ignore-daemonsets', type=str2bool, default=True, help='ignore daemonsets')
        parser_drain.set_defaults(func=self._kubectl_drain)

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

    def _kubectl_get_nodes(self, args):
        # get a copy of the response template
        response = dict(self.list_template)
        # add node to template
        response['items'] = self.nodes
        with StringIO() as output:
            yaml.dump(response, stream=output, default_flow_style=False)
            return output.getvalue()

    def _kubectl_delete_node(self, args):
        # pretend to succeed
        pass

    def _kubectl_get_pods(self, args):
        # get a copy of the response template
        response = dict(self.list_template)
        self.request_counter += 1
        # every 2 responses, return an empty list
        if self.request_counter % 2 == 0:
            response['items'] = []
        else:
            response['items'] = self.pods
        with StringIO() as output:
            yaml.dump(response, stream=output, default_flow_style=False)
            return output.getvalue()

    def _kubectl_cordon(self, args):
        with StringIO() as output:
            output.write(f"node/{args.node_name} cordoned")
            return output.getvalue()

    def _kubectl_drain(self, args):
        with StringIO() as output:
            output.write(f"node/{args.node_name} drained")
            return output.getvalue()

    def _kubectl_get_secrets(self, args):
        if args.name:
            # Temporary workaround to always return a matching secret to the
            # name requested. This is because the secret should have been auto created
            # when the projman helm chart is installed, which we aren't doing in the mocker.
            secret = copy.deepcopy(self.secrets[0])
            secret.get('metadata')['name'] = args.name
            response = secret
        else:
            # get a copy of the response template
            response = dict(self.list_template)
            # add node to template
            response['items'] = self.secrets
        with StringIO() as output:
            yaml.dump(response, stream=output, default_flow_style=False)
            return output.getvalue()
