# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Secrets-store failure, distinct from "nothing is stored" (#14126).

Two consumers converted a broken store into a clean, healthy-looking success:

* ``api/infrastructure.py`` returned ``[]``, which reads as "the user has
  configured no hosts" — the operator saw nothing wrong and no host.
* ``codebase_analytics/endpoints/sources.py`` returned ``None`` for the
  credential, and the caller then built a **token-less** clone URL. A private
  repository failed with a git error naming permissions rather than the
  credential store, and a public one cloned anonymously with the intended
  credential silently unused.

Its own module because ``security/command_patterns.py`` and several API
modules sit at their recorded size ceilings, and a grandfathered file may not
grow to host it (#14236).
"""

from __future__ import annotations


class SecretsStoreUnavailable(RuntimeError):
    """The secrets store could not answer, so its answer is unknown.

    Never raised to mean "no such secret" — that is a legitimate ``None``.
    Raised only when the store itself failed, so a caller cannot mistake a
    fault for an empty configuration.
    """

    def __init__(self, what: str) -> None:
        super().__init__(f"secrets store unavailable while resolving {what}")
        self.what = what
