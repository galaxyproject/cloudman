import argparse
import logging as log

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from ...api import HelmsManAPI, HMServiceContext


class Command(BaseCommand):
    help = 'Adds a new template to the install templates'

    def add_arguments(self, parser):
        parser.add_argument('name',
                            help='Name to give the install template')
        parser.add_argument('repo',
                            help='Which repo to install from (e.g. stable)')
        parser.add_argument('chart',
                            help='name of the chart to install (e.g. postgres)')
        parser.add_argument('--chart_ver', required=False,
                            help='version of chart to install. defaults'
                                 ' to latest')
        parser.add_argument('--template_file', required=False,
                            type=argparse.FileType('r'),
                            help='The jinja2 template to use to render final values')
        parser.add_argument('--context', required=False,
                            help='Default context values to use when'
                                 ' evaluating this jinja2 template')

    def handle(self, *args, **options):
        self.add_install_template(
            options['name'], options['repo'], options['chart'],
            options.get('chart_version'),
            options['template_file'].read() if options.get('template_file') else None,
            options.get('context'))

    @staticmethod
    def add_install_template(name, repo, chart, chart_version,
                             template, context):
        try:
            print(f"Adding template: {name}")
            admin = User.objects.filter(is_superuser=True).first()
            client = HelmsManAPI(HMServiceContext(user=admin))
            existing_template = client.templates.find(name)
            if existing_template:
                print(f"Template named: '{name}' for chart: '{repo}/{chart}'"
                      " already exists.")
            else:
                client.templates.create(name, repo, chart,
                                        chart_version, template,
                                        context)
                print(f"Successfully added template named: '{name}'"
                      f" for chart: '{repo}/{chart}'.")
        except Exception as e:
            log.exception("An error occurred while "
                          f"adding the template '{name}':", e)
            print(f"An error occurred while adding the template '{name}':",
                  str(e))
            raise e
