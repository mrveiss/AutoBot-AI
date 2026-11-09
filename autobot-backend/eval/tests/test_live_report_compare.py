# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Live report (per_model, pins, markdown), eval.compare, and the CLI path (#20843)."""

import json

import pytest

from eval import compare
from eval.live import LiveRunRecord
from eval.live_run import run_live_eval
from eval.report import RegressionReport, TrajectoryOutcome
from eval.run import _parse_args, _run


def _o(tid, model, passed, cats=(), not_run=False, tokens=None):
    return TrajectoryOutcome(
        tid,
        "code_fix",
        0.9,
        1.0 if passed else 0.0,
        tools_ok=None if not_run else True,
        status_ok=None if not_run else True,
        model=model,
        provider="ollama",
        failure_categories=list(cats),
        passed=None if not_run else passed,
        tokens=tokens,
        score_indeterminate=not_run,
    )


def _run_pins(**over):
    pins = {
        "label": "x",
        "step_budget": 5,
        "loop_abort_threshold": 2,
        "timeout": 300.0,
        "corpus_size": 3,
        "corpus_fingerprint": "f1",
        "repeats": 1,
        "judge_model": None,
        "judge_local_only": None,
        "judge_endpoint_class": None,
        "local_only": True,
        "fallback_local_only": True,
        "kb_status": "populated",
        "models": [{"model": "m1", "provider": "ollama", "endpoint_class": "loopback", "local_only": True}],
    }
    return {**pins, **over}


def test_per_model_counts_pass_fail_not_run_and_categories_and_never_counts_not_run_as_passed():
    outcomes = [
        _o("a", "m1", True),
        _o("b", "m1", False, ["false_done", "loop_stall"]),
        _o("c", "m1", False, not_run=True),
        _o("a", "m2", False, ["unknown_tool"]),
    ]
    data = RegressionReport(outcomes, run=_run_pins()).to_dict()
    m1 = data["per_model"]["m1"]
    assert (m1["pass"], m1["fail"], m1["not_run"]) == (1, 1, 1)
    assert m1["categories"] == {"false_done": 1, "loop_stall": 1}
    assert m1["per_task"]["c"] == {"pass": 0, "fail": 0, "not_run": 1}
    assert data["per_model"]["m2"]["categories"] == {"unknown_tool": 1}
    assert data["run"]["step_budget"] == 5


def test_a_non_live_report_has_no_live_blocks():
    plain = TrajectoryOutcome("a", "c", 0.9, 0.9, tools_ok=True, status_ok=True)
    data = RegressionReport([plain]).to_dict()
    assert "per_model" not in data and "run" not in data


def test_markdown_escapes_untrusted_model_names_and_shows_the_tables():
    hostile = "m|`x`\n# injected"
    text = RegressionReport([_o("a", hostile, False, ["loop_stall"])], run=_run_pins()).render_markdown()
    assert "\n# injected" not in text and "m\\|" in text
    assert "| Model | Pass | Fail | Not run | Failure categories |" in text and "[FAIL]" in text


def _report(passes, **pins):
    outcomes = [_o(f"t{i}", "m1", ok, [] if ok else ["false_done"]) for i, ok in enumerate(passes)]
    return RegressionReport(outcomes, run=_run_pins(**pins)).to_dict()


def test_compare_reports_the_per_model_delta():
    delta = compare.compare_reports(
        _report([False, False, True], label="before"), _report([True, True, True], label="after")
    )
    m1 = delta["models"]["m1"]
    assert (m1["pass_rate"]["before"], m1["pass_rate"]["after"]) == (0.3333, 1.0)
    assert m1["categories"]["false_done"] == {"before": 2, "after": 0}
    assert "| m1 | 0.33 | 1.00 |" in compare.render_markdown(delta)


def _m1(**over):
    return [{"model": "m1", "provider": "ollama", "endpoint_class": "loopback", "local_only": True, **over}]


@pytest.mark.parametrize(
    "pin,value,message",
    [
        ("step_budget", 9, "step_budget"),
        ("loop_abort_threshold", 3, "loop_abort_threshold"),
        ("timeout", 60.0, "timeout"),
        ("corpus_size", 4, "corpus_size"),
        ("corpus_fingerprint", "f2", "corpus_fingerprint"),
        ("judge_local_only", False, "judge_local_only"),
        ("fallback_local_only", False, "fallback_local_only"),
        ("repeats", 5, "repeats"),
        ("judge_model", "judge-x", "judge_model"),
        ("local_only", False, "local_only"),
        ("kb_status", "empty", "kb_status"),
        ("models", [{"model": "m2"}], "model"),
        ("models", _m1(provider="openai"), "provider"),
        ("models", _m1(endpoint_class="private"), "endpoint_class"),
        ("models", _m1(local_only=False), "m1 local_only"),
    ],
)
def test_compare_refuses_reports_whose_pins_differ(pin, value, message):
    with pytest.raises(compare.NotComparable, match=message):
        compare.compare_reports(_report([True]), _report([True], **{pin: value}))


def test_compare_cli_exits_2_on_a_refusal_and_0_on_a_comparison(tmp_path):
    before, after, other = (tmp_path / n for n in ("b.json", "a.json", "o.json"))
    before.write_text(json.dumps(_report([True])), encoding="utf-8")
    after.write_text(json.dumps(_report([False])), encoding="utf-8")
    other.write_text(json.dumps(_report([True], step_budget=1)), encoding="utf-8")
    assert compare.main([str(before), str(after)]) == 0
    assert compare.main([str(before), str(other)]) == 2
    assert compare.main([str(before), str(tmp_path / "missing.json")]) == 2


