from cm.framework.messages.storage.local import LocalStorage

def get_storage():
    """ Ideally, imports the appropriate message storage class. Currently,
        returns the default one.
    """
    return LocalStorage()

# Callable with the same interface as the storage classes to allow for dynamic
# changing of the storage type
default_storage = lambda: get_storage()