# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Controls for the shared comment stripper (#17941).

Every syntax `_code_lines` claims to handle gets a control here, and the
headline case gets its own test: a file whose **comment contains the exact
literal a guard is searching for**. That is the defect the module exists to
prevent, so it is asserted directly rather than implied by the unit tests.

The permissive direction matters as much as the strict one. A stripper that
removed too much would make guards pass over code they never read, which is
the same failure wearing the opposite sign -- so each case below pins what
survives, not only what is removed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.lint._comment_syntax import CodeLine, code_lines, code_text, markers_for, strip_trailing_comment

# ---------------------------------------------------------------------------
# The headline case: prose must not satisfy a search
# ---------------------------------------------------------------------------

#: A shell script whose comment spells the forbidden construct and whose code
#: does not use it. This is witness 1 of #17941 reduced to four lines.
_PROSE_NAMES_THE_FORBIDDEN_THING = """\
#!/bin/sh
# Never call `read -r answer` here -- under `curl | bash` stdin is the script.
printf 'continue? '
read -r answer < /dev/tty
"""

#: The same file with the real violation and no comment about it.
_CODE_USES_THE_FORBIDDEN_THING = """\
#!/bin/sh
printf 'continue? '
read -r answer
"""


def test_a_comment_naming_the_literal_does_not_satisfy_a_search() -> None:
    """#17941 in one assertion."""
    prose = code_text(_PROSE_NAMES_THE_FORBIDDEN_THING, name="install.sh")
    assert "Never call" not in prose, "the comment survived the stripper, so a guard would still match it"
    assert "read -r answer < /dev/tty" in prose, "the real code was removed -- the guard would now read nothing"


def test_the_stripper_does_not_hide_the_real_violation() -> None:
    """The permissive-direction control: removing prose must not remove code.

    Without this, `return ""` satisfies the test above -- the cheapest way to
    stop matching a comment is to stop reading the file.
    """
    code = code_text(_CODE_USES_THE_FORBIDDEN_THING, name="install.sh")
    assert "read -r answer" in code


# ---------------------------------------------------------------------------
# One control per syntax claimed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "label,name,source,present,absent",
    [
        ("python hash", "x.py", "# secret_token here\nvalue = 1\n", "value = 1", "secret_token"),
        ("shell hash", "x.sh", "# rm -rf / is forbidden\necho ok\n", "echo ok", "rm -rf"),
        ("yaml hash", "x.yml", "# uses: evil/action@v1\njobs: {}\n", "jobs: {}", "evil/action"),
        ("typescript slashes", "x.ts", "// any is banned\nconst a = 1\n", "const a = 1", "any is banned"),
        ("vue slashes", "x.vue", "// console.log banned\nconst b = 2\n", "const b = 2", "console.log"),
        ("no suffix defaults to hash", "pre-push", "# --no-verify is banned\nexec true\n", "exec true", "no-verify"),
        ("toml hash", "x.toml", "# exclude = bad\nname = 'a'\n", "name = 'a'", "exclude = bad"),
    ],
)
def test_each_claimed_syntax_has_a_control(label: str, name: str, source: str, present: str, absent: str) -> None:
    """A syntax listed in `_MARKERS` but untested is a claim, not a capability."""
    text = code_text(source, name=name)
    assert absent not in text, f"{label}: the comment survived"
    assert present in text, f"{label}: the code did not"


def test_an_unknown_suffix_falls_back_to_hash_rather_than_stripping_nothing() -> None:
    """Silently stripping nothing is the dangerous default, so it is asserted."""
    assert markers_for("weird.xyz") == ("#",)
    assert "banned" not in code_text("# banned\nreal = 1\n", name="weird.xyz")


# ---------------------------------------------------------------------------
# Quote awareness -- the reason the private copies refused to do this
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "label,line,escapes,expected",
    [
        ("plain trailing comment", "echo ok  # trailing", True, "echo ok  "),
        ("hash inside double quotes", 'echo "a # b"', True, 'echo "a # b"'),
        ("hash inside single quotes", "grep '#!/bin/sh' f", True, "grep '#!/bin/sh' f"),
        ("quoted hash then real comment", 'echo "a # b"  # real', True, 'echo "a # b"  '),
        ("escaped hash is data in shell", "echo \\# literal", True, "echo \\# literal"),
        ("escaped hash is not special without escapes", "x = 1  # c", False, "x = 1  "),
        ("apostrophe inside double quotes", 'echo "don\'t # stop"', True, 'echo "don\'t # stop"'),
        ("no comment at all", "value = 1", False, "value = 1"),
    ],
)
def test_trailing_comments_are_stripped_only_outside_quotes(
    label: str, line: str, escapes: bool, expected: str
) -> None:
    """A regex cannot do this, which is why nobody did it seven times over."""
    assert strip_trailing_comment(line, ("#",), escapes=escapes) == expected, label


