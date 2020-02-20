from django.db import models

from cloudlaunch import models as cl_models
from djcloudbridge import models as cb_models
import yaml


class CMCluster(models.Model):
    """CloudMan cluster details."""
    # Automatically add timestamps when object is created
    added = models.DateTimeField(auto_now_add=True)
    # Automatically add timestamps when object is updated
    updated = models.DateTimeField(auto_now=True)
    name = models.CharField(max_length=60)
    cluster_type = models.CharField(max_length=255, blank=False, null=False)
    autoscale = models.BooleanField(
        default=True, help_text="Whether autoscaling is activated")
    _connection_settings = models.TextField(
        max_length=1024 * 16, help_text="External provider specific settings "
        "for this cluster.", blank=True, null=True,
        db_column='connection_settings')

    @property
    def connection_settings(self):
        return yaml.safe_load(self._connection_settings)

    @connection_settings.setter
    def connection_settings(self, value):
        """
        Save the connection_settings value.

        .. seealso:: connection_settings property getter
        """
        self._connection_settings = yaml.dump(value, default_flow_style=False)

    class Meta:
        verbose_name = "Cluster"
        verbose_name_plural = "Clusters"


class CMAutoScaler(models.Model):
    name = models.CharField(max_length=60)
    cluster = models.ForeignKey(CMCluster, on_delete=models.CASCADE,
                                null=False, related_name="autoscaler_list")
    vm_type = models.CharField(max_length=200)
    zone = models.ForeignKey(cb_models.Zone, on_delete=models.CASCADE,
                             null=False, related_name="autoscaler_list")
    min_nodes = models.IntegerField(default=0)
    max_nodes = models.IntegerField(default=None, null=True)

    class Meta:
        verbose_name = "Cluster Autoscaler"
        verbose_name_plural = "Cluster Autoscalers"
        unique_together = (("cluster", "name"),)


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
    autoscaler = models.ForeignKey(
        CMAutoScaler, on_delete=models.CASCADE, null=True,
        related_name="nodegroup")

    class Meta:
        verbose_name = "Cluster Node"
        verbose_name_plural = "Cluster Nodes"
