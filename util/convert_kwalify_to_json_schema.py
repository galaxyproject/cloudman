# Converts a kwalify yaml schema to a json schema
import yaml
import json
import os
from collections import OrderedDict

from pykwalify.core import Core


# Extracted from https://github.com/galaxyproject/galaxy/blob/master/lib/
# galaxy/webapps/config_manage.py
# This resolver handles custom !include tags in galaxy yaml
def _ordered_load(stream):

    class OrderedLoader(yaml.Loader):

        def __init__(self, stream):
            self._root = os.path.split(stream.name)[0]
            super(OrderedLoader, self).__init__(stream)

        def include(self, node):
            filename = os.path.join(self._root, self.construct_scalar(node))
            with open(filename, 'r') as f:
                return yaml.load(f, OrderedLoader)

    def construct_mapping(loader, node):
        loader.flatten_mapping(node)
        return OrderedDict(loader.construct_pairs(node))

    OrderedLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
        construct_mapping)
    OrderedLoader.add_constructor('!include', OrderedLoader.include)

    return yaml.load(stream, OrderedLoader)


# Load the Galaxy config schema file
schema_path = './config_schema.yml'
with open(schema_path, "r") as f:
    schema = _ordered_load(f)

# Parse it using pykwalify
c = Core(source_file="galaxy.yml", schema_data=schema)

# Get a handle to the galaxy config section
galaxy_config = c.schema['mapping']['galaxy']

TYPE_MAPPINGS = {
    'map': 'object',
    'str': 'string',
    'int': 'number',
    'bool': 'boolean'
}


# Recursively transform it to a json schema
def transform_schema(schema):
    json_schema = {}
    for key, val in schema.items():
        if key == 'type':
            json_schema['type'] = TYPE_MAPPINGS.get(val, val)
        elif key == 'mapping':
            json_schema['properties'] = transform_schema(val)
        elif key == 'desc':
            json_schema['description'] = ((val[:150] + '...') if len(val) > 150
                                          else val)
        elif key == 'required':
            pass
        else:
            if not val:
                json_schema[key] = ""
            elif isinstance(val, dict):
                json_schema[key] = transform_schema(val)
            else:
                json_schema[key] = val
    return json_schema


json_cschema = transform_schema(galaxy_config)
print(json.dumps(json_cschema, indent=4))
