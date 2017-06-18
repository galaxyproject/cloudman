"""Tasks to be executed asynchronously (via Celery)."""
import logging as log
from celery.app import shared_task


@shared_task
def create_node(cloud_id, node_id):
    """Launch a VM create task on the given cloud"""
    log.debug("Launching VM")
    return "done"
