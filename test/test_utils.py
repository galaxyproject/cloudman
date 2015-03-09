from tempfile import mkdtemp
from os.path import join, dirname
from os import pardir
from shutil import copyfile, rmtree
from logging import getLogger
from contextlib import contextmanager
from datetime import datetime, timedelta

from cm.util.bunch import Bunch
from cm.config import Configuration

from mock import patch

TEST_INDICES_DIR = "/mnt/indicesTest"
TEST_DATA_DIR = "/mnt/dataTest"
TEST_TOOLS_DIR = "/mnt/toolsTest"


class TestApp(object):
    """ Dummy version of UniverseApplication used for
    unit testing."""

    TESTFLAG = False

    def __init__(self, ud={}, **kwargs):
        self.path_resolver = TestPathResolver()
        self.ud = ud
        for key, value in kwargs.iteritems():
            setattr(self, key, value)
        self.manager = TestManager()
        self.cloud_interface = TestCloudInterface()
        self.config = Configuration(kwargs, self.ud)


class TestCloudInterface(object):

    def __init__(self):
        self.terminate_expectations = {}

    def set_mock_instances(self, instances=[]):
        self.instances = instances

    def get_all_instances(self, id):
        return [Bunch(instances=self.instances)]

    def expect_terminatation(self, instance_id, spot_request_id=None, success=True):
        self.terminate_expectations[instance_id] = (spot_request_id, success)

    def terminate_instance(self, instance_id, spot_request_id):
        if instance_id not in self.terminate_expectations:
            assert False, "terminate_instance called with unexpected instance_id"
        (expected_spot_request_id, success) = self.terminate_expectations[instance_id]
        if spot_request_id != expected_spot_request_id:
            assert False, "terminate_instance called with wrong spot_request_id"
        return success


class TestManager(object):
    manager_type = "master"

    def __init__(self, worker_instances=[]):
        self.worker_instances = worker_instances
        self.console_monitor = Bunch(conn=None)


class TestPathResolver(object):
    """ Dummy implementation of PathResolver
    for unit testing."""

    def __init__(self):
        self._galaxy_home = None
        self._lwr_home = None
        self.galaxy_data = TEST_DATA_DIR
        self.galaxy_tools = TEST_TOOLS_DIR
        self.galaxy_indices = TEST_INDICES_DIR

    @property
    def galaxy_home(self):
        if not self._galaxy_home:
            self._galaxy_home = mkdtemp()
            cm_directory = join(dirname(__file__), pardir)
            src = join(cm_directory, 'universe_wsgi.ini.cloud')
            dest = join(self._galaxy_home, 'universe_wsgi.ini')
            copyfile(src, dest)
            copyfile(src, '%s.sample' % dest)
        return self._galaxy_home

    @property
    def lwr_home(self):
        if not self._lwr_home:
            self._lwr_home = mkdtemp()
        return self._lwr_home


def test_logger():
    return getLogger(__name__)


DEFAULT_MOCK_BOTO_INSTANCE_ID = "TEST_INSTANCE"


class MockBotoInstance(object):

    def __init__(self, id=DEFAULT_MOCK_BOTO_INSTANCE_ID):
        self.id = id
        self.ip_address = "10.1.0.1"
        self.state = None
        self.was_updated = False
        self.was_rebooted = False

    def update(self):
        self.was_updated = True

    def reboot(self):
        self.was_rebooted = True


@contextmanager
def instrument_time():
    class MockTime(object):

        def __init__(self, mock_now):
            self.initial = datetime.utcnow()
            self.mock_now = mock_now
            self.mock_now.return_value = self.initial

        def set_offset(self, **kwds):
            new_time = self.initial + timedelta(**kwds)
            self.mock_now.return_value = new_time

    with patch("cm.util.Time.now") as mock_now:
        yield MockTime(mock_now)


@contextmanager
def mock_runner():
    with patch("cm.util.misc.run") as mock_run:
        mock_run.return_value = True
        yield mock_run


@contextmanager
def temp_dir():
    temp_directory = mkdtemp()
    yield temp_directory
    rmtree(temp_directory)
