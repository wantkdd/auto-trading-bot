"""Pytest configuration for the offline trading MVP safety suite."""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SRC_ROOT = PROJECT_ROOT / "src"
PRODUCTION_SRC_ROOT = Path(os.environ.get("AUTO_TRADING_BOT_SRC_ROOT", DEFAULT_SRC_ROOT)).resolve()

# Keep tests runnable in team worktrees before implementation branches are integrated.
# In the integrated repo this defaults to ./src and requires no environment variable.
if PRODUCTION_SRC_ROOT.exists():
    sys.path.insert(0, str(PRODUCTION_SRC_ROOT))
