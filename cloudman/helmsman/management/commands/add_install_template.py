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
        parser.add_argument('--chart_version', required=False,
                            help='version of chart to install. defaults'
                                 ' to latest')
        parser.add_argument('--template_file', required=False,
                            type=argparse.FileType('r'),
                            help='The jinja2 template to use to render final values')
        parser.add_argument('--context', required=False,
                            help='Default context values to use when'
                                 ' evaluating this jinja2 template')
        parser.add_argument('--display_name', required=False,
                            help='chart display name')
        parser.add_argument('--summary', required=False,
                            help='chart summary')
        parser.add_argument('--description', required=False,
                            help='chart description')
        parser.add_argument('--maintainers', required=False,
                            help='chart maintainers')
        parser.add_argument('--info_url', required=False,
                            help='chart info url')
        parser.add_argument('--icon_url', required=False,
                            help='chart icon url')
        parser.add_argument('--screenshot_url', required=False,
                            help='chart screenshot url')
        parser.add_argument('--upgrade', dest='upgrade_template',
                            action='store_true',
                            help='upgrade template if it already exists')

    def handle(self, *args, **options):
        self.add_install_template(
            options['name'], options['repo'], options['chart'],
            options.get('chart_version'),
            options['template_file'].read() if options.get('template_file') else None,
            options.get('context'),
            options.get('display_name'),
            options.get('summary'),
            options.get('description'),
            options.get('maintainers'),
            options.get('info_url'),
            options.get('icon_url'),
            options.get('screenshot_url'),
            options.get('upgrade_template'))

    @staticmethod
    def add_install_template(name, repo, chart, chart_version, template,
                             context, display_name, summary, description,
                             maintainers, info_url, icon_url, screenshot_url,
                             upgrade_template):
        try:
            print(f"Adding template: {name}")
            admin = User.objects.filter(is_superuser=True).first()
            client = HelmsManAPI(HMServiceContext(user=admin))
            existing_template = client.templates.find(name=name)
            if existing_template:
                print(f"Template named: '{name}' for chart: '{repo}/{chart}'"
                      " already exists.")
            else:
                client.templates.create(
                    name, repo, chart, chart_version, template, context,
                    display_name=display_name, summary=summary,
                    description=description, maintainers=maintainers,
                    info_url=info_url, icon_url=icon_url, screenshot_url=screenshot_url)
                print(f"Successfully added template named: '{name}'"
                      f" for chart: '{repo}/{chart}'.")
        except Exception as e:
            log.exception("An error occurred while "
                          f"adding the template '{name}':", e)
            print(f"An error occurred while adding the template '{name}':",
                  str(e))
            raise e
