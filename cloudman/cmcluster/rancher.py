import requests
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

    KUBE_CONFIG_URL = ("{rancher_url}/v3/clusters/{cluster_id}"
                       "?action=generateKubeconfig")
    INSTALLED_APP_URL = ("{rancher_url}/v3/projects/{project_id}/app"
                         "?targetNamespace=galaxy-ns")
    NODE_COMMAND_URL = "{rancher_url}/v3/clusterregistrationtoken"

    def __init__(self, rancher_url, api_key, cluster_id, project_id):
        self.rancher_url = rancher_url
        self.api_key = api_key
        self.cluster_id = cluster_id
        self.project_id = project_id

    def format_url(self, url):
        return url.format(rancher_url=self.rancher_url,
                          cluster_id=self.cluster_id,
                          project_id=self.project_id)

    def get_auth(self):
        return RancherAuth(self)

    def _api_get(self, url):
        return requests.get(self.format_url(url), auth=self.get_auth(),
                            verify=False).json()

    def _api_post(self, url, data):
        return requests.post(self.format_url(url), auth=self.get_auth(),
                             verify=False, json=data).json()

    def _api_put(self, url, data):
        return requests.put(self.format_url(url), auth=self.get_auth(),
                            verify=False, json=data).json()

    def list_installed_charts(self):
        return self._api_get(self.INSTALLED_APP_URL).get('data')

    def update_installed_chart(self, data):
        r = self._api_put(data.get('links').get('self'), data)
        return r

    def fetch_kube_config(self):
        return self._api_post(self.KUBE_CONFIG_URL, data=None).get('config')

    def get_cluster_registration_command(self):
        return self._api_post(
            self.NODE_COMMAND_URL,
            data={"type": "clusterRegistrationToken",
                  "clusterId": f"{self.cluster_id}"}
        ).get('nodeCommand')
