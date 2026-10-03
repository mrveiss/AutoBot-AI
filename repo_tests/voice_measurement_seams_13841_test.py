# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The two voice measurements stay different, and the WAV arithmetic stays shared (#13841).

Both commits in this batch made a claim that nothing enforced, which is the bias review
caught three times on the two PRs before this one: a correct change with an assertion that
does not pin it. These are those assertions, written before review rather than after.

**Why no test asserts the two real-time factors agree.** #13841 offered that as a fallback
criterion, and it would be a guard whose PASSING is the defect: the backend figure measures
audio over the worker's own generation time, the frontend's measures audio over wall time at
the client, and they diverge whenever a consumer is slow -- the only condition either number
exists for. A test asserting agreement either fails permanently or is written loosely enough
to pass, and then pins the false premise that the two are one quantity (recorded on #15826).
What IS assertable is the structural property that makes them different, which is the clock
restarting *after* the yield.
"""

import ast
import re

from repo_tests._paths import repo_root

_CLIENT = "autobot-backend/services/tts_client.py"
_PROVIDER = "autobot-backend/voice_processing/providers/generic_provider.py"


def _loop_bodies(tree: ast.AST):
    """Only loop bodies, because only the streaming route has this property.

    The blob route starts its clock, observes the whole payload and yields it once -- a
    perfectly correct ``start -> observe -> yield`` which an unscoped walk reads as a
    violation. My first version of this guard did exactly that and reported the blob path
    as the defect: a correct measurement, a real failure, and about the wrong route.
    """
    for node in ast.walk(tree):
        if isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
            yield node.body


def _call_name(stmt: ast.stmt) -> str:
    """``throughput.observe(x)`` -> ``observe``; anything else -> ``""``."""
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
        func = stmt.value.func
        if isinstance(func, ast.Attribute):
            return func.attr
    return ""


def test_the_worker_clock_restarts_after_the_yield() -> None:
    """``observe`` -> ``yield`` -> ``start``, in that order, in one block.

    This ordering IS the difference between the two real-time factors. Moving
    ``throughput.start()`` above the ``yield`` makes the backend figure include the time
    the consumer spent away, which is wall time -- the frontend's quantity. The two
    numbers would then agree, nothing would fail, and the measurement that answers "is
    the worker fast enough" would be gone. That is the reconciliation #13841 exists to
    prevent, and it is a one-line edit.
    """
    tree = ast.parse((repo_root() / _CLIENT).read_text(encoding="utf-8"))
    instrumented = 0
    for block in _loop_bodies(tree):
        names = [_call_name(s) for s in block]
        yields = [i for i, s in enumerate(block) if isinstance(s, ast.Expr) and isinstance(s.value, ast.Yield)]
        if "observe" not in names or not yields:
            continue
        yield_at, observe_at = yields[0], names.index("observe")
        restarts_after = [i for i, n in enumerate(names) if n == "start" and i > yield_at]
        assert restarts_after, (
            f"{_CLIENT}: the instrumented loop observes@{observe_at} and yields@{yield_at} but "
            "never restarts the clock after the yield. The worker's real-time factor then "
            "includes the time the consumer spent away -- which is wall time, the frontend's "
            "quantity -- and the two measures collapse into one"
        )
        assert observe_at == yield_at - 1, (
            f"{_CLIENT}: observe@{observe_at} is not immediately before yield@{yield_at}; "
            "anything between them is billed to the worker"
        )
        instrumented += 1

    assert instrumented, (
        f"{_CLIENT}: no loop body contained an observe and a yield — the instrumented stream "
        "was moved, renamed or unrolled, so this guard is no longer looking at anything"
    )


def test_both_wav_duration_sites_use_the_shared_helper() -> None:
    """One arithmetic, two callers — asserted at the call sites, not in the helper's own test.

    ``audio_wav_test.py`` pins what the helper computes. It cannot notice a caller that
    stops calling it: re-inlining ``getnframes() / float(getframerate())`` in either file
    leaves every test green and the duplication back. jscpd will not see a one-line clone
    either.
    """
    inlined = re.compile(r"getnframes\(\)\s*/\s*(float\()?\s*\w*(getframerate\(\)|frame_rate|sample_rate)")
    for rel in (_CLIENT, _PROVIDER):
        source = (repo_root() / rel).read_text(encoding="utf-8")
        assert (
            "wav_duration_seconds" in source
        ), f"{rel} no longer reaches the shared helper; the duration arithmetic has forked again"
        assert not inlined.search(source), (
            f"{rel} computes the WAV duration inline again — that arithmetic belongs to "
            "autobot_shared/audio_wav.py, which is the one place its zero-frame-rate guard lives"
        )
