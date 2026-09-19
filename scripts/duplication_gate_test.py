# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""duplication_gate.py pins the duplicated-line count, not the ratio (#16319).

The fixtures are jscpd Total rows in the form jscpd prints them: U+2502 box
separators inside ANSI colour, and no ASCII pipe (#16163).
- ``_BASE_ROW`` is verbatim from run 34414434867, captured for #16163.
- ``_PR_16308_ROW`` carries #16308's figures from job 103212663862 (753 files,
  255,420 lines, 1,205,679 tokens, 135 clones, 4,729 duplicated lines at 1.85%)
  in that same form.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("duplication_gate", Path(__file__).parent / "duplication_gate.py")
duplication_gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(duplication_gate)

_SEP = "\x1b[90m│\x1b[39m"

_BASE_ROW = (
    "\x1b[90m│\x1b[39m \x1b[1mTotal:\x1b[22m     \x1b[90m│\x1b[39m 759            "
    "\x1b[90m│\x1b[39m 259798      \x1b[90m│\x1b[39m 1227700      "
    "\x1b[90m│\x1b[39m 135           \x1b[90m│\x1b[39m 4729 (1.82%)   \x1b[90m│\x1b[39m"
)


def _row(files: int, lines: int, tokens: int, clones: int, duplicated: int, percent: str) -> str:
    return (
        f"{_SEP} \x1b[1mTotal:\x1b[22m     {_SEP} {files}            {_SEP} {lines}      {_SEP} {tokens}      "
        f"{_SEP} {clones}           {_SEP} {duplicated} ({percent}%)   {_SEP}"
    )


_PR_16308_ROW = _row(753, 255420, 1205679, 135, 4729, "1.85")


def _totals(row: str):
    return duplication_gate.parse_totals(row)


def test_the_captured_jscpd_row_parses_to_its_figures():
    """The row #16163 captured from a real run, read field by field.

    Asserting the figures, not merely that parsing succeeded, is what catches an
    off-by-one in the field split: one such bug read tokens as lines.
    """
    assert _totals(_BASE_ROW) == duplication_gate.Totals(files=759, lines=259798, clones=135, duplicated_lines=4729)


def test_16308s_tree_passes_although_its_ratio_rose():
    """#16319's own case: the same duplication over fewer lines is not new duplication."""
    totals = _totals(_PR_16308_ROW)

    code, report = duplication_gate.gate(totals, "4729")

    assert (totals.duplicated_lines, totals.lines) == (4729, 255420)
    assert round(totals.duplicated_lines / totals.lines * 100, 2) == 1.85, "the ratio the old 1.82% pin failed"
    assert code == 0, report


def test_one_added_duplicated_line_fails():
    """The known positive: the gate must still catch the smallest real growth."""
    code, report = duplication_gate.gate(_totals(_row(753, 255421, 1205680, 136, 4730, "1.85")), "4729")

    assert code == 1
    assert "OVER BY:   1 lines" in report


def test_a_count_under_the_pin_passes_and_says_to_lower_it():
    code, report = duplication_gate.gate(_totals(_row(753, 255420, 1205679, 134, 4700, "1.84")), "4729")

    assert code == 0
    assert any("lower it to 4700" in line for line in report)


def test_an_unmeasured_pin_fails_and_prints_the_figure_to_pin():
    code, report = duplication_gate.gate(_totals(_PR_16308_ROW), duplication_gate.UNMEASURED)

    assert code == 1
    assert any("pin it to 4729" in line for line in report)


def test_a_leftover_percentage_pin_is_refused_not_misread():
    """``1.82`` must not parse as a line count, or a stale pin would gate on 1 line."""
    code, report = duplication_gate.gate(_totals(_PR_16308_ROW), "1.82")

    assert code == 2
    assert any("is not a count" in line for line in report)


def test_a_log_without_a_total_row_reports_no_figure(tmp_path, capsys):
    log = tmp_path / "jscpd.log"
    log.write_text("jscpd started\nno table here\n", encoding="utf-8")

    assert duplication_gate.main([str(log), "4729"]) == 2
    output = capsys.readouterr().out
    assert "could not read jscpd totals" in output
    assert "OVER BY" not in output


def test_a_missing_log_reports_no_figure(tmp_path, capsys):
    assert duplication_gate.main([str(tmp_path / "absent.log"), "4729"]) == 2
    assert "could not read jscpd totals" in capsys.readouterr().out


def test_the_cli_exits_on_the_pin_through_a_real_log(tmp_path):
    log = tmp_path / "jscpd.log"
    log.write_text(f"jscpd summary\n{_PR_16308_ROW}\n", encoding="utf-8")

    assert duplication_gate.main([str(log), "4729"]) == 0
    assert duplication_gate.main([str(log), "4728"]) == 1
