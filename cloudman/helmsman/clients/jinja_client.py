"""A wrapper around the Jinjactl commandline client"""
import jinja2

class JinjaService(object):

    def __init__(self, client):
        self._client = client

    def client(self):
        return self._client


class JinjaClient(JinjaService):

    def __init__(self):
        super(JinjaClient, self).__init__(self)
        self._templates_svc = JinjaTemplatingService(self)

    @property
    def templates(self):
        return self._templates_svc


class JinjaTemplatingService(JinjaService):

    def __init__(self, client):
        super(JinjaTemplatingService, self).__init__(client)

    def render(self, macros, values, **kwargs):
        tmpl = jinja2.Template("\n".join([macros, values]))
        return tmpl.render({"context": kwargs})
