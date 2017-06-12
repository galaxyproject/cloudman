from consul import Consul
from django.template.defaultfilters import slugify
import json


class CMInfrastructureAPI(object):

    def __init__(self):
        self._clouds = CMCloudService(self)

    @property
    def clouds(self):
        return self._clouds


class CMCloudService(object):

    def __init__(self, config):
        self.consul = Consul()

    def list(self):
        _, data = self.consul.kv.get('infrastructure/clouds/', recurse=True)
        return [json.loads(row['Value']) for row in data or [] if row]

    def create(self, name, cloud_type):
        slug = slugify(name)
        cloud = {'name': name, 'cloud_type': cloud_type}
        self.consul.kv.put(f'infrastructure/clouds/{slug}', json.dumps(cloud))
        return cloud
