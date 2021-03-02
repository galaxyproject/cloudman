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

    def scaleup(self, labels=None):
        print(f"Scale up requested. labels: {labels}")

        if self.autoscale:
            matched = False
            for scaler in self.autoscalers.list():
                if scaler.match(labels=labels):
                    matched = True
                    scaler.scaleup(labels=labels)
                    break
            if not matched:
                default_scaler = self._get_default_scaler()
                requested_group = labels.get("usegalaxy.org/cm_autoscaling_group")
                if not requested_group or requested_group == default_scaler.name:
                    labels["usegalaxy.org/cm_autoscaling_group"] = default_scaler.name
                    default_scaler.scaleup(labels=labels)
        else:
            log.debug("Autoscale up signal received but autoscaling is disabled.")

    def scaledown(self, labels=None):
        print(f"Scale down requested. labels: {labels}")

        if self.autoscale:
            matched = False
            for scaler in self.autoscalers.list():
                if scaler.match(labels=labels):
                    matched = True
                    scaler.scaledown(labels=labels)
                    break
            if not matched:
                default_scaler = self._get_default_scaler()
                requested_group = labels.get("usegalaxy.org/cm_autoscaling_group")
                if not requested_group or requested_group == default_scaler.name:
                    labels["usegalaxy.org/cm_autoscaling_group"] = default_scaler.name
                    default_scaler.scaledown(labels=labels)
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
    def allowed_vm_type_prefixes(self):
        return self.db_model.allowed_vm_type_prefixes

    @allowed_vm_type_prefixes.setter
    def allowed_vm_type_prefixes(self, value):
        self.db_model.allowed_vm_type_prefixes = value

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

    def match(self, labels=None):
        # Currently, a scaling group matches by zone name and node only.
        # In future, we could add other criteria, like the scaling group name
        # itself, or custom labels to determine whether this scaling group
        # matches a scaling signal.
        labels = labels.copy() if labels else {}
        zone = labels.pop('availability_zone', None)
        scaling_group = labels.get('usegalaxy.org/cm_autoscaling_group')
        # Ignore these keys anyway
        labels.pop('min_vcpus', None)
        labels.pop('min_ram', None)
        if not zone and not labels:
            return False
        match = False
        if zone:
            match = zone == self.db_model.zone.name
        if scaling_group:
            match = self.name == scaling_group
        if labels:
            node = self.cluster.nodes.find(labels=labels)
            if node:
                match = bool(self.db_model.nodegroup.filter(id=node.id)
                             .first())
        return match

    def _filter_stable_nodes(self, nodegroup):
        return list(reversed(
            [node for node in nodegroup.all()
             if node.is_stable()])
        )

    def _filter_running_nodes(self, nodegroup):
        return list(reversed(
            [node for node in nodegroup.all()
             if node.is_running()])
        )

    def scaleup(self, labels=None):
        print(f"Scaling up in group {self.name} with labels: {labels}")
        labels = labels or {}
        total_node_count = self.db_model.nodegroup.count()
        running_nodes = self._filter_running_nodes(self.db_model.nodegroup)
        running_count = len(running_nodes)

        # Allow 5 times the number of max nodes to be in a failed state
        if running_count < self.max_nodes and total_node_count < (5 * self.max_nodes):
            self.cluster.nodes.create(
                vm_type=self.vm_type,
                min_vcpus=labels.get('min_vcpus', 0),
                min_ram=labels.get('min_ram', 0),
                zone=self.zone,
                autoscaler=self)

    def scaledown(self, labels=None):
        print(f"Scaling down in group {self.name} with labels: {labels}")
        # If we've got here, we've already matched availability zone
        zone = labels.pop('availability_zone', None)
        nodes = self._filter_stable_nodes(self.db_model.nodegroup)
        node_count = len(nodes)
        if node_count > self.min_nodes:
            if labels:
                matching_node = self.cluster.nodes.find(
                    labels=labels)
                if matching_node and matching_node.is_stable():
                    print(f"Performing targeted deletion of: {matching_node}")
                    matching_node.delete()
                elif matching_node:
                    print(f"Node targeted for deletion found {matching_node}"
                          " but not deleting as another operation is already"
                          " in progress.")
                else:
                    print(f"Targeted downscale attempted, but matching node"
                          f" not found with labels: {labels}")
                    return
            else:
                # if no host was specified,
                # remove the last added node
                last_node = nodes[0]
                print(f"Non-targeted downscale deleting last launched"
                      f" node: {last_node}")
                node = self.cluster.nodes.get(last_node.id)
                node.delete()
