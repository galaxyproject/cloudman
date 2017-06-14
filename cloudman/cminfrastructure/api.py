"""CloudMan Service API."""
from consul import Consul
import json

from cminfrastructure.models import CMCloud
from cminfrastructure.models import CMCloudNode


class CMInfrastructureAPI(object):

    def __init__(self):
        self._clouds = CMCloudService(self)

    @property
    def clouds(self):
        return self._clouds


class CMService(object):

    @property
    def consul(self):
        if not getattr(self, '_consul', None):
            self._consul = Consul()
        return self._consul

    def __iter__(self):
        for result in self.list():
            yield result


class CMCloudService(CMService):

    def __init__(self, api):
        self.api = api

    def list(self):
        _, data = self.consul.kv.get('infrastructure/clouds/', recurse=True,
                                     keys=True, separator='/')
        # Filter only the top-level keys for this layer
        # (e.g., infrastructure/clouds/us-east-1)
        return [self.get(row.split('/')[-1]) for row in data or [] if row and
                row[-1] != '/']

    def get(self, cloud_id):
        """
        Returns a CMCloud object
        """
        _, data = self.consul.kv.get(f'infrastructure/clouds/{cloud_id}')
        return CMCloud.from_kv(data) if data else None

    def create(self, name, cloud_type):
        cloud = CMCloud(name, cloud_type)
        self.consul.kv.put(f'infrastructure/clouds/{cloud.cloud_id}',
                           cloud.to_json())
        return cloud


class CMCloudNodeService(CMService):

    def __init__(self, cloud):
        self.cloud = cloud

    def list(self):
        """
        Returns a CMCloudNode object
        """
        _, data = self.consul.kv.get(
            f'infrastructure/clouds/{self.cloud.cloud_id}/instances/',
            recurse=True)
        return [CMCloudNode.from_kv(row)
                for row in data or [] if row]

    def get(self, instance_id):
        """
        Returns a CMCloud object
        """
        _, data = self.consul.kv.get(
            'infrastructure/clouds/{self.cloud.cloud_id}'
            '/instances/{instance_id}')
        return CMCloudNode.from_kv(data) if data else None

    def create(self, name, instance_type):
        inst = CMCloudNode(self.cloud.cloud_id, name, instance_type)
        self.consul.kv.put(
            f'infrastructure/clouds/{self.cloud.cloud_id}/instances/{inst.id}',
            inst.to_json())
        return inst
