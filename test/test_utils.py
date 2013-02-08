
from tempfile import mkdtemp
from os.path import join, dirname
from os import pardir
from shutil import copyfile


TEST_INDICES_DIR = "/mnt/indicesTest"
TEST_DATA_DIR = "/mnt/dataTest"
TEST_TOOLS_DIR = "/mnt/toolsTest"


class TestApp(object):
    """ Dummy version of UniverseApplication used for
    unit testing."""

    def __init__(self, ud={}, **kwargs):
        self.path_resolver = TestPathResolver()
        self.ud = ud
        for key, value in kwargs.iteritems():
            setattr(self, key, value)


class TestPathResolver(object):
    """ Dummy implementation of PathResolver
    for unit testing."""

    def __init__(self):
        self._galaxy_home = None
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