@pytest.mark.parametrize("pin", ["timeout", "corpus_fingerprint", "step_budget"])
def test_compare_refuses_reports_that_both_omit_a_pin(pin):
    before, after = _report([True]), _report([True])
    del before["run"][pin], after["run"][pin]
    with pytest.raises(compare.NotComparable, match=f"missing pin '{pin}'"):
        compare.compare_reports(before, after)


def test_compare_refuses_a_model_pin_that_both_reports_omit():
    before, after = _report([True]), _report([True])
    for report in (before, after):
        del report["run"]["models"][0]["provider"]
    with pytest.raises(compare.NotComparable, match="missing pin 'provider'"):
        compare.compare_reports(before, after)


def test_compare_refuses_a_report_without_the_aggregate_of_a_pinned_model():
    before, after = _report([True]), _report([True])
    del after["per_model"]["m1"]
    with pytest.raises(compare.NotComparable, match="no aggregate for pinned model 'm1'"):
        compare.compare_reports(before, after)


def test_compare_cli_exits_2_when_the_json_output_cannot_be_written(tmp_path):
    before, after = tmp_path / "b.json", tmp_path / "a.json"
    before.write_text(json.dumps(_report([True])), encoding="utf-8")
    after.write_text(json.dumps(_report([False])), encoding="utf-8")
    assert compare.main([str(before), str(after), "--json", str(tmp_path / "no-such-dir" / "d.json")]) == 2


async def _kb():
    return "populated"


async def _resolve(model):
    return "http://127.0.0.1:11434"


@pytest.mark.asyncio
async def test_run_live_eval_loops_models_by_repeats_and_stamps_the_pins():
    async def turn(golden, model, workspace):
        return LiveRunRecord(final_text="DEFAULT_TIMEOUT .get('timeout' websocket proxy slm role")

    report = await run_live_eval(
        ["m1", "m2", "m1"],
        "ollama",
        repeat=2,
        label="before",
        turn_runner=turn,
        resolve_endpoint=_resolve,
        resolve_provider=lambda: "ollama",
        probe_kb=_kb,
    )
    corpus = len({o.trajectory_id for o in report.outcomes})
    assert len(report.outcomes) == 2 * 2 * corpus  # duplicate model collapsed
    rows = json.loads(json.dumps(report.to_dict()))["trajectories"]
    for model in ("m1", "m2"):
        for trajectory_id in {o.trajectory_id for o in report.outcomes}:
            indices = [r["repeat"] for r in rows if r["model"] == model and r["trajectory_id"] == trajectory_id]
            assert sorted(indices) == [0, 1]
    run = report.run
    assert (run["repeats"], run["label"], run["corpus_size"], run["local_only"]) == (2, "before", corpus, True)
    assert {m["model"]: (m["endpoint_class"], m["tokens"]) for m in run["models"]} == {
        "m1": ("loopback", None),
        "m2": ("loopback", None),
    }
    assert "127.0.0.1" not in json.dumps(report.to_dict())  # a class, never a host


def test_the_cli_exits_2_on_a_refused_remote_and_the_runner_is_never_reached(monkeypatch):
    monkeypatch.delenv("AUTOBOT_EVAL_ALLOW_REMOTE_PROVIDER", raising=False)

    calls = []

    async def fake_live(**kwargs):
        from eval.live_guard import RemoteProviderRefused

        calls.append(kwargs["provider"])
        raise RemoteProviderRefused("refused")

    monkeypatch.setattr("eval.live_run.run_live_eval", fake_live)
    monkeypatch.setattr("sys.argv", ["eval.run", "--live", "--model", "m1", "--provider", "openai"])
    assert _run(_parse_args()) == 2 and calls == ["openai"]


def test_the_gate_can_still_go_red_in_live_mode():
    """A failing live outcome is a regression (exit 1 when gated); an all-not-run corpus is exit 2, not 0."""
    from eval.run import _gated_exit

    class Args:
        fail_on_regression = True
        require_real_candidate = False

    assert _gated_exit(Args, RegressionReport([_o("a", "m1", True), _o("b", "m1", False, ["loop_stall"])])) == 1
    assert _gated_exit(Args, RegressionReport([_o("a", "m1", True)])) == 0
    assert _gated_exit(Args, RegressionReport([_o("a", "m1", False, not_run=True)])) == 2


def test_a_candidate_pass_that_fails_a_deterministic_check_is_a_fail_in_every_view():
    outcome = _o("a", "m1", True)
    outcome.tools_ok = False
    data = RegressionReport([outcome], run=_run_pins()).to_dict()
    row = data["trajectories"][0]
    assert (row["state"], row["passed"]) == ("fail", False)
    assert (data["per_model"]["m1"]["pass"], data["per_model"]["m1"]["fail"]) == (0, 1)


def test_the_corpus_fingerprint_follows_the_content_of_a_golden_not_its_count():
    from eval.live_run import corpus_fingerprint
    from eval.store import GoldenTrajectory

    def golden(prompt):
        return GoldenTrajectory("g", "code_fix", {"prompt": prompt}, [], 0.9)

    assert corpus_fingerprint([golden("a")]) == corpus_fingerprint([golden("a")])
    assert corpus_fingerprint([golden("a")]) != corpus_fingerprint([golden("b")])


def test_an_empty_live_report_exits_2_and_still_carries_the_run_pins(monkeypatch, tmp_path):
    empty = RegressionReport([], run=_run_pins())
    monkeypatch.setattr("eval.run._live_report", lambda args: empty)
    out = tmp_path / "r.json"
    monkeypatch.setenv("EVAL_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr("sys.argv", ["eval.run", "--live", "--json", str(out)])
    assert _run(_parse_args()) == 2
    assert json.loads(out.read_text(encoding="utf-8"))["run"]["corpus_size"] == 3
    assert "**Run pins:**" in empty.render_markdown()
