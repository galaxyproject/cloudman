from django.core.management.base import BaseCommand

from ...kubectl.client import KubeCtlClient


class Command(BaseCommand):
    help = 'Adds a new repository to helm'

    def add_arguments(self, parser):
        parser.add_argument('namespace')

    def handle(self, *args, **options):
        self.create_namespace(options['namespace'])

    @staticmethod
    def create_namespace(name):
        client = KubeCtlClient()
        client.namespaces.create_if_not_exists(name)
