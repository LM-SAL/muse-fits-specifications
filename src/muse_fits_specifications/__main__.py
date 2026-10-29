"""
``python -m muse_fits_specifications`` checks the packaged keyword sheet, its generated
YAML and every defined level.
"""

import sys

from .sheet import check

sys.exit(check())
