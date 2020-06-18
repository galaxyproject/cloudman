from django.contrib.auth.models import User
from django.test import TestCase

from helmsman.api import HelmsManAPI
from helmsman.api import HMServiceContext

class InstallTemplateUnitTest(TestCase):


    def setUp(self):
        admin = User.objects.get_or_create(username='admin', is_superuser=True)[0]
        self.client = HelmsManAPI(HMServiceContext(user=admin))

    def test_render_values(self):
        base_tpl = ('hosts:\n'
                    '  - ~\n'
                    '  {%- if not (context.domain | ipaddr) %}\n'
                    '  - "{{ context.domain }}"\n'
                    '  {%- endif %}')

        tpl = self.client.templates.create(
                        'dummytpl', 'dummyrepo', 'dummychart',
                        template=base_tpl)

        ip_expected = ('hosts:\n'
                       '  - ~')
        host_expected = ('hosts:\n'
                         '  - ~\n'
                         '  - "example.com"')

        ip_rendered = tpl.render_values(context={'domain': '192.168.2.1'})
        self.assertEquals(ip_expected, ip_rendered)

        host_rendered = tpl.render_values(context={'domain': 'example.com'})
        self.assertEquals(host_expected, host_rendered)
