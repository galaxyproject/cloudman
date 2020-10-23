import logging as log
import requests
import yaml

from django.core.management import call_command
from django.core.management.base import BaseCommand

from helmsman import helpers


class Command(BaseCommand):
    help = 'Adds a new template registry to cloudman'

    def add_arguments(self, parser):
        parser.add_argument('name', help='Name of the template registry')
        parser.add_argument('url', help='Url to the template registry')

    def handle(self, *args, **options):
        self.add_template_registry(options['name'], options['url'])

    @staticmethod
    def add_template_registry(name, url):
        print(f"Importing template registry: {name} from: {url}")
        try:
            with requests.get(url) as r:
                registry = yaml.safe_load(r.content)
                if registry.get('install_templates'):
                    Command.process_install_templates(registry.get('install_templates'))
        except Exception as e:
            log.exception(f"An error occurred while importing registry '{name}':", e)
            print(f"An error occurred while importing registry '{name}':", str(e))
            raise e

    @staticmethod
    def process_install_templates(install_templates):
        for template_name in install_templates:
            template = install_templates.get(template_name)
            extra_args = []
            if template.get('chart_version'):
                extra_args += ["--chart_version", template.get('chart_version')]
            if template.get('context'):
                extra_args += ["--context", template.get('context')]
            if template.get('display_name'):
                extra_args += ["--display_name", template.get('display_name')]
            if template.get('summary'):
                extra_args += ["--summary", template.get('summary')]
            if template.get('description'):
                extra_args += ["--description", template.get('description')]
            if template.get('maintainers'):
                extra_args += ["--maintainers", template.get('maintainers')]
            if template.get('info_url'):
                extra_args += ["--info_url", template.get('info_url')]
            if template.get('icon_url'):
                extra_args += ["--icon_url", template.get('icon_url')]
            if template.get('screenshot_url'):
                extra_args += ["--screenshot_url", template.get('screenshot_url')]
            if template.get('upgrade'):
                extra_args += ["--upgrade"]
            if template.get('template'):
                with helpers.TempInputFile(template.get('template')) as f:
                    extra_args += ["--template_file", f.name]
                    call_command("add_install_template", template_name,
                                 template.get('repo'), template.get('chart'),
                                 *extra_args)
            else:
                call_command("add_install_template", template_name,
                             template.get('repo'), template.get('chart'),
                             *extra_args)

