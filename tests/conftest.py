"""Pytest configuration for the offline trading MVP safety suite."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_SRC_ROOT = (PROJECT_ROOT / "src").resolve()

# Safety tests must always scan the repository production source tree. Environment
# overrides are intentionally ignored so CI/user shells cannot redirect the scan.
if PRODUCTION_SRC_ROOT.exists():
    sys.path.insert(0, str(PRODUCTION_SRC_ROOT))
