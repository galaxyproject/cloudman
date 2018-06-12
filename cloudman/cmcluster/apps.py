from django.apps import AppConfig
from .cluster_templates import CMRancherTemplate


class CmClusterConfig(AppConfig):
    name = 'cmcluster'

    def ready(self):
        CMRancherTemplate(context=None, cluster=None).setup()
