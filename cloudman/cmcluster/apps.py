from django.apps import AppConfig
from .cluster_templates import CMRancherTemplate


class CmClusterConfig(AppConfig):
    name = 'cmcluster'

    def ready(self):
        try:
            print("Setting up kube environment")
            CMRancherTemplate(context=None, cluster=None).setup()
            print("kube environment successfully setup")
        except Exception as e:
            print("CmClusterConfig.ready()->CMRancherTemplate.setup(): "
                  "An error occurred while setting up Rancher!!: ", e)
