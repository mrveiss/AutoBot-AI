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


def test_an_apostrophe_in_a_line_comment_does_not_open_a_string_that_hides_later_globs() -> None:
    """The #21509 defect: `worker's` in a `//` comment swallowed the `/**/` of every later glob."""
    source = (
        "// the worker's stdout, and a stray /* opener\n"
        "const g = ['src/**/*.spec.ts'] // don't\n"
        "const after = 1 /* real */\n"
    )
    text = code_text(source, name="x.ts", strip_trailing=True)
    assert "'src/**/*.spec.ts'" in text, f"the glob was eaten: {text!r}"
    assert "const after = 1" in text and "real" not in text, text
    assert "worker" not in text and "don't" not in text


def test_a_double_slash_inside_a_regex_class_is_not_a_line_comment() -> None:
    """The regression against the previous scanner: the real block opener after the regex must still be found."""
    source = "const re = /[//]/; /*\nbanned_token\n*/\nconst z = 1\n"
    text = code_text(source, name="x.ts")
    assert "banned_token" not in text, "the regex's `//` hid the block comment that follows it"
    assert "/[//]/" in text and "const z = 1" in text, "the regex itself must be kept verbatim"


def test_a_double_slash_after_a_division_is_still_a_line_comment() -> None:
    text = code_text("const q = a / b // banned_token\nconst z = 1\n", name="x.ts", strip_trailing=True)
    assert "banned_token" not in text and "const q = a / b" in text and "const z = 1" in text


def test_a_block_comment_between_two_divisions_is_still_stripped() -> None:
    text = code_text("x = 4 / 2 /* banned_token */ / 1\n", name="x.ts")
    assert "banned_token" not in text and "x = 4 / 2" in text and "/ 1" in text


def test_a_quote_inside_a_regex_does_not_open_a_string() -> None:
    source = "const q = /'/; /* banned_token */\nconst s = 'x'\n"
    text = code_text(source, name="x.ts")
    assert "banned_token" not in text, "the regex's quote opened a string that hid the block comment"
    assert "/'/" in text and "const s = 'x'" in text


def test_a_regex_after_a_keyword_or_at_a_line_start_is_read_as_a_regex() -> None:
    assert "banned_token" not in code_text("function f() { return /[//]/ } /* banned_token */\n", name="x.ts")
    assert "banned_token" not in code_text("/[//]/.test(a) /* banned_token */\n", name="x.ts")


def test_a_slash_with_no_closing_slash_on_its_line_is_a_plain_character() -> None:
    text = code_text("const a = /unterminated\nconst b = 2 /* banned_token */\n", name="x.ts")
    assert "banned_token" not in text and "const b = 2" in text


def test_a_url_in_a_string_is_untouched_by_line_comment_handling() -> None:
    text = code_text("const u = 'http://x/y' /* banned_token */ // tail\nconst v = 1\n", name="x.ts")
    assert "http://x/y" in text and "banned_token" not in text and "const v = 1" in text


@pytest.mark.parametrize("name", ["x.mts", "x.cts"])
def test_module_typescript_suffixes_get_slash_and_block_comment_handling(name) -> None:
    source = "// banned_one\n/* banned_two */\nconst live = 1\n"
    text = code_text(source, name=name)
    assert "banned" not in text and "const live = 1" in text


@pytest.mark.parametrize(
    "source,kept",
    [
        ("const n = i++ / 2; /* banned_token */\n", "const n = i++ / 2;"),
        ("const n = i++ / 2 + '/'; /* banned_token */\n", "const n = i++ / 2 + '/';"),
        ("const n = i-- / 2 + '/'; /* banned_token */\n", "const n = i-- / 2 + '/';"),
        ("<b>x</b> '/' /* banned_token */\n", "<b>x</b> '/'"),
        ("const w = </b> /* banned_token */\n", "const w = </b>"),
        ("i++ / 2; // don't\n/* banned_token */\nconst k = 1\n", "i++ / 2;"),
        ("<div>x</div> // worker's\n/* banned_token */\nconst k = 1\n", "<div>x</div>"),
        ("x! / 2; // don't\n/* banned_token */\nconst k = 1\n", "x! / 2;"),
        ("const d = 8 / 2 / 1; /* banned_token */\n", "const d = 8 / 2 / 1;"),
        ("const n = x! / 2 + '/'; /* banned_token */\n", "const n = x! / 2 + '/';"),
        ("const of = 8;\nconst n = of / 2 + '/'; /* banned_token */\n", "const n = of / 2 + '/';"),
        ("<b>x</b> / 2 + '/'; /* banned_token */\n", "<b>x</b> / 2 + '/';"),
        ("const n = (a) / 2 + '/'; /* banned_token */\n", "const n = (a) / 2 + '/';"),
    ],
)
def test_a_division_is_never_read_as_a_regex_that_swallows_a_comment(source, kept) -> None:
    text = code_text(source, name="x.vue", strip_trailing=True)
    assert "banned_token" not in text and "worker" not in text and "don't" not in text, text
    assert kept in text, f"the code before the comment was damaged: {text!r}"


