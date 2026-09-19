#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Fail when a BEHAVIOURAL pre-commit hook reported a finding (#14878).

`.github/workflows/enforce-precommit.yml` runs `pre-commit run --all-files` and
routes findings to `::warning::`. For a formatter or a linter that is the right
call and the step's own comment says so: gating a merge on Black's opinion is a
judgement nobody made. `check_precommit_hooks_executed.py` (#14181) already
covers the other half — a hook that could not *execute* fails the job, because a
pass over a hook that never ran is a false clean bill of health.

Between those two sits a class neither one catches. `ssot-config-lib-guard` is
not a formatter: its entry is a **test suite**, and a failure means a shipped
script's config bootstrap is broken. It executed fine, so #14181 is satisfied;
it reported a finding, so the workflow warns and moves on. The regression guard
written for #14041 therefore runs in exactly one place and blocks nothing —
the same shape as the defect it exists to catch (#14878).

THE CRITERION, written down rather than implied
-----------------------------------------------
A hook belongs in ``GATING_HOOK_IDS`` when it **asserts the repository's own
shipped state, so its verdict is independent of the diff under review**.
Everything else — style, formatting, and the "no new X" pattern bans whose
subject is the changed lines — stays informational, which is what the
surrounding step already decided.

The criterion was first written as "its entry is a test suite". That named the
implementation of the one hook it then selected rather than the property doing
the work: independence from the diff is what makes a warning the wrong
disposition, and pytest is not the only way to reach it. #14895 widened the
wording to the property, and the list grew from one to two.

``no-root-clutter`` (#14216, admitted in #14895) is the second. It qualifies on
the same property by a different route:

* ``pass_filenames: false`` and a full ``git ls-files`` sweep — it rules on the
  whole tracked tree, never on the staged subset, so the answer does not move
  with the diff.
* Its subject is repository *state*, not code style: a session report at the
  root, or a ``MagicMock/`` artifact tree committed by the #14217 path bug.
  Neither is an opinion, and neither goes away by being warned about — the
  file stays in the tree, and the next run warns again.
* It was already non-advisory in intent: it exits 2 (not 1) when its own scan
  loses reach, precisely so an empty result cannot read as clean. A hook that
  careful about false-clean, wired to a ``::warning::``, blocked nothing.

The list is guarded in both directions, so the next append is an append rather
than a redesign.

WHY THE ALLOWLIST IS KEYED BY HOOK ``id``, NOT BY NAME
------------------------------------------------------
pre-commit prints the hook's ``name``, and a name is not a stable identifier:
it is prose, it gets reworded, and until #14923 it could not even survive its
own file. 23 names were written unquoted with a ``#`` issue reference —
``name: Function Length Check (Issue #620)`` — where the space-``#`` opens a
YAML comment, so the parsed name was ``Function Length Check (Issue`` and that
truncated string is what pre-commit printed. Those names are quoted now, and
``repo_tests/precommit_hook_names_survive_yaml_parse_test.py`` fails if a new
one loses text the same way.

Resolving ``id -> name`` through the same YAML parser stays correct either
way, which is the point: it reproduces whatever pre-commit will print without
this module having to know which spelling won. Hard-coding a name would have
matched nothing before #14923 and would break again on the next reword — and
in a gate, matching nothing reads as clean.

The allowlist is self-guarding in both directions:

* an id that is no longer in ``.pre-commit-config.yaml`` FAILS, rather than
  silently exempting itself. An allowlist entry stranded by a rename exempts
  nothing and says nothing while it does it.
* a hook whose result line is absent, or reads ``Skipped``, FAILS. A
  behavioural suite that did not run validated nothing, and "no result" must
  not read as "clean" — the whole subject of #14878.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_precommit_hooks_executed import _RAN_AT_ALL  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CONFIG = _REPO_ROOT / ".pre-commit-config.yaml"

# See "THE CRITERION" above before adding to this. Both entries assert
# repository state independently of the diff; neither is a style opinion.
GATING_HOOK_IDS: tuple[str, ...] = ("ssot-config-lib-guard", "no-root-clutter")

# pre-commit colours only a tty; the workflow redirects to a file. Stripped
# anyway so a future `--color always` cannot turn this gate into a false alarm
# that blocks every pull request.
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def hook_names(config_text: str) -> dict[str, str]:
    """Map every configured hook ``id`` to the ``name`` pre-commit will print."""
    document = yaml.safe_load(config_text) or {}
    names: dict[str, str] = {}
    for repo in document.get("repos") or []:
        for hook in repo.get("hooks") or []:
            hook_id = hook.get("id")
            if hook_id:
                names[hook_id] = str(hook.get("name") or hook_id)
    return names


def hook_result(output: str, name: str) -> str | None:
    """The status pre-commit printed for ``name``, or None when it printed none.

    pre-commit pads the name with dots to a fixed width and may insert a
    parenthesised postfix (``(no files to check)Skipped``). The name is never
    truncated: when it is longer than the field, the dot run is empty.
    """
    line = re.compile(
        r"^" + re.escape(name) + r"\.*(?:\([^)\n]*\))?(Passed|Failed|Skipped)\s*$",
        re.MULTILINE,
    )
    found = {match.group(1) for match in line.finditer(output)}
    if not found:
        return None
    # A hook cannot both pass and fail in one run; if the log says otherwise,
    # take the worst so the ambiguity cannot resolve in the green direction.
    for status in ("Failed", "Skipped", "Passed"):
        if status in found:
            return status
    return None


def _verdicts(output: str, names: dict[str, str]) -> list[tuple[str, str]]:
    """One ``(hook_id, problem)`` pair per gating hook that is not a clean pass."""
    problems: list[tuple[str, str]] = []
    for hook_id in GATING_HOOK_IDS:
        name = names.get(hook_id)
        if name is None:
            problems.append((hook_id, "not present in .pre-commit-config.yaml"))
            continue
        status = hook_result(output, name)
        if status == "Passed":
            continue
        if status is None:
            problems.append((hook_id, f"no result line for {name!r} in the output"))
        else:
            problems.append((hook_id, f"reported {status}"))
    return problems


def _report(problems: list[tuple[str, str]]) -> None:
    print(f"check-gating-precommit-hooks: {len(problems)} behavioural hook(s) not clean\n")  # noqa: print
    for hook_id, problem in problems:
        print(f"  FAIL   {hook_id}: {problem}")  # noqa: print
    print(  # noqa: print
        "\nThese hooks are behavioural regression suites, not formatters: a finding\n"
        "means shipped behaviour is broken, so it blocks rather than warns (#14878).\n"
        "Reproduce locally with:\n"
        "  pre-commit run --all-files " + " ".join(GATING_HOOK_IDS) + "\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gate on behavioural pre-commit hooks (#14878)")
    parser.add_argument("logfile", nargs="?", help="pre-commit output; stdin when omitted")
    parser.add_argument("--config", default=str(_CONFIG), help="path to .pre-commit-config.yaml")
    parser.add_argument(
        "--print-ids",
        action="store_true",
        help=(
            "print the gating hook ids, one per line, and exit. #15358 scopes the "
            "main sweep to the pull request diff, which makes every hook the diff "
            "does not touch report Skipped -- and Skipped FAILS this gate by "
            "design. The gating hooks therefore run in a second, full-scope "
            "invocation, and the workflow asks for their ids here rather than "
            "hard-coding them: a copy in YAML is a second thing to go stale, the "
            "same reasoning that made check_precommit_hooks_executed import its "
            "dormant list instead of duplicating it (#14202)."
        ),
    )
    args = parser.parse_args(argv)

    if args.print_ids:
        for hook_id in GATING_HOOK_IDS:
            print(hook_id)  # noqa: print
        return 0

    raw = Path(args.logfile).read_text(encoding="utf-8") if args.logfile else sys.stdin.read()
    output = _ANSI.sub("", raw)

    if not _RAN_AT_ALL.search(output):
        print(  # noqa: print
            "check-gating-precommit-hooks: FATAL -- no hook result line in the captured\n"
            "output, so no hook ran and this gate has nothing to verify. Reporting success\n"
            "here would be the fail-open the gate exists to remove."
        )
        return 1

    problems = _verdicts(output, hook_names(Path(args.config).read_text(encoding="utf-8")))
    if not problems:
        print(  # noqa: print
            "check-gating-precommit-hooks: every behavioural hook passed " f"({', '.join(GATING_HOOK_IDS)})"
        )
        return 0

    _report(problems)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
