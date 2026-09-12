# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A hook that rewrites a shared file must run as one process (#16343).

pre-commit splits the staged files into batches and, unless a hook declares
``require_serial: true``, runs those batches in parallel. That's harmless for a
hook that only reads. It's a race for a hook that *writes one shared file*.
``detect-secrets-hook`` reads ``.secrets.baseline``, updates the entries for its
own batch, and writes the whole file back, so parallel batches overwrite each
other and the last writer wins. A large commit (any base merge) then fails
"Please ``git add .secrets.baseline``" on every attempt, keeping only a
fraction of the updates each time. Upstream's manifest doesn't set the flag,
so this config has to.

The check has three halves, because each can pass while the others are broken:

* **the property**: every hook listed in ``_REWRITES_A_SHARED_FILE`` declares
  ``require_serial: true`` in ``.pre-commit-config.yaml``.
* **the floor**: every listed hook is actually present. A renamed or removed
  hook would otherwise leave the property checked over nothing.
* **the self-test**: the detector is fed a config it *must* reject, and one it
  must accept.
"""

from __future__ import annotations

import pytest
from repo_tests._paths import repo_root

yaml = pytest.importorskip("yaml")

_CONFIG = repo_root() / ".pre-commit-config.yaml"

#: Hook ids that rewrite a file shared by every batch. Add a hook here when it
#: writes back to one file; the guard then requires it to run serially.
_REWRITES_A_SHARED_FILE = frozenset({"detect-secrets"})


def _hooks_by_id(config_text: str) -> dict[str, dict]:
    """Every hook in the config, across every repo block, keyed by id."""
    document = yaml.safe_load(config_text) or {}
    return {
        str(hook["id"]): hook for repo in document.get("repos", []) for hook in repo.get("hooks", []) if "id" in hook
    }


def not_serial(config_text: str, hook_ids: frozenset[str] = _REWRITES_A_SHARED_FILE) -> list[str]:
    """The listed hooks present in *config_text* that don't declare require_serial: true.

    A plain function over text, so it can be driven with a synthetic config: a
    detector only ever pointed at a clean file can't be told apart from one
    that has stopped detecting.
    """
    hooks = _hooks_by_id(config_text)
    return sorted(
        hook_id for hook_id in hook_ids if hook_id in hooks and hooks[hook_id].get("require_serial") is not True
    )


def test_every_shared_file_rewriting_hook_is_present() -> None:
    """Floor: a hook missing from the config would make the property vacuous."""
    assert _CONFIG.is_file(), ".pre-commit-config.yaml is gone, so this guard has no subject"
    missing = sorted(_REWRITES_A_SHARED_FILE - _hooks_by_id(_CONFIG.read_text(encoding="utf-8")).keys())
    assert not missing, (
        f"{missing} are listed as rewriting a shared file but aren't in .pre-commit-config.yaml. "
        "Update _REWRITES_A_SHARED_FILE if the hook was renamed or removed."
    )


def test_every_shared_file_rewriting_hook_runs_serially() -> None:
    """#16343's acceptance criterion: the property, checked by parsing."""
    offenders = not_serial(_CONFIG.read_text(encoding="utf-8"))
    assert not offenders, (
        f"{offenders} rewrite a shared file but don't declare `require_serial: true`. "
        "pre-commit runs them in parallel batches that race on that file, and the last "
        "writer wins (#16343)."
    )


def test_the_detector_rejects_a_parallel_hook_and_accepts_a_serial_one() -> None:
    """Self-test. Without it, a detector that matches nothing passes forever."""
    parallel = "\n".join(
        (
            "repos:",
            "  - repo: https://github.com/Yelp/detect-secrets",
            "    rev: v1.5.0",
            "    hooks:",
            "      - id: detect-secrets",
            "        args: ['--baseline', '.secrets.baseline']",
        )
    )
    assert not_serial(parallel) == ["detect-secrets"], "the detector missed a hook with no require_serial"
    assert not_serial(parallel + "\n        require_serial: false") == [
        "detect-secrets"
    ], "an explicit `require_serial: false` must be flagged too"
    assert not not_serial(
        parallel + "\n        require_serial: true"
    ), "a hook declaring `require_serial: true` must not be reported"
