"""Tasks to be executed asynchronously (via Celery)."""
import logging as log
from celery.app import shared_task
from .exceptions import InvalidStateException
from .api import CMInfrastructureAPI
import traceback
from cloudbridge.cloud.factory import CloudProviderFactory, ProviderList
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend


def populate_task_status(node, task_id, status, message=None,
                         stack_trace=None):
    task = node.tasks.get(task_id)
    task.status = status
    task.message = message
    task.stack_trace = stack_trace
    node.tasks.update(task)


def _derive_public_key_from_private(pem_key):
    prv_key = serialization.load_pem_private_key(bytes(pem_key, "ascii"),
                                                 password=None,
                                                 backend=default_backend())
    return prv_key.public_key().public_bytes(
        serialization.Encoding.OpenSSH,
        serialization.PublicFormat.OpenSSH)


def _get_or_create_cluster_pk(provider, cloud):
    """
    The key generated here will be used for inter-node
    communication within the cluster.
    """
    if cloud.default_ssh_private_key and not cloud.default_ssh_public_key:
        # TODO: change this so that cloudbridge directly returns
        # public key: see https://github.com/gvlproject/cloudbridge/issues/49
        cloud.default_ssh_public_key = _derive_public_key_from_private(
            cloud.default_ssh_private_key)
        cloud.save()
    elif not cloud.default_ssh_private_key:
        key_pair = rsa.generate_private_key(
            backend=default_backend(),
            public_exponent=65537,
            key_size=2048)
        private_key = key_pair.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption())
        public_key = key_pair.public_key().public_bytes(
            serialization.Encoding.OpenSSH,
            serialization.PublicFormat.OpenSSH)
        cloud.default_ssh_private_key = private_key,
        cloud.default_ssh_public_key = public_key
        cloud.save()

    return (cloud.default_ssh_private_key, cloud.default_ssh_public_key)


@shared_task
def create_node(cloud_id, node_id, task_id=None):
    """Launch a VM create task on the given cloud"""
    cloud = CMInfrastructureAPI().clouds.get(cloud_id)
    node = cloud.nodes.get(node_id)
    populate_task_status(node, task_id, "IN_PROGRESS",
                         message="Launching a new node")
    try:
        if len(node.tasks.list()) > 1:
            raise InvalidStateException("A create task has already been run"
                                        " for this node and cannot be rerun.")
        log.debug("Launching VM")
        provider = CloudProviderFactory().create_provider(
            cloud.provider_id, cloud.provider_config)
        img = provider.compute.images.get(cloud.default_image_id)
        pub_key, prv_key = _get_or_create_cluster_pk(provider, cloud)
        user_id = cloud.default_login_user or "ubuntu"
        user_data = \
            f"#!/bin/bash\n" \
            f"echo \"{pub_key}\" >> /home/{user_id}/.ssh/authorized_keys" \
            f"chown {user_id}: /home/{user_id}/.ssh/authorized_keys\n" \
            f"chmod 0600 /home/{user_id}/.ssh/authorized_keys"
        subnet_id = cloud.default_subnet
        sg = cloud.default_security_group
        placement_zone = cloud.default_zone
        kp = cloud.default_user_kp
        inst_type = node.instance_type
        name = f"cm-node-{node.id}"

        task = create_node
        task.update_state(state='PROGRESSING',
                          meta={'action': "Launching an instance of type %s "
                                "with keypair %s in zone %s" %
                                (inst_type, kp.name, placement_zone)})
        inst = provider.compute.instances.create(
            name=name, image=img, instance_type=inst_type, subnet=subnet_id,
            key_pair=kp, security_groups=[sg], zone=placement_zone,
            user_data=user_data)

        # Save node data thus far
        node.instance_id = inst.id
        node.save()

        task.update_state(state='PROGRESSING',
                          meta={'action': "Waiting for instance %s" % inst.id})
        inst.wait_till_ready()

        node.public_ips = inst.public_ips
        node.private_ips = inst.private_ips
        node.save()

        populate_task_status(node, task_id, "SUCCESS",
                             message="Successfully launched")
        return inst.id
    except Exception as e:
        populate_task_status(node, task_id, "FAILED",
                             str(e), traceback.format_exc())
        raise e


@shared_task
def delete_node(cloud_id, node_id, task_id=None):
    """Delete a vm on the given cloud"""
    node = CMInfrastructureAPI().clouds.get(cloud_id).nodes.get(node_id)
    populate_task_status(node, task_id, "IN_PROGRESS",
                         message="Deleting node")
    try:
        if len(node.tasks.list()) > 1:
            raise InvalidStateException("A delete task has already been run"
                                        " for this node and cannot be rerun.")
        log.debug("Deleting VM")
        populate_task_status(node, task_id, "SUCCESS",
                             message="Successfully deleted")
        return None
    except Exception as e:
        populate_task_status(node, task_id, "FAILED",
                             str(e), traceback.format_exc())
        raise e