def test_trailing_stripping_is_opt_in() -> None:
    """The conservative default is what the migrated call sites relied on.

    Heredoc bodies are not parsed, so a `#` inside `<<EOF ... EOF` would be
    treated as a comment. Defaulting to off keeps that unsoundness opt-in.
    """
    source = "echo ok  # trailing\n"
    assert "# trailing" in code_text(source, name="x.sh")
    assert "# trailing" not in code_text(source, name="x.sh", strip_trailing=True)


# ---------------------------------------------------------------------------
# Line continuations
# ---------------------------------------------------------------------------


def test_a_continued_command_is_read_as_one_command() -> None:
    """The phase-validation case: the operator sits on a later physical line.

    A per-physical-line scan sees the line naming the script and never sees an
    operator appended after the redirect two lines below.
    """
    source = "python3 run.py \\\n  --ci-mode \\\n  > out.json || true\n"
    joined = code_lines(source, name="x.sh", join_continuations=True)
    assert len(joined) == 1
    assert "|| true" in joined[0].text and "run.py" in joined[0].text
    assert joined[0].lineno == 1, "the command must be reported where it starts"

    unjoined = code_lines(source, name="x.sh")
    assert not any(
        "run.py" in line.text and "|| true" in line.text for line in unjoined
    ), "without joining, no single physical line carries both -- which is the defect"


def test_line_numbers_survive_comment_removal() -> None:
    """A guard that reports `file:line` needs the original numbering."""
    lines = code_lines("# a\nreal_one = 1\n# b\nreal_two = 2\n", name="x.py")
    assert lines == [CodeLine(2, "real_one = 1"), CodeLine(4, "real_two = 2")]


def test_a_path_supplies_its_own_syntax(tmp_path: Path) -> None:
    """The `Path` form must not need the caller to repeat the file type."""
    path = tmp_path / "thing.ts"
    path.write_text("// banned\nconst a = 1\n", encoding="utf-8")
    assert "banned" not in code_text(path)
    assert "const a = 1" in code_text(path)


# ---------------------------------------------------------------------------
# Block comments -- and the glob that broke the heuristic they replaced
# ---------------------------------------------------------------------------


def test_a_block_comment_is_removed_but_a_glob_in_a_string_is_not() -> None:
    """The exact pair that defeated the anchored-regex approach.

    `import.meta.glob('../locales/*.json')` contains `/*`. An unanchored
    pattern treated it as a comment opener and ate the rest of the file; the
    anchored workaround then could not see a block comment that began after a
    non-space character. Tracking quotes answers both without a heuristic.
    """
    source = (
        "/* locale: 'en' used to be hardcoded here */\n"
        "const mods = import.meta.glob('../locales/*.json')\n"
        "const fallback = 'lv'\n"
    )
    text = code_text(source, name="bootstrap.ts")

    assert "used to be hardcoded" not in text, "the block comment survived"
    assert (
        "import.meta.glob('../locales/*.json')" in text
    ), "the glob was eaten as a comment opener -- this is the failure the anchored regex had"
    assert "const fallback = 'lv'" in text, "everything after the glob was swallowed"


def test_a_block_comment_opening_mid_line_is_still_removed() -> None:
    """What the line-anchored heuristic could not do."""
    text = code_text("const a = 1 /* banned_token */\n", name="x.ts")
    assert "banned_token" not in text
    assert "const a = 1" in text


def test_block_comment_removal_preserves_line_numbering() -> None:
    """A multi-line comment must not shift the lines a guard reports."""
    source = "const a = 1\n/* one\n   two */\nconst b = 2\n"
    lines = code_lines(source, name="x.ts")
    numbers = {line.lineno: line.text.strip() for line in lines}
    assert numbers.get(1) == "const a = 1"
    assert numbers.get(4) == "const b = 2", f"line 4 moved: {numbers}"


def test_a_block_comment_marker_inside_a_string_is_data() -> None:
    """The permissive-direction control for the block scanner."""
    text = code_text('const s = "not /* a comment */ really"\nconst c = 3\n', name="x.ts")
    assert "really" in text, "a block marker inside a string literal was treated as a comment"
    assert "const c = 3" in text
