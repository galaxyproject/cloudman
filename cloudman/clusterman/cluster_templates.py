import abc
from rest_framework.exceptions import ValidationError
from cloudlaunch import models as cl_models


class CMClusterTemplate(object):

    def __init__(self, context, cluster):
        self.context = context
        self.cluster = cluster

    @property
    def connection_settings(self):
        return self.cluster.connection_settings

    @abc.abstractmethod
    def add_node(self, name, size):
        pass

    @abc.abstractmethod
    def remove_node(self):
        pass

    @abc.abstractmethod
    def activate_autoscaling(self, min_nodes=0, max_nodes=None, size=None):
        pass

    @abc.abstractmethod
    def deactivate_autoscaling(self):
        pass

    @staticmethod
    def get_template_for(context, cluster):
        if cluster.cluster_type == "KUBE_RKE":
            return CMRKETemplate(context, cluster)
        else:
            raise KeyError("Cannon get cluster template for unknown cluster "
                           "type: %s" % cluster.cluster_type)


class CMRKETemplate(CMClusterTemplate):

    def __init__(self, context, cluster):
        super(CMRKETemplate, self).__init__(context, cluster)
        settings = cluster.connection_settings.get('rke_config')
        self._rke_registration_server = settings.get('rke_registration_server')
        self._rke_registration_token = settings.get('rke_registration_token')
        self._rke_cluster_id = settings.get('rke_cluster_id')

    @property
    def rke_registration_server(self):
        return self._rke_registration_server

    @property
    def rke_registration_token(self):
        return self._rke_registration_token

    @property
    def rke_cluster_id(self):
        return self._rke_cluster_id

    def _find_matching_vm_type(self, zone_model=None, default_vm_type=None,
                               min_vcpus=0, min_ram=0, vm_family=""):
        """
        Finds the vm_type that best matches the given criteria. If no criteria
        is specified, will return the default vm type.

        :param zone_model:
        :param default_vm_type:
        :param min_vcpus:
        :param min_ram:
        :param vm_family:
        :return:
        """
        vm_type = default_vm_type or self.cluster.default_vm_type
        if min_vcpus > 0 or min_ram > 0 or not vm_type.startswith(vm_family):
            # Add some accommodation for rancher and k8s reserved resources
            # https://kubernetes.io/docs/tasks/administer-cluster/reserve-compute-resources/
            min_vcpus += 1.0
            min_ram *= 1.1

            cloud = self.context.cloudlaunch_client.infrastructure.clouds.get(
                zone_model.region.cloud.id)
            region = cloud.regions.get(zone_model.region.region_id)
            zone = region.zones.get(zone_model.zone_id)
            default_matches = zone.vm_types.list(vm_type_prefix=vm_type)
            if default_matches:
                default_match = default_matches[0]
                min_vcpus = min_vcpus if min_vcpus > float(default_match.vcpus) else default_match.vcpus
                min_ram = min_ram if min_ram > float(default_match.ram) else default_match.ram
            candidates = zone.vm_types.list(min_vcpus=min_vcpus, min_ram=min_ram,
                                            vm_type_prefix=vm_family)
            if candidates:
                candidate_type = sorted(candidates, key=lambda x: float(x.vcpus) * float(x.ram))[0]
                return candidate_type.name
        return vm_type

    def add_node(self, name, vm_type=None, zone=None, min_vcpus=0, min_ram=0, vm_family=""):
        settings = self.cluster.connection_settings
        zone = zone or self.cluster.default_zone
        deployment_target = cl_models.CloudDeploymentTarget.objects.get(
            target_zone=zone)
        params = {
            'name': name,
            'application': 'cm_rke_kubernetes_plugin',
            'deployment_target_id': deployment_target.id,
            'application_version': '0.1.0',
            'config_app': {
                'action': 'add_node',
                'config_kube_rke': {
                    'rke_registration_server': self.rke_registration_server,
                    'rke_registration_token': self.rke_registration_token,
                    'rke_cluster_id': self.rke_cluster_id
                },
                "config_appliance": {
                    "sshUser": "ubuntu",
                    "runner": "ansible",
                    "repository": "https://github.com/CloudVE/cloudman-boot",
                    "inventoryTemplate":
                        "[controllers]\n\n"
                        "[agents]\n"
                        "${host}\n\n"
                        "[rke_cluster:children]\n"
                        "controllers\n"
                        "agents\n\n"
                        "[all:vars]\n"
                        "ansible_ssh_port=22\n"
                        "ansible_user='${user}'\n"
                        "ansible_ssh_private_key_file=pk\n"
                        "ansible_ssh_extra_args='-o StrictHostKeyChecking=no"
                        " -o ControlMaster=no'\n"
                },
                'config_cloudlaunch': (settings.get('app_config', {})
                                       .get('config_cloudlaunch', {})),
                'config_cloudman': {
                    'cluster_name': self.cluster.name
                }
            }
        }

        params['config_app']['config_cloudlaunch']['vmType'] = \
            self._find_matching_vm_type(
                zone_model=zone, default_vm_type=vm_type, min_vcpus=min_vcpus,
                min_ram=min_ram, vm_family=vm_family)

        print("Adding node: {0} of type: {1}".format(
            name, params['config_app']['config_cloudlaunch']['vmType']))

        # Don't use hostname config
        params['config_app']['config_cloudlaunch'].pop('hostnameConfig', None)
        try:
            print("Launching node with settings: {0}".format(params))
            return self.context.cloudlaunch_client.deployments.create(**params)
        except Exception as e:
            raise ValidationError("Could not launch node: " + str(e))

    def remove_node(self, node):
        return self.context.cloudlaunch_client.deployments.tasks.create(
            action='DELETE', deployment_pk=node.deployment.pk)
