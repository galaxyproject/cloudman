import unittest
from cminfrastructure.kvstore import ConsulKVStore


class KVStoreTest(unittest.TestCase):

    TEST_DATA = {'parent1/child1': "pc11",
                 'parent1/child1/nested1': "pc111",
                 'parent1/child1/nested2': "pc112",
                 'parent1/child2': "pc12",
                 'parent1/child2/nested2': "pc122",
                 'parent2/child1': "pc21",
                 'parent2/child1/nested1': "pc121",
                 'parent2/child2': "pc22"}

    _kvstore = None

    def get_kvstore_impl(self):
        """For future implementations to override"""
        return ConsulKVStore()

    @property
    def kvstore(self):
        if not self._kvstore:
            self._kvstore = self.get_kvstore_impl()
        return self._kvstore

    def test_get_put_value(self):
        self.assertIsNone(self.kvstore.get('parent3/child1'),
                          "Retrieving a non-existent key should return None")

        self.kvstore.put('parent3/child1', "hello world")
        self.assertEqual(self.kvstore.get('parent3/child1'), "hello world",
                         "Stored value does not match retrieved value")

    def test_list_invalid_key(self):
        for (k, v) in self.TEST_DATA.items():
            self.kvstore.put(k, v)

        results = self.kvstore.list('parent3/')
        self.assertEqual(len(results), 0)

    def test_list_first_level(self):
        for (k, v) in self.TEST_DATA.items():
            self.kvstore.put(k, v)

        results = self.kvstore.list('parent1/')
        self.assertEqual(len(results), 2)
        self.assertEqual(results['parent1/child1'],
                         self.TEST_DATA['parent1/child1'])
        self.assertEqual(results['parent1/child2'],
                         self.TEST_DATA['parent1/child2'])

    def test_list_second_level(self):
        for (k, v) in self.TEST_DATA.items():
            self.kvstore.put(k, v)

        # purposefully omit trailing slash as that should work too
        results = self.kvstore.list('parent1/child1')
        self.assertEqual(len(results), 2)
        self.assertEqual(results['parent1/child1/nested1'],
                         self.TEST_DATA['parent1/child1/nested1'])
        self.assertEqual(results['parent1/child1/nested2'],
                         self.TEST_DATA['parent1/child1/nested2'])
