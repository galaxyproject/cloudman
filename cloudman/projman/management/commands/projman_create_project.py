import logging as log

from django.core.management.base import BaseCommand

from django.contrib.auth.models import User


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
            if not pmapi.projects.find(name):
                pmapi.projects.create(name)
                print("Project created successfully.")
        except Exception as e:
            log.exception("An error occurred while creating the initial project!!:")
            print("An error occurred while creating the initial project!!:", e)
