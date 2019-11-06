"""CloudMan Service API."""
import uuid
from django.contrib.auth import get_user_model
from rest_framework.exceptions import PermissionDenied

from cloudlaunch import models as cl_models
from cloudlaunch_cli.api.client import APIClient
from . import models
from .cluster_templates import CMClusterTemplate


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
        # Always perform internal tasks as the admin user
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

    def add_child_services(self, cluster):
        cluster.service = self
        cluster.nodes = CMClusterNodeService(self.context, cluster)
        return cluster

    def list(self):
        return list(map(self.add_child_services,
                        (c for c in models.CMCluster.objects.all()
                         if self.has_permissions('clusters.view_cluster', c))))

    def get(self, cluster_id):
        obj = models.CMCluster.objects.get(id=cluster_id)
        self.check_permissions('clusters.view_cluster', obj)
        return self.add_child_services(obj)

    def create(self, name, cluster_type, connection_settings):
        self.check_permissions('clusters.add_cluster')
        obj = models.CMCluster.objects.create(
            name=name, cluster_type=cluster_type,
            connection_settings=connection_settings)
        cluster = self.add_child_services(obj)
        template = self.get_cluster_template(cluster)
        template.setup()
        return cluster

    def delete(self, cluster_id):
        obj = models.CMCluster.objects.get(id=cluster_id)
        if obj:
            self.check_permissions('clusters.delete_cluster', obj)
            obj.delete()
        else:
            self.raise_no_permissions('clusters.delete_cluster')

    def get_cluster_template(self, cluster):
        return CMClusterTemplate.get_template_for(self.context, cluster)


class CMClusterNodeService(CMService):

    def __init__(self, context, cluster):
        super(CMClusterNodeService, self).__init__(context)
        self.cluster = cluster

    def list(self):
        nodes = models.CMClusterNode.objects.filter(cluster=self.cluster)
        return [n for n in nodes
                if self.has_permissions('clusternodes.view_clusternode', n)]

    def get(self, node_id):
        obj = models.CMClusterNode.objects.get(id=node_id)
        self.check_permissions('clusternodes.view_clusternode', obj)
        return obj

    def create(self, instance_type):
        self.check_permissions('clusternodes.add_clusternode')
        name = "{0}-{1}".format(self.cluster.name, str(uuid.uuid4())[:6])
        template = self.cluster.service.get_cluster_template(self.cluster)
        cli_deployment = template.add_node(name, instance_type)
        deployment = cl_models.ApplicationDeployment.objects.get(
            pk=cli_deployment.id)
        return models.CMClusterNode.objects.create(
            name=name, cluster=self.cluster, deployment=deployment)

    def delete(self, node_id):
        obj = models.CMClusterNode.objects.get(id=node_id)
        if obj:
            self.check_permissions('clusternodes.delete_clusternode', obj)
            template = self.cluster.service.get_cluster_template()
            template.remove_node(obj)
            obj.delete()
        else:
            self.raise_no_permissions('clusternodes.delete_clusternode')
