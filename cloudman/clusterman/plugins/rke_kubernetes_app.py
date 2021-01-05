"""Plugin implementation for a simple web application."""
import tenacity

from celery.utils.log import get_task_logger

from cloudlaunch.backend_plugins.base_vm_app import BaseVMAppPlugin
from cloudlaunch.backend_plugins.cloudman2_app import get_iam_handler_for
from cloudlaunch.configurers import AnsibleAppConfigurer

from clusterman.clients.kube_client import KubeClient

from rest_framework.serializers import ValidationError

log = get_task_logger('cloudlaunch')


def get_required_val(data, name, message):
    val = data.get(name)
    if not val:
        raise ValidationError({"error": message})
    return val


class NodeNotDeleted(Exception):
    pass


class RKEKubernetesApp(BaseVMAppPlugin):
    """
    RKE Kubernetes Appliance.
    """
    @staticmethod
    def validate_app_config(provider, name, cloud_config, app_config):
        rke_config = get_required_val(
            app_config, "config_kube_rke", "RKE configuration data"
            " must be provided. config_kube_rke entry not found in"
            " app_config.")
        assert 'rke_cluster_id' in rke_config
        assert 'rke_registration_server' in rke_config
        assert 'rke_registration_token' in rke_config
        return app_config

    def deploy(self, name, task, app_config, provider_config, **kwargs):
        """
        Handle the app launch process and wait for http.

        Pass boolean ``check_http`` as a ``False`` kwarg if you don't
        want this method to perform the app http check and prefer to handle
        it in the child class.
        """
        result = super().deploy(
            name, task, app_config, provider_config)
        return result

    @tenacity.retry(stop=tenacity.stop_after_attempt(2),
                    wait=tenacity.wait_fixed(10),
                    reraise=True,
                    after=lambda *args: log.debug("Node not deleted yet, checking again..."))
    def check_node_no_longer_exists(self, node_ip):
        # Newly added node should now be registered with the cluster
        kube_client = KubeClient()
        k8s_node = kube_client.nodes.find(node_ip)
        if not k8s_node:
            return True
        else:
            raise NodeNotDeleted(
                f"Deleted node with ip: {node_ip} still attached to the cluster.")

    @tenacity.retry(stop=tenacity.stop_after_attempt(2),
                    wait=tenacity.wait_fixed(10),
                    reraise=True,
                    after=lambda *args: log.debug("Node not removed, retrying......"))
    def delete(self, provider, deployment):
        """
        Delete resource(s) associated with the supplied deployment.

        This is a blocking call that will wait until the instance is marked
        as deleted or disappears from the provider.

        *Note* that this method will delete resource(s) associated with
        the deployment - this is an un-recoverable action.
        """
        node_ip = deployment.get(
            'launch_result', {}).get('cloudLaunch', {}).get('publicIP')
        try:
            kube_client = KubeClient()
            k8s_node = kube_client.nodes.find(node_ip)
            if k8s_node:
                k8s_node = k8s_node[0]
                try:
                    # stop new jobs being scheduled on this node
                    kube_client.nodes.cordon(k8s_node)
                    # let existing jobs finish
                    kube_client.nodes.wait_till_jobs_complete(k8s_node)
                    # drain remaining pods
                    kube_client.nodes.drain(k8s_node, timeout=120)
                finally:
                    # delete the k8s node
                    kube_client.nodes.delete(k8s_node)
        finally:
            # delete the VM
            result = super().delete(provider, deployment)
        if self.check_node_no_longer_exists(node_ip):
            return result
        else:
            raise NodeNotDeleted(
                f"Node has not been removed from the cluster")

    def _get_configurer(self, app_config):
        # CloudMan2 can only be configured with ansible
        return RKEKubernetesAnsibleAppConfigurer()

    def _provision_host(self, name, task, app_config, provider_config):
        provider = provider_config.get('cloud_provider')
        clust_name = app_config.get('config_cloudman', {}).get('cluster_name')

        handler_class = get_iam_handler_for(provider.PROVIDER_ID)
        if handler_class:
            provider = provider_config.get('cloud_provider')
            handler = handler_class(provider, clust_name, app_config)
            provider_config['extra_provider_args'] = \
                handler.create_iam_policy()
        result = super()._provision_host(name, task, app_config, provider_config)
        return result


class NodeNotRegistered(Exception):
    pass


class RKEKubernetesAnsibleAppConfigurer(AnsibleAppConfigurer):
    """Add CloudMan2 specific vars to playbook."""

    def _cb_provider_id_to_kube_provider_id(self, provider_id):
        CB_CLOUD_TO_KUBE_CLOUD_MAP = {
            'aws': 'aws',
            'openstack': 'openstack',
            'azure': 'azure',
            'gcp': 'gce'
        }
        return CB_CLOUD_TO_KUBE_CLOUD_MAP.get(provider_id)

    @tenacity.retry(stop=tenacity.stop_after_attempt(2),
                    wait=tenacity.wait_fixed(10),
                    reraise=True,
                    after=lambda *args: log.debug("Node not registered yet, checking again..."))
    def has_reached_desired_state(self, provider_config):
        # Newly added node should now be registered with the cluster
        kube_client = KubeClient()
        node_ip = provider_config.get(
            'host_config', {}).get('private_ip')
        k8s_node = kube_client.nodes.find(node_ip)
        if k8s_node and k8s_node[0]:
            return True
        else:
            raise NodeNotRegistered(
                f"New node with ip: {node_ip} has still not registered with k8s cluster")

    @tenacity.retry(stop=tenacity.stop_after_attempt(2),
                    wait=tenacity.wait_fixed(10),
                    reraise=True,
                    after=lambda *args: log.debug("Node not registered, rerunning playbook..."))
    def configure(self, app_config, provider_config):
        playbook_vars = {
            'kube_cloud_provider': self._cb_provider_id_to_kube_provider_id(
                provider_config.get('cloud_provider').PROVIDER_ID),
            'cluster_hostname': app_config.get('config_kube_rke', {}).get(
                'rke_cluster_id'),
            'rke_registration_server': app_config.get('config_kube_rke', {}).get(
                'rke_registration_server'),
            'rke_registration_token': app_config.get('config_kube_rke', {}).get(
                'rke_registration_token')
        }
        result = super().configure(app_config, provider_config,
                                   playbook_vars=playbook_vars)
        if self.has_reached_desired_state(provider_config):
            return result
        else:
            raise NodeNotRegistered(
                f"Node has not been added to the cluster")
