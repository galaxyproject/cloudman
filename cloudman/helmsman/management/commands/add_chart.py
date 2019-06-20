import yaml

from django.core.management.base import BaseCommand

from ...helm.client import HelmClient


class Command(BaseCommand):
    help = 'Adds a new repository to helm'

    def add_arguments(self, parser):
        parser.add_argument('chart_ref',
                            help='Reference to the chart. e.g. cloudve/cloudman')
        parser.add_argument('--namespace', default="default", required=False,
                            help='namespace to install chart into')
        parser.add_argument('--release_name', required=False,
                            help='name to give release')
        parser.add_argument('--chart_ver', required=False,
                            help='version of chart to install. defaults'
                                 ' to latest')
        parser.add_argument('--values_file', required=False,
                            help='Values file to apply to the chart')

    def handle(self, *args, **options):
        self.add_chart(options['chart_ref'], options['namespace'],
                       options['release_name'], options['chart_ver'],
                       options['values_file'])

    @staticmethod
    def add_chart(chart_ref, namespace, release_name, version, values_file):
        client = HelmClient()
        Command.install_if_not_exist(client, chart_ref, namespace, release_name,
                                     version, values_file)

    @staticmethod
    def install_if_not_exist(client, chart_ref, namespace, release_name,
                             version, values_file):
        repo_name, chart_name = chart_ref.split("/")
        existing_release = [r for r in client.releases.list()
                            if chart_name == client.releases.parse_chart_name(r.get('CHART'))]
        if existing_release:
            print(f"Chart {repo_name}/{chart_name} already installed.")
        else:
            client.repositories.update()
            print(f"Installing chart {repo_name}/{chart_name} into namespace"
                  f" {namespace}")
            if values_file:
                with open(values_file, 'r') as f:
                    values = yaml.safe_load(f)
            else:
                values = None
            client.releases.create(f"{repo_name}/{chart_name}", namespace,
                                   release_name=release_name, version=version,
                                   values=values)
