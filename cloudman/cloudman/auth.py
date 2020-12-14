import requests

from django.core.cache import cache


def get_metadata(metadata_endpoint):
    op_metadata = cache.get('OIDC_OP_METADATA')
    if not op_metadata:
        response = requests.get(url=metadata_endpoint, verify=False)
        response.raise_for_status()
        op_metadata = response.json()
        cache.set('OIDC_OP_METADATA', op_metadata)
    return op_metadata


def get_from_well_known(metadata_endpoint, attr):
    metadata = get_metadata(metadata_endpoint)
    return metadata.get(attr)
