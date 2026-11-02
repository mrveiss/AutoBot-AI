# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Fetch (or check) the pinned HuggingFace models install provisions (#19869, #19738).

    python -m autobot_shared.model_prefetch            fetch each model at its pinned revision, then verify it
    python -m autobot_shared.model_prefetch --check    verify only; downloads nothing

Run as the service user, with the same ``HF_HOME`` the backend runs with, so the files land in the cache the
backend reads. Every model is attempted; the exit status is 1 if any failed, and each failure is one line naming
the model, its pinned revision, what went wrong and the room left in the cache. A model already in the cache
costs no network.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path
from typing import Callable, Sequence

from autobot_shared.pinned_model_registry import (
    ModelIntegrityError,
    get_pinned_revision,
    pinned_weight_files,
    verify_cached_model,
)
from autobot_shared.ssot_hf_models import PREFETCHED_HF_MODELS

DEFAULT_RETRIES = 3
DEFAULT_RETRY_DELAY_S = 30.0
#: Files besides the pinned weights a ``from_pretrained`` call reads.
_SUPPORT_PATTERNS = ["*.json", "*.txt", "*.model"]


def _cache_dir() -> Path:
    from huggingface_hub import constants  # noqa: PLC0415 -- heavy at import time

    return Path(constants.HF_HUB_CACHE)


def free_space(path: Path) -> str:
    """The room left where ``path`` is (or would be created), for a failure message."""
    probe = path
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    return f"{shutil.disk_usage(probe).free / 1024**3:.1f} GiB free in {path}"


def _snapshot(repo_id: str, revision: str, *, local_only: bool) -> None:
    from huggingface_hub import snapshot_download  # noqa: PLC0415 -- heavy at import time

    patterns = [*pinned_weight_files(repo_id), *_SUPPORT_PATTERNS]
    snapshot_download(repo_id, revision=revision, allow_patterns=patterns, local_files_only=local_only)


def _fetch_and_verify(repo_id: str, revision: str, retries: int, delay: float, sleep: Callable[[float], None]) -> None:
    attempts = retries + 1
    for attempt in range(1, attempts + 1):
        try:
            _snapshot(repo_id, revision, local_only=False)
            verify_cached_model(repo_id)
            return
        except ModelIntegrityError:
            raise  # a download that does not match its pin is not helped by trying again
        except Exception as exc:  # the hub raises many kinds: offline, 5xx, disk full, auth
            if attempt == attempts:
                raise RuntimeError(f"{type(exc).__name__}: {exc}") from exc
            sleep(delay)


def _check(repo_id: str, revision: str) -> None:
    _snapshot(repo_id, revision, local_only=True)
    verify_cached_model(repo_id)


def run(
    models: Sequence[str], *, check_only: bool, retries: int, delay: float, sleep: Callable[[float], None] = time.sleep
) -> list[str]:
    """One line per model: ``OK`` or ``FAILED``; never stops at the first failure."""
    lines = []
    for repo_id in models:
        revision = get_pinned_revision(repo_id)
        try:
            _check(repo_id, revision) if check_only else _fetch_and_verify(repo_id, revision, retries, delay, sleep)
            lines.append(f"OK {repo_id} @ {revision}")
        except Exception as exc:
            what = "is not in the cache" if check_only else f"could not be fetched after {retries + 1} attempts"
            lines.append(f"FAILED {repo_id} @ {revision} {what}: {exc}. {free_space(_cache_dir())}")
    return lines


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="verify the cache only; download nothing")
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES)
    parser.add_argument("--delay", type=float, default=DEFAULT_RETRY_DELAY_S)
    args = parser.parse_args(argv)
    lines = run(PREFETCHED_HF_MODELS, check_only=args.check, retries=args.retries, delay=args.delay)
    print("\n".join(lines))  # noqa: print -- the report install reads on stdout
    return 1 if any(line.startswith("FAILED") for line in lines) else 0


if __name__ == "__main__":
    sys.exit(main())
