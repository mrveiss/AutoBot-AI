# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The SLM speaks the shared token vocabulary, and a state never repeats its base (#17566).

Three guards over ``autobot-slm-frontend``, each reading every source kind that can declare or use a token:

1. No custom property exists only in the SLM unless ``DESIGN_SYSTEM.md`` documents it. The names the SLM
   declares, minus the names declared in the *shared token files*, must equal the documented set.
2. Every ``var(--x)`` in SLM source resolves to a declared name (SLM or shared).
3. No class list gives a state variant (``hover:`` / ``focus:`` / ``active:`` / ``enabled:hover:``) the same
   utility as its base, literally or after following the alias chain to the same value.

Scope (also written in ``DESIGN_SYSTEM.md``): the SLM side reads ``*.css``, the ``<style>`` blocks and inline
``style`` values of ``*.vue``, ``index.html``, and ``setProperty('--x')`` / ``{'--x': v}`` in ``*.ts`` and
``*.vue``. The shared side is only ``design-tokens.css``, ``tailwind.css`` and ``themes/*.css`` of the user
frontend plus the kit's ``tokens/contract.css`` and ``tokens/adapter.css``: a name declared in some other
component of the user frontend is not shared. Population floors fail when a source kind reads nothing.
"""

from __future__ import annotations

import re

from repo_tests._paths import repo_root

_ROOT = repo_root()
_DOC = _ROOT / "docs" / "developer" / "DESIGN_SYSTEM.md"
_SLM = _ROOT / "autobot-slm-frontend"
_SLM_SRC = _SLM / "src"
_SLM_STYLES = _SLM_SRC / "assets" / "styles"
_USER_CSS = _ROOT / "autobot-frontend" / "src" / "assets"
_KIT_TOKENS = _ROOT / "libs" / "autobot-ui" / "src" / "tokens"
_SECTION = "## SLM token vocabulary (#17566)"
_ONLY = "**What is still SLM-only, on purpose**"

# `--x:` at the start of a line or straight after `;` / `{`, so `a{--x:1;--y:2}` yields both (a bare
# `^\s*` read only the first declaration of a line).
_DECLARATION = re.compile(r"(?:^|[;{])\s*(--[\w-]+)\s*:", re.MULTILINE)
_SET_PROPERTY = re.compile(r"""setProperty\(\s*['"](--[\w-]+)['"]""")
_OBJECT_KEY = re.compile(r"""['"](--[\w-]+)['"]\s*:""")
_STYLE_BLOCK = re.compile(r"<style\b[^>]*>(.*?)</style>", re.DOTALL)
_STYLE_ATTR = re.compile(r"""\bstyle\s*=\s*"([^"]*)"|\bstyle\s*=\s*'([^']*)'""")
_VAR_USE = re.compile(r"var\(\s*(--[\w-]+)")


def _read(path) -> str:
    return path.read_text(encoding="utf-8")


def _slm_files(*suffixes: str) -> list:
    return sorted(p for p in _SLM_SRC.rglob("*") if p.suffix in suffixes and "node_modules" not in p.parts)


def _names_in(kind: str, text: str) -> set[str]:
    """The custom properties ``text`` (a file of ``kind``) declares. ``kind`` is the suffix, without the dot."""
    if kind == "css":
        return set(_DECLARATION.findall(text))
    names: set[str] = set()
    for block in _STYLE_BLOCK.findall(text):
        names.update(_DECLARATION.findall(block))
    for attr in _STYLE_ATTR.findall(text):
        names.update(_DECLARATION.findall("".join(attr)))
    names.update(_SET_PROPERTY.findall(text))
    if kind in ("ts", "vue"):
        names.update(_OBJECT_KEY.findall(text))
    return names


def _slm_declarations() -> dict[str, set[str]]:
    """Source kind -> the names declared in it, across all of the SLM's source."""
    found: dict[str, set[str]] = {"css": set(), "vue": set(), "ts": set(), "html": set()}
    for suffix, kind in ((".css", "css"), (".vue", "vue"), (".ts", "ts")):
        for path in _slm_files(suffix):
            found[kind].update(_names_in(kind, _read(path)))
    found["html"].update(_names_in("html", _read(_SLM / "index.html")))
    return found


def _shared_files() -> list:
    files = [_USER_CSS / "css" / "design-tokens.css", _USER_CSS / "tailwind.css"]
    files += sorted(p for p in (_USER_CSS / "css" / "themes").iterdir() if p.suffix == ".css")
    files += [_KIT_TOKENS / "contract.css", _KIT_TOKENS / "adapter.css"]
    return files


def _shared() -> set[str]:
    return {name for path in _shared_files() for name in _names_in("css", _read(path))}


def _slm_declared() -> set[str]:
    return set().union(*_slm_declarations().values())


def _slm_only() -> set[str]:
    return _slm_declared() - _shared()


def _documented() -> set[str]:
    """Backticked `--name` tokens in the table that follows the SLM-only marker, to the next heading."""
    text = _read(_DOC)
    body = text[text.index(_SECTION) :]
    body = body[body.index(_ONLY) :]
    table = body.split("\n## ", 1)[0]
    rows = [ln for ln in table.splitlines() if ln.startswith("| `")]
    return {name for ln in rows for name in re.findall(r"`(--[\w-]+)`", ln.split("|")[1])}


def test_every_extractor_reads_its_source_kind() -> None:
    """Each source kind has a reader, proven on a planted sample (an empty read is not a clean read)."""
    assert _names_in("css", "a{--p1:1;--p2:2}\n.b {\n  --p3: 3;\n}") == {"--p1", "--p2", "--p3"}
    assert _names_in("vue", "<template><i/></template><style scoped>\n.x { --v1: 1; }\n</style>") == {"--v1"}
    assert _names_in("vue", '<div style="--v2: 3px; color: red"></div>') == {"--v2"}
    assert _names_in("ts", "el.style.setProperty('--t1', 'x'); const o = { '--t2': 1 }") == {"--t1", "--t2"}
    assert _names_in("html", '<style>:root{--h1:1}</style><p style="--h2:2">') == {"--h1", "--h2"}


def test_the_population_is_measured() -> None:
    """A derivation that finds nothing would pass the other tests for the wrong reason."""
    found = _slm_declarations()
    assert len(found["css"]) > 200, "the SLM stylesheets are not being read"
    assert found["vue"], "no <style>/inline-style declaration read from any .vue (LanguageSwitcher.vue declares some)"
    assert len(_slm_files(".vue")) > 50 and len(_slm_files(".ts")) > 20, "the SLM sources are not being walked"
    assert (_SLM / "index.html").is_file(), "index.html is not where the guard reads it"
    assert len(_shared()) > 400, "the shared token files are not being read"
    assert all(p.is_file() for p in _shared_files()), "a shared token file moved; update _shared_files"
    assert len(_documented()) >= 10


def test_every_slm_only_name_is_documented() -> None:
    undocumented = sorted(_slm_only() - _documented())
    assert not undocumented, (
        f"{undocumented} exist only in the SLM sources. Declare the shared name with the SLM's value "
        f"(see DESIGN_SYSTEM.md, '{_SECTION[3:]}'), or document the name there with the reason it has no "
        "user-frontend counterpart."
    )


def test_every_documented_name_still_exists_only_in_the_slm() -> None:
    stale = sorted(_documented() - _slm_only())
    assert not stale, f"{stale} are documented as SLM-only but are shared or gone; drop them from the table."


def _used_names() -> dict[str, set[str]]:
    """``var(--x)`` uses, name -> the files that use it, over every SLM source kind and index.html."""
    used: dict[str, set[str]] = {}
    paths = _slm_files(".css", ".vue", ".ts") + [_SLM / "index.html"]
    for path in paths:
        for name in _VAR_USE.findall(_read(path)):
            used.setdefault(name, set()).add(str(path.relative_to(_ROOT)))
    return used


def test_every_var_use_resolves_to_a_declared_name() -> None:
    declared = _slm_declared() | _shared()
    used = _used_names()
    assert len(used) > 100, "var() uses are not being read"
    dangling = {n: sorted(f)[:3] for n, f in sorted(used.items()) if n not in declared}
    assert not dangling, (
        f"var() uses with no declaration in the SLM or the shared token files: {dangling}. "
        "A var() of an undeclared name silently falls back; declare it or use the shared name."
    )


# ---- a state must not repeat its base -------------------------------------------------------------

_STATES = ("hover", "focus", "active", "focus-visible")
_UTILITY = re.compile(r"^(bg|text|border|ring)-(.+)$")
_TOKEN = re.compile(r"""[^\s'"`,\[\]{};?:]+(?::[^\s'"`,\[\]{};?:]+)*""")
_ALIAS = re.compile(r"^var\(\s*(--[\w-]+)\s*\)$")
_ARBITRARY = re.compile(r"^\((--[\w-]+)\)$")
# One element's opening tag, quote-aware: a `>` or an apostrophe inside a quoted attribute value never ends
# or shifts it, which a whole-file quote pairing cannot promise. An unquoted value never holds `=`, so a name
# and its value have exactly one split point (a value that could swallow `=` made the match ambiguous: CodeQL py/redos).
_TAG = re.compile(
    r"""<([a-zA-Z][\w.-]*)((?:\s+[^\s=>/"']+(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>"'=]+))?)*)\s*/?>""",
)
_ATTR = re.compile(r"""\s([:@\w.-]*class)\s*=\s*(?:"([^"]*)"|'([^']*)')""")
_JS_STRING = re.compile(r"""'([^'\n]*)'|`([^`]*)`|"([^"\n]*)\"""")
_APPLY = re.compile(r"@apply\s+([^;]*);")
_ATTR_NAIVE = re.compile(r"""[\s]:?class\s*=\s*["']""")


