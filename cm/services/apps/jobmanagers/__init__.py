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

    def enable_node(self, alias, address):
        """
            Enable the node identified by ``alias`` and/or ``address`` for
            running jobs.

            :type alias: string
            :param alias: A name an instance is associated with in the job manager

            :type address: string
            :param address: An address (IP or FQDN) an instance is associated
                            with in the job manager.

            :rtype: bool
            :return: ``True`` if the node was successfully enabled for running
                     jobs; ``False`` otherwise.
        """
        raise NotImplementedError("enable_node method not implemented")

    def disable_node(self, alias, address, **kwargs):
        """
            Disable the node identified by ``alias`` and/or ``address`` from
            running jobs.

            :type alias: string
            :param alias: A name an instance is associated with in the job manager

            :type address: string
            :param address: An address (IP or FQDN) an instance is associated
                            with in the job manager.

            :rtype: bool
            :return: ``True`` if the node was successfully disabled from running
                     jobs; ``False`` otherwise.
        """
        raise NotImplementedError("disable_node method not implemented")

    def idle_nodes(self):
        """
            Return a list of nodes that are currently not executing any jobs.

            :rtype: list
            :return: A list of strings (alias or private hostname) identifying
                     the nodes.
        """
        raise NotImplementedError("idle_nodes method not implemented")

    def suspend_queue(self, queue_name=None):
        """
            Suspend ``queue_name`` queue from running jobs.

            :type queue_name: string
            :param queue_name: A name of the queue to suspend. If not specified,
                               suspend the default job manager queue.
        """
        raise NotImplementedError("suspend_queue method not implemented")

    def unsuspend_queue(self, queue_name=None):
        """
            Unsuspend ``queue_name`` queue so it can run jobs.

            :type queue_name: string
            :param queue_name: A name of the queue to unsuspend. If not specified,
                               unsuspend the default job manager queue.
        """
        raise NotImplementedError("unsuspend_queue method not implemented")
