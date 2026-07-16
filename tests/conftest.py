"""
conftest.py
===========
pytest runs this automatically before the tests. We use it to add the project
root to the import path so `import config_loader`, `import ml...`, and
`import backend...` all work when running `pytest` from the project folder.
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
