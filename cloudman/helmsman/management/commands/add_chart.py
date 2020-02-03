import yaml

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from ...api import HelmsManAPI, HMServiceContext
from ...api import ChartExistsException, NamespaceNotFoundException


class Command(BaseCommand):
    help = 'Adds a new repository to helm'

    def add_arguments(self, parser):
        parser.add_argument('chart_ref',
                            help='Reference to a chart e.g. cloudve/cloudman')
        parser.add_argument('--namespace', required=True,
                            help='namespace to install chart into')
        parser.add_argument('--release_name', required=False,
                            help='name to give release')
        parser.add_argument('--chart_ver', required=False,
                            help='version of chart to install. defaults'
                                 ' to latest')
        parser.add_argument('--values_file', required=False,
                            help='Values file to apply to the chart')
        parser.add_argument('--create_namespace', dest='create_namespace',
                            action='store_true',
                            help='attempt to create namespace if not found')

    def handle(self, *args, **options):
        self.add_chart(options['chart_ref'], options['namespace'],
                       options['release_name'], options['chart_ver'],
                       options['values_file'], options['create_namespace'])

    @staticmethod
    def add_chart(chart_ref, namespace, release_name, version, values_file,
                  create_namespace):
        Command.install_if_not_exist(chart_ref, namespace, release_name,
                                     version, values_file, create_namespace)

    @staticmethod
    def install_if_not_exist(chart_ref, namespace, release_name,
                             version, values_file, create_namespace):
        admin = User.objects.filter(is_superuser=True).first()
        client = HelmsManAPI(HMServiceContext(user=admin))
        repo_name, chart_name = chart_ref.split("/")
        values = None
        if values_file:
            with open(values_file, 'r') as f:
                values = yaml.safe_load(f)
        if not client.namespaces.get(namespace):
            print(f"Namespace '{namespace}' not found.")
            if create_namespace:
                print(f"Creating Namespace '{namespace}'.")
                client.namespaces.create(namespace)
            else:
                message = (f"Namespace {namespace} does not exist. "
                           f"Use the '--create_namespace' flag if you have "
                           f"appropriate permissions.")
                raise NamespaceNotFoundException(message)
        print(f"Installing chart {repo_name}/{chart_name} into namespace"
              f" {namespace}")
        try:
            client.charts.create(repo_name, chart_name, namespace,
                                 release_name, version, values)
        except ChartExistsException as e:
            print(f"Chart {repo_name}/{chart_name} already installed.")
