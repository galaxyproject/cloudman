from django.apps import AppConfig
from .helm.client import HelmClient


class HelmsmanConfig(AppConfig):
    name = 'helmsman'

    def ready(self):
        try:
            self.setup_helmsman()
        except Exception as e:
            print("HelmsManConfig.ready()->setup_helmsman(): An error occurred"
                  " while setting up HelmsMan!!: ", e)

    def setup_helmsman(self):
        client = HelmClient()
        print("Initializing tiller...")
        client.helm_init(wait=True)
        print("Adding default repos...")
        client.repositories.create(
            "galaxyproject",
            "https://raw.githubusercontent.com/CloudVE/helm-charts/master/")
        self.add_default_charts(client)

    def add_default_charts(self, client):
        print("Installing default charts...")
        self.install_if_not_exist(client, "galaxyproject", "galaxy-stable")

    def install_if_not_exist(self, client, repo_name, chart_name):
        existing_release = [r for r in client.releases.list()
                            if chart_name in r.get('CHART')]
        if existing_release:
            print(f"Chart {repo_name}/{chart_name} already installed.")
        else:
            client.repositories.update()
            print(f"Installing chart {repo_name}/{chart_name} into namespace"
                  " default")
            client.releases.create(f"{repo_name}/{chart_name}", "default")
