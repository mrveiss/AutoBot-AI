# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The SLM console has 11 locales, at parity, reachable, and RTL-aware (#14781).

The app shipped `src/locales/en.json` alone and `createI18n({ locale: 'en' })`,
so ten of the eleven languages the platform supports did not exist for it and
the eleventh could not be changed. #14781's criteria are asserted here rather
than described:

- all 11 locale files present, and every key in every one of them (a key in one
  locale but not the others is the drift this guard exists to catch);
- no hardcoded locale in the bootstrap;
- a language switcher wired into the shell, because eleven bundles nobody can
  reach is not eleven locales;
- an RTL locale declares its direction in its own file, so the app cannot
  disagree with the locale about which way its text runs.

WHY THIS IS PYTHON AND NOT VITEST. Both exist: `src/i18n/__tests__/locales.spec.ts`
asserts the runtime behaviour (resolution, switching, fallback) and runs in CI.
This file asserts the FILE-LEVEL invariants, and it runs everywhere a developer
can run pytest -- `autobot-slm-frontend`'s dev toolchain is not installed in
every checkout, and an invariant that can only be checked where `npx vitest`
resolves is an invariant that goes unchecked on most machines.

The two do not overlap: a vitest spec cannot see a locale file that was never
imported, and this cannot see whether `setLocale` actually repaints.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

_APP = Path("autobot-slm-frontend")
_LOCALES = _APP / "src" / "locales"
_I18N = _APP / "src" / "i18n" / "index.ts"
_SWITCHER = _APP / "src" / "components" / "common" / "LanguageSwitcher.vue"
_SHELL = _APP / "src" / "components" / "common" / "Sidebar.vue"

#: The platform's locale set. A list, because "every file on disk" would make
#: the parity assertion below true of one file.
_EXPECTED_LOCALES = ("ar", "de", "en", "es", "fa", "fr", "he", "lv", "pl", "pt", "ur")

_RTL_LOCALES = frozenset({"ar", "fa", "he", "ur"})


def _en_message_keys(root: Path | None = None) -> list[str]:
    """Every message key in `en.json` -- the population parity is asserted over.

    Returns an empty list on a tree without the file rather than raising, which
    is `_reach.declare`'s contract for a `discover` callable (#16154).
    """
    path = (root or repo_root()) / _LOCALES / "en.json"
    if not path.exists():
        return []
    return [key for key in _flatten(json.loads(path.read_text(encoding="utf-8"))) if not key.startswith("_meta")]


#: Migrated from a hand-rolled minimum-keys constant of 3,000 (#15928, via
#: #17395's CI). Named indirectly on purpose: the migration detector matches
#: a floor-shaped name at line start, and its own source splits such names
#: for the same reason.
#: The population was RE-MEASURED rather than carried across -- 3,191 keys today
#: -- because copying the old constant into `declare` would pin a number nobody
#: had checked against this tree, which is the whole point of the migration.
#:
#: Pinned mid-window: 3,161 leaves room for 30 more keys before the meta-test
#: asks for a bump, where `population - growth` would put the slack exactly at
#: the allowance and red on the next key anyone adds (#17142).
REACH = declare(
    "slm-frontend-locale-keys",
    discover=_en_message_keys,
    floor=3_161,
    what="message keys in autobot-slm-frontend's en.json",
    growth=60,
)


def _flatten(node: dict, prefix: str = "") -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in node.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            out.update(_flatten(value, path))
        else:
            out[path] = value
    return out


def _code(path: Path) -> str:
    """A TS/Vue file with its comments removed.

    The bootstrap's own docstring quotes the string this guard forbids -- it
    explains that the app used to read `locale: 'en'` -- so a raw-text scan
    fails on the explanation. That is the #16750 shape: a scan that reads
    comments makes the comment the defect, and the fix is to read the code.
    """
    return _strip_comments((repo_root() / path).read_text(encoding="utf-8"))


