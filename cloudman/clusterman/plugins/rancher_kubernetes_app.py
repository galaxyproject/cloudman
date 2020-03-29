"""Plugin implementation for a simple web application."""
import time

from celery.utils.log import get_task_logger

from cloudlaunch.backend_plugins.base_vm_app import BaseVMAppPlugin
from cloudlaunch.backend_plugins.cloudman2_app import get_iam_handler_for
from cloudlaunch.configurers import AnsibleAppConfigurer

from clusterman.clients.rancher import RancherClient

from rest_framework.serializers import ValidationError

log = get_task_logger('cloudlaunch')


def get_required_val(data, name, message):
    val = data.get(name)
    if not val:
        raise ValidationError({"error": message})
    return val


class RancherKubernetesApp(BaseVMAppPlugin):
    """
    Rancher Kubernetes Appliance.
    """
    @staticmethod
    def validate_app_config(provider, name, cloud_config, app_config):
        rancher_config = get_required_val(
            app_config, "config_rancher_kube", "Rancher configuration data"
            " must be provided. config_rancher_kube entry not found in"
            " app_config.")
        #user_data = "#!/bin/bash\n"
        #user_data += get_required_val(
        #    rancher_config, "rancher_node_command",
        #    "The rancher node command for adding the worker node must be"
        #    "included as part of config_rancher_kube")
        #user_data += "\n"
        #return user_data
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

    def _create_rancher_client(self, rancher_cfg):
        return RancherClient(rancher_cfg.get('rancher_url'),
                             rancher_cfg.get('rancher_api_key'),
                             rancher_cfg.get('rancher_cluster_id'),
                             rancher_cfg.get('rancher_project_id'))

    def delete(self, provider, deployment):
        """
        Delete resource(s) associated with the supplied deployment.

        This is a blocking call that will wait until the instance is marked
        as deleted or disappears from the provider.

        *Note* that this method will delete resource(s) associated with
        the deployment - this is an un-recoverable action.
        """
        app_config = deployment.get('app_config')
        rancher_cfg = app_config.get('config_rancher_kube')
        rancher_client = self._create_rancher_client(rancher_cfg)
        node_ip = deployment.get(
            'launch_result', {}).get('cloudLaunch', {}).get('publicIP')
        rancher_node_id = rancher_client.find_node(ip=node_ip)
        if rancher_node_id:
            rancher_client.drain_node(rancher_node_id)
            # during tests, node_ip is None, so skip sleep if so
            if node_ip:
                time.sleep(60)
            # remove node from rancher
            rancher_client.delete_node(rancher_node_id)
        # delete the VM
        return super().delete(provider, deployment)

    def _get_configurer(self, app_config):
        # CloudMan2 can only be configured with ansible
        return RancherKubernetesAnsibleAppConfigurer()

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
        # Add required cluster tag for AWS
        if provider.PROVIDER_ID == "aws":
            inst_id = result['cloudLaunch'].get('instance').get('id')
            cluster_id = app_config.get('config_rancher_kube', {}).get(
                'rancher_cluster_id')
            inst = provider.compute.instances.get(inst_id)
            # pylint:disable=protected-access
            inst._ec2_instance.create_tags(
                Tags=[{'Key': f'kubernetes.io/cluster/{cluster_id}',
                       'Value': "owned"}])
        return result


class RancherKubernetesAnsibleAppConfigurer(AnsibleAppConfigurer):
    """Add CloudMan2 specific vars to playbook."""

    def configure(self, app_config, provider_config):
        playbook_vars = [
            ('ansible_shell_command', app_config.get('config_rancher_kube', {}).get(
                'rancher_node_command'))
        ]
        return super().configure(app_config, provider_config,
                                 playbook_vars=playbook_vars)
