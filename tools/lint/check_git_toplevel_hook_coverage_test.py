# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The toplevel gate must see the git hooks, which have no `.sh` suffix (#17035).

`check_git_toplevel_env_scrubbed.py` gates the #15783 class: a bare
`git rev-parse --show-toplevel` that an inherited `GIT_DIR` redirects to another
repository. Its shell population was `tracked_paths(root, "*.sh")`, and a git
hook is named for the event it serves -- `pre-push`, `commit-msg` -- so **no
hook was ever in the population.**

`tools/git-hooks/pre-push` carried exactly that call, on the one path where it
is most dangerous: the pre-push environment exports `GIT_DIR` pointing at the
pushing worktree's git dir, which is why `scripts/install-git-hooks.sh` already
has to `unset GIT_DIR` (#15246). The gate could not read the file that most
needed it.

These live beside the module's own test file rather than inside it: that file
is 584 lines against a 600-line ceiling, and #17035 is a distinct concern --
whether the population reaches the hooks at all, rather than what the scanner
does once it has a line.

The population itself moved to `_scan_helpers` for the same ceiling reason: the
gate sat at exactly 600 of 600, so every line added to widen it had to come
back out of the same file. `iter_shell_files` is generic, and it now lives
beside `tracked_paths`.

Mutation check: narrow `EXTENSIONLESS_SHELL_GLOBS` to `()` and
`test_every_tracked_hook_is_in_the_population` names the hooks that vanished;
restore the bare call in `tools/git-hooks/pre-push` and
`test_the_gate_reports_a_bare_call_in_a_hook` fails.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _scan_helpers import (  # noqa: E402
    EXTENSIONLESS_SHELL_GLOBS,
    has_shell_shebang,
    iter_shell_files,
    tracked_paths,
)
from check_git_toplevel_env_scrubbed import scan_shell  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK_DIR = REPO_ROOT / "tools" / "git-hooks"


def _tracked_hooks() -> list[str]:
    """Every tracked file under `tools/git-hooks/`, via the canonical enumeration.

    Through `tracked_paths` rather than a bare `git ls-files`: the first draft
    of this file shelled out directly and **the gate under test reported it**,
    which is the defect this whole module exists to catch, written into its own
    test. An inherited GIT_DIR outranks the `cwd=` passed, so the bare form
    answers for another checkout without erroring.
    """
    return tracked_paths(REPO_ROOT, "tools/git-hooks/*")


def _population() -> set[str]:
    return {p.resolve().relative_to(REPO_ROOT).as_posix() for p in iter_shell_files([], REPO_ROOT)}


def test_every_tracked_shell_hook_is_in_the_population() -> None:
    """Pinned against the directory's real contents, not a hand-written list.

    A list would be correct the day it was written and silently wrong the day
    someone adds a hook -- which is the failure this issue is about, one level
    up. Anything tracked under `tools/git-hooks/` that declares a shell
    interpreter must be scanned.
    """
    expected = {rel for rel in _tracked_hooks() if rel.endswith(".sh") or has_shell_shebang(REPO_ROOT / rel)}
    assert expected, "no shell hooks found under tools/git-hooks/ — this test is asserting nothing"

    missing = sorted(expected - _population())
    assert not missing, (
        f"these tracked shell hooks are not scanned by the toplevel gate: {missing}. "
        "A hook has no .sh suffix, so a suffix-only population never sees it (#17035)."
    )


def test_a_non_shell_file_in_the_hook_directory_is_not_scanned() -> None:
    """The other half: the globs must not drag in every file in that directory.

    `tools/git-hooks/README.md` is tracked there and is not a script. A
    population that swallowed it would report findings against prose.
    """
    assert "tools/git-hooks/README.md" in _tracked_hooks()
    assert "tools/git-hooks/README.md" not in _population()


def test_the_globs_are_not_empty() -> None:
    """The mechanism itself, so an empty tuple cannot pass as coverage."""
    assert EXTENSIONLESS_SHELL_GLOBS, "no extensionless globs declared — hooks are invisible again"


class TestTheShebangDetector:
    """Contrast pair for `has_shell_shebang`, which decides the population."""

    def test_it_accepts_a_bash_shebang(self, tmp_path) -> None:
        f = tmp_path / "pre-push"
        f.write_text("#!/usr/bin/env bash\necho hi\n", encoding="utf-8")
        assert has_shell_shebang(f) is True

    def test_it_accepts_a_plain_sh_shebang(self, tmp_path) -> None:
        f = tmp_path / "hook"
        f.write_text("#!/bin/sh\n", encoding="utf-8")
        assert has_shell_shebang(f) is True

    def test_it_rejects_a_python_shebang(self, tmp_path) -> None:
        f = tmp_path / "hook"
        f.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
        assert has_shell_shebang(f) is False

    def test_it_rejects_a_file_with_no_shebang(self, tmp_path) -> None:
        f = tmp_path / "README.md"
        f.write_text("# not a script\n", encoding="utf-8")
        assert has_shell_shebang(f) is False

    def test_a_binary_answers_false_rather_than_raising(self, tmp_path) -> None:
        f = tmp_path / "hook"
        f.write_bytes(b"\x7fELF\x02\x01\x01\x00\xff\xfe")
        assert has_shell_shebang(f) is False

    def test_a_missing_file_answers_false(self, tmp_path) -> None:
        assert has_shell_shebang(tmp_path / "absent") is False


class TestTheGateSeesWhatItNowReaches:
    """The negative control #17035 asks for, and its positive pair."""

    def test_the_gate_reports_a_bare_call_in_a_hook(self, tmp_path) -> None:
        """A planted bare call in a hook-shaped file must be reported.

        This is the finding the gate could not make before: the file has no
        suffix, so it was never handed to the scanner at all.
        """
        hook = tmp_path / "pre-push"
        hook.write_text(
            '#!/usr/bin/env bash\nREPO_ROOT="$(git rev-parse --show-toplevel)"\n',
            encoding="utf-8",
        )
        findings = scan_shell(hook, tmp_path)
        assert findings, "a bare --show-toplevel in a hook was not reported"
        assert findings[0][0] == 2

    def test_the_gate_stays_quiet_on_the_scrubbed_form(self, tmp_path) -> None:
        hook = tmp_path / "pre-push"
        hook.write_text('#!/usr/bin/env bash\nREPO_ROOT="$PWD"\n', encoding="utf-8")
        assert scan_shell(hook, tmp_path) == []

    def test_the_gate_stays_quiet_on_a_comment_naming_the_pattern(self, tmp_path) -> None:
        """`tools/git-hooks/commit-msg` documents the call it deliberately avoids.

        Flagging a hook's explanation of the defect is #16060's lesson, and it
        would have fired the moment the population widened to reach that file.
        """
        hook = tmp_path / "commit-msg"
        hook.write_text(
            "#!/usr/bin/env bash\n# no bare `git rev-parse --show-toplevel` here (#15783)\n",
            encoding="utf-8",
        )
        assert scan_shell(hook, tmp_path) == []


def test_the_real_pre_push_hook_no_longer_takes_the_bare_call() -> None:
    """The defect this issue was filed for, asserted against the real file."""
    findings = scan_shell(HOOK_DIR / "pre-push", REPO_ROOT)
    assert findings == [], f"tools/git-hooks/pre-push still has a raw call: {findings}"
