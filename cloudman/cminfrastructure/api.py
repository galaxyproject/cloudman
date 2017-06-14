"""CloudMan Service API."""
from cminfrastructure.models import CMCloud
from cminfrastructure.models import CMCloudNode
from .kvstore import ConsulKVStore


class CMInfrastructureAPI(object):

    def __init__(self):
        self._clouds = CMCloudService(self)

    @property
    def clouds(self):
        return self._clouds


class CMService(object):

    def __init__(self):
        self._kvstore = ConsulKVStore()

    @property
    def kvstore(self):
        return self._kvstore

    def __iter__(self):
        for result in self.list():
            yield result


class CMCloudService(CMService):

    def __init__(self, api):
        super(CMCloudService, self).__init__()
        self.api = api

    def list(self):
        return [CMCloud.from_json(val) for (_, val) in
                self.kvstore.list('infrastructure/clouds/').items()]

    def get(self, cloud_id):
        """
        Returns a CMCloud object
        """
        data = self.kvstore.get(f'infrastructure/clouds/{cloud_id}')
        return CMCloud.from_json(data) if data else None

    def create(self, name, cloud_type):
        cloud = CMCloud(name, cloud_type)
        self.kvstore.put(f'infrastructure/clouds/{cloud.cloud_id}',
                         cloud.to_json())
        return cloud


class CMCloudNodeService(CMService):

    def __init__(self, cloud):
        super(CMCloudNodeService, self).__init__()
        self.cloud = cloud

    def list(self):
        """
        Returns a CMCloudNode object
        """
        return [CMCloudNode.from_json(val) for (_, val) in self.kvstore.list(
            f'infrastructure/clouds/{self.cloud.cloud_id}/instances/').items()]

    def get(self, instance_id):
        """
        Returns a CMCloud object
        """
        data = self.kvstore.get(
            f'infrastructure/clouds/{self.cloud.cloud_id}'
            '/instances/{instance_id}')
        return CMCloudNode.from_json(data) if data else None

    def create(self, name, instance_type):
        inst = CMCloudNode(self.cloud.cloud_id, name, instance_type)
        self.kvstore.put(f'infrastructure/clouds/{self.cloud.cloud_id}/'
                         f'instances/{inst.id}', inst.to_json())
        return inst
