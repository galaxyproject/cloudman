import os

from django.apps import AppConfig

DEFAULT_MACRO_FILE = os.path.join(os.path.dirname(__file__), 'default_macros.j2')


class HelmsManConfig(AppConfig):
    name = "helmsman"

    def __init__(self, app_name, app_module):
        super().__init__(app_name, app_module)
        with open(DEFAULT_MACRO_FILE) as f:
            self.default_macros = f.read()
