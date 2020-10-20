import argparse
import yaml

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Loads projman config data from a yaml file'

    def add_arguments(self, parser):
        parser.add_argument('config_file', type=argparse.FileType('r'))

    def handle(self, *args, **options):
        settings = yaml.safe_load(options['config_file'].read())
        self.process_settings(settings)

    @staticmethod
    def process_settings(settings):
        projects = settings.get('projects')
        for project in projects:
            if project:
                call_command("projman_create_project", project)
                charts = projects.get(project).get('charts', [])
                for key in charts:
                    chart = charts.get(key)
                    template = chart.get("install_template")
                    if template:
                        release_name = chart.get("release_name", '')
                        values = yaml.safe_load(chart.get("values", '')) or ''
                        context = yaml.safe_load(chart.get("context", '')) or ''
                        upgrade = chart.get("upgrade")
                        call_command("install_template_in_project",
                                     project, template,
                                     release_name,
                                     values, context)
