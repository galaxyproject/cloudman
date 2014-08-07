from cm.services.apps import ApplicationService

import logging
log = logging.getLogger('cloudman')


class BaseJobManager(ApplicationService):
    def __init__(self, app):
        super(BaseJobManager, self).__init__(app)

    def add_node(self, instance):
        """
            Add the ``instance`` as a worker node into the cluster.

            :type instance: cm.instance.Instance
            :param instance: An object representing an instance being added into
                             the cluster. This object needs to have fields required
                             by the chosen job manager (eg, name alias, IP address);
                             see chosen job manager for details.

            :rtype: bool
            :return: ``True`` if the node was successfully added into the cluster;
                     ``False`` otherwise.
        """
        raise NotImplementedError("add_node method not implemented")

    def remove_node(self, instance):
        """
            Remove the ``instance`` from the list of worker nodes in the cluster.

            :type instance: cm.instance.Instance
            :param instance: An object representing an instance being removed
                             from the cluster.

            :rtype: bool
            :return: ``True`` if the node was successfully removed from the
                     cluster; ``False`` otherwise.
        """
        raise NotImplementedError("remove_node method not implemented")

    def enable_node(self, alias):
        """
            Enable the node identified by ``alias`` for running jobs.

            :rtype: bool
            :return: ``True`` if the node was successfully enabled for running
                     jobs; ``False`` otherwise.
        """
        raise NotImplementedError("enable_node method not implemented")

    def disable_node(self, alias, **kwargs):
        """
            Disable the node identified by ``alias`` from running jobs.

            :rtype: bool
            :return: ``True`` if the node was successfully disabled from running
                     jobs; ``False`` otherwise.
        """
        raise NotImplementedError("disable_node method not implemented")

    def idle_nodes(self):
        """
            Return a list of nodes that are currently not executing any jobs.

            :rtype: list
            :return: A list of instance alias strings representing idle nodes.
        """
        raise NotImplementedError("idle_nodes method not implemented")