@pytest.mark.parametrize(
    "source,regex",
    [
        ("if (!/'/.test(x)) {} /* banned_token */\n", "!/'/.test(x)"),
        ("x = /'\\//; /* banned_token */\n", "/'\\//"),
        ("x = /a\\/\\/b/;  // banned_token\n", "/a\\/\\/b/;"),
        ("const re = /[//]/; /*\nbanned_token\n*/\n", "/[//]/;"),
        ("function f() { return /'/ } /* banned_token */\n", "return /'/"),
        ("const f = (s) => /'/.test(s); /* banned_token */\n", "=> /'/.test(s);"),
        ("if (a && !/'/.test(x)) {} /* banned_token */\n", "&& !/'/.test(x)"),
        ("if ((!/'/.test(x))) {} /* banned_token */\n", "(!/'/.test(x))"),
        ("if (!!/'/.test(x)) {} /* banned_token */\n", "!!/'/.test(x)"),
        ("function f() { return !/'/.test(x) } /* banned_token */\n", "return !/'/.test(x)"),
        ("!/'/.test(x); /* banned_token */\n", "!/'/.test(x);"),
    ],
)
def test_a_regex_literal_stays_a_regex_and_the_comment_after_it_is_stripped(source, regex) -> None:
    text = code_text(source, name="x.ts", strip_trailing=True)
    assert "banned_token" not in text, text
    assert regex in text, f"the regex literal was damaged: {text!r}"


def test_a_vue_line_with_a_closing_tag_a_html_comment_and_a_line_comment_is_read_as_code() -> None:
    text = code_text('<a href="/x/y">t</a> <!-- n --> // banned_token\n', name="x.vue", strip_trailing=True)
    assert 'href="/x/y">t</a>' in text and "banned_token" not in text and "<!-- n -->" in text


#: Lines where the scanner and the older quote-only trailing strip must cut at the same place.
_AGREED = [
    ("const a = 1 // c", "const a = 1 "),
    ("const u = 'http://x/y' // c", "const u = 'http://x/y' "),
    ('const s = "a // b" // c', 'const s = "a // b" '),
    ("no comment here", "no comment here"),
    ("const n = i++ / 2; // c", "const n = i++ / 2; "),
    ("x! / 2; // c", "x! / 2; "),
    ("<b>x</b> // c", "<b>x</b> "),
]

#: Lines the quote-only strip cannot read (a regex class, an escaped slash, a template, a division).
_SCANNER_ONLY = [
    ("const re = /[//]/; // c", "const re = /[//]/; "),
    ("x = /a\\/\\/b/; // c", "x = /a\\/\\/b/; "),
    ("const t = `x // y` // c", "const t = `x // y` "),
]


@pytest.mark.parametrize("line,expected", _AGREED)
def test_the_trailing_cut_is_the_scanners_and_matches_the_quote_only_strip_where_that_can_read_the_line(
    line, expected
) -> None:
    assert code_text(line + "\n", name="x.ts", strip_trailing=True) == expected
    assert strip_trailing_comment(line, ("//",)) == expected, "the two stages disagree on a line both can read"


@pytest.mark.parametrize("line,expected", _SCANNER_ONLY)
def test_the_trailing_cut_follows_the_scanner_on_lines_the_quote_only_strip_cannot_read(line, expected) -> None:
    assert code_text(line + "\n", name="x.ts", strip_trailing=True) == expected


def test_a_line_that_is_only_a_comment_is_dropped_and_numbering_survives_the_scanner_cut() -> None:
    lines = code_lines("// whole\nconst a = 1 // t\n/* b */ const b = /[//]/ // t\n", name="x.ts", strip_trailing=True)
    assert [(line.lineno, line.text.strip()) for line in lines] == [(2, "const a = 1"), (3, "const b = /[//]/")]
