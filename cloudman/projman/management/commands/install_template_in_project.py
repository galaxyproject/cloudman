import logging as log
import yaml

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

from helmsman.api import ChartExistsException

from ...api import ProjManAPI, PMServiceContext


class Command(BaseCommand):
    help = 'Installs a template in a project.'

    def add_arguments(self, parser):
        parser.add_argument('project_name')
        parser.add_argument('template_name')
        parser.add_argument('release_name')
        parser.add_argument('values_file', help='Values file to apply to the chart')
        parser.add_argument('context_file', help='Context to apply to the chart')
        parser.add_argument('--upgrade', dest='upgrade_chart', action='store_true')

    def handle(self, *args, **options):
        values_file = options.get("values_file")
        if values_file:
            with open(values_file, 'r') as f:
                values = yaml.safe_load(f)
        else:
            values = {}
        context_file = options.get("context_file")
        if context_file:
            with open(context_file, 'r') as f:
                context = yaml.safe_load(f)
        else:
            context = {}
        self.install_template_in_project(options['project_name'],
                                         options['template_name'],
                                         options['release_name'],
                                         values,
                                         context=context,
                                         upgrade_chart=options['upgrade_chart'])

    @staticmethod
    def install_template_in_project(project_name, template_name,
                                    release_name=None, values=None, context=None,
                                    upgrade_chart=False):
        try:
            print("Installing template {}"
                  " into project: {}".format(template_name, project_name))
            admin = User.objects.filter(is_superuser=True).first()
            pmapi = ProjManAPI(PMServiceContext(user=admin))
            proj = pmapi.projects.find(project_name)
            if not proj:
                print("Cannot find project {}.")
                return None
            try:
                existing = proj.charts.find(release_name or template_name)
                if existing and upgrade_chart:
                    ch = proj.charts.update(existing, values, context=context)
                    print(f"Successfully updated template '{template_name}' "
                          f"with release named '{release_name}' into project "
                          f"'{project_name}'")
                else:
                    ch = proj.charts.create(template_name,
                                            release_name,
                                            values, context)
                    print(f"Successfully installed template '{template_name}' "
                          f"with release named '{release_name}' into project "
                          f"'{project_name}'")
                return ch
            except ChartExistsException as ce:
                log.warning(str(ce))
                print(str(ce))

        except Exception as e:
            log.exception(f"An error occurred while "
                          f"installing template '{template_name}' "
                          f"into project '{project_name}'", e)
            print(f"Error occurred while installing template '{template_name}' "
                  f"into project '{project_name}'", str(e))
            # Re-raise the exception
            raise e
