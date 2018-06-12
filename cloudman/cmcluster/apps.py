from django.apps import AppConfig
from .cluster_templates import CMRancherTemplate


class CmClusterConfig(AppConfig):
    name = 'cmcluster'

    def ready(self):
        print("Setting up kube environment")
        CMRancherTemplate(context=None, cluster=None).setup()
        print("kube environment successfully setup")
