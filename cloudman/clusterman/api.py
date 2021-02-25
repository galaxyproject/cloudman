"""CloudMan Service API."""
import uuid

from django.db import IntegrityError

from rest_framework.exceptions import PermissionDenied

from cloudlaunch import models as cl_models
from cloudlaunch_cli.api.client import APIClient
from . import exceptions
from . import models
from . import resources
from . import tasks


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
        return 'http://localhost:8000/cloudman/cloudlaunch/api/v1/'

    @property
    def cloudlaunch_token(self):
        token_obj, _ = cl_models.AuthToken.objects.get_or_create(
            name='cloudman', user=self.user)
        return token_obj.key

    @property
    def cloudlaunch_client(self):
        return APIClient(self.cloudlaunch_url,
                         token=self.cloudlaunch_token,
                         cloud_credentials=None)

    @classmethod
    def from_request(cls, request):
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

    def has_permissions(self, scopes, obj=None):
        if not isinstance(scopes, list):
            scope = [scopes]
        return self.context.user.has_perms(scope, obj)

    def check_permissions(self, scopes, obj=None):
        if not self.has_permissions(scopes, obj):
            self.raise_no_permissions(scopes)

    def raise_no_permissions(self, scopes):
        raise PermissionDenied(
            "Object does not exist or you do not have permissions to "
            "perform '%s'" % (scopes,))


class CloudManAPI(CMService):

    def __init__(self, context):
        super(CloudManAPI, self).__init__(context)
        self._clusters = CMClusterService(context)

    @classmethod
    def from_request(cls, request):
        context = CMServiceContext.from_request(request)
        return cls(context)

    @property
    def clusters(self):
        return self._clusters


class CMClusterService(CMService):

    def __init__(self, context):
        super(CMClusterService, self).__init__(context)

    def to_api_object(self, model):
        cluster = resources.Cluster(self, model)
        cluster.nodes = CMClusterNodeService(self.context, cluster)
        cluster.autoscalers = CMClusterAutoScalerService(self.context, cluster)
        return cluster

    def list(self):
        return [self.to_api_object(c) for c in models.CMCluster.objects.all()
                if self.has_permissions('clusters.view_cluster', c)]

    def get(self, cluster_id):
        obj = models.CMCluster.objects.get(id=cluster_id)
        self.check_permissions('clusters.view_cluster', obj)
        return self.to_api_object(obj)

    def find(self, name):
        return [self.to_api_object(c) for c in models.CMCluster.objects.filter(name=name)
                if self.has_permissions('clusters.view_cluster', c)]

    def create(self, name, cluster_type, connection_settings, autoscale=True):
        self.check_permissions('clusters.add_cluster')
        try:
            obj = models.CMCluster.objects.create(
                name=name, cluster_type=cluster_type,
                connection_settings=connection_settings,
                autoscale=autoscale)
            cluster = self.to_api_object(obj)
            return cluster
        except IntegrityError as e:
            raise exceptions.CMDuplicateNameException(
                "A cluster with name: %s already exists" % name)

    def update(self, cluster):
        self.check_permissions('clusters.change_cluster', cluster)
        cluster.db_model.save()
        return cluster

    def delete(self, cluster):
        self.check_permissions('clusters.delete_cluster', cluster)
        for node in cluster.nodes.list():
            node.delete()
        cluster.db_model.delete()


