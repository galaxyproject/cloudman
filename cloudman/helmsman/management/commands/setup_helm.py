import argparse
import logging as log
import yaml

from django.core.management.base import BaseCommand

from ...helm.client import HelmClient


class Command(BaseCommand):
    help = 'Installs and initializes helm/tiller'

    def handle(self, *args, **options):
        self.setup_helm()

    @staticmethod
    def setup_helm():
        client = HelmClient()
        print("Setting up roles and installing helm/tiller...")
        client.install_helm()
