import logging as log

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from ...api import HelmsManAPI, HMServiceContext


class Command(BaseCommand):
    help = 'Adds a new template to the install templates'

    def add_arguments(self, parser):
        parser.add_argument('name')
        parser.add_argument('repo')
        parser.add_argument('chart')
        parser.add_argument('chart_version')
        parser.add_argument('context')
        parser.add_argument('macros')
        parser.add_argument('values')

    def handle(self, *args, **options):
        self.add_template(options['name'], options['repo'],
                          options['chart'], options['chart_version'],
                          options['context'], options['macros'],
                          options['values'])

    @staticmethod
    def add_template(name, repo, chart, chart_version,
                     context, macros, values):
        try:
            print("Adding template: {0}".format(name))
            admin = User.objects.filter(is_superuser=True).first()
            client = HelmsManAPI(HMServiceContext(user=admin))
            if not client.templates.find(name):
                client.templates.create(name, repo, chart,
                                        chart_version, context,
                                        macros, values)
                print("Successfully added {} template \
                       for '{}/{}' chart.".format(name, repo, chart))
            else:
                return client.templates.find(name)
        except Exception as e:
            log.exception(f"An error occurred while "
                          f"adding the template '{name}':", e)
            print(f"An error occurred while adding the template '{name}':",
                  str(e))
            # Re-raise the exception
            raise e
