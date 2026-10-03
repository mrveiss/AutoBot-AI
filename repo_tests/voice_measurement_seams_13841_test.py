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


_CLOCK = "throughput"


def _is_clock_call(stmt: ast.stmt, attr: str) -> bool:
    """``throughput.<attr>(...)`` -- the RECEIVER is checked, not only the method name.

    Review on #17887: matching any ``.start()`` meant another object's ``start()`` after the
    yield satisfied the assertion even with ``throughput.start()`` moved above it, so the
    detector passed on the exact edit it exists to catch.
    """
    if not (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call)):
        return False
    func = stmt.value.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr == attr
        and isinstance(func.value, ast.Name)
        and func.value.id == _CLOCK
    )


def _ordering_problems(source: str) -> list[str]:
    """Every way the instrumented loop can break its contract, as a list.

    A list rather than assertions so fixtures can drive it: the repo's rule is that a
    detector needs one fixture that trips it and one that does not, and a detector only ever
    run against a complying file has never been seen to fail.
    """
    problems: list[str] = []
    instrumented = 0
    for block in _loop_bodies(ast.parse(source)):
        observes = [i for i, s in enumerate(block) if _is_clock_call(s, "observe")]
        yields = [i for i, s in enumerate(block) if isinstance(s, ast.Expr) and isinstance(s.value, ast.Yield)]
        if not observes or not yields:
            continue
        instrumented += 1
        observe_at, yield_at = observes[0], yields[0]
        starts = [i for i, s in enumerate(block) if _is_clock_call(s, "start")]
        early = [i for i in starts if i < observe_at]
        if early:
            problems.append(
                f"the clock restarts at {early} BEFORE observing at {observe_at}, which zeroes "
                "the interval the chunk was produced in"
            )
        if not any(i > yield_at for i in starts):
            problems.append(
                f"no {_CLOCK}.start() after the yield at {yield_at}: the worker's figure then "
                "includes the time the consumer spent away, which is wall time -- the frontend's "
                "quantity -- and the two measures collapse into one"
            )
        if observe_at != yield_at - 1:
            problems.append(f"observe@{observe_at} is not immediately before yield@{yield_at}")
    if not instrumented:
        problems.append(f"no loop body contained a {_CLOCK}.observe() and a yield -- nothing was examined")
    return problems


def test_the_worker_clock_restarts_after_the_yield() -> None:
    """``observe`` -> ``yield`` -> ``start``, in that order, in one loop body.

    This ordering IS the difference between the two real-time factors. Moving
    ``throughput.start()`` above the ``yield`` makes the backend figure include the time the
    consumer spent away, which is wall time -- the frontend's quantity. The two numbers would
    then agree, nothing would fail, and the measurement that answers "is the worker fast
    enough" would be gone. That is the reconciliation #13841 exists to prevent, and it is a
    one-line edit.
    """
    problems = _ordering_problems((repo_root() / _CLIENT).read_text(encoding="utf-8"))
    assert not problems, f"{_CLIENT}: " + "; ".join(problems)


_LOOP = """
async def stream():
    throughput = Clock()
    async for chunk in source():
{body}
"""


def test_the_correct_ordering_is_accepted() -> None:
    """The contrast half: without it, a detector that always complains passes everything below."""
    body = "        throughput.observe(chunk)\n        yield chunk\n        throughput.start()"
    assert _ordering_problems(_LOOP.format(body=body)) == []


def test_a_clock_restarted_before_the_yield_is_reported() -> None:
    body = "        throughput.observe(chunk)\n        throughput.start()\n        yield chunk"
    assert any("after the yield" in p for p in _ordering_problems(_LOOP.format(body=body)))


def test_another_objects_start_does_not_satisfy_the_contract() -> None:
    """The review finding: a receiver-blind detector passes this, which is the bug plus noise."""
    body = (
        "        throughput.observe(chunk)\n        throughput.start()\n        yield chunk\n" "        other.start()"
    )
    assert any("after the yield" in p for p in _ordering_problems(_LOOP.format(body=body)))


def test_a_clock_restarted_before_observing_is_reported() -> None:
    body = (
        "        throughput.start()\n        throughput.observe(chunk)\n        yield chunk\n"
        "        throughput.start()"
    )
    assert any("BEFORE observing" in p for p in _ordering_problems(_LOOP.format(body=body)))


def test_an_unexamined_module_is_reported_rather_than_passing_empty() -> None:
    """A rename or an unrolled loop must fail here, not read as compliant."""
    assert any("nothing was examined" in p for p in _ordering_problems("async def stream():\n    yield 1\n"))


def _calls_named(tree: ast.AST, name: str) -> int:
    """Calls to exactly *name* -- the local ``_``-prefixed wrapper is a different name."""
    found = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        called = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
        found += called == name
    return found


