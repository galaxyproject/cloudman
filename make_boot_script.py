"""
Usage (from cm directory):

    python make_boot_script.py

"""
from ast import parse, NodeTransformer
from astor.codegen import to_source


class MergeRelativeModules(NodeTransformer):

    def __init__(self):
        self.merged_modules = []

    def visit_ImportFrom(self, node):
        level = node.level
        module = node.module
        if level == 0:
            # Do not process non-relative imports
            result_node = node
        elif module in self.merged_modules:
            # Relative module has already been merged in
            # skip.
            result_node = None
        else:
            merged_imported_node = self.get_merged(module)
            self.merged_modules.append(module)
            result_node = merged_imported_node
        return result_node

    def __parse(self, module):
        filename = "cm/boot/%s.py" % module
        contents = open(filename).read()
        return parse(contents)

    def get_merged(self, module):
        node = self.__parse(module)
        merged_node = self.visit(node)
        return merged_node


def main():
    HEADER = """#!/usr/bin/env python\n"""
    merged_node = MergeRelativeModules().get_merged("__init__")
    open("cm_boot.py", "w").write(HEADER + to_source(merged_node))


if __name__ == "__main__":
    main()
