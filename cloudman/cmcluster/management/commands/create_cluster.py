import argparse
import base64
import logging as log
import json
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
        parser.add_argument('--format', required=False, default="yaml",
                            choices=['yaml', 'json', 'base64yaml'],
                            help='Format that the data is encoded in')

    def handle(self, *args, **options):
        name = options['name']
        cluster_type = options['cluster_type']
        data = options['settings_file'].read()
        format = options['format']
        if format == "base64yaml":
            # Pad data: https://gist.github.com/perrygeo/ee7c65bb1541ff6ac770
            data = base64.b64decode(data + "===").decode('utf-8')

        if format == "json":
            settings = json.loads(data)
        elif format == "yaml" or format == "base64yaml":
            settings = yaml.safe_load(data)

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