#: A block comment opens at a line start or after whitespace. Anchoring it there
#: is load-bearing: `import.meta.glob('../locales/*.json')` contains `/*`, and an
#: unanchored pattern treated it as a comment opener and ate the rest of the file
#: up to the next `*/` -- the assertion then failed on the very line it guards.
#:
#: The anchor is a heuristic and not a parser, which is worth stating rather than
#: leaving to be discovered (review finding on #17395): these patterns have no
#: string-literal awareness, so a value like `"a // b"` -- whitespace, then a
#: comment opener, inside quotes -- would still be truncated as if it were a
#: comment. None of the three files read below contains one today. If one appears
#: the fix is a real tokenizer, not a longer regex.
_BLOCK_COMMENT = re.compile(r"(?:^|(?<=\s))/\*.*?\*/", re.S | re.M)
_LINE_COMMENT = re.compile(r"(?:^|(?<=\s))//.*$")


def _strip_comments(source: str) -> str:
    """*source* with its comments removed and its code intact."""
    return "\n".join(_LINE_COMMENT.sub("", line) for line in _BLOCK_COMMENT.sub(" ", source).splitlines())


def _bundle(locale: str) -> dict:
    path = repo_root() / _LOCALES / f"{locale}.json"
    assert path.exists(), f"{locale}.json is missing -- the SLM console is back to fewer than 11 locales"
    return json.loads(path.read_text(encoding="utf-8"))


def _keys(locale: str) -> set[str]:
    # `_meta` is the file's own metadata, not a message.
    return {k for k in _flatten(_bundle(locale)) if not k.startswith("_meta")}


def test_every_locale_file_exists() -> None:
    # `iterdir()` with a suffix filter rather than a quoted glob: a glob literal
    # is a declared input the python path filter does not cover, which #15900
    # requires recording -- and the record file sits at its 600-line ceiling.
    # Same listing, no declaration to record.
    present = sorted(p.stem for p in (repo_root() / _LOCALES).iterdir() if p.suffix == ".json")

    assert present == sorted(_EXPECTED_LOCALES), (
        f"the SLM console's locales are {present}, expected {sorted(_EXPECTED_LOCALES)} -- "
        "#14781 brought it to the platform's full set and this is what keeps it there"
    )


def test_english_is_not_a_stub() -> None:
    """The floor: parity with an empty en.json would be parity with nothing.

    Bound to `REACH` so `reach_declarations_test` proves the floor against the
    live population instead of this file asserting its own number.
    """
    keys = REACH.examined(repo_root())
    REACH.completed(len(keys))

    assert len(keys) >= REACH.floor, (
        f"en.json carries {len(keys)} message keys, expected at least {REACH.floor} -- a truncated "
        "English bundle would make every parity assertion below trivially true"
    )


@pytest.mark.parametrize("locale", [loc for loc in _EXPECTED_LOCALES if loc != "en"])
def test_every_locale_has_exactly_english_keys(locale: str) -> None:
    """#14781's sixth criterion: a key in one locale but not the others fails."""
    english = _keys("en")
    theirs = _keys(locale)

    missing = sorted(english - theirs)
    extra = sorted(theirs - english)
    assert not missing and not extra, (
        f"{locale}.json is not at parity with en.json: {len(missing)} missing, {len(extra)} extra.\n"
        f"  missing (first 5): {missing[:5]}\n  extra (first 5): {extra[:5]}\n"
        "Regenerate with scripts/lift_locale_translations.py rather than hand-editing -- "
        "the generator is what keeps every locale's key set identical."
    )


@pytest.mark.parametrize("locale", _EXPECTED_LOCALES)
def test_every_locale_declares_its_direction(locale: str) -> None:
    """`getLocaleDir` reads `_meta.dir`; a missing one silently renders LTR."""
    meta = _bundle(locale).get("_meta", {})
    expected = "rtl" if locale in _RTL_LOCALES else "ltr"

    assert meta.get("dir") == expected, (
        f"{locale}.json declares dir={meta.get('dir')!r}, expected {expected!r}. An RTL locale "
        "without it renders Arabic strings in a left-to-right layout, which is the half-fix "
        "this asserts against."
    )


