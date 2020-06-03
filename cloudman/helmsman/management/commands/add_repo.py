from django.core.management.base import BaseCommand

from ...clients.helm_client import HelmClient


class Command(BaseCommand):
    help = 'Adds a new repository to helm'

    def add_arguments(self, parser):
        parser.add_argument('name', help='Name of the repository')
        parser.add_argument('url', help='Url to the repository')

    def handle(self, *args, **options):
        self.add_chart(options['name'], options['url'])

    @staticmethod
    def add_chart(name, url):
        client = HelmClient()
        client.repositories.create(name, url)
