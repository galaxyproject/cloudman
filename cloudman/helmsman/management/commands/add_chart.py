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

    def handle(self, *args, **options):
        self.add_chart(options['chart_ref'], options['namespace'],
                       options['release_name'], options['chart_ver'])

    @staticmethod
    def add_chart(chart_ref, namespace, release_name, version):
        client = HelmClient()
        Command.install_if_not_exist(client, chart_ref, namespace, release_name,
                                     version)

    @staticmethod
    def install_if_not_exist(client, chart_ref, namespace, release_name,
                                     version):
        repo_name, chart_name = chart_ref.split("/")
        existing_release = [r for r in client.releases.list()
                            if chart_name == client.releases.parse_chart_name(r.get('CHART'))]
        if existing_release:
            print(f"Chart {repo_name}/{chart_name} already installed.")
        else:
            client.repositories.update()
            print(f"Installing chart {repo_name}/{chart_name} into namespace"
                  f" {namespace}")
            client.releases.create(f"{repo_name}/{chart_name}", namespace,
                                   release_name=release_name, version=version)
