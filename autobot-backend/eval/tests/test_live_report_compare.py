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
    pins = {"label": "x", "step_budget": 5, "timeout": 300.0, "corpus_size": 3, "models": [{"model": "m1"}]}
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


@pytest.mark.parametrize(
    "pin,value", [("step_budget", 9), ("timeout", 60.0), ("corpus_size", 4), ("models", [{"model": "m2"}])]
)
def test_compare_refuses_reports_whose_pins_differ(pin, value):
    with pytest.raises(compare.NotComparable, match=pin if pin != "models" else "model"):
        compare.compare_reports(_report([True]), _report([True], **{pin: value}))


def test_compare_cli_exits_2_on_a_refusal_and_0_on_a_comparison(tmp_path):
    before, after, other = (tmp_path / n for n in ("b.json", "a.json", "o.json"))
    before.write_text(json.dumps(_report([True])), encoding="utf-8")
    after.write_text(json.dumps(_report([False])), encoding="utf-8")
    other.write_text(json.dumps(_report([True], step_budget=1)), encoding="utf-8")
    assert compare.main([str(before), str(after)]) == 0
    assert compare.main([str(before), str(other)]) == 2
    assert compare.main([str(before), str(tmp_path / "missing.json")]) == 2


async def _resolve(model):
    return "http://127.0.0.1:11434"


@pytest.mark.asyncio
async def test_run_live_eval_loops_models_by_repeats_and_stamps_the_pins():
    async def turn(golden, model, workspace):
        return LiveRunRecord(final_text="DEFAULT_TIMEOUT .get('timeout' websocket proxy slm role")

    report = await run_live_eval(
        ["m1", "m2", "m1"], "ollama", repeat=2, label="before", turn_runner=turn, resolve_endpoint=_resolve
    )
    corpus = len({o.trajectory_id for o in report.outcomes})
    assert len(report.outcomes) == 2 * 2 * corpus  # duplicate model collapsed
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
