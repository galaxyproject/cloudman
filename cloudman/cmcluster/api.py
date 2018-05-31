"""CloudMan Service API."""
import abc

from cloudlaunch import models as cl_models
from cloudlaunch_cli.api.client import APIClient
from . import models
from rest_framework.exceptions import ValidationError


class CMServiceContext(object):
    """
    A class to contain contextual information when processing a
    service request, such as the current user. A ServiceContext object
    must be passed in when creating a service.
    """

    def __init__(self, user):
        self._user = user

    @property
    def user(self):
        return self._user

    @property
    def cloudlaunch_url(self):
        return 'http://localhost:8000/cloudlaunch/api/v1/'

    @property
    def cloudlaunch_token(self):
        token_obj, _ = cl_models.Token.objects.get_or_create(user=self.user)
        return token_obj.key

    @property
    def cloudlaunch_client(self):
        return APIClient(self.cloudlaunch_url,
                         token=self.cloudlaunch_token,
                         cloud_credentials=None)

    @classmethod
    def from_request(cls, request):
        # Construct and return an instance of CMServiceContext
        return cls(user=request.user)


class CMService(object):
    """Marker interface for CloudMan services"""
    def __init__(self, context):
        self._context = context

    @property
    def context(self):
        """
        Returns the currently associated service context.
        """
        return self._context


class CloudManAPI(CMService):

    def __init__(self, request):
        context = CMServiceContext.from_request(request)
        super(CloudManAPI, self).__init__(context)
        self._clusters = CMClusterService(context)

    @property
    def clusters(self):
        return self._clusters


class CMClusterService(CMService):

    def __init__(self, context):
        super(CMClusterService, self).__init__(context)

    def add_child_services(self, cluster):
        cluster.service = self
        cluster.nodes = CMClusterNodeService(self.context, cluster)
        return cluster

    def list(self):
        return list(map(self.add_child_services,
                        models.CMCluster.objects.all()))

    def get(self, cluster_id):
        return self.add_child_services(
            models.CMCluster.objects.get(id=cluster_id))

    def create(self, name, cluster_type, connection_settings):
        obj = models.CMCluster.objects.create(
            name=name, cluster_type=cluster_type,
            connection_settings=connection_settings)
        return self.add_child_services(obj)

    def delete(self, cluster_id):
        obj = models.CMCluster.objects.get(id=cluster_id)
        if obj:
            obj.delete()

    def get_cluster_template(self, cluster):
        return CMClusterTemplate.get_template_for(self.context, cluster)


class CMClusterTemplate(object):

    def __init__(self, context, cluster):
        self.context = context
        self.cluster = cluster

    @property
    def connection_settings(self):
        return self.cluster.connection_settings

    @abc.abstractmethod
    def add_node(self, name, size):
        pass

    @abc.abstractmethod
    def remove_node(self):
        pass

    @abc.abstractmethod
    def activate_autoscaling(self, min_nodes=0, max_nodes=None, size=None):
        pass

    @abc.abstractmethod
    def deactivate_autoscaling(self):
        pass

    @staticmethod
    def get_template_for(context, cluster):
        if cluster.cluster_type == "KUBE_RANCHER":
            return CMRancherTemplate(context, cluster)
        else:
            raise KeyError("Cannon get cluster template for unknown cluster "
                           "type: %s" % cluster.cluster_type)


class CMRancherTemplate(CMClusterTemplate):

    def __init__(self, context, cluster):
        super(CMRancherTemplate, self).__init__(context, cluster)

    def add_node(self, name, size):
        params = {
            'name': name,
            'application': 'cm_rancher_kubernetes_plugin',
            'target_cloud': self.connection_settings.get('target_cloud'),
            'application_version': '0.1.0',
            'config_app': {
                'connecting_settings': self.cluster.connection_settings,
                'rancher_action': 'add_node'
            }
        }
        try:
            return self.context.cloudlaunch_client.deployments.create(**params)
        except Exception as e:
            raise ValidationError(str(e))

    def remove_node(self, node):
        return self.context.cloudlaunch_client.deployments.delete(
            node.deployment.id)

    def activate_autoscaling(self, min_nodes=0, max_nodes=None, size=None):
        pass

    def deactivate_autoscaling(self):
        pass


class CMClusterNodeService(CMService):

    def __init__(self, context, cluster):
        super(CMClusterNodeService, self).__init__(context)
        self.cluster = cluster

    def list(self):
        return models.CMClusterNode.objects.filter(cluster=self.cluster)

    def get(self, node_id):
        return models.CMClusterNode.objects.get(id=node_id)

    def create(self, name, instance_type):
        template = self.cluster.service.get_cluster_template(self.cluster)
        cli_deployment = template.add_node(name, instance_type)
        deployment = cl_models.ApplicationDeployment.objects.get(
            pk=cli_deployment.id)
        return models.CMClusterNode.objects.create(
            name=name, cluster=self.cluster, deployment=deployment)

    def delete(self, node_id):
        obj = models.CMClusterNode.objects.get(id=node_id)
        if obj:
            template = self.cluster.service.get_cluster_template()
            template.remove_node(obj)
            obj.delete()
