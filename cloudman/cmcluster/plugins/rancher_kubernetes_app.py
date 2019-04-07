"""Plugin implementation for a simple web application."""
from celery.utils.log import get_task_logger

from cloudlaunch.backend_plugins.base_vm_app import BaseVMAppPlugin
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
        user_data = "#!/bin/bash\n"
        user_data += get_required_val(
            rancher_config, "rancher_node_command",
            "The rancher node command for adding the worker node must be"
            "included as part of config_rancher_kube")
        return user_data

    def deploy(self, name, task, app_config, provider_config, **kwargs):
        """
        Handle the app launch process and wait for http.

        Pass boolean ``check_http`` as a ``False`` kwarg if you don't
        want this method to perform the app http check and prefer to handle
        it in the child class.
        """
        result = super(RancherKubernetesApp, self).deploy(
            name, task, app_config, provider_config)
        return result

    def delete(self, provider, deployment):
        """
        Delete resource(s) associated with the supplied deployment.

        This is a blocking call that will wait until the instance is marked
        as deleted or disappears from the provider.

        *Note* that this method will delete resource(s) associated with
        the deployment - this is an un-recoverable action.
        """
        # key += get_required_val(rancher_config, "RANCHER_API_KEY")
        # Contact rancher API and delete node
        return super(RancherKubernetesApp, self).delete(provider, deployment)