def _divides_frames(tree: ast.AST) -> bool:
    """True when ``getnframes()`` is the IMMEDIATE left operand of a ``/``, in CODE.

    The narrower claim is the accurate one and it is deliberate (#17891): ``n =
    wav.getnframes()`` then ``n / rate`` is OUTSIDE this, and
    ``test_the_division_detector_does_not_claim_to_catch_a_bound_intermediate`` pins that so a
    future widening has to be deliberate. The load-bearing assertion is the ``ast.Call`` count
    for ``wav_duration_seconds``; this is a second net, and a net is not a proof.

    AST rather than a pattern over source, and the reason is a failure this test produced
    on itself: the widened regex matched the *comment* in `generic_provider.py` explaining
    the arithmetic it forbids. A source pattern cannot tell code from prose, which is the
    recurring shape -- a substring check matching its own docstring. It also removes the
    need to enumerate denominators: `float(rate)`, `wav.getframerate()` and `audio.frame_rate`
    are one node shape here, where the first version of this caught one spelling of six.
    """
    for node in ast.walk(tree):
        if not (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div)):
            continue
        left = node.left
        inner = left.func if isinstance(left, ast.Call) else None
        name = inner.attr if isinstance(inner, ast.Attribute) else inner.id if isinstance(inner, ast.Name) else ""
        if name == "getnframes":
            return True
    return False


def test_both_wav_duration_sites_use_the_shared_helper() -> None:
    """One arithmetic, two callers — asserted as a CALL, because a mention is not a call.

    The first version of this test asserted ``"wav_duration_seconds" in source``, which is
    **always true** of ``tts_client.py``: the import line and ``def _wav_duration_seconds``
    both contain the substring, so the caller could revert to inline arithmetic and this
    still passed. I wrote this guard precisely because the helper's own test cannot notice a
    departing caller, and the first version had the same blind spot through a different
    mechanism (review on #17887). An ``ast.Call`` to the exact name is the thing that is
    false when a caller leaves.

    The second assertion is AST too, for the same reason: the regex it replaced matched one
    of six plausible re-inline spellings (a ``word`` class cannot cross a ``.``), and when widened it
    matched the *comment* in the provider describing the arithmetic it forbids. The call
    check carries the claim; the division check catches a duplicate inline added *beside* a
    surviving call.
    """
    for rel in (_CLIENT, _PROVIDER):
        tree = ast.parse((repo_root() / rel).read_text(encoding="utf-8"))
        assert _calls_named(tree, "wav_duration_seconds") >= 1, (
            f"{rel} mentions wav_duration_seconds but never CALLS it; the duration "
            "arithmetic has forked again, and a substring check would not have seen it"
        )
        assert not _divides_frames(tree), (
            f"{rel} divides getnframes() by a rate again — that arithmetic belongs to "
            "autobot_shared/audio_wav.py, which is the one place its zero-frame-rate guard lives"
        )


_NON_POSITIVE = {ast.LtE: (0,), ast.Lt: (0, 1), ast.Eq: (0,)}


def refusal_problems(source: str, *, loader: str = "_load_audio_input") -> list[str]:
    """Why *source*'s loader does not provably refuse a non-positive frame rate.

    A detector over source so fixtures can drive it, because the first version asserted only
    that *some* ``if`` on ``sample_rate`` led to a ``raise`` -- which accepts
    ``if sample_rate > 0: raise`` (permitting a zero rate, the exact case it guards) and
    accepts a refusal placed AFTER the ``AudioInput(...)`` it is meant to protect. Both were
    raised independently by two reviewers on #17887.
    """
    tree = ast.parse(source)
    fns = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == loader]
    if not fns:
        return [f"no function named {loader} -- the detector is looking at nothing"]
    problems: list[str] = []
    construction = [
        n.lineno
        for n in ast.walk(fns[0])
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "AudioInput"
    ]
    refusals = []
    for node in ast.walk(fns[0]):
        if not (isinstance(node, ast.If) and isinstance(node.test, ast.Compare)):
            continue
        left, ops, comps = node.test.left, node.test.ops, node.test.comparators
        if not (isinstance(left, ast.Name) and left.id == "sample_rate" and len(ops) == 1):
            continue
        if not any(isinstance(stmt, ast.Raise) for stmt in node.body):
            continue
        bound = comps[0].value if isinstance(comps[0], ast.Constant) else None
        allowed = _NON_POSITIVE.get(type(ops[0]), ())
        if bound not in allowed:
            problems.append(
                f"the refusal compares sample_rate with {ast.unparse(node.test)}, which does not "
                "establish a non-positive rate -- `> 0` permits exactly the zero it guards"
            )
            continue
        refusals.append(node.lineno)
    if not refusals:
        problems.append("nothing in the loader refuses a non-positive frame rate")
    elif construction and min(refusals) > min(construction):
        problems.append(
            f"the refusal at line {min(refusals)} comes AFTER the AudioInput built at line "
            f"{min(construction)} -- it cannot protect what has already been constructed"
        )
    return problems


