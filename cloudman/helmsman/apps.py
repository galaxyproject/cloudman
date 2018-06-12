from django.apps import AppConfig


class HelmsmanConfig(AppConfig):
    name = 'helmsman'

    def ready(self):
        pass
#         self.run_helm_init()
#         add_default_repos()
#         add_default_charts()
