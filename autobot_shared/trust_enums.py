# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Trust Level Enumeration

Issue #8957: Consolidated trust level enum for federated peer evaluation.
Used across a2a (agent-to-agent) and security domain to determine what
capabilities a peer agent can access based on continuous trust scoring.

Trust levels are ordered UNTRUSTED < LIMITED < STANDARD < TRUSTED, with
higher levels granting more capabilities.
"""

from enum import Enum


class TrustLevel(str, Enum):
    """Trust level for federated peer evaluation (GH#8957, Issue #7358).

    Used to determine what capabilities a peer agent can access based on
    continuous trust scoring. Higher levels grant more capabilities.

    Score ranges:
      UNTRUSTED  (score ≤ 0.30)  — discovery info only
      LIMITED    (0.30–0.60)     — discovery + task submission
      STANDARD   (0.60–0.85)     — + memory/knowledge queries
      TRUSTED    (> 0.85)        — + new agent definitions
    """

    UNTRUSTED = "UNTRUSTED"
    LIMITED = "LIMITED"
    STANDARD = "STANDARD"
    TRUSTED = "TRUSTED"
