"""
Utility functions used systemwide.

"""
import logging
import threading
import re
import os
import sys
from datetime import datetime

from cm.util.bunch import Bunch

# Define available states for various services
cluster_status = Bunch(
    STARTING="STARTING",  # or configuring services
    WAITING="WAITING",  # on user input
    READY="READY",  # to be used
    SHUTTING_DOWN="SHUTTING_DOWN",
    TERMINATED="TERMINATED",
    ERROR="ERROR"
)

# All of the following are used by the Instance class
instance_states = Bunch(
    PENDING="pending",
    RUNNING="running",
    SHUTTING_DOWN="shutting-down",
    TERMINATED="terminated",
    ERROR="error"
)
instance_lifecycle = Bunch(
    SPOT="Spot",
    ONDEMAND="On-demand"
)
spot_states = Bunch(
    OPEN="open",
    ACTIVE="active",
    CANCELLED="cancelled"
)

log = logging.getLogger(__name__)
_lock = threading.RLock()


def synchronized(func):
    """This wrapper will serialize access to 'func' to a single thread. Use it as a decorator."""
    def caller(*params, **kparams):
        _lock.acquire(True)  # Wait
        try:
            return func(*params, **kparams)
        finally:
            _lock.release()
    return caller


def file_iter(fname, sep=None):
    """
    This generator iterates over a file and yields its lines
    splitted via the C{sep} parameter. Skips empty lines and lines starting with
    the C{#} character.

    >>> lines = [ line for line in file_iter(__file__) ]
    >>> len(lines) !=  0
    True
    """
    for line in file(fname):
        if line and line[0] != '#':
            yield line.split(sep)


def file_reader(fp, chunk_size=65536):
    """This generator yields the open fileobject in chunks (default 64k). Closes the file at the end"""
    while True:
        data = fp.read(chunk_size)
        if not data:
            break
        yield data
    fp.close()


def string_as_bool(string):
    if str(string).lower() in ('true', 'yes', 'on'):
        return True
    else:
        return False


def listify(item):
    """
    Make a single item a single item list, or return a list if passed a
    list.  Passing a None returns an empty list.
    """
    if not item:
        return []
    elif isinstance(item, list):
        return item
    elif isinstance(item, basestring) and item.count(','):
        return item.split(',')
    else:
        return [item]


def commaify(amount):
    orig = amount
    new = re.sub("^(-?\d+)(\d{3})", '\g<1>,\g<2>', amount)
    if orig == new:
        return new
    else:
        return commaify(new)


def relpath(path, start=None):
    """Return a relative version of a path"""
    # modified from python 2.6.1 source code

    # version 2.6+ has it built in, we'll use the 'official' copy
    if sys.version_info[:2] >= (2, 6):
        if start is not None:
            return os.path.relpath(path, start)
        return os.path.relpath(path)

    # we need to initialize some local parameters
    curdir = os.curdir
    pardir = os.pardir
    sep = os.sep
    commonprefix = os.path.commonprefix
    join = os.path.join
    if start is None:
        start = curdir

    # below is the unedited (but formated) relpath() from posixpath.py of 2.6.1
    # this will likely not function properly on non-posix systems, i.e. windows
    if not path:
        raise ValueError("no path specified")

    start_list = os.path.abspath(start).split(sep)
    path_list = os.path.abspath(path).split(sep)

    # Work out how much of the filepath is shared by start and path.
    i = len(commonprefix([start_list, path_list]))

    rel_list = [pardir] * (len(start_list) - i) + path_list[i:]
    if not rel_list:
        return curdir
    return join(*rel_list)


class Time:
    """ Time utilities of now that can be instrumented for testing."""

    @classmethod
    def now(cls):
        return datetime.utcnow()

if __name__ == '__main__':
    import doctest
    doctest.testmod(sys.modules[__name__], verbose=False)
