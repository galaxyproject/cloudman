"""CloudMan Service API."""
from cloudlaunch import models as cl_models
from . import models


class CloudManAPI(object):

    def __init__(self):
        self._clusters = CMClusterService(self)

    @property
    def clusters(self):
        return self._clusters


class CMService(object):
    """Marker interface for CloudMan services"""
    pass


class CMClusterService(CMService):

    def __init__(self, api):
        super(CMClusterService, self).__init__()
        self.api = api

    def list(self):
        return models.CMCluster.objects.all()

    def get(self, cluster_id):
        return models.CMCluster.objects.get(id=cluster_id)

    def create(self, name, cluster_type, connection_settings=None):
        return models.CMCluster.objects.create(
            name=name, cluster_type=cluster_type,
            connection_settings=connection_settings)

    def delete(self, cluster_id):
        return models.CMCluster.objects.delete(cluster_id)
