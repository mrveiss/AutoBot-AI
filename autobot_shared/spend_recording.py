# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Spend-recording hook for the LLM call sites that sit below ``services`` (#19650).

``autobot_shared`` and ``llm_shared`` cannot import ``services.llm_usage_recording``
(the layering runs the other way), yet two sites call a provider directly:
``ComplexityRouter.route_with_escalation`` and ``_call_verifier_once``. Both
recorded nothing. The backend registers the canonical recorder here at startup
(``initialization.background_workers.wire_llm_spend_recorder``) and those sites
call :func:`report_spend` once the provider has answered.

**An unregistered hook is loud, once per site.** A process that never wires the
recorder (a script, a worker) would otherwise lose spend with no sign, which is
the defect this module closes. The warning is per site, not one for the whole
process: a second site that forgets the hook is a separate omission and a single
global flag would hide it behind the first.

**A failing hook never loses the answer.** The provider call already succeeded
and its response is in hand; recording is best-effort with respect to the
caller, as in ``record_response_usage``. The failure is logged with a traceback
at error level, never swallowed.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

#: ``hook(response, *, endpoint, metadata)`` -- records one finished call's usage.
SpendRecorder = Callable[..., Awaitable[None]]

_recorder: SpendRecorder | None = None
_warned_sites: set[str] = set()


def register_spend_recorder(recorder: SpendRecorder | None) -> None:
    """Install the process-wide recorder; ``None`` unregisters it."""
    global _recorder
    _recorder = recorder


def spend_recorder_registered() -> bool:
    """Whether a recorder is installed."""
    return _recorder is not None


def _reset_for_tests() -> None:
    """Forget the recorder and the once-per-site warnings."""
    register_spend_recorder(None)
    _warned_sites.clear()


async def report_spend(response: Any, *, site: str, metadata: Dict[str, Any] | None = None) -> None:
    """Record ``response``'s usage through the registered recorder; never raises.

    ``site`` names the caller (also the ``endpoint`` the usage is attributed to).
    """
    recorder = _recorder
    if recorder is None:
        if site not in _warned_sites:
            _warned_sites.add(site)
            logger.warning(
                "%s finished an LLM call but no spend recorder is registered; its spend is not recorded (#19650)",
                site,
            )
        return
    try:
        await recorder(response, endpoint=site, metadata=metadata)
    except Exception:
        logger.exception("Spend recorder failed for %s; the call's result is returned unrecorded", site)
