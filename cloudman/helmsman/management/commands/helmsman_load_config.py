import argparse
import yaml

from django.core.management import call_command
from django.core.management.base import BaseCommand

from helmsman import helpers
from helmsman.management.commands.add_template_registry import Command as TplCommand


class Command(BaseCommand):
    help = 'Loads helmsman config data from a yaml file'

    def add_arguments(self, parser):
        parser.add_argument('config_file', type=argparse.FileType('r'))

    def handle(self, *args, **options):
        settings = yaml.safe_load(options['config_file'].read())
        self.process_settings(settings)

    @staticmethod
    def process_settings(settings):
        if settings.get('repositories'):
            Command.process_helm_repos(settings.get('repositories'))

        if settings.get('template_registries'):
            Command.process_template_registries(settings.get('template_registries'))

        if settings.get('install_templates'):
            TplCommand.process_install_templates(settings.get('install_templates'))

        if settings.get('charts'):
            Command.process_helm_charts(settings.get('charts'))

    @staticmethod
    def process_helm_repos(repositories):
        for repo in repositories:
            call_command("add_repo", repo.get('name'), repo.get('url'))

    @staticmethod
    def process_template_registries(template_registries):
        for registry in template_registries:
            call_command("add_template_registry", registry.get('name'), registry.get('url'))

    @staticmethod
    def process_helm_charts(charts):
        for chart in charts.values():
            extra_args = {}
            if chart.get('namespace'):
                extra_args["namespace"] = chart.get('namespace')
                if chart.get('create_namespace'):
                    extra_args['create_namespace'] = True
            if chart.get('version'):
                extra_args["chart_version"] = chart.get('version')
            if chart.get('upgrade'):
                extra_args["upgrade"] = True
            if chart.get('values'):
                values = chart.get('values')
                with helpers.TempValuesFile(values) as f:
                    extra_args["values_file"] = f.name
                    call_command("add_chart", chart.get('name'), **extra_args)
            else:
                call_command("add_chart", chart.get('name'), **extra_args)
