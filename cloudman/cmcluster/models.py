from django.db import models

from cloudlaunch import models as cl_models


class CMCluster(models.Model):
    """CloudMan cluster details."""
    # Automatically add timestamps when object is created
    added = models.DateTimeField(auto_now_add=True)
    # Automatically add timestamps when object is updated
    updated = models.DateTimeField(auto_now=True)
    name = models.CharField(max_length=60)
    cluster_type = models.CharField(max_length=255, blank=False, null=False)
    connection_settings = models.TextField(
        max_length=1024 * 16, help_text="External provider specific settings "
        "for this cluster.", blank=True, null=True)


class CMClusterNode(models.Model):
    name = models.CharField(max_length=60)
    cluster = models.ForeignKey(CMCluster, on_delete=models.CASCADE,
                                null=False, related_name="node_list")
    # This introduces a tight coupling between the cloudlaunch and cloudman
    # models, although we go through the cloudlaunch API for everything else.
    # This may need to be changed to an IntegerField if we go for a fully
    # decoupled route.
    deployment = models.OneToOneField(
        cl_models.ApplicationDeployment, models.CASCADE,
        related_name="cm_cluster_node")

