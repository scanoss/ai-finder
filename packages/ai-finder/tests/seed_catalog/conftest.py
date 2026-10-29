"""Make the repository root importable so ``scripts.seed_catalog`` resolves.

The generator is build-time tooling and lives in ``scripts/`` next to
``create_seed_db.py``, which is outside the installed package. pytest's
``testpaths`` points at this tests tree, so the root goes on the path here
rather than in every test module.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
