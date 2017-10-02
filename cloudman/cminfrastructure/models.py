from django.template.defaultfilters import slugify
import cminfrastructure
import inspect
import uuid
import types
from abc import abstractstaticmethod
from abc import abstractmethod


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

    def __init__(self, api, name, provider_id, provider_config,
                 default_image_id=None, default_login_user=None,
                 default_subnet=None, default_sec_group=None,
                 default_zone=None, default_user_kp=None):
        super(CMCloud, self).__init__(api)
        self.cloud_id = slugify(name)
        self.name = name
        self.provider_id = provider_id
        self.provider_config = provider_config
        self.default_image_id = default_image_id
        self.default_login_user = default_login_user
        self.default_subnet = default_subnet
        self.default_sec_group = default_sec_group
        self.default_zone = default_zone
        self.default_user_kp = default_user_kp
        self.nodes = cminfrastructure.api.CMCloudNodeService(self)

    def save(self):
        self.api.clouds.delete(self.cloud_id)

    def delete(self):
        self.api.clouds.delete(self.cloud_id)

    @staticmethod
    def from_json(api, val):
        return CMCloud(api, val['name'], val['provider_id'],
                       val['provider_config'],
                       default_image_id=val.get('default_image_id'),
                       default_login_user=val.get('default_login_user'),
                       default_subnet=val.get('default_subnet'),
                       default_sec_group=val.get('default_sec_group'),
                       default_zone=val.get('default_zone'),
                       default_user_kp=val.get('default_user_kp'))


class CMCloudNode(CMBaseModel):

    def __init__(self, api, cloud_id, name, instance_type, node_id=None,
                 instance_id=None, public_ips=None, private_ips=None):
        super(CMCloudNode, self).__init__(api)
        self.id = node_id or str(uuid.uuid4())
        self.cloud_id = cloud_id
        self.name = name
        self.instance_type = instance_type
        self.instance_id = instance_id
        self.public_ips = public_ips
        self.private_ips = private_ips
        self.tasks = cminfrastructure.api.CMNodeTaskService(self)

    def delete(self):
        self.api.clouds.get(self.cloud_id).nodes.delete(self.cloud_id)

    @staticmethod
    def from_json(api, val):
        return CMCloudNode(api, val['cloud_id'], val['name'],
                           val['instance_type'], node_id=val['id'],
                           instance_id=val.get('instance_id'),
                           public_ips=val.get('public_ips'),
                           private_ips=val.get('private_ips'))


class CMNodeTask(CMBaseModel):

    def __init__(self, api, task_type, cloud_id, node_id, task_id=None,
                 task_params=None):
        super(CMNodeTask, self).__init__(api)
        self.task_id = task_id or str(uuid.uuid4())
        self.task_type = task_type
        self.cloud_id = cloud_id
        self.node_id = node_id
        self.task_params = task_params
        self.status = 'NOT_STARTED'
        self.message = None
        self.stack_trace = None

    @abstractmethod
    def execute(self):
        pass

    @staticmethod
    def from_json(api, val):
        return CMTaskFactory.from_json(api, val)

    def delete(self):
        cloud = self.api.clouds.get(self.cloud_id)
        node = cloud.nodes.get(self.node_id)
        node.tasks.delete(self.task_id)


class CMCreateNodeTask(CMNodeTask):

    def __init__(self, api, cloud_id, node_id, task_id=None):
        super(CMCreateNodeTask, self).__init__(api, "create_node", cloud_id,
                                               node_id, task_id=task_id)

    def execute(self):
        cminfrastructure.tasks.create_node.delay(self.cloud_id, self.node_id,
                                                 task_id=self.task_id)


class CMDeleteNodeTask(CMNodeTask):

    def __init__(self, api, cloud_id, node_id, task_id=None):
        super(CMDeleteNodeTask, self).__init__(api, "delete_node", cloud_id,
                                               node_id, task_id=task_id)

    def execute(self):
        cminfrastructure.tasks.delete_node.delay(self.cloud_id, self.node_id,
                                                 task_id=self.task_id)


class CMTaskFactory():

    def create(self, api, cloud_id, node_id, task_type,
               task_id=None, task_params=None):
        if task_type == "create_node":
            return CMCreateNodeTask(api, cloud_id, node_id, task_id=task_id)
        elif task_type == "delete_node":
            return CMDeleteNodeTask(api, cloud_id, node_id, task_id=task_id)
        else:
            raise ValueError(f"Unknown task_type: {task_type}")

    @staticmethod
    def from_json(api, val):
        task_type = val.get("task_type")
        if task_type in ("create_node", "delete_node"):
            task = CMTaskFactory().create(api, val['cloud_id'], val['node_id'],
                                          task_type, task_id=val['task_id'])
            task.status = val['status']
            task.message = val.get('message')
            task.stack_trace = val.get('stack_trace')
            return task
        return None
