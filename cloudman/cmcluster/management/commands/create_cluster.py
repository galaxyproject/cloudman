import argparse
import logging as log
import yaml

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Creates a CloudMan cluster. Currently supported cluster' \
           'types: RANCHER_KUBE. Specify rancher connection settings in yaml' \
           'format in the settings_file.'

    def add_arguments(self, parser):
        parser.add_argument('name')
        parser.add_argument('cluster_type')
        parser.add_argument('settings_file', type=argparse.FileType('r'))

    def handle(self, *args, **options):
        name = options['name']
        cluster_type = options['cluster_type']
        settings = yaml.safe_load(options['settings_file'].read())
        self.create_cluster(name, cluster_type, settings)

    @staticmethod
    def create_cluster(name, cluster_type, settings):
        try:
            print("Setting up kube environment")
            from cmcluster import api
            cmapi = api.CloudManAPI(api.CMServiceContext(user="admin"))
            cmapi.clusters.create("default", "KUBE_RANCHER",
                                  connection_settings=settings)
            print("kube environment successfully setup")
        except Exception as e:
            log.exception("CmClusterConfig.ready()->CMRancherTemplate.setup(): "
                          "An error occurred while setting up Rancher!!:")
            print("CmClusterConfig.ready()->CMRancherTemplate.setup(): "
                  "An error occurred while setting up Rancher!!: ", e)
