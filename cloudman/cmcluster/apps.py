import os
import logging as log
from django.apps import AppConfig
from .cluster_templates import CMRancherTemplate


class CmClusterConfig(AppConfig):
    name = 'cmcluster'

    def ready(self):
        try:
            if os.environ.get("HELMSMAN_AUTO_DEPLOY"):
                print("Setting up kube environment")
                from . import api
                cmapi = api.CloudManAPI(api.CMServiceContext(user="admin"))
                settings = {
                    'rancher_url': os.environ.get('RANCHER_URL'),
                    'rancher_api_key': os.environ.get('RANCHER_API_KEY'),
                    'rancher_cluster_id': os.environ.get('RANCHER_CLUSTER_ID'),
                    'rancher_project_id': os.environ.get('RANCHER_PROJECT_ID')
                }
                cmapi.clusters.create("default", "KUBE_RANCHER",
                                      connection_settings=settings)
                print("kube environment successfully setup")
        except Exception as e:
            log.exception("CmClusterConfig.ready()->CMRancherTemplate.setup(): "
                          "An error occurred while setting up Rancher!!:")
            print("CmClusterConfig.ready()->CMRancherTemplate.setup(): "
                  "An error occurred while setting up Rancher!!: ", e)
