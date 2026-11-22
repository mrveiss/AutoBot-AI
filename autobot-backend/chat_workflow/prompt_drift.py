# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Prompt drift detection for the stable system-prompt prefix (#17277).

The stable prefix (persona, tool teaching, rules, language) is deterministic per
``(language, company, codeexec)``. It is hashed every turn and the hash is kept
on the session, so a later edit that makes it vary is reported with *where* it
changed (block indexes and sizes - never the prompt text, so nothing internal
leaves the process). A change under a different release id is *intended*; a
change under the same release id inside a session is *drift*.

Command: ``python -m chat_workflow.prompt_drift [--language en] [--company]
[--against saved.json]`` prints the current record, or the drift report.
"""

import hashlib
import json
import sys
from typing import Any, Dict, List, Optional

from autobot_shared.env_registry import env
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

PROMPT_RELEASE = str(env("AUTOBOT_OTEL_SERVICE_VERSION"))
METADATA_KEY = "prompt_prefix_records"
_BLOCK_SEP = "\n\n"
_DIGEST_CHARS = 16


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:_DIGEST_CHARS]


def prefix_record(text: str, release: str = PROMPT_RELEASE) -> Dict[str, Any]:
    """Hash the whole prefix and each blank-line-delimited block of it."""
    blocks = text.split(_BLOCK_SEP)
    return {
        "hash": _digest(text),
        "chars": len(text),
        "release": release,
        "blocks": [_digest(b) for b in blocks],
        "block_chars": [len(b) for b in blocks],
    }


def _changed_blocks(old: List[str], new: List[str]) -> List[int]:
    width = max(len(old), len(new))
    return [i for i in range(width) if i >= len(old) or i >= len(new) or old[i] != new[i]]


def compare_records(recorded: Optional[Dict[str, Any]], current: Dict[str, Any]) -> Dict[str, Any]:
    """Return the divergence between two records: kind, hashes, changed blocks, size delta."""
    if not recorded:
        return {"kind": "first", "changed": False, "current": current["hash"]}
    if recorded["hash"] == current["hash"]:
        return {"kind": "same", "changed": False, "current": current["hash"]}
    intended = recorded.get("release", "") != current.get("release", "")
    return {
        "kind": "release_change" if intended else "drift",
        "changed": True,
        "previous": recorded["hash"],
        "current": current["hash"],
        "changed_blocks": _changed_blocks(recorded["blocks"], current["blocks"]),
        "chars_delta": current["chars"] - recorded["chars"],
    }


def record_turn_prefix(metadata: Dict[str, Any], key: str, text: str) -> Dict[str, Any]:
    """Record this turn's prefix on the session and log a divergence from the last turn."""
    records = metadata.setdefault(METADATA_KEY, {})
    current = prefix_record(text)
    report = compare_records(records.get(key), current)
    records[key] = current
    if report["kind"] == "drift":
        logger.warning("[#17277] Stable prompt prefix drifted within a session: %s", json.dumps(report))
    elif report["kind"] == "release_change":
        logger.info("[#17277] Stable prompt prefix changed with the release: %s", json.dumps(report))
    return report


def prefix_key(language: str, company_id: Optional[str], codeexec: bool) -> str:
    """Key the records by what the stable prefix is deterministic over."""
    return f"{language or ''}|{'company' if company_id else '-'}|{int(bool(codeexec))}"


def record_session_prefix(
    session: Any, language: Optional[str], company_id: Optional[str], codeexec: bool, text: str
) -> None:
    """Non-fatal per-turn hook: a drift check must never cost the user their turn."""
    try:
        if session is not None and isinstance(getattr(session, "metadata", None), dict):
            record_turn_prefix(session.metadata, prefix_key(language, company_id, codeexec), text)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[#17277] Prefix drift record failed: %s", exc)


def main(argv: Optional[List[str]] = None) -> int:
    """Print the current prefix record, or its drift against a saved record."""
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--language", default=None)
    ap.add_argument("--company", action="store_true", help="include the company tool teaching")
    ap.add_argument("--against", help="JSON file holding a previously printed record")
    args = ap.parse_args(argv)
    from chat_workflow.llm_handler import LLMHandlerMixin

    text = LLMHandlerMixin._get_system_prompt(LLMHandlerMixin(), args.language, "c" if args.company else None)
    current = prefix_record(text)
    if args.against:
        with open(args.against, encoding="utf-8") as fh:
            out = compare_records(json.load(fh), current)
    else:
        out = current
    sys.stdout.write(json.dumps(out, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
