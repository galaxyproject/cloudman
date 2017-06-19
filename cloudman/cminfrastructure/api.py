"""CloudMan Service API."""
from .models import CMCloud
from .models import CMCloudNode
from .models import CMNodeTask
from .models import CMTaskFactory
from .kvstore import ConsulKVStore


class CloudManAPI(object):
    """Marker interface for CloudMan APIs"""
    pass


class CMInfrastructureAPI(CloudManAPI):

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
        return [CMCloud.from_json(self.api, val) for (_, val) in
                self.kvstore.list('infrastructure/clouds/').items()]

    def get(self, cloud_id):
        data = self.kvstore.get(f'infrastructure/clouds/{cloud_id}')
        return CMCloud.from_json(self.api, data) if data else None

    def create(self, name, provider_id, provider_config):
        cloud = CMCloud(self.api, name, provider_id, provider_config)
        self.kvstore.put(f'infrastructure/clouds/{cloud.cloud_id}',
                         cloud.to_json())
        return cloud

    def delete(self, cloud_id):
        self.kvstore.delete(f'infrastructure/clouds/{cloud_id}')


class CMCloudNodeService(CMService):

    def __init__(self, cloud):
        super(CMCloudNodeService, self).__init__()
        self.cloud = cloud

    def list(self):
        return [CMCloudNode.from_json(self.cloud.api, val) for (_, val) in
                self.kvstore.list(f'infrastructure/clouds/'
                                  f'{self.cloud.cloud_id}/instances/').items()]

    def get(self, node_id):
        data = self.kvstore.get(f'infrastructure/clouds/{self.cloud.cloud_id}'
                                f'/instances/{node_id}')
        return CMCloudNode.from_json(self.cloud.api, data) if data else None

    def create(self, name, instance_type):
        node = CMCloudNode(self.cloud.api, self.cloud.cloud_id, name,
                           instance_type)
        self.kvstore.put(f'infrastructure/clouds/{self.cloud.cloud_id}'
                         f'/instances/{node.id}', node.to_json())
        # Kick off instance creation
        node.tasks.create("create_node")
        return node

    def delete(self, node_id):
        self.kvstore.delete(f'infrastructure/clouds/{self.cloud.cloud_id}'
                            f'/instances/{node_id}')


class CMNodeTaskService(CMService):

    def __init__(self, node):
        super(CMNodeTaskService, self).__init__()
        self.node = node

    def list(self):
        return [CMNodeTask.from_json(self.node.api, val) for (_, val) in
                self.kvstore.list(f'infrastructure/clouds/'
                                  f'{self.node.cloud_id}/instances'
                                  f'/{self.node.id}/tasks').items()]

    def get(self, task_id):
        data = self.kvstore.get(
            f'infrastructure/clouds/{self.node.cloud_id}'
            f'/instances/{self.node.id}/tasks/{task_id}')
        return CMNodeTask.from_json(self.node.api,
                                    data) if data else None

    def create(self, task_type, task_params=None):
        task = CMTaskFactory().create(self.node.api, self.node, task_type,
                                      task_params=task_params)
        # Perform the task so task_id is populated
        self.kvstore.put(f'infrastructure/clouds/{self.node.cloud_id}/'
                         f'instances/{self.node.id}/tasks/{task.task_id}',
                         task.to_json())
        task.execute()
        return task

    def update(self, task):
        # Perform the task so task_id is populated
        self.kvstore.put(f'infrastructure/clouds/{self.node.cloud_id}/'
                         f'instances/{self.node.id}/tasks/{task.task_id}',
                         task.to_json())
        return task

    def delete(self, task_id):
        self.kvstore.delete(
            f'infrastructure/clouds/{self.node.cloud_id}/instances/'
            f'{self.node.id}/tasks/{task_id}')
