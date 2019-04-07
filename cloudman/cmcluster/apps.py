import os
import base64
import json
import logging as log
from django.apps import AppConfig
from .cluster_templates import CMRancherTemplate


class CmClusterConfig(AppConfig):
    name = 'cmcluster'

    def ready(self):
        try:
            env_bootstrap = os.environ.get("CM_BOOTSTRAP_DATA")
            if env_bootstrap:
                data = base64.b64decode(env_bootstrap).decode('utf-8')
                self.import_bootstrap_data(json.loads(data))
            if os.environ.get("HELMSMAN_AUTO_DEPLOY"):
                print("Setting up kube environment")
                CMRancherTemplate(context=None, cluster=None).setup()
                print("kube environment successfully setup")
        except Exception as e:
            log.exception("CmClusterConfig.ready()->CMRancherTemplate.setup(): "
                          "An error occurred while setting up Rancher!!:")
            print("CmClusterConfig.ready()->CMRancherTemplate.setup(): "
                  "An error occurred while setting up Rancher!!: ", e)

    def import_bootstrap_data(self, json_data):
        pass
