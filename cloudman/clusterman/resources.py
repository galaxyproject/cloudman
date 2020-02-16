import logging as log

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

    @property
    def cluster_type(self):
        return self.db_model.cluster_type

    @property
    def connection_settings(self):
        return self.db_model.connection_settings

    def delete(self):
        return self.service.delete(self)

    def get_cluster_template(self):
        return CMClusterTemplate.get_template_for(self.service.context, self)


class ClusterAutoScaler(object):

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

    @property
    def instance_type(self):
        return self.db_model.instance_type

    @property
    def zone_id(self):
        return self.db_model.zone.id

    @property
    def min_nodes(self):
        return self.db_model.min_nodes

    @property
    def max_nodes(self):
        return self.db_model.max_nodes

    def delete(self):
        return self.service.delete(self)

