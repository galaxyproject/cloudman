from tempfile import NamedTemporaryFile
from os.path import exists

from cm.boot.util import _is_running, _make_dir

from test_utils import test_logger


def test_is_running():
    # If this test is executing, there must be a python process.
    assert _is_running(test_logger(), "python")
    # Highly unlikely there is a process called flork78 on this system.
    assert not _is_running(test_logger(), "flork78")


def test_make_dir():
    temp = NamedTemporaryFile().name
    assert not exists(temp)
    _make_dir(test_logger(), temp)
    assert exists(temp)
