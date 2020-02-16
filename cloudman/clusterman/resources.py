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
        return self.service.delete(self.db_model)

    def get_cluster_template(self):
        return CMClusterTemplate.get_template_for(self.service.context, self)

