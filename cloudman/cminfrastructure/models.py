from django.template.defaultfilters import slugify
import cminfrastructure
import inspect
import uuid
from abc import abstractstaticmethod


class CMBaseModel(object):

    def to_json(self):
        # Get all attributes but filter methods and private/magic ones
        attr = inspect.getmembers(
            self,
            lambda a: not(inspect.isroutine(a)) and not
            isinstance(a, cminfrastructure.api.CMService))
        js = {k: v for(k, v) in attr if not k.startswith('_')}
        return js

    @abstractstaticmethod
    def from_json(val):
        pass


class CMCloud(CMBaseModel):

    def __init__(self, name, cloud_type):
        self.cloud_id = slugify(name)
        self.name = name
        self.cloud_type = cloud_type
        self.nodes = cminfrastructure.api.CMCloudNodeService(self)

    @staticmethod
    def from_json(val):
        return CMCloud(val['name'], val.get('cloud_type'))


class CMCloudNode(CMBaseModel):

    def __init__(self, cloud_id, name, instance_type):
        self.id = str(uuid.uuid4())
        self.cloud_id = cloud_id
        self.name = name
        self.instance_type = instance_type

    @staticmethod
    def from_json(val):
        node = CMCloudNode(val['cloud_id'],
                           val['name'],
                           val['instance_type'])
        # TODO: simplify/change this
        node.id = val['id']
