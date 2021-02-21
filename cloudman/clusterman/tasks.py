"""Tasks to be executed asynchronously (via Celery)."""
from celery.app import shared_task
from celery.result import AsyncResult
from celery.result import allow_join_result

from django.contrib.auth.models import User

from clusterman import api
from clusterman.clients.kube_client import KubeClient


def node_not_present(node):
    kube_client = KubeClient()
    launch_task = node.deployment.tasks.filter(action='LAUNCH').first()
    node_ip = launch_task.result.get('cloudLaunch', {}).get('private_ip')
    print(f"Checking for presence of node ip: {node_ip}")
    k8s_node = kube_client.nodes.find(node_ip)
    return not k8s_node


def wait_till_deployment_deleted(deployment_delete_task_id):
    with allow_join_result():
        deployment_delete_task = AsyncResult(deployment_delete_task_id)
        print("Waiting for node deployment to be deleted...")
        deployment_delete_task.wait()
        if deployment_delete_task.successful():
            print("Deployment deleted successfully.")
            return
        else:
            task_meta = deployment_delete_task.backend.get_task_meta(
                deployment_delete_task.id)
            print(f"Deployment delete failed: {task_meta.get('status')} with traceback:"
                  f"{task_meta.get('traceback')}")


@shared_task(bind=True, expires=120)
def delete_node(self, deployment_delete_task_id, cluster_id, node_id):
    """
    Triggers a delete task through cloudlaunch.
    If successful, removes reference to node
    """
    admin = User.objects.filter(is_superuser=True).first()
    cmapi = api.CloudManAPI(api.CMServiceContext(user=admin))
    cluster = cmapi.clusters.get(cluster_id)
    node = cluster.nodes.get(node_id)
    wait_till_deployment_deleted(deployment_delete_task_id)
    if node_not_present(node):
        # if desired state has been reached, clusterman no longer
        # needs to maintain a reference to the node
        # call the saved django delete method which we remapped
        print(f"Node does not exist, removing clusterman reference.")
        node.original_delete()
    else:
        print("Deleted node still exists, not removing clusterman"
              "node reference.")
