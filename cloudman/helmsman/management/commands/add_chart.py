import yaml

from django.core.management.base import BaseCommand

from ...api import HelmsManAPI, ChartExistsException


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
        Command.install_if_not_exist(chart_ref, namespace, release_name,
                                     version, values_file)

    @staticmethod
    def install_if_not_exist(chart_ref, namespace, release_name,
                             version, values_file):
        client = HelmsManAPI()
        repo_name, chart_name = chart_ref.split("/")
        values = None
        if values_file:
            with open(values_file, 'r') as f:
                values = yaml.safe_load(f)
        print(f"Installing chart {repo_name}/{chart_name} into namespace"
              f" {namespace}")
        try:
            client.charts.create(repo_name, chart_name, namespace,
                                 release_name, version, values)
        except ChartExistsException as e:
            print(f"Chart {repo_name}/{chart_name} already installed.")