def _declaration_values() -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    for path in _slm_files(".css"):
        for name, value in re.findall(r"(?:^|[;{])\s*(--[\w-]+)\s*:\s*([^;}]+)", _read(path), re.MULTILINE):
            values.setdefault(name, []).append(value.strip())
    return values


def _leaf(name: str, values: dict[str, list[str]]) -> str:
    """Follow single-valued pure aliases (``--a: var(--b)``); a name declared per theme, or with a fallback, ends it."""
    seen: set[str] = set()
    while name not in seen and len(values.get(name, [])) == 1:
        seen.add(name)
        m = _ALIAS.match(values[name][0])
        if not m:
            break
        name = m.group(1)
    return name


def _resolve(utility_body: str, values: dict[str, list[str]]) -> str:
    """The value a utility's colour part stands for: the leaf custom property, else the literal text.

    ``bg-autobot-primary`` is Tailwind's ``--color-autobot-primary`` (the utility body already carries the
    ``autobot-`` namespace), and ``bg-(--x)`` names ``--x`` directly.
    """
    arb = _ARBITRARY.match(utility_body)
    var = arb.group(1) if arb else f"--color-{utility_body}"
    if arb or var in values:
        return _leaf(var, values)
    return utility_body


def _state_repeats(class_list: str, values: dict[str, list[str]]) -> list[str]:
    toks = _TOKEN.findall(class_list)
    base: dict[str, set[str]] = {}
    for t in toks:
        m = _UTILITY.match(t)
        if m:
            base.setdefault(m.group(1), set()).add(_resolve(m.group(2), values))
    repeats = []
    for t in toks:
        parts = t.split(":")
        if len(parts) < 2 or parts[-2] not in _STATES or any(p not in ("enabled", "disabled") for p in parts[:-2]):
            continue
        m = _UTILITY.match(parts[-1])
        if m and _resolve(m.group(2), values) in base.get(m.group(1), set()):
            repeats.append(t)
    return repeats


