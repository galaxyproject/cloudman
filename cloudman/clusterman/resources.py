import logging as log

from djcloudbridge import models as cb_models

from .cluster_templates import CMClusterTemplate


class Cluster(object):

    def __init__(self, service, db_model):
        self.db_model = db_model
        self.service = service

    @property
    def id(self):
        return self.db_model.id

    @property
    def added(self):
        return self.db_model.added

    @property
    def updated(self):
        return self.db_model.updated

    @property
    def name(self):
        return self.db_model.name

    @name.setter
    def name(self, value):
        self.db_model.name = value

    @property
    def cluster_type(self):
        return self.db_model.cluster_type

    @property
    def connection_settings(self):
        return self.db_model.connection_settings

    @property
    def default_vm_type(self):
        return self.db_model.default_vm_type

    @property
    def default_zone(self):
        return self.db_model.default_zone

    @property
    def autoscale(self):
        return self.db_model.autoscale

    @autoscale.setter
    def autoscale(self, value):
        self.db_model.autoscale = bool(value)

    def delete(self):
        return self.service.delete(self)

    def get_cluster_template(self):
        return CMClusterTemplate.get_template_for(self.service.context, self)

    def _get_default_scaler(self):
        return self.autoscalers.get_or_create_default()

    def scaleup(self, zone_name=None, min_vcpus=None, min_ram=None):
        if zone_name:
            zone = cb_models.Zone.objects.get(name=zone_name)
        else:
            zone = None

        if self.autoscale:
            matched = False
            for scaler in self.autoscalers.list():
                if scaler.match(zone=zone):
                    matched = True
                    scaler.scaleup(min_vcpus=min_vcpus, min_ram=min_ram)
            if not matched:
                scaler = self._get_default_scaler()
                scaler.scaleup(min_vcpus=min_vcpus, min_ram=min_ram)
        else:
            log.debug("Autoscale up signal received but autoscaling is disabled.")

    def scaledown(self, zone_name=None):
        if zone_name:
            zone = cb_models.Zone.objects.get(name=zone_name)
        else:
            zone = None

        if self.autoscale:
            matched = False
            for scaler in self.autoscalers.list():
                if scaler.match(zone=zone):
                    matched = True
                    scaler.scaledown()
            if not matched:
                scaler = self._get_default_scaler()
                scaler.scaledown()
        else:
            log.debug("Autoscale down signal received but autoscaling is disabled.")


class ClusterAutoScaler(object):
    """
    This class represents an AutoScaler Group, and is
    analogous to a scaling group in AWS.
    """

    def __init__(self, service, db_model):
        self.db_model = db_model
        self.service = service

    @property
    def cluster(self):
        return self.service.cluster

    @property
    def id(self):
        return self.db_model.id

    @property
    def name(self):
        return self.db_model.name

    @name.setter
    def name(self, value):
        self.db_model.name = value

    @property
    def vm_type(self):
        return self.db_model.vm_type

    @vm_type.setter
    def vm_type(self, value):
        self.db_model.vm_type = value

    @property
    def zone_id(self):
        return self.db_model.zone.id

    @property
    def zone(self):
        return self.db_model.zone

    @zone.setter
    def zone(self, value):
        self.db_model.zone = value

    @property
    def min_nodes(self):
        return self.db_model.min_nodes

    @min_nodes.setter
    def min_nodes(self, value):
        self.db_model.min_nodes = max(int(value), 0)

    @property
    def max_nodes(self):
        # 5000 being the current k8s node limit
        return self.db_model.max_nodes or 5000

    @max_nodes.setter
    def max_nodes(self, value):
        self.db_model.max_nodes = max(int(value), 0)

    def delete(self):
        return self.service.delete(self)

    def match(self, zone=None):
        # Currently, a scaling group matches by zone name only.
        # In future, we could add other criteria, like the scaling group name
        # itself, or custom labels to determine whether this scaling group
        # matches a scaling signal.
        return zone == self.db_model.zone

    def scaleup(self, min_vcpus=0, min_ram=0):
        node_count = self.db_model.nodegroup.count()
        if node_count < self.max_nodes:
            self.cluster.nodes.create(
                vm_type=self.vm_type, min_vcpus=min_vcpus, min_ram=min_ram,
                zone=self.zone, autoscaler=self)

    def scaledown(self):
        node_count = self.db_model.nodegroup.count()
        if node_count > self.min_nodes:
            last_node = self.db_model.nodegroup.last()
            node = self.cluster.nodes.get(last_node.id)
            node.delete()
