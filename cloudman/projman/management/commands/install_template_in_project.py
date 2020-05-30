import logging as log

from django.core.management.base import BaseCommand

from django.contrib.auth.models import User

from ...api import ProjManAPI, PMServiceContext


class Command(BaseCommand):
    help = 'Installs a template in a project.'

    def add_arguments(self, parser):
        parser.add_argument('project_name')
        parser.add_argument('template_name')
        parser.add_argument('release_name')
        parser.add_argument('values')
        parser.add_argument('context')

    def handle(self, *args, **options):
        context = options.get("context")
        if not context:
            context = {}
        self.install_template_in_project(options['project_name'],
                                         options['template_name'],
                                         options['release_name'],
                                         options['values'],
                                         context=context)

    @staticmethod
    def install_template_in_project(project_name, template_name,
                                    release_name=None, values=None, context=None):
        try:
            print("Installing template {}"
                  " into project: {}".format(template_name, project_name))
            admin = User.objects.filter(is_superuser=True).first()
            pmapi = ProjManAPI(PMServiceContext(user=admin))
            proj = pmapi.projects.find(project_name)
            if not proj:
                print("Cannot find project {}.")
                return None
            elif proj.charts.find(release_name):
                print("A release already exists in project '{}'"
                      " with name '{}'".format(project_name, release_name))
            else:
                ch = proj.charts.create(template_name,
                                        release_name,
                                        values, context)
                print(f"Successfully installed template '{template_name}' "
                      f"with release named '{release_name}' into project "
                      f"'{project_name}'")
                return ch
        except Exception as e:
            log.exception(f"An error occurred while "
                          f"installing template '{template_name}' "
                          f"into project '{project_name}'", e)
            print(f"Error occurred while installing template '{template_name}' "
                  f"into project '{project_name}'", str(e))
            # Re-raise the exception
            raise e
