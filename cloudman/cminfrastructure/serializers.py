"""DRF serializers for the CloudMan Create API endpoints."""

from rest_framework import serializers
from .api import CMInfrastructureAPI
#from cloudbridge import CloudProviderFactory


class CloudSerializer(serializers.Serializer):
    slug = serializers.CharField(read_only=True)
    name = serializers.CharField()
    cloud_type = serializers.ChoiceField(choices=[('aws', 'AWS'), ('openstack', 'OpenStack')])
    extra_data = serializers.SerializerMethodField()

    def get_extra_data(self, obj):
        if hasattr(obj, 'aws'):
            aws = obj.aws
            extra_data = {}
            if aws.compute:
                compute = aws.compute
                extra_data['ec2_region_name'] = compute.ec2_region_name
                extra_data['ec2_region_endpoint'] = compute.ec2_region_endpoint
                extra_data['ec2_conn_path'] = compute.ec2_conn_path
                extra_data['ec2_port'] = compute.ec2_port
                extra_data['ec2_is_secure'] = compute.ec2_is_secure
            if aws.object_store:
                s3 = aws.object_store
                extra_data['s3_host'] = s3.s3_host
                extra_data['s3_conn_path'] = s3.s3_conn_path
                extra_data['s3_port'] = s3.s3_port
                extra_data['s3_is_secure'] = s3.s3_is_secure
            return extra_data
        elif hasattr(obj, 'openstack'):
            os = obj.openstack
            return {
                'auth_url': os.auth_url,
                'region_name': os.region_name,
                'identity_api_version': os.identity_api_version
            }
        else:
            return {}

    def create(self, valid_data):
        return CMInfrastructureAPI().clouds.create(
            valid_data.get('name'), valid_data.get('cloud_type'))


class VMSerializer(serializers.Serializer):
    """A serializer for a virtual machine resource."""

    id = serializers.CharField()
    name = serializers.CharField()
