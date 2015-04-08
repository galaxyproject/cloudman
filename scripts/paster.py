"""
Bootstrap the CloudMan framework.

This should not be called directly! Use the `run.sh` script in CloudMan's
top level directory.
"""

import os
import sys

# ensure supported version
from check_python import check_python
try:
    check_python()
except:
    sys.exit(1)

new_path = [os.path.join(os.getcwd())]
new_path.extend(sys.path[1:])  # remove scripts/ from the path
sys.path += new_path

from paste.script import command
command.run()
