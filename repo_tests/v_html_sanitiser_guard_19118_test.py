# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every HTML sink goes through the kit sanitiser or is listed (#19118).

#2847 fixed stored XSS in chat and terminal with DOMPurify; KnowledgeEntries
was missed and regressed the class. The check is per binding, not per file:
each ``v-html`` binding (``.vue``) and each ``innerHTML`` / ``outerHTML`` /
``insertAdjacentHTML`` assignment (``.vue`` or ``.ts``, the kit included) must
wrap a kit sanitiser call, directly or through the function / ref it names.
Anything else is in ``UNSANITISED_ALLOWLIST`` with a reason. The allowlist is
shrink-only: an entry whose sinks are now all sanitised, or whose count differs
from the recorded one, fails -- delete or lower it, never raise it.

``dompurify`` is NOT a sanitiser import here: only the kit may import it.
"""

from __future__ import annotations

import re
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare

REPO = repo_root()
ROOTS = ("autobot-frontend/src", "autobot-slm-frontend/src", "libs/autobot-ui/src", "libs/autobot-ui/index.ts")

# file -> (unsanitised sink count, reason). Shrink-only.
UNSANITISED_ALLOWLIST: dict[str, tuple[int, str]] = {
    "autobot-frontend/src/views/llc/WorkItemDetail.vue": (
        2,
        "renderMarkdown escapes & < > before adding its own tags",
    ),
    "autobot-frontend/src/components/knowledge/KBSearchResultPanel.vue": (
        2,
        "applyHighlight/highlightedContent escape & < > before wrapping <mark>",
    ),
    "autobot-frontend/src/components/canvas/CanvasCell.vue": (
        3,
        "formatMarkdown escapes & < > before adding its own tags",
    ),
    "autobot-frontend/src/components/knowledge/SystemKnowledgeManager.vue": (
        6,
        "static i18n strings with <strong>/<code>; no interpolated params",
    ),
    "autobot-frontend/src/components/analytics/CodeGenerationDashboard.vue": (
        1,
        "formatDiff escapes every line with escapeHtml before adding its own <span> tags",
    ),
    "autobot-frontend/src/components/terminal/TerminalOutput.vue": (
        1,
        "formatTerminalLine strips ANSI then escapeHtml; no markup is added",
    ),
    "autobot-frontend/src/components/terminal/TerminalWindow.vue": (
        1,
        "formatTerminalLine strips ANSI then escapeHtml; no markup is added (the prompt binding is sanitised)",
    ),
    "autobot-frontend/src/utils/cacheManagement.ts": (
        4,
        "static toast templates (svg/style/onclick, which a sanitiser would strip); values go through escapeHtml",
    ),
    "autobot-frontend/src/utils/asyncComponentHelpers.ts": (
        1,
        "static toast template (svg/style, which a sanitiser would strip); values go through escapeHtml",
    ),
}

# Both Vue attribute quote styles; group 2 is the bound expression.
_VHTML = re.compile(r"""(?<![\w-])v-html\s*=\s*(["'])(.*?)\1""")
_DOM_SINK = re.compile(r"""\.(?:innerHTML|outerHTML)\s*=(?!=)\s*([^\n]*)|\binsertAdjacentHTML\s*\([^,]*,\s*([^\n]*)""")
# The canonical module is libs/autobot-ui/src/utils/sanitize.ts, reached through the
# kit (`@autobot/ui`) or the autobot-frontend re-export (`@/utils/sanitize`).
CANONICAL = "libs/autobot-ui/src/utils/sanitize.ts"
_SANITISER = re.compile(
    r"""from\s+['"]@/utils/sanitize['"]"""
    # The name must sit inside the braces of the import that names @autobot/ui -- `[^}]` cannot
    # cross into a neighbouring import, so `import { sanitizeHtml } from './x'` is never credited.
    r"""|\bimport\s*(?:type\s+)?\{[^}]*\bsanitize(?:Html|ChatHtml|KnowledgeHtml)\b[^}]*\}\s*from\s+['"]@autobot/ui['"]""",
)
_CALL = re.compile(r"\bsanitize(?:Html|ChatHtml|KnowledgeHtml)\s*\(")
_COMMENT_LINE = re.compile(r"^\s*(<!--|//|\*|/\*)")
_TOP_LEVEL = re.compile(r"^[A-Za-z]")
_IDENT = re.compile(r"^\s*!?\s*([A-Za-z_$][\w$]*)")
_LITERAL_RHS = re.compile(r"""^\s*(?:['"`]|\d|null\b|true\b|false\b|undefined\b|\[\s*\]|ref\b)""")


def _discover(repo: Path) -> list[Path]:
    """Every non-test ``.vue`` / ``.ts`` under ``ROOTS``; empty on an empty tree, never a raise."""
    found: set[Path] = set()
    for root in ROOTS:
        base = repo / root
        paths = [base] if base.is_file() else [*base.rglob("*.vue"), *base.rglob("*.ts")]
        for p in paths:
            rel = p.relative_to(repo).as_posix()
            if re.search(r"\.(test|spec)\.ts$|/__tests__/|/test/|\.d\.ts$", rel):
                continue
            found.add(p)
    return sorted(found)


#: Train 84 (#19118): pinned mid-window on the population this sweep discovers, so an empty or
#: truncated enumeration fails rather than reporting the same green as a clean tree.
REACH = declare(
    "v-html-sanitiser-sinks",
    discover=_discover,
    floor=1369,  # mid-window [1221, 1371] on a population of 1371
    growth=150,
    skips=0,
    what="non-test .vue/.ts source files",
    roots=ROOTS,
)


def _source_files() -> list[Path]:
    files = REACH.examined(REPO)
    REACH.completed(files)
    return list(files)


def _live_lines(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if not _COMMENT_LINE.match(ln)]


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _definitions(name: str, lines: list[str]) -> list[str]:
    """Each declaration/assignment of ``name``, as the text up to the next statement at or above its indent."""
    decl = re.compile(
        rf"(?:\bfunction\s+{re.escape(name)}\b|\b(?:const|let|var)\s+{re.escape(name)}\b|(?<![\w.]){re.escape(name)}(?:\.value)?\s*=(?!=))"
    )
    spans = []
    for i, line in enumerate(lines):
        if not decl.search(line):
            continue
        j = i + 1
        while j < len(lines) and (
            not lines[j].strip() or _indent(lines[j]) > _indent(line) or lines[j].lstrip()[0] in "})].,"
        ):
            j += 1
        spans.append("\n".join(lines[i:j]))
    return spans


def _call_end(s: str, open_at: int) -> int:
    """Index of the ``)`` closing the ``(`` at ``open_at``, skipping string literals; -1 if unclosed."""
    depth, quote, i = 0, "", open_at
    while i < len(s):
        c = s[i]
        if quote:
            i += 1 if c == "\\" else 0
            quote = "" if c == quote else quote
        elif c in "'\"`":
            quote = c
        elif c in "()":
            depth += 1 if c == "(" else -1
            if depth == 0:
                return i
        i += 1
    return -1


def _wholly_sanitised(value: str) -> bool:
    """``value`` is ONE kit-sanitiser call and nothing else on its line (a ``;`` aside), so
    ``raw + sanitizeHtml('')`` or ``sanitizeHtml(a) + raw`` is not credited."""
    s = value.strip()
    m = _CALL.match(s)
    end = _call_end(s, m.end() - 1) if m else -1
    return end >= 0 and s[end + 1 :].split("\n", 1)[0].strip() in ("", ";")


def _binding_ok(expr: str, lines: list[str], depth: int = 2) -> bool:
    if _wholly_sanitised(expr):
        return True
    m = _IDENT.match(expr)
    if not m:
        return False
    spans = _definitions(m.group(1), lines)
    if not any(_CALL.search(s) or _calls_sanitised_helper(s, m.group(1), lines, depth) for s in spans):
        return False
    # every non-literal assignment of the name must itself be sanitised
    for s in spans:
        first = s.splitlines()[0]
        rhs = re.search(r"(?<![=!<>])=(?!=)(?!>)\s*(.*)$", first)
        if rhs and not _CALL.search(s) and not _LITERAL_RHS.match(rhs.group(1)) and "=>" not in first:
            if not _calls_sanitised_helper(s, m.group(1), lines, depth):
                return False
    return True


def _calls_sanitised_helper(span: str, self_name: str, lines: list[str], depth: int) -> bool:
    """The span calls another local function that itself wraps a kit sanitiser (bounded depth)."""
    if depth <= 0:
        return False
    callees = {c for c in re.findall(r"\b([A-Za-z_$][\w$]*)\s*\(", span) if c != self_name}
    return any(
        any(_CALL.search(d) or _calls_sanitised_helper(d, c, lines, depth - 1) for d in _definitions(c, lines))
        for c in callees
    )


def _unsanitised(path: Path) -> int:
    text = path.read_text(encoding="utf-8")
    lines = _live_lines(text)
    imported = bool(_SANITISER.search(text)) or path.relative_to(REPO).as_posix() == CANONICAL
    bad = 0
    for i, line in enumerate(lines):
        for m in _VHTML.finditer(line):
            bad += 0 if imported and _binding_ok(m.group(2), lines) else 1
        for m in _DOM_SINK.finditer(line):
            rhs = m.group(1) if m.group(1) is not None else m.group(2)
            # the call may close on a later line; the value is checked to its own end
            bad += 0 if imported and _wholly_sanitised("\n".join([rhs, *lines[i + 1 :]])) else 1
    return bad


def _rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def test_every_html_sink_is_sanitised_or_allowlisted() -> None:
    offenders = []
    for path in _source_files():
        n = _unsanitised(path)
        if n and _rel(path) not in UNSANITISED_ALLOWLIST:
            offenders.append(f"{_rel(path)}: {n} sink(s) not wrapping a kit sanitiser call")
    assert not offenders, "route each sink through the kit sanitiser or allowlist with a reason:\n" + "\n".join(
        offenders
    )


def test_allowlist_is_shrink_only() -> None:
    stale = []
    for rel, (count, reason) in UNSANITISED_ALLOWLIST.items():
        path = REPO / rel
        assert reason.strip(), f"{rel}: allowlist entry needs a reason"
        if not path.exists():
            stale.append(f"{rel}: file gone, drop the entry")
            continue
        actual = _unsanitised(path)
        if actual == 0:
            stale.append(f"{rel}: every sink is sanitised now, drop the entry")
        elif actual != count:
            stale.append(f"{rel}: {actual} unsanitised sink(s) vs {count} recorded -- never raise, lower on shrink")
    assert not stale, "\n".join(stale)


def test_there_is_exactly_one_sanitiser_implementation() -> None:
    """One class, one implementation: the kit owns it, apps only re-export."""
    assert (REPO / CANONICAL).is_file()
    assert "DOMPurify.sanitize" in (REPO / CANONICAL).read_text(encoding="utf-8")
    assert not (REPO / "autobot-slm-frontend/src/utils/sanitize.ts").exists()
    shim = (REPO / "autobot-frontend/src/utils/sanitize.ts").read_text(encoding="utf-8")
    assert "DOMPurify.sanitize" not in shim and "@autobot/ui" in shim


def test_only_the_kit_imports_dompurify() -> None:
    importers = [
        _rel(p)
        for root in ("autobot-frontend/src", "autobot-slm-frontend/src", "libs/autobot-ui/src")
        for p in [*(REPO / root).rglob("*.vue"), *(REPO / root).rglob("*.ts")]
        if not re.search(r"\.(test|spec)\.ts$|/__tests__/", _rel(p))
        and re.search(
            r"""from\s+['"]dompurify['"]|import\(\s*['"]dompurify['"]|require\(\s*['"]dompurify['"]""",
            p.read_text(encoding="utf-8"),
        )
    ]
    assert importers == [CANONICAL], importers


def test_kit_sanitiser_takes_named_presets_only() -> None:
    """No exported way to pass a loosening DOMPurify config from a call site."""
    text = (REPO / CANONICAL).read_text(encoding="utf-8")
    assert (
        "config?:" not in text and "DOMPurifyConfig," not in text.split("export function sanitizeHtml")[1].split("{")[0]
    )
    assert "export function sanitizeHtml(html: string, preset: SanitizePreset" in text


def test_guard_detects_an_unsanitised_binding() -> None:
    """Control: the detector must see a bare binding and accept a sanitised one."""
    assert _VHTML.search('<div v-html="x"></div>')
    assert not _VHTML.search('<div :data-v-html="x"></div>')
    assert _SANITISER.search("import { sanitizeHtml } from '@/utils/sanitize'")
    assert not _SANITISER.search("import { escapeHtml } from '@/utils/format'")
    assert _SANITISER.search("import { BaseModal, sanitizeHtml } from '@autobot/ui'")
    assert not _SANITISER.search("import { BaseModal } from '@autobot/ui'\nconst a = 1; // sanitizeHtml")
    # A direct dompurify import is a second sanitiser, not an accepted one.
    assert not _SANITISER.search("import DOMPurify from 'dompurify'")
    assert not _SANITISER.search("const d = await import('dompurify')")


def test_guard_is_per_binding() -> None:
    """Control: one sanitised binding in a file must not excuse another."""
    lines = _live_lines(
        "const a = computed(() => sanitizeHtml(x))\nconst b = computed(() => x + '<i>')\nconst c = ref('')\nc.value = y"
    )
    assert _binding_ok("a", lines)
    assert not _binding_ok("b", lines)
    assert not _binding_ok("c", lines)
    assert _binding_ok("sanitizeChatHtml(z)", lines)
    assert not _binding_ok("renderMarkdown(z)", lines)
    assert _DOM_SINK.search("el.innerHTML = sanitizeHtml(x)") and _DOM_SINK.search(
        "el.insertAdjacentHTML('beforeend', x)"
    )


def test_contrast_single_quotes_import_binding_and_whole_value() -> None:
    """CodeRabbit on #19388: each near miss the detector once accepted, beside the case it must accept."""
    # single-quoted bindings are sinks too
    assert _VHTML.search("<div v-html='untrustedHtml'></div>").group(2) == "untrustedHtml"
    assert _VHTML.search("""<div v-html='sanitizeHtml(x, "plain")'></div>""").group(2) == 'sanitizeHtml(x, "plain")'
    # the sanitiser name must come from the import that names the kit
    assert not _SANITISER.search("import { sanitizeHtml } from './unsafe'\nimport { BaseModal } from '@autobot/ui'\n")
    assert _SANITISER.search("import {\n  BaseModal,\n  sanitizeHtml,\n} from '@autobot/ui'\n")
    # the whole sink value is the sanitiser call, not just a part of it
    lines = _live_lines("const a = 1")
    assert not _binding_ok("untrustedHtml + sanitizeHtml('')", lines)
    assert not _binding_ok("sanitizeHtml(a) + untrustedHtml", lines)
    assert _binding_ok("sanitizeHtml(a + ')', 'plain')", lines)
    assert not _wholly_sanitised("sanitizeHtml(a) + raw;")
    assert _wholly_sanitised("sanitizeHtml(\n  a,\n  'plain'\n);\nnext()")
