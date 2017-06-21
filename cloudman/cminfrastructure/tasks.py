"""Tasks to be executed asynchronously (via Celery)."""
import logging as log
from celery.app import shared_task
from .exceptions import InvalidStateException
from .api import CMInfrastructureAPI
import traceback


def populate_task_status(node, task_id, status, message=None,
                         stack_trace=None):
    task = node.tasks.get(task_id)
    task.status = 'FAILED'
    task.message = message
    task.stack_trace = stack_trace
    node.tasks.update(task)


@shared_task
def create_node(cloud_id, node_id, task_id=None):
    """Launch a VM create task on the given cloud"""
    node = CMInfrastructureAPI().clouds.get(cloud_id).nodes.get(node_id)
    populate_task_status(node, task_id, "IN_PROGRESS",
                         message="Launching a new node")
    try:
        if len(node.tasks.list()) > 0:
            raise InvalidStateException("A create task has already been run"
                                        " for this node and cannot be rerun.")
        log.debug("Launching VM")
        populate_task_status(node, task_id, "SUCCESS",
                             message="Successfully launched")
        return None
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
        if len(node.tasks.list()) > 0:
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
