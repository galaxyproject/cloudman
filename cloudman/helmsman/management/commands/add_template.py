from django.core.management.base import BaseCommand

from ...clients.helm_client import HelmClient


class Command(BaseCommand):
    help = 'Adds a new template to the install templates'

    def add_arguments(self, parser):
        parser.add_argument('name')
        parser.add_argument('repo')
        parser.add_argument('chart')
        parser.add_argument('chart_version')
        parser.add_argument('macros')
        parser.add_argument('values')

    def handle(self, *args, **options):
        self.add_template(options['name'], options['repo'],
                       options['chart'], options['chart_version'],
                       options['macros'], options['values'])

    @staticmethod
    def add_template(name, repo, chart, chart_version, macros, values):
        admin = User.objects.filter(is_superuser=True).first()
        client = HelmsManAPI(HMServiceContext(user=admin))
        client.templates.create(name, repo, chart, chart_version, macros, values)
        print("Successfully installed {} template for '{}/{}' chart.".format(name, repo, chart))
