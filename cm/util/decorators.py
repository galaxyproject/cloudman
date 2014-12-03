import logging
from cm.util import cluster_status
from boto.exception import EC2ResponseError, S3ResponseError

log = logging.getLogger('cloudman')


def CatchCloudErr(f):
    """ Not complete; do not use yet.
    """
    def _boto(self, *args, **kwargs):
        try:
            print "Inside __call__ (args: {0})".format(args)
            f(self, *args, **kwargs)
            print "After self.f(*args)"
        except EC2ResponseError, e:
            log.error("General EC2ResponseError: {0}".format(e))
        except S3ResponseError, e:
            log.error("General S3ResponseError: {0}".format(e))
        except Exception, e:
            log.error("General exception: {0}".format(e))
    return _boto


def TestFlag(ret_val, quiet=False):
    """
    Check if ``app.TESTFLAG`` is ``True``. If so, return ``ret_val`` without
    calling the function. Else, call the function.
    If ``quiet`` is set to ``True``, do not log anything.
    """
    def decorator(fn):
        def df(*args, **kwargs):
            cl = args[0]  # Get the function class
            if cl.app.TESTFLAG is True and cl.app.LOCALFLAG is False:
                if not quiet:
                    log.debug("Attempted to use the '{0}->{1}.{2}' method but TESTFLAG is set. Returning '{3}'."
                              .format(cl.__module__, cl.__class__.__name__, fn.func_name, ret_val))
                return ret_val
            else:
                # TESTFLAG is not set; call the function
                return fn(*args, **kwargs)
        return df
    return decorator


def cluster_ready(func):
    """
    Check if the cluster status is READY and return `True` if so, `False`
    otherwise.
    """
    def wrap(*args, **kwargs):
        cl = args[0]  # Get the function class
        current_status = cl.app.manager.cluster_status
        # log.debug("Cluster current_status: {0}".format(current_status))
        if current_status != cluster_status.READY:
            log.debug("Cluster not yet ready ({0}), skipping method {1}->{2}.{3}"
                      .format(current_status, cl.__module__, cl.__class__.__name__,
                      func.func_name))
        else:
            # The cluster is READY, call the function
            func(*args, **kwargs)
    return wrap
