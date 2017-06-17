from django.template.defaultfilters import slugify
import cminfrastructure
import inspect
import uuid
from abc import abstractstaticmethod


class CMBaseModel(object):

    def __init__(self, api):
        self._api = api

    @property
    def api(self):
        return self._api

    def to_json(self):
        # Get all attributes but filter methods and private/magic ones
        attr = inspect.getmembers(
            self,
            lambda a: not(inspect.isroutine(a)) and not
            isinstance(a, cminfrastructure.api.CMService) and
            not isinstance(a, cminfrastructure.api.CloudManAPI))
        js = {k: v for(k, v) in attr if not k.startswith('_')}
        return js

    @abstractstaticmethod
    def from_json(api, val):
        pass


class CMCloud(CMBaseModel):

    def __init__(self, api, name, provider_id):
        super(CMCloud, self).__init__(api)
        self.cloud_id = slugify(name)
        self.name = name
        self.provider_id = provider_id
        self.nodes = cminfrastructure.api.CMCloudNodeService(self)

    def delete(self):
        self.api.clouds.delete(self.cloud_id)

    @staticmethod
    def from_json(api, val):
        return CMCloud(api, val['name'], val.get('provider_id'))


class CMAWSCloud(CMCloud):

    def __init__(self, api, name, aws_access_key, aws_secret_key,
                 ec2_region_name, ec2_region_endpoint, ec2_conn_path="/",
                 ec2_is_secure=True, ec2_port=None, s3_host, s3_conn_path="/",
                 s3_is_secure=True, s3_port=None):
        super(CMCloud, self).__init__(api, name, "aws")
        self.aws_access_key = aws_access_key
        self.aws_secret_key = aws_secret_key
        self.ec2_region_name = ec2_region_name
        self.ec2_region_endpoint = ec2_region_endpoint
        self.ec2_conn_path = ec2_conn_path
        self.ec2_is_secure = ec2_is_secure
        self.ec2_port = ec2_port
        self.s3_host = s3_host
        self.s3_conn_path = s3_conn_path
        self.s3_is_secure = s3_is_secure
        self.s3_port = s3_port
        self.s3_port = s3_port


class CMOpenStackCloud(CMCloud):

    def __init__(self, api, name, username, password, project_name, auth_url,
                 region_name, identity_api_version, project_domain_name=None,
                 user_domain_name=None):
        super(CMCloud, self).__init__(api, name, "aws")
        self.username = username
        self.password = password
        self.project_name = project_name
        self.auth_url = auth_url
        self.region_name = region_name
        self.identity_api_version = identity_api_version
        self.project_domain_name = project_domain_name
        self.user_domain_name = user_domain_name


class CMCloudNode(CMBaseModel):

    def __init__(self, api, cloud_id, name, instance_type, node_id=None):
        super(CMCloudNode, self).__init__(api)
        self.id = node_id or str(uuid.uuid4())
        self.cloud_id = cloud_id
        self.name = name
        self.instance_type = instance_type

    def delete(self):
        self.api.clouds.delete(self.cloud_id)

    @staticmethod
    def from_json(api, val):
        return CMCloudNode(api, val['cloud_id'], val['name'],
                           val['instance_type'], node_id=val['id'])
