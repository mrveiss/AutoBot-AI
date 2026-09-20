# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A locale string must not contain an HTML entity (#17152).

Every consumer renders a locale value through `{{ $t(...) }}` text interpolation, which escapes
its output -- so a value that stores `&mdash;` as text displays the literal characters `&mdash;`,
not an em dash. #17152 found 11 such values across 9 keys in the SLM frontend's `en.json`, put
there by an i18n extraction pass that lifted inline HTML markup without decoding it first. Fixing
today's values does not stop the next extraction doing it again -- this guard does.
"""

from __future__ import annotations

import json
import re

from repo_tests._paths import repo_root

_ROOT = repo_root()

#: Both locale trees in the repo: the SLM dashboard (one file today) and the main frontend
#: (11 locale files). Globbed rather than hand-listed, so a new locale file is covered on sight.
_LOCALE_GLOBS = (
    "autobot-slm-frontend/src/locales/*.json",
    "autobot-frontend/src/i18n/locales/*.json",
)

#: Matches a named HTML entity (`&mdash;`, `&amp;`, `&nbsp;`, ...). Deliberately not numeric
#: entities (`&#8212;`) -- none of the 11 real occurrences used that form, and a locale value
#: legitimately discussing markup syntax in prose (a docs string) is far more likely to write
#: one than a translator is to accidentally introduce a named entity via extraction.
_ENTITY_RE = re.compile(r"&[a-zA-Z]+;")


def _locale_files() -> list:
    files = []
    for pattern in _LOCALE_GLOBS:
        files.extend(sorted(_ROOT.glob(pattern)))
    return files


def _entity_leaks() -> list:
    """(file, key path, entity) for every locale value containing an HTML entity."""
    leaks = []
    for path in _locale_files():
        data = json.loads(path.read_text(encoding="utf-8"))
        stack = [((), data)]
        while stack:
            key_path, node = stack.pop()
            if isinstance(node, dict):
                for k, v in node.items():
                    stack.append((key_path + (k,), v))
            elif isinstance(node, str):
                match = _ENTITY_RE.search(node)
                if match:
                    leaks.append((str(path.relative_to(_ROOT)), ".".join(key_path), match.group(0)))
    return leaks


def test_the_sweep_reached_the_locale_files() -> None:
    """Positive assertion first -- an empty glob reports every tree clean."""
    files = _locale_files()
    assert len(files) >= 2, (
        f"found only {len(files)} locale file(s) across {_LOCALE_GLOBS} -- "
        "the glob is broken, so a clean result below asserts nothing"
    )


def test_no_locale_value_contains_an_html_entity() -> None:
    leaks = _entity_leaks()
    assert not leaks, "these locale values store an HTML entity as text, which `{{ $t(...) }}` "
    "renders literally instead of decoding:\n" + "\n".join(
        f"  {f} [{k}] contains {e}" for f, k, e in leaks
    )


def test_the_scan_catches_a_reintroduced_entity(tmp_path, monkeypatch) -> None:
    """Negative control: mutate a real, currently-clean value back to an entity and confirm the
    scan reports it. Without this, a scan that silently matches nothing (a broken glob, a typo'd
    regex) would pass `test_no_locale_value_contains_an_html_entity` by reading no data at all.
    """
    real_path = sorted(_ROOT.glob(_LOCALE_GLOBS[0]))[0]
    data = json.loads(real_path.read_text(encoding="utf-8"))
    data["orchestrationView"]["mdash"] = "&mdash;"

    mutated_dir = tmp_path / "autobot-slm-frontend" / "src" / "locales"
    mutated_dir.mkdir(parents=True)
    (mutated_dir / real_path.name).write_text(json.dumps(data), encoding="utf-8")

    monkeypatch.setattr("repo_tests.locale_html_entity_leak_test._ROOT", tmp_path)
    monkeypatch.setattr(
        "repo_tests.locale_html_entity_leak_test._LOCALE_GLOBS",
        ("autobot-slm-frontend/src/locales/*.json",),
    )

    leaks = _entity_leaks()
    assert any(k == "orchestrationView.mdash" and e == "&mdash;" for _, k, e in leaks), (
        "reintroducing &mdash; into a real key was not caught -- the scan itself is broken"
    )
