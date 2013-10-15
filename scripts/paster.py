"""
Bootstrap the Galaxy framework.

This should not be called directly!  Use the run.sh script in Galaxy's
top level directly.
"""

import os
import sys
import paste

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