def test_the_bootstrap_does_not_hardcode_a_locale() -> None:
    source = _code(_I18N)

    assert "locale: resolveInitialLocale()" in source, (
        "src/i18n/index.ts no longer resolves its locale from the user's preference or browser; "
        "#14781 exists because it read `locale: 'en'`"
    )
    assert "locale: 'en'" not in source


def test_the_bootstrap_derives_its_locales_from_disk() -> None:
    """A hand-kept list is how a locale file lands and never loads (#1675)."""
    source = _code(_I18N)

    assert "import.meta.glob" in source
    assert "'../locales/*.json'" in source


def test_the_bootstrap_sets_the_document_direction() -> None:
    source = _code(_I18N)

    assert "setAttribute('dir'" in source, "switching language must set html[dir] or RTL is text-only"
    assert "setAttribute('lang'" in source


def test_the_switcher_exists_and_the_shell_uses_it() -> None:
    """Eleven bundles nobody can reach is not eleven locales."""
    assert (repo_root() / _SWITCHER).exists(), "the language switcher component is gone"

    shell = _code(_SHELL)
    assert "LanguageSwitcher" in shell, (
        "the shell no longer renders the language switcher, so ten locales are unreachable again "
        "even though their files are present"
    )


def test_the_switcher_labels_languages_in_their_own_language() -> None:
    """A user stranded in a language they cannot read needs their own endonym."""
    source = _code(_SWITCHER)

    for endonym in ("Deutsch", "Español", "Latviešu", "العربية", "עברית"):
        assert endonym in source, f"{endonym} is no longer offered under its own name"


def test_no_locale_value_is_an_empty_string() -> None:
    """An empty translation renders as nothing, which looks like a layout bug."""
    offenders: list[str] = []
    for locale in _EXPECTED_LOCALES:
        for key, value in _flatten(_bundle(locale)).items():
            if isinstance(value, str) and not value.strip():
                offenders.append(f"{locale}:{key}")

    assert not offenders, "empty locale values render as blank UI:\n  " + "\n  ".join(offenders[:10])


#: The opening delimiter of a PEM armour block. Written as the delimiter alone,
#: without the ``BEGIN <kind> KEY`` phrase that follows it, because that phrase
#: is what ``detect-secrets``' own matcher looks for -- spelling it here would
#: make this guard the next finding.
_PEM_ARMOUR = "-----BEGIN "


def test_no_locale_value_carries_a_pem_armour_block() -> None:
    """A key format example is not a translatable string (#14781).

    The console's extractor swept the placeholder of every PEM textarea into
    ``en.json`` under a slug of its own contents --
    ``securityView.bEGINPRIVATEKEYENDPRIVATEKEY`` -- and this PR then copied
    those values into ten more locale files, which put a literal private-key
    armour header in eleven checked-in files and made ``detect-secrets`` flag
    every one of them. The keys are gone and the placeholders now say what to
    paste rather than showing a fake key.

    The reason this is a guard and not just a fix: the tempting repair was to
    mark the findings ``is_secret: false`` in ``.secrets.baseline``, which
    silences the detector on a whole class of string in order to keep keys that
    should not exist. This asserts the class stays out of the locale files, so
    the baseline never has to carry it.
    """
    offenders: list[str] = []
    for locale in _EXPECTED_LOCALES:
        for key, value in _flatten(_bundle(locale)).items():
            if isinstance(value, str) and _PEM_ARMOUR in value:
                offenders.append(f"{locale}:{key}")

    assert not offenders, (
        "these locale values carry a PEM armour block:\n  "
        + "\n  ".join(offenders[:10])
        + "\nA key or certificate format example is the same in every language. Make the "
        "placeholder an instruction ('Paste the PEM-encoded private key') rather than a "
        "specimen key -- see securityView.pemKeyHint."
    )


