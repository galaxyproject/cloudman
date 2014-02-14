from cm.boot.object_store import _get_file_from_bucket
from test_utils import test_logger
from StringIO import StringIO
from tempfile import NamedTemporaryFile
from os.path import exists


def test_get_file_from_bucket():
    mock_s3_conn = S3ConnMock()
    mock_s3_conn.responses.append(MockResponse("Test Contents"))
    mock_bucket = BucketMock("bucket_test", mock_s3_conn)
    mock_bucket.files["remote_file"] = "moocow"
    temp = NamedTemporaryFile().name
    assert not exists(temp)
    _get_file_from_bucket(test_logger(),
                          mock_s3_conn,
                          "bucket_test",
                          "remote_file",
                          temp)
    assert exists(temp)
    assert open(temp, "r").read() == "Test Contents"


class BucketMock(object):

    def __init__(self, name, connection):
        self.connection = connection
        self.name = name
        connection.buckets[name] = self
        self.files = {}

    def lookup(self, arg):
        return True


class S3ConnMock(object):

    def __init__(self):
        self.buckets = {}
        self.provider = self
        self.responses = []

    def __getattr__(self, name):
        return None

    def get_bucket(self, bucket_name):
        return self.buckets[bucket_name]

    def make_request(self, *args, **kwds):
        return self.responses.pop()


class MockResponse(object):

    def __init__(self, response_body):
        self.status = 200
        self.msg = {}
        s = StringIO(response_body)
        self.read = s.read

    def getheader(self, key, default):
        return default
