import sys
from unittest.mock import MagicMock

_HEAVY_MODULES = ("torch", "transformers", "accelerate", "decord")
for name in _HEAVY_MODULES:
    if name not in sys.modules:
        try:
            __import__(name)
        except ImportError:
            sys.modules[name] = MagicMock()

from app.extraction import extract_candidate_fields
