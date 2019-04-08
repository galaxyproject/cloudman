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
                CMRancherTemplate(context=None, cluster=None).setup()
                print("kube environment successfully setup")
        except Exception as e:
            log.exception("CmClusterConfig.ready()->CMRancherTemplate.setup(): "
                          "An error occurred while setting up Rancher!!:")
            print("CmClusterConfig.ready()->CMRancherTemplate.setup(): "
                  "An error occurred while setting up Rancher!!: ", e)
