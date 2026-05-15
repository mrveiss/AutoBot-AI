# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Re-export of canonical mock fixtures (#7125 wire-in).

The 289-LOC original at this path duplicated `MockLLMInterface`,
`MockCommandValidator`, `MockKnowledgeBase`, and `MockWorkerNode` verbatim
with `autobot-backend/tests/fixtures/mocks.py`. After #6994 made
`autobot-backend/tests/fixtures/mocks.py` the canonical location and added
`MockLLMService`, this shared copy had 0 production callers and would have
silently drifted from the SSOT (e.g. `MockLLMService` only existed in the
canonical file).

This module is now a thin re-export pointing at the SSOT. Importing names
from `autobot_infrastructure.shared.tests.fixtures.mocks` continues to work
for infrastructure-side tests, and any new mock added to the canonical file
is automatically reachable here.
"""

import sys
from pathlib import Path

# autobot-infrastructure/shared/tests/fixtures/mocks.py → repo root is 5 levels up
_BACKEND = Path(__file__).resolve().parents[4] / "autobot-backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from tests.fixtures.mocks import (  # noqa: E402  (sys.path bootstrap above)
    MockCommandValidator,
    MockKnowledgeBase,
    MockLLMInterface,
    MockLLMService,
    MockWorkerNode,
)

__all__ = [
    "MockCommandValidator",
    "MockKnowledgeBase",
    "MockLLMInterface",
    "MockLLMService",
    "MockWorkerNode",
]
