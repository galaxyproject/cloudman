import logging as log
import os

from django.apps import AppConfig


class CmClusterConfig(AppConfig):
    name = 'cmcluster'

    def ready(self):
        # FIXME: Hack to download the initial kube config file
        # Both this and helmsman data import should be done as part of a
        # startup script
        if os.environ.get("HELMSMAN_AUTO_DEPLOY"):
            try:
                from cmcluster import api
                cmapi = api.CloudManAPI(api.CMServiceContext(user="admin"))
                print("Setting up kube environment")
                clusters = cmapi.clusters.list()
                template = cmapi.clusters.get_cluster_template(clusters[0])
                template.setup()
                print("kube environment successfully setup")
            except Exception as e:
                log.exception("CmClusterConfig.ready()->CMRancherTemplate.setup(): "
                              "An error occurred while setting up Rancher!!:")
                print("CmClusterConfig.ready()->CMRancherTemplate.setup(): "
                      "An error occurred while setting up Rancher!!: ", e)
