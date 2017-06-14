import json

from abc import ABCMeta, abstractmethod
from consul import Consul


class KVStore(object):
    """
    An abstraction for a Key Value store
    """
    __metaclass__ = ABCMeta

    @abstractmethod
    def get(self, key):
        """
        Returns a value at a given key.
        e.g. /infastructure/clouds/aws

        Will not return child nodes.
        Value assumed to be a string or json.

        :type key: :class:`str`
        :param key: String Key value.
        e.g. /infastructure/clouds/aws

        :rtype: :class:`str` or :class:`json`
        :return:  Returns a string or json
        """
        pass

    @abstractmethod
    def put(self, key, value):
        """
        Stores a given key value pair in the store.
        Returns a string or json object.
        """
        pass

    @abstractmethod
    def list(self, key):
        """
        Returns a dict of key value
        pairs which are immediate descendants
        of provided key prefix.
        e.g. /infastructure/clouds/

        returns:
        /infrastructure/clouds/aws
        /infrastructure/clouds/openstack

        but not:
        /infrastructure/clouds/aws/instances
        """
        pass


class ConsulKVStore(KVStore):
    """
    Implementation of KVStore abstraction for Hashicorp's Consul
    """

    def __init__(self):
        self.consul = Consul()

    def get(self, key):
        _, data = self.consul.kv.get(key)
        return json.loads(data['Value']) if data else None

    def put(self, key, value):
        self.consul.kv.put(key, json.dumps(value))

    def list(self, key):
        if not key.endswith("/"):
            key += "/"
        _, data = self.consul.kv.get(key, recurse=True,
                                     keys=True, separator='/')
        return {row: self.get(row) for row in (data or [])
                if row and row[-1] != '/'}
