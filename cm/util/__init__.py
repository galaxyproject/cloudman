"""
Utility functions used systemwide.

"""
from datetime import datetime
import hashlib
import logging
import threading
import re
import requests
import os
import sys
import tarfile
from contextlib import closing

from cm.util import misc
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

log = logging.getLogger('cloudman')
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


class ExtractArchive(threading.Thread):

    """
    Extracts an archive from `archive_url` to a specified `path`, optionally
    checking if the MD5 sum of the downloaded file matches `md5_sum`. If MD5
    sum does not match, keep retrying while `num_retries` is greated than 0.
    This is intended to be invoked in a separate thread. After the thread
    finishes execution, `callback` method will be called.

    Note: currently only tar files are supported for the archive.
    """

    def __init__(self, archive_url, path, md5_sum=None, callback=None, num_retries=1):
        threading.Thread.__init__(self)
        self.archive_url = archive_url
        self.path = path
        self.md5_sum = md5_sum
        self.callback = callback
        self.num_retries = num_retries

    def _md5_check_ok(self, digest):
        """Do the MD5 checksum. Return `True` if OK; `False` otherwise."""
        if self.md5_sum and not digest == self.md5_sum:
            log.debug("Invalid MD5 sum for archive {0}. Expected: {1} but "
                      "found {2}".format(self.archive_url, self.md5_sum, digest))
            return False
        if self.md5_sum:
            log.info("MD5 checksum for archive {0} is OK: {1}=={2}".format(
                     self.archive_url, self.md5_sum, digest))
        return True

    def _extract(self):
        """
        Do the extraction of a tar archive from `archive_url` to a specified
        `path`. The data is streamed. Currently supports only tar files.
        """
        try:
            start = datetime.utcnow()
            with closing(requests.get(self.archive_url, stream=True)) as r:
                stream = MD5TransparentFilter(r.raw)
                with closing(tarfile.open(fileobj=stream, mode='r|*', errorlevel=0)) as archive:
                    archive.extractall(path=self.path)
                    hexdigest = stream.hexdigest()
                    archive_size = r.headers.get('content-length', -1)
                    log.debug("Completed extracting archive {0} ({1}) to {2} ({3}) in {4}"
                              .format(self.archive_url, misc.nice_size(archive_size),
                                      self.path, misc.nice_size(misc.get_dir_size(self.path)),
                                      datetime.utcnow() - start))
                    return hexdigest
        except Exception as e:
            log.exception("Exception extracting archive {0} to {1}: {2}".format(
                self.archive_url, self.path, e))
            return None

    def run(self):
        log.info("Extracting archive url {0} to {1}. This could take a while..."
                 .format(self.archive_url, self.path))
        digest = self._extract()
        while not self._md5_check_ok(digest) and self.num_retries > 0:
            digest = self._extract()
            self.num_retries -= 1
        if self.callback:
            log.debug(" (X) Callback method defined; calling it now.")
            self.callback()


class MD5TransparentFilter:

    """
    Calculate an md5 checksum of the contents read from a stream
    without making an extra copy.

    http://stackoverflow.com/questions/14014854/python-on-the-fly-md5-as-one-reads-a-stream
    """

    def __init__(self, fp):
        self._md5 = hashlib.md5()
        self._fp = fp

    def read(self, size):
        buf = self._fp.read(size)
        self._md5.update(buf)
        return buf

    def hexdigest(self):
        return self._md5.hexdigest()
