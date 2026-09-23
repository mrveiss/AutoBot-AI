# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Why a backend path has no frontend caller, and whether that is a defect (#16816).

``audit_api_wiring.py --dead-surface`` lists paths the frontend never reaches. Most
of them are reached correctly by something that is not a browser, so a bare count is
large, mostly benign, and gets dismissed on first read -- which is how the mode went
unused for the life of the script. Splitting it is what makes the number actionable.

Lives here rather than in the auditor because that file sits at its recorded size
ceiling, and a ceiling only ever goes down.
"""

import os

#: Where the GUI-gap count is pinned. UNMEASURED until CI prints a real figure:
#: measuring it means importing the backend to dump its OpenAPI schema, which is
#: running codebase code outside CI, so the first number has to come from there.
BASELINE_PATH = "scripts/dead_surface_baseline.txt"
#: Resolved next to this module, so the pin is found whatever the caller's cwd
#: is; BASELINE_PATH stays repo-relative because it is what the message tells a
#: human to edit.
_BASELINE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dead_surface_baseline.txt")
UNMEASURED = "UNMEASURED"

_AGENT_FACING_PREFIXES = ("/api/agent/", "/api/llc/agent/", "/agent/")
_MACHINE_FACING_PREFIXES = ("/api/webhooks/", "/webhooks/", "/api/health", "/health", "/api/metrics", "/metrics")
_COMPANY_OS_MARKERS = ("/llc/", "/companies", "/work-items", "/boards", "/approvals", "/sprints", "/backlog")


def _is_company_os(path: str) -> bool:
    """Company OS surface, for the subtotal that answers 'can a user run the company'."""
    return any(m in path for m in _COMPANY_OS_MARKERS)


def classify_dead_surface(dead: list) -> dict:
    """Split paths with no frontend caller by whether a caller was ever expected (#16816).

    Three reasons a backend path has no frontend consumer, and only one of them
    is a defect:

    ``agent``    reached by an adapter or an agent's own API key, never by a browser.
    ``machine``  webhooks, health and metrics -- called by senders outside this repo.
    ``gui``      a capability that exists and no part of the UI can reach. The gap.

    Returning the split rather than a total is the point: the undifferentiated
    number is large, mostly benign, and therefore ignored.
    """
    out = {"agent": [], "machine": [], "gui": []}
    for path in dead:
        if path.startswith(_AGENT_FACING_PREFIXES):
            out["agent"].append(path)
        elif path.startswith(_MACHINE_FACING_PREFIXES):
            out["machine"].append(path)
        else:
            out["gui"].append(path)
    return out


def read_pin(path: str = None) -> str:
    """The pinned GUI-gap count, or UNMEASURED. A missing file reads as UNMEASURED."""
    try:
        with open(path or _BASELINE_FILE, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#"):
                    return line
    except OSError:
        return UNMEASURED
    return UNMEASURED


def ratchet_lines(gui_count: int, pin: str) -> list:
    """The pin comparison, as report lines. Advisory: it never decides an exit code.

    #16816 AC3 is report-only until a real count has been read and triaged, so
    this says what a gate WOULD say without being one. The direction is the
    point: a pin that only ever falls turns "we know the number" into "the
    number cannot grow while nobody is looking".
    """
    if pin == UNMEASURED:
        return [
            f"pin:      {UNMEASURED} -- pin it to {gui_count}, the figure above, in {BASELINE_PATH}",
        ]
    if not pin.isdigit():
        return [f"pin:      {pin!r} is not a count of GUI-unreachable paths"]
    over = gui_count - int(pin)
    lines = [f"pin:      {pin} GUI-unreachable path(s)"]
    if over > 0:
        lines.append(f"OVER BY:  {over} -- report-only today (#16816 AC3); this is what a gate would block on")
    elif over < 0:
        lines.append(f"under the pin by {-over}: lower it to {gui_count} in {BASELINE_PATH} to keep the ratchet tight")
    return lines


def report_lines(dead: list, split: dict, pin_lines: list) -> list:
    """The console report, as data.

    Built as a list so the emission has ONE call site: this module is not a CLI
    entry point (the auditor is), so the no-print hook scans it, and a single
    exempted loop is honest where ten scattered markers would be noise. Testable
    without capturing stdout, too.
    """
    gui = split["gui"]
    lines = [
        "",
        f"== BACKEND PATHS WITH NO FRONTEND CONSUMER: {len(dead)} ==",
        f"   agent-facing (adapters call these):  {len(split['agent'])}",
        f"   machine-facing (webhooks, health):   {len(split['machine'])}",
        f"   NO GUI PATH TO THIS CAPABILITY:      {len(gui)}",
        f"     of which Company OS:               {len([d for d in gui if _is_company_os(d)])}",
    ]
    lines += [f"   {line}" for line in pin_lines]
    lines += [f"  {d}" for d in gui[:100]]
    if len(gui) > 100:
        lines.append(f"  ... and {len(gui) - 100} more")
    return lines


def _summary_markdown(dead: list, split: dict, gui: list, pin_lines: list) -> str:
    company = [d for d in gui if _is_company_os(d)]
    lines = [
        "### Backend capability the GUI cannot reach (#16816)",
        "",
        "| Class | Count |",
        "| --- | ---: |",
        f"| agent-facing (adapters call these) | {len(split['agent'])} |",
        f"| machine-facing (webhooks, health, metrics) | {len(split['machine'])} |",
        f"| **no GUI path to this capability** | **{len(gui)}** |",
        f"| of which Company OS | {len(company)} |",
        f"| total with no frontend caller | {len(dead)} |",
        "",
        "```",
        *pin_lines,
        "```",
    ]
    if gui:
        lines += ["", "<details><summary>GUI-unreachable paths</summary>", ""]
        lines += [f"- `{d}`" for d in gui[:100]]
        if len(gui) > 100:
            lines.append(f"- ... and {len(gui) - 100} more")
        lines += ["", "</details>"]
    return "\n".join(lines) + "\n"


def report_dead_surface(dead: list, pin: str = None) -> list:
    """Write the report to the job summary, and return it for a caller to print.

    Three constraints meet here and only one arrangement satisfies all of them.
    Logging is what broke this originally: audit_api_wiring.py configures no
    logging at all, so the logger calls this function used to make went to a
    root logger at WARNING and emitted NOTHING. Printing from here instead
    makes this module a library that prints, and #16008's guard -- rightly --
    holds the print exemption to a property of CLI ENTRY POINTS, which this is
    not. And the entry point that could print, the auditor, cannot currently be
    edited at all: it carries pre-existing hardcoded-value findings in a
    directory the repo-wide scan does not walk (so they cannot be baselined,
    #17329) and a `main` of 106 body lines against a 65-line threshold, while
    sitting at exactly its 895-line size ceiling.

    So the report goes where it does not need the auditor's cooperation: the
    GITHUB_STEP_SUMMARY file, which is the criterion #16816 AC1 actually asks
    for. The lines are returned as well, so that the moment #17330 makes that
    file editable, printing them to the job log is a one-line change at the
    call site and nothing here moves.
    """
    split = classify_dead_surface(dead)
    gui = split["gui"]
    pin_lines = ratchet_lines(len(gui), read_pin() if pin is None else pin)

    lines = report_lines(dead, split, pin_lines)

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        # Appended by the script rather than assembled in YAML, so the number
        # reaches the summary without a pipeline that could swallow the
        # auditor's exit code on the way.
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write(_summary_markdown(dead, split, gui, pin_lines))

    return lines