def _element_class_lists(text: str):
    """(line, joined class text) per element: ``class=`` and ``:class=`` strings of one tag are read together."""
    for tag in _TAG.finditer(text):
        parts = []
        for attr in _ATTR.finditer(" " + tag.group(2)):
            value = attr.group(2) if attr.group(2) is not None else attr.group(3)
            if attr.group(1).startswith(":"):
                parts += [next(g for g in m.groups() if g is not None) for m in _JS_STRING.finditer(value)]
            else:
                parts.append(value)
        if parts:
            yield text[: tag.start()].count("\n") + 1, " ".join(parts)


def _line_class_lists(text: str):
    """Quoted strings per line (script code, ``.ts``): a stray quote cannot shift pairing past its own line."""
    for number, line in enumerate(text.splitlines(), 1):
        for m in _JS_STRING.finditer(line):
            yield number, next(g for g in m.groups() if g is not None)
    for m in _APPLY.finditer(text):
        yield text[: m.start()].count("\n") + 1, m.group(1)


def _all_class_lists():
    for path in _slm_files(".css", ".vue", ".ts") + [_SLM / "index.html"]:
        text = _read(path)
        if path.suffix in (".vue", ".html"):
            for line, s in _element_class_lists(text):
                yield path, line, s
        for line, s in _line_class_lists(text):
            yield path, line, s


