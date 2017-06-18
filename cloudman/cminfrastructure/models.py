from django.template.defaultfilters import slugify
import cminfrastructure
import inspect
import uuid
import types
from abc import abstractstaticmethod
from abc import abstractmethod
from cminfrastructure import tasks


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
            isinstance(a, (property, types.MethodType)) and not
            isinstance(a, cminfrastructure.api.CMService) and
            not isinstance(a, cminfrastructure.api.CloudManAPI))
        js = {k: v for(k, v) in attr if not k.startswith('_')}
        return js

    @abstractstaticmethod
    def from_json(api, val):
        pass


class CMCloud(CMBaseModel):

    def __init__(self, api, name, provider_id, provider_config):
        super(CMCloud, self).__init__(api)
        self.cloud_id = slugify(name)
        self.name = name
        self.provider_id = provider_id
        self.provider_config = provider_config
        self.nodes = cminfrastructure.api.CMCloudNodeService(self)

    def delete(self):
        self.api.clouds.delete(self.cloud_id)

    @staticmethod
    def from_json(api, val):
        return CMCloud(api, val['name'], val.get('provider_id'),
                       val.get('provider_config'))


class CMCloudNode(CMBaseModel):

    def __init__(self, api, cloud_id, name, instance_type, node_id=None):
        super(CMCloudNode, self).__init__(api)
        self.id = node_id or str(uuid.uuid4())
        self.cloud_id = cloud_id
        self.name = name
        self.instance_type = instance_type
        self.tasks = cminfrastructure.api.CMNodeTaskService(self)

    def delete(self):
        self.api.clouds.delete(self.cloud_id)

    @staticmethod
    def from_json(api, val):
        return CMCloudNode(api, val['cloud_id'], val['name'],
                           val['instance_type'], node_id=val['id'])


class CMNodeTask(CMBaseModel):

    def __init__(self, api, task_type, cloud_id, node_id, task_id=None):
        super(CMNodeTask, self).__init__(api)
        self.task_id = task_id or str(uuid.uuid4())
        self.task_type = task_type
        self.cloud_id = cloud_id
        self.node_id = node_id

    @abstractmethod
    def execute(self):
        pass

    @staticmethod
    def from_json(api, val):
        return CMTaskFactory.from_json(api, val)


class CMCreateNodeTask(CMNodeTask):

    def __init__(self, api, cloud_id, node_id, task_id=None):
        super(CMCreateNodeTask, self).__init__(api, "create_node", cloud_id,
                                               node_id, task_id=task_id)

    def execute(self):
        tasks.create_node.apply_async((self.cloud_id, self.node_id),
                                      task_id=self.task_id)


class CMTaskFactory():

    def create(self, api, task_type, node):
        if task_type == "create_node":
            return CMCreateNodeTask(api, node.cloud_id, node.id)
        else:
            raise ValueError(f"Unknown task_type: {task_type}")

    @staticmethod
    def from_json(api, val):
        task_type = val.get("task_type")
        if task_type == "create_node":
            return CMCreateNodeTask(api, val['task_type'], val['task_params'],
                                    task_id=val['task_id'])
        return None