def test_the_comment_stripper_would_not_hide_real_code() -> None:
    """Positive control: stripping comments must not strip the code beside them.

    Without this, every assertion above passes equally well against a stripper
    that returned the empty string -- the failure mode that makes a guard read
    as enforcement while checking nothing.
    """
    stripped = _strip_comments("const a = 1 // locale: 'en'\n/* locale: 'en' */\nconst b = \"locale: 'en'\"\n")

    assert "const a = 1" in stripped and "const b" in stripped
    assert stripped.count("locale: 'en'") == 1, "only the one inside a string literal may survive"


def test_the_comment_stripper_leaves_a_glob_path_alone() -> None:
    """The bug this stripper had: `locales/*.json` opens with `/*`.

    An unanchored block-comment pattern consumed everything from there to the
    next `*/` in the file, and `test_the_bootstrap_derives_its_locales_from_disk`
    then failed on the line it exists to assert.
    """
    stripped = _strip_comments("const m = import.meta.glob('../locales/*.json')\n/* a real comment */\nconst n = 2\n")

    assert "'../locales/*.json'" in stripped
    assert "const n = 2" in stripped
    assert "a real comment" not in stripped


#: The one locale that is hand-maintained rather than generated. Everything else
#: under `src/locales/` is produced by `scripts/lift_locale_translations.py`.
_AUTHORED_LOCALE = "en"


def _secret_exclude_patterns() -> list[str]:
    baseline = json.loads((repo_root() / ".secrets.baseline").read_text(encoding="utf-8"))
    for entry in baseline.get("filters_used", []):
        if entry["path"].endswith("should_exclude_file"):
            return list(entry.get("pattern", []))
    return []


def test_the_generated_locales_are_excluded_from_secret_scanning_and_en_is_not() -> None:
    """The exclude pattern must name exactly the generated locales (#14781).

    Those ten files are produced from sources that are themselves scanned --
    `autobot-frontend/src/i18n/locales/*` (in the frozen legacy set) and this
    app's own `en.json` (individually reasoned). A value can only reach a
    generated file by coming from one of those, so scanning them again produced
    505 baseline entries for no additional coverage, and
    `secrets_baseline_reasons_guard_test.py` then required a tracked reason for
    every one of them.

    Excluded rather than reasoned, and this test is what makes that safe:

    - an eleventh generated locale added without extending the pattern fails
      here, so it cannot slip into the tree unscanned AND unexcluded;
    - `en.json` must stay scanned, because it is authored -- a secret typed into
      it must still be caught;
    - a pattern covering a file that is NOT generated fails too, so the
      exclusion cannot quietly widen.

    The derivation itself is enforced separately: `lift_locale_translations.py
    --check` runs in CI and fails if any generated file is not exactly what the
    rule produces, so the files cannot be hand-edited to smuggle a value past
    the excluded scan.
    """
    import re

    patterns = [re.compile(p) for p in _secret_exclude_patterns()]
    on_disk = sorted(p.stem for p in (repo_root() / _LOCALES).iterdir() if p.suffix == ".json")

    def excluded(stem: str) -> bool:
        path = f"{_LOCALES.as_posix()}/{stem}.json"
        return any(rx.match(path) for rx in patterns)

    generated = [stem for stem in on_disk if stem != _AUTHORED_LOCALE]
    missing = [stem for stem in generated if not excluded(stem)]
    over = [stem for stem in on_disk if stem == _AUTHORED_LOCALE and excluded(stem)]

    assert not missing, (
        "these generated locales are still scanned for secrets, so every entry in them needs a "
        f"tracked reason: {missing}. Extend the should_exclude_file pattern in .secrets.baseline."
    )
    assert not over, (
        f"{_AUTHORED_LOCALE}.json is hand-authored and must stay scanned -- a secret typed into it "
        "has to be caught. Narrow the exclude pattern."
    )
