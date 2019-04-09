import argparse
import logging as log
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
        for chart in settings.get('charts'):
            extra_args = {}
            if chart.get('namespace'):
                extra_args["--namespace"] = chart.get('namespace')
            if chart.get('version'):
                extra_args["--version"] = chart.get('version')
            call_command("add_chart", chart.get('name'), **extra_args)
