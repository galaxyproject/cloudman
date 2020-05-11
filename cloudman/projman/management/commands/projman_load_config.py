import argparse
import tempfile
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
                proj = call_command("projman_create_project", project)
                charts = projects.get(project).get('charts', [])
                for chart in charts:
                    template = charts.get(chart).get("install_template")
                    if template:
                        release_name = charts.get(chart).get("release_name")
                        values = charts.get(chart).get("values")
                        context = charts.get(chart).get("context")
                        proj.charts.install_template(template,
                                                     release_name=release_name,
                                                     values=values,
                                                     **context)
