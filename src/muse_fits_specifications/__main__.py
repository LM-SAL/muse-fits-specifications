"""
``python -m muse_fits_specifications`` checks the packaged keyword sheet and every
defined level.
"""

import sys

from .spec import main

sys.exit(main())
