import requests
from string import Template
from requests.auth import AuthBase


class RancherAuth(AuthBase):

    def __init__(self, client):
        # setup any auth-related data here
        self.client = client

    def __call__(self, r):
        # modify and return the request
        r.headers['content-type'] = "application/json"
        r.headers['authorization'] = "Bearer " + self.client.api_key
        return r


class RancherClient(object):

    KUBE_CONFIG_URL = ("$rancher_url/v3/clusters/$cluster_id"
                       "?action=generateKubeconfig")
    INSTALLED_APP_URL = ("$rancher_url/v3/projects/$project_id/app"
                         "?targetNamespace=galaxy-ns")
    NODE_COMMAND_URL = "$rancher_url/v3/clusterregistrationtoken"
    NODE_LIST_URL = "$rancher_url/v3/nodes/?clusterId=$cluster_id"
    NODE_DRAIN_URL = "$rancher_url/v3/nodes/$node_id?action=drain"
    NODE_DELETE_URL = "$rancher_url/v3/nodes/$node_id"

    def __init__(self, rancher_url, api_key, cluster_id, project_id):
        self.rancher_url = rancher_url
        self.api_key = api_key
        self.cluster_id = cluster_id
        self.project_id = project_id

    def _format_url(self, url):
        result = Template(url).safe_substitute({
            'rancher_url': self.rancher_url,
            'cluster_id': self.cluster_id,
            'project_id': self.project_id
        })
        return result

    def _get_auth(self):
        return RancherAuth(self)

    def _api_get(self, url, data):
        return requests.get(self._format_url(url), auth=self._get_auth(),
                            verify=False, json=data).json()

    def _api_post(self, url, data, json_response=True):
        r = requests.post(self._format_url(url), auth=self._get_auth(),
                          verify=False, json=data)
        if json_response:
            return r.json()
        else:
            return r

    def _api_delete(self, url, data):
        return requests.delete(self._format_url(url), auth=self._get_auth(),
                               verify=False, json=data).json()

    def fetch_kube_config(self):
        return self._api_post(self.KUBE_CONFIG_URL, data=None).get('config')

    def get_cluster_registration_command(self):
        return self._api_post(
            self.NODE_COMMAND_URL,
            data={"type": "clusterRegistrationToken",
                  "clusterId": f"{self.cluster_id}"}
        ).get('nodeCommand')

    def get_nodes(self):
        return self._api_get(self.NODE_LIST_URL, data=None)

    def find_node(self, ip):
        matches = [n for n in self.get_nodes()['data']
                   if n.get('ipAddress') == ip or
                   n.get('externalIpAddress') == ip]
        return matches[0]['id'] if matches else None

    def drain_node(self, node_id):
        node_url = Template(self.NODE_DRAIN_URL).safe_substitute({
            'node_id': node_id
        })
        return self._api_post(node_url, data={
            "deleteLocalData": True,
            "force": True,
            "ignoreDaemonSets": True,
            "gracePeriod": "-1",
            "timeout": "60"
        }, json_response=False)

    def delete_node(self, node_id):
        node_url = Template(self.NODE_DELETE_URL).safe_substitute({
            'node_id': node_id
        })
        return self._api_delete(node_url, data=None)
