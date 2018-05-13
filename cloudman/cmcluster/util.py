"""Utility functions used throughout the CloudMan framework."""
import operator


def getattrd(obj, name):
    """Same as ``getattr()``, but allows dot notation lookup."""
    try:
        return operator.attrgetter(name)(obj)
    except AttributeError:
        return None
