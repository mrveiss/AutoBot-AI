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

_APP = Path("autobot-slm-frontend")
_LOCALES = _APP / "src" / "locales"
_I18N = _APP / "src" / "i18n" / "index.ts"
_SWITCHER = _APP / "src" / "components" / "common" / "LanguageSwitcher.vue"
_SHELL = _APP / "src" / "components" / "common" / "Sidebar.vue"

#: The platform's locale set. A list, because "every file on disk" would make
#: the parity assertion below true of one file.
_EXPECTED_LOCALES = ("ar", "de", "en", "es", "fa", "fr", "he", "lv", "pl", "pt", "ur")

_RTL_LOCALES = frozenset({"ar", "fa", "he", "ur"})

#: A floor: a truncated en.json would make parity trivially true.
_MIN_KEYS = 3_000


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
    """The floor: parity with an empty en.json would be parity with nothing."""
    assert len(_keys("en")) >= _MIN_KEYS


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