def _lost_class_attributes() -> list[str]:
    """Files whose tag scan read fewer ``class`` / ``:class`` attributes than the naive text count finds."""
    lost = []
    for path in _slm_files(".vue") + [_SLM / "index.html"]:
        text = _read(path)
        template = text.split("<script", 1)[0] if text.lstrip().startswith("<script") is False else text
        naive = len(_ATTR_NAIVE.findall(template))
        read = sum(len(_ATTR.findall(" " + t.group(2))) for t in _TAG.finditer(template))
        if read < naive:
            lost.append(f"{path.relative_to(_ROOT)}: read {read} of {naive}")
    return lost


def test_the_state_guard_sees_a_repeat_and_a_distinct_step() -> None:
    v = _declaration_values()
    assert _state_repeats("bg-autobot-primary hover:bg-autobot-primary", v) == ["hover:bg-autobot-primary"]
    assert _state_repeats("bg-autobot-primary enabled:hover:bg-autobot-primary", v)
    assert _state_repeats("text-autobot-text-link hover:text-autobot-text-link", v)
    # two names, one value (both resolve to --surface2): an alias pair is a repeat too
    assert _state_repeats("bg-autobot-bg-tertiary hover:bg-autobot-bg-hover", v) == ["hover:bg-autobot-bg-hover"]
    assert not _state_repeats("bg-autobot-primary hover:bg-autobot-primary-hover", v)
    assert not _state_repeats("bg-autobot-success enabled:hover:bg-autobot-success-hover", v)
    assert not _state_repeats("text-autobot-text-link hover:text-(--text-link-hover)", v)
    assert not _state_repeats("bg-autobot-bg-tertiary hover:bg-autobot-bg-active", v)
    assert len(v) > 200, "the declaration values are not being read"


def test_the_element_scan_survives_a_stray_apostrophe_and_reads_both_class_attributes() -> None:
    v = _declaration_values()
    sample = (
        "<p>it's here</p>\n"
        "<button class=\"px-2 bg-autobot-pill-bad-bg\" :class=\"[ok ? 'x' : 'hover:bg-autobot-pill-bad-bg']\">"
        "don't</button>\n"
    )
    hits = [(n, r) for n, s in _element_class_lists(sample) for r in _state_repeats(s, v)]
    assert hits == [(2, "hover:bg-autobot-pill-bad-bg")], hits


def test_no_class_attribute_is_lost_to_quote_mispairing() -> None:
    lost = _lost_class_attributes()
    assert not lost, f"the tag scan read fewer class attributes than the file holds: {lost[:10]}"


def test_no_state_variant_resolves_to_its_base() -> None:
    values = _declaration_values()
    found = []
    seen = 0
    for path, line, s in _all_class_lists():
        seen += 1
        found += [f"{path.relative_to(_SLM_SRC)}:{line} {t}" for t in _state_repeats(s, values)]
    assert seen > 1000, "class lists are not being read"
    assert not found, (
        f"{len(found)} class lists give a state the same utility as its base, so the state shows no change: "
        f"{found[:20]}. Use the -hover step of the base, or a hover tint token (--ok-bg-hover, --color-*-bg-hover)."
    )
