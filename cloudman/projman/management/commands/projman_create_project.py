import logging as log

from django.core.management.base import BaseCommand

from django.contrib.auth.models import User

from ...api import ProjManAPI, PMServiceContext


class Command(BaseCommand):
    help = 'Creates a ProjMan project.'

    def add_arguments(self, parser):
        parser.add_argument('name')

    def handle(self, *args, **options):
        name = options['name']
        self.create_project(name)

    @staticmethod
    def create_project(name):
        try:
            print("Creating project: {0}".format(name))
            admin = User.objects.filter(is_superuser=True).first()
            pmapi = ProjManAPI(PMServiceContext(user=admin))
            if not pmapi.projects.find(name):
                proj = pmapi.projects.create(name)
                print("Project created successfully.")
                return proj
            else:
                return pmapi.projects.find(name)
        except Exception as e:
            log.exception(f"An error occurred while "
                          f"creating the project '{name}':", e)
            print(f"An error occurred while creating the project '{name}':", str(e))
            # Re-raise the exception
            raise e