def test_a_corrupt_frame_rate_is_still_a_load_error() -> None:
    """The error path the shared helper quietly removed, restored explicitly.

    Before #13841 the provider computed ``getnframes() / float(sample_rate)`` inline, so a
    header declaring rate 0 raised ``ZeroDivisionError``, hit the handler and was logged as a
    load error. The shared helper returns ``0.0`` instead -- it must never raise, because its
    other caller is a throughput probe that would break synthesis -- so without an explicit
    check a corrupt header became an ``AudioInput`` with ``sample_rate=0`` and
    ``duration=0.0``, reported nowhere.

    Asserted structurally rather than by running the provider, which is application code.
    """
    problems = refusal_problems((repo_root() / _PROVIDER).read_text(encoding="utf-8"))
    assert not problems, f"{_PROVIDER}: " + "; ".join(problems)


_LOADER = """
def _load_audio_input(path):
{body}
"""
_REFUSE = "    if sample_rate <= 0:\n        raise ValueError('bad rate')"
_BUILD = "    return AudioInput(sample_rate=sample_rate)"


def test_a_correct_refusal_is_accepted() -> None:
    """The positive control: without it a detector that always complains passes the rest."""
    assert refusal_problems(_LOADER.format(body=f"{_REFUSE}\n{_BUILD}")) == []


def test_a_refusal_that_permits_zero_is_reported() -> None:
    """`> 0` passes a name-and-raise check while permitting the exact value it guards."""
    body = "    if sample_rate > 0:\n        raise ValueError('bad rate')\n" + _BUILD
    assert any("does not establish a non-positive rate" in p for p in refusal_problems(_LOADER.format(body=body)))


def test_a_refusal_after_the_construction_is_reported() -> None:
    """It cannot protect an AudioInput that already exists."""
    body = f"{_BUILD.replace('return ', 'built = ')}\n{_REFUSE}\n    return built"
    assert any("comes AFTER the AudioInput" in p for p in refusal_problems(_LOADER.format(body=body)))


def test_no_refusal_at_all_is_reported() -> None:
    assert any("nothing in the loader refuses" in p for p in refusal_problems(_LOADER.format(body=_BUILD)))


def test_a_renamed_loader_is_reported_rather_than_passing_empty() -> None:
    """The reach half: a detector that finds no loader must say so, not report clean."""
    assert any("looking at nothing" in p for p in refusal_problems(_LOADER.format(body=_BUILD), loader="gone"))


# --- the two source detectors, driven on literals -------------------------
#
# Both were asserted only against the live modules, which shows them agreeing with files that
# already comply and never shows either rejecting anything. `repo_tests/**` requires a positive
# and a negative fixture per detector, and the absence of one here was raised independently by
# two reviewers on #17887.

_IMPORT_ONLY = "from autobot_shared.audio_wav import wav_duration_seconds\n\ndef f(wav):\n    return 0.0\n"
_REAL_CALL = _IMPORT_ONLY.replace("    return 0.0", "    return wav_duration_seconds(wav)")
_LOCAL_WRAPPER = _IMPORT_ONLY.replace("    return 0.0", "    return _wav_duration_seconds(wav)")


def test_a_real_call_satisfies_the_detector() -> None:
    assert _calls_named(ast.parse(_REAL_CALL), "wav_duration_seconds") == 1


def test_an_import_only_mention_does_not() -> None:
    """The whole reason this is an ast.Call count: a `def`, an import or a comment cannot pass."""
    assert _calls_named(ast.parse(_IMPORT_ONLY), "wav_duration_seconds") == 0


def test_the_underscored_local_wrapper_is_a_different_name() -> None:
    """`_wav_duration_seconds` is the route's own adapter; calling it is not reaching the helper."""
    assert _calls_named(ast.parse(_LOCAL_WRAPPER), "wav_duration_seconds") == 0


def test_the_division_detector_flags_an_inlined_arithmetic() -> None:
    assert _divides_frames(ast.parse("def f(wav, rate):\n    return wav.getnframes() / float(rate)\n"))


def test_the_division_detector_passes_a_delegating_caller() -> None:
    """Positive control for the second net: delegation must not read as re-inlining."""
    assert not _divides_frames(ast.parse(_REAL_CALL))


def test_the_division_detector_does_not_claim_to_catch_a_bound_intermediate() -> None:
    """Pins the documented LIMIT, so a reader does not mistake the net for a proof.

    `n = wav.getnframes()` then `n / rate` is outside what this matches. Asserting the limit
    rather than leaving it in prose means a future widening has to change this test on purpose.
    """
    bound = "def f(wav, rate):\n    n = wav.getnframes()\n    return n / float(rate)\n"
    assert not _divides_frames(ast.parse(bound))
