import argparse
import tempfile
import yaml

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Loads helmsman config data from a yaml file'

    def add_arguments(self, parser):
        parser.add_argument('config_file', type=argparse.FileType('r'))

    def handle(self, *args, **options):
        settings = yaml.safe_load(options['config_file'].read())
        self.process_settings(settings)

    @staticmethod
    def process_settings(settings):
        for repo in settings.get('repositories'):
            call_command("add_repo", repo.get('name'), repo.get('url'))

        for template_name in settings.get('install_templates', {}):
            template = settings.get('install_templates', {}).get(template_name)
            call_command("add_template", template_name,
                         template.get('repo'), template.get('chart'),
                         template.get('chart_version'),
                         template.get('context') or '',
                         template.get('macros'), template.get('values'))

        for chart in settings.get('charts', {}).values():
            extra_args = {}
            if chart.get('namespace'):
                extra_args["namespace"] = chart.get('namespace')
                if chart.get('create_namespace'):
                    extra_args['create_namespace'] = True
            if chart.get('version'):
                extra_args["chart_version"] = chart.get('version')
            if chart.get('values'):
                values = chart.get('values')
                with tempfile.NamedTemporaryFile(mode="w", prefix="helmsman") as f:
                    yaml.dump(values, stream=f, default_flow_style=False)
                    extra_args["values_file"] = f.name
                    call_command("add_chart", chart.get('name'), **extra_args)
            else:
                call_command("add_chart", chart.get('name'), **extra_args)