class CMClusterNodeService(CMService):

    def __init__(self, context, cluster):
        super(CMClusterNodeService, self).__init__(context)
        self.cluster = cluster

    def to_api_object(self, node):
        # Remap the returned django model's delete method to the API method
        # This is just a lazy alternative to writing an actual wrapper around
        # the django object.
        node.original_delete = node.delete
        node.delete = lambda: self.delete(node)
        return node

    def list(self):
        nodes = models.CMClusterNode.objects.filter(
            cluster=self.cluster.db_model)
        return [self.to_api_object(n) for n in nodes
                if self.has_permissions('clusternodes.view_clusternode', n)]

    def find(self, labels=None):
        template = self.cluster.get_cluster_template()
        n = template.find_matching_node(labels=labels)
        return (n
                if self.has_permissions('clusternodes.view_clusternode', n)
                else None)

    def get(self, node_id):
        obj = models.CMClusterNode.objects.get(id=node_id)
        self.check_permissions('clusternodes.view_clusternode', obj)
        return self.to_api_object(obj)

    def create(self, vm_type=None, zone=None, autoscaler=None, min_vcpus=0, min_ram=0):
        self.check_permissions('clusternodes.add_clusternode')
        name = "{0}-{1}".format(self.cluster.name, str(uuid.uuid4())[:6])
        template = self.cluster.get_cluster_template()
        cli_deployment = template.add_node(
            name, vm_type=vm_type, zone=zone,
            min_vcpus=min_vcpus, min_ram=min_ram,
            vm_family=autoscaler.allowed_vm_type_prefixes if autoscaler else "",
            autoscaling_group=autoscaler.name if autoscaler else None)
        deployment = cl_models.ApplicationDeployment.objects.get(
            pk=cli_deployment.id)
        node = models.CMClusterNode.objects.create(
            name=name, cluster=self.cluster.db_model, deployment=deployment,
            autoscaler=autoscaler.db_model if autoscaler else None)
        return self.to_api_object(node)

    def delete(self, node):
        if node:
            print(f"Deleting node: {node.name}")
            self.check_permissions('clusternodes.delete_clusternode', node)
            template = self.cluster.get_cluster_template()
            task = template.remove_node(node)
            tasks.delete_node.delay(task.asdict().get('celery_id'),
                                    node.cluster_id, node.id)
        else:
            print(f"Unexpected, asked to delete a null node!")


class CMClusterAutoScalerService(CMService):

    def __init__(self, context, cluster):
        super(CMClusterAutoScalerService, self).__init__(context)
        self.cluster = cluster

    def to_api_object(self, model):
        autoscaler = resources.ClusterAutoScaler(self, model)
        return autoscaler

    def list(self):
        self.check_permissions('clusters.view_cluster', self.cluster)
        autoscalers = models.CMAutoScaler.objects.filter(
            cluster=self.cluster.db_model)
        return [self.to_api_object(a) for a in autoscalers]

    def get(self, autoscaler_id):
        self.check_permissions('clusters.view_cluster', self.cluster)
        obj = models.CMAutoScaler.objects.get(id=autoscaler_id)
        return self.to_api_object(obj)

    def create(self, vm_type=None, allowed_vm_type_prefixes=None, name=None,
               zone=None, min_nodes=None, max_nodes=None):
        self.check_permissions('clusters.change_cluster', self.cluster)
        if not name:
            name = "{0}-{1}".format(self.cluster.name, str(uuid.uuid4())[:6])
        vm_type = vm_type or self.cluster.default_vm_type
        autoscaler = models.CMAutoScaler.objects.create(
            cluster=self.cluster.db_model, name=name, vm_type=vm_type,
            allowed_vm_type_prefixes=allowed_vm_type_prefixes,
            zone=zone, min_nodes=min_nodes, max_nodes=max_nodes)
        return self.to_api_object(autoscaler)

    def update(self, autoscaler):
        self.check_permissions('clusters.change_cluster', autoscaler)
        autoscaler.db_model.save()
        return autoscaler

    def delete(self, autoscaler):
        self.check_permissions('clusters.change_cluster', self.cluster)
        if autoscaler:
            # call the saved django delete method which we remapped
            autoscaler.db_model.delete()

    def get_or_create_default(self):
        self.check_permissions('clusters.view_cluster', self.cluster)
        obj, created = models.CMAutoScaler.objects.get_or_create(
            name='default', cluster=self.cluster.db_model,
            defaults={
                'vm_type': self.cluster.default_vm_type,
                'zone': self.cluster.default_zone,
                'min_nodes': 0,
                'max_nodes': 5
            })
        return self.to_api_object(obj)
