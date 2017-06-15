from django.template.defaultfilters import slugify
import cminfrastructure
import inspect
import uuid
from abc import abstractstaticmethod


class CMBaseModel(object):

    def __init__(self, api):
        self._api = api

    @property
    def api(self):
        return self._api

    def to_json(self):
        # Get all attributes but filter methods and private/magic ones
        attr = inspect.getmembers(
            self,
            lambda a: not(inspect.isroutine(a)) and not
            isinstance(a, cminfrastructure.api.CMService) and
            not isinstance(a, cminfrastructure.api.CloudManAPI))
        js = {k: v for(k, v) in attr if not k.startswith('_')}
        return js

    @abstractstaticmethod
    def from_json(api, val):
        pass


class CMCloud(CMBaseModel):

    def __init__(self, api, name, cloud_type):
        super(CMCloud, self).__init__(api)
        self.cloud_id = slugify(name)
        self.name = name
        self.cloud_type = cloud_type
        self.nodes = cminfrastructure.api.CMCloudNodeService(self)

    def delete(self):
        self.api.clouds.delete(self.cloud_id)

    @staticmethod
    def from_json(api, val):
        return CMCloud(api, val['name'], val.get('cloud_type'))


class CMCloudNode(CMBaseModel):

    def __init__(self, api, cloud_id, name, instance_type, node_id=None):
        super(CMCloudNode, self).__init__(api)
        self.id = node_id or str(uuid.uuid4())
        self.cloud_id = cloud_id
        self.name = name
        self.instance_type = instance_type

    def delete(self):
        self.api.clouds.delete(self.cloud_id)

    @staticmethod
    def from_json(api, val):
        return CMCloudNode(api, val['cloud_id'], val['name'],
                           val['instance_type'], node_id=val['id'])
