import html
import re
import requests

from django.contrib.auth.models import User
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase, APILiveServerTestCase


class CMCloudManAuthIntegrationTests(APILiveServerTestCase):
    host = "localhost"
    port = 8000
    REGEX_KEYCLOAK_LOGIN_ACTION = re.compile(r'action=\"(.*)\"\s+')
    REGEX_CSRF_TOKEN = re.compile(r'csrfmiddlewaretoken\" value=\"(.*)\"')

    def setUp(self):
        self.session = requests.Session()

    def _attempt_login(self):
        url = reverse('oidc_authentication_init')
        return self.session.get(f"http://localhost:8000{url}")

    def _attempt_logout(self):
        # first, get a CSRF token
        response = self._get_clusters()
        matches = self.REGEX_CSRF_TOKEN.search(response.text)
        csrftoken = html.unescape(matches.groups(1)[0])
        # now logout with that csrf token
        url = reverse('oidc_logout')
        return self.session.post(f"http://localhost:8000{url}", headers={'X-CSRFToken': csrftoken})

    def _get_clusters(self):
        url = reverse('clusterman:clusters-list')
        # retrieve html page
        return self.session.get(f"http://localhost:8000{url}?format=api")

    def test_redirects_to_keycloak(self):
        response = self._attempt_login()
        self.assertEqual(response.status_code, status.HTTP_200_OK, response)
        self.assertIn("auth/realms/master/protocol/openid-connect/auth", response.url)
        return response

    def _login_via_keycloak(self, username, password):
        response = self._attempt_login()
        response = self.session.get(response.url)
        matches = self.REGEX_KEYCLOAK_LOGIN_ACTION.search(response.text)
        auth_url = html.unescape(matches.groups(1)[0])
        response = self.session.post(auth_url, data={
            "username": username, "password": password})
        return response

    def test_can_auth_admin(self):
        response = self._login_via_keycloak("admin", "testpassword")
        # Should have redirected back if auth succeeded
        self.assertIn("http://localhost:8000/", response.url)

        # User should have been created
        oidc_user = User.objects.get(email="admin@cloudve.org")
        assert oidc_user.is_superuser
        assert oidc_user.is_staff

    def test_invalid_auth_admin(self):
        response = self._login_via_keycloak("admin", "wrongpassword")
        # Should not have redirected back if auth succeeded
        self.assertNotIn("http://localhost:8000/", response.url)

        # User should have been created
        with self.assertRaises(User.DoesNotExist):
            User.objects.get(email="admin@cloudve.org")

    def test_can_auth_non_admin(self):
        response = self._login_via_keycloak("nonadmin", "testpassword")
        # Should have redirected back if auth succeeded
        self.assertIn("http://localhost:8000/", response.url)

        # User should have been created
        oidc_user = User.objects.get(email="nonadmin@cloudve.org")
        assert not oidc_user.is_superuser
        assert not oidc_user.is_staff

    def test_can_logout(self):
        self._login_via_keycloak("nonadmin", "testpassword")
        response = self._attempt_logout()
        self.assertIn("auth/realms/master/protocol/openid-connect/logout", response.url)
