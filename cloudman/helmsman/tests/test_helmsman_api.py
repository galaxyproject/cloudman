import argparse
import csv
from io import StringIO
from unittest.mock import patch
import uuid
import yaml

from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase


class MockHelm(object):

    """ Mocks all calls to the helm command"""
    def __init__(self, testcase):
        self.patch1 = patch(
            'helmsman.helm.client.HelmClient._check_environment',
            return_value=True)
        self.patch2 = patch('helmsman.helm.helpers.run_command',
                            self.mock_run_command)
        self.patch1.start()
        self.patch2.start()
        testcase.addCleanup(self.patch2.stop)
        testcase.addCleanup(self.patch1.stop)
        self.list_field_name = ["NAME", "REVISION", "UPDATED", "STATUS", "CHART", "APP VERSION", "NAMESPACE"]
        self.installed_charts = [
            {
                'NAME': 'turbulent-markhor',
                'REVISION': 12,
                'UPDATED': 'Fri Apr 19 05:33:37 2019',
                'STATUS': 'DEPLOYED',
                'CHART': 'cloudlaunch-0.2.0',
                'APP VERSION': '2.0.2',
                'NAMESPACE': 'cloudlaunch',
                'VALUES': {
                    'foo': 'bar'
                }
            }
        ]

    def _parse_helm_command(self, command):
        parser = argparse.ArgumentParser(prog='helm')
        subparsers = parser.add_subparsers(help='Available Commands')

        parser_init = subparsers.add_parser('init', help='init Helm')
        parser_init.set_defaults(func=self._helm_init)

        parser_list = subparsers.add_parser('list', help='list releases')
        parser_list.set_defaults(func=self._helm_list)

        parser_inst = subparsers.add_parser('install', help='install a chart')
        parser_inst.add_argument(
            'chart', type=str, help='chart name')
        parser_inst.add_argument('--namespace', type=str, help='namespace')
        parser_inst.add_argument('--version', type=str, help='version')
        parser_inst.add_argument(
            '-f', '--values', type=str, help='value files')
        parser_inst.set_defaults(func=self._helm_install)

        parser_repo = subparsers.add_parser('repo', help='install a chart')
        subparser_repo = parser_repo.add_subparsers()
        p_repo_update = subparser_repo.add_parser('update', help='update repo')
        p_repo_update.set_defaults(func=self._helm_repo_update)
        p_repo_add = subparser_repo.add_parser('add', help='install repo')
        p_repo_add.set_defaults(func=self._helm_repo_add)

        parser_get = subparsers.add_parser(
            'get', help='download a named release')
        subparser_get = parser_get.add_subparsers()

        p_get_values = subparser_get.add_parser(
            'values', help='download values for a release')
        p_get_values.add_argument(
            'release', type=str, help='release name')
        p_get_values.add_argument(
            '--all', action='store_true', help='dump all values')
        p_get_values.set_defaults(func=self._helm_get_values)

        p_get_manifest = subparser_get.add_parser(
            'manifest', help='download manifest for a release')
        p_get_manifest.set_defaults(func=self._helm_get_manifest)

        args = parser.parse_args(command)
        return args.func(args)

    def _helm_init(self, args):
        # pretend to succeed
        pass

    def _helm_list(self, args):
        # pretend to succeed
        with StringIO() as output:
            writer = csv.DictWriter(output, fieldnames=self.list_field_name, delimiter="\t",
                                    extrasaction='ignore')
            writer.writeheader()
            writer.writerows(self.installed_charts)
            return output.getvalue()

    def _helm_install(self, args):
        repo_name, chart_name = args.chart.split('/')
        chart = {
            'NAME': '%s-%s' % (chart_name, uuid.uuid4().hex[:6]),
            'REVISION': 1,
            'UPDATED': 'Fri Apr 19 05:33:37 2019',
            'STATUS': 'DEPLOYED',
            'CHART': '%s-%s' % (chart_name, args.version or "1.0.0"),
            'APP VERSION': '2.0.2',
            'NAMESPACE': args.namespace,
            'VALUES': {}
        }
        if args.values:
            with open(args.values, 'r') as f:
                values = yaml.safe_load(f)
                chart['VALUES'] = values
        self.installed_charts.append(chart)
        return chart

    def _helm_repo_update(self, args):
        # pretend to succeed
        pass

    def _helm_repo_add(self, args):
        # pretend to succeed
        pass

    def _helm_get_values(self, args):
        matches = [chart for chart in self.installed_charts
                   if chart.get('NAME') == args.release]
        if matches:
            chart = matches[0]
            with StringIO() as output:
                yaml.safe_dump(chart.get('VALUES'), output)
                return output.getvalue()
        else:
            return 'Error: release: "%s" not found' % args.release

    def _helm_get_manifest(self, args):
        # pretend to succeed
        pass

    def mock_run_command(self, command, shell=False):
        if isinstance(command, list):
            prog = command[0]
        else:
            prog = command or ""

        if prog.startswith("helm"):
            return self._parse_helm_command(command[1:])
        elif prog.startswith("kubectl create"):
            # pretend to succeed
            pass
        else:
            raise Exception("Unrecognised command: {0}".format(prog))


# Create your tests here.
class HelmsManServiceTestBase(APITestCase):

    def setUp(self):
        self.mock_helm = MockHelm(self)
        self.client.force_login(
            User.objects.get_or_create(username='admin')[0])

    def tearDown(self):
        self.client.logout()


class RepoServiceTests(HelmsManServiceTestBase):

    def test_crud_repo(self):
        """
        Ensure we can register a new cluster with cloudman.
        """
        # Check listing
        url = reverse('repositories-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class ChartServiceTests(HelmsManServiceTestBase):

    CHART_DATA = {
        'id': 'precise-sparrow',
        'name': 'galaxy',
        'display_name': 'Galaxy',
        'chart_version': '3.0.0',
        'app_version': 'v19.05',
        'namespace': 'gvl',
        'access_address': "/galaxy/",
        'state': "DEPLOYED",
        'updated': "Wed Jun 19 18:02:26 2019",
        'values': {
            'hello': 'world'
        }
    }

    def test_crud_chart(self):
        """
        Ensure we can register a new cluster with cloudman.
        """
        # create the object
        url = reverse('charts-list')
        response = self.client.post(url, self.CHART_DATA, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        # list existing objects
        url = reverse('charts-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        expected_data = {
            'name': self.CHART_DATA.get('name'),
            'display_name': self.CHART_DATA.get('name').title(),
            'chart_version': self.CHART_DATA.get('chart_version'),
            'namespace': self.CHART_DATA.get('namespace'),
            'state': self.CHART_DATA.get('state'),
            'values': self.CHART_DATA.get('values')
        }
        self.assertDictContainsSubset(expected_data, response.data['results'][1])

        # check it exists
        url = reverse('charts-detail', args=[response.data['results'][1]['id']])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertDictContainsSubset(expected_data, response.data)

        # # delete the object
        # url = reverse('charts-detail', args=[response.data['id']])
        # response = self.client.delete(url)
        # self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        #
        # # check it no longer exists
        # url = reverse('clusters-list')
        # response = self.client.get(url)
        # self.assertEqual(response.status_code, status.HTTP_200_OK)
