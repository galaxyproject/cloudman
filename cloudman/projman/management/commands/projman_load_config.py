import argparse
import yaml

from django.core.management import call_command
from django.core.management.base import BaseCommand

from helmsman import helpers


class Command(BaseCommand):
    help = 'Loads projman config data from a yaml file'

    def add_arguments(self, parser):
        parser.add_argument('config_file', type=argparse.FileType('r'))

    def handle(self, *args, **options):
        settings = yaml.safe_load(options['config_file'].read())
        self.process_settings(settings or {})

    @staticmethod
    def process_settings(settings):
        projects = settings.get('projects')
        for project in projects or {}:
            if project:
                call_command("projman_create_project", project)
                charts = projects.get(project, {}).get('charts', [])
                for key in charts or []:
                    chart = charts.get(key)
                    template = chart.get("install_template")
                    if template:
                        release_name = chart.get("release_name", '')
                        values = chart.get("values", '')
                        context = chart.get("context", '')
                        extra_args = []
                        if chart.get("upgrade"):
                            extra_args += ['--upgrade']
                        if chart.get("reset_values"):
                            extra_args += ['--reset_values']
                        with helpers.TempValuesFile(values) as values_file:
                            with helpers.TempValuesFile(context) as context_file:
                                call_command("install_template_in_project",
                                             project, template,
                                             release_name,
                                             values_file.name,
                                             context_file.name,
                                             *extra_args)
