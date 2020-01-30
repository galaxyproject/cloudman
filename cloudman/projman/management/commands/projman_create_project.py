import logging as log

from django.core.management import call_command
from django.core.management.base import BaseCommand

from django.contrib.auth.models import User

from ...api import HelmsManAPI, HMServiceContext
from helmsman.api import NamespaceExistsException


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
            from projman import api
            admin = User.objects.filter(is_superuser=True).first()
            pmapi = api.ProjManAPI(api.PMServiceContext(user=admin))
            client = HelmsManAPI(HMServiceContext(user=admin))
            if not pmapi.projects.find(name):
                if name in client.namespaces.list_names():
                    message = (f"The project '{name}' could not be created."
                               f"A namespace by the same name already exists.")
                    raise NamespaceExistsException(message)
                else:
                    client.namespaces.create(name)
                pmapi.projects.create(name)
                print("Project created successfully.")
        except Exception as e:
            log.exception(f"An error occurred while "
                          f"creating the project '{name}':", e)
            print(f"An error occurred while creating the project '{name}':", e)
