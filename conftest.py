"""
conftest.py
-----------
Pytest configuration that ensures the project root is on sys.path,
allowing all modules to be imported without installation.
"""

import sys
from pathlib import Path

# Insert the project root at position 0 so local packages shadow any
# system-installed versions with the same name.
ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
