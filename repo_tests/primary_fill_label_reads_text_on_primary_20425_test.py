# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A label on a ``--color-primary`` fill reads ``--text-on-primary``, never a literal white (#20425).

**The defect.** The primary is white in High Contrast Dark and pale in Dark. A rule that paints
``background: var(--color-primary)`` and sets ``color: white`` (or ``#fff``, ``rgb(255,255,255)``)
renders an invisible label there. ``--text-on-primary`` is the token every theme flips with the fill.

**The boundary.** One rule block (innermost ``{...}``, nested at-rules read) in a ``.vue`` ``<style>``
or a ``.css`` file under ``autobot-frontend/src``, plus ``style="..."`` attributes in ``.vue`` files.
A rule counts when a ``background``, ``background-color`` or ``background-image`` value names
``var(--color-primary*)`` (hover, active, dark and light included, gradients included) AND the same
rule sets ``color`` to a literal white. Not counted: a fill that is another token (``--color-info-solid``,
``--color-blue-600``, ``--color-accent``, ``--color-electric-600``), and a white written through a token
(``--faildash-on-accent`` and the other per-view on-accent tokens sit on those other fills). The
other frontend and the kit are out of scope here.

**The pin.** Rules in files held by open pull requests (#20388, #20405, #20401) when this landed, so
they could not be edited here. Pinned per file and selector, down-only (a pin below the live count is
stale and fails). Delete an entry when its file is converted.
"""

from __future__ import annotations

import re
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare

_FRONTEND_SRC = "autobot-frontend/src"
_STYLE = re.compile(r"<style[^>]*>(.*?)</style>", re.S)
_INLINE_STYLE = re.compile(r'style="([^"]*)"')
_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")
_DECL = re.compile(r"(?<![-\w])([a-z-]+)\s*:\s*([^;]+)", re.I)
_FILL_PROPS = frozenset({"background", "background-color", "background-image"})
_PRIMARY = re.compile(r"var\(\s*--color-primary(?:-[a-z0-9-]+)?\s*[,)]")
_WHITE = re.compile(
    r"^(?:white|#fff(?:fff)?|rgba?\(\s*255\s*,\s*255\s*,\s*255\s*(?:,\s*1(?:\.0+)?\s*)?\))\s*(?:!important)?$",
    re.I,
)

# Rules in files still held by an open PR. Delete an entry when its file is converted.
PINS = {
    "components/browser/InteractiveScreenshot.vue :: .type-submit": 1,
    "components/chat/ChatInput.vue :: .image-gen-submit": 1,
    "components/chat/MCPPromptTemplatePicker.vue :: .btn-apply": 1,
    "components/plugins/CapabilityApprovalDialog.vue :: .btn-primary": 1,
    "components/profile/DeviceManagementPanel.vue :: .btn-primary": 1,
    "components/workflow/WorkflowRunner.vue :: .step-icon.executing": 1,
    "views/llc/ApprovalsInbox.vue :: .tab-btn.active": 1,
    "views/llc/BacklogView.vue :: .btn-primary": 1,
    "views/llc/HeartbeatMonitor.vue :: .btn-trigger": 1,
    "views/llc/WorkItemDetail.vue :: .action-done, .action-ready": 1,
    "views/llc/WorkItemDetail.vue :: .btn-primary": 1,
}


def frontend_files(root: Path) -> list[Path]:
    return sorted([*root.rglob("*.vue"), *root.rglob("*.css")])


REACH_FILES = declare(
    "primary-fill-white-label-files",
    discover=lambda root: [p.relative_to(root).as_posix() for p in frontend_files(root / _FRONTEND_SRC)],
    roots=(_FRONTEND_SRC,),
    floor=480,  # population 505 when measured
    growth=40,
    skips=0,
    what=".vue and .css files scanned for a literal white label on a --color-primary fill",
)


def _decls(body: str) -> dict[str, str]:
    return {m.group(1).lower(): m.group(2).strip() for m in _DECL.finditer(body)}


def _is_hit(decls: dict[str, str]) -> bool:
    filled = any(k in _FILL_PROPS and _PRIMARY.search(v) for k, v in decls.items())
    return filled and bool(_WHITE.match(decls.get("color", "")))


def white_labels_on_primary(root: Path) -> dict[str, int]:
    """``{"<file> :: <selector>": occurrences}`` for every literal-white label on a primary fill."""
    found: dict[str, int] = {}

    def add(path: Path, selector: str) -> None:
        key = f"{path.relative_to(root).as_posix()} :: {' '.join(selector.split())}"
        found[key] = found.get(key, 0) + 1

    for path in frontend_files(root):
        source = path.read_text(encoding="utf-8")
        is_vue = path.suffix == ".vue"
        for css in _STYLE.findall(source) if is_vue else [source]:
            for selector, body in _RULE.findall(_COMMENT.sub("", css)):
                if _is_hit(_decls(body)):
                    add(path, selector)
        if is_vue:
            template = _STYLE.sub("", source)
            for attr in _INLINE_STYLE.findall(template):
                if _is_hit(_decls(attr)):
                    add(path, "inline style")
    return found


class TestTheDetectorWorksBeforeItsOutputIsRead:
    def _w(self, root: Path, rel: str, body: str) -> None:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")

    def test_control_a_white_label_on_the_primary_fires(self, tmp_path: Path) -> None:
        self._w(
            tmp_path,
            "A.vue",
            "<template><b/></template>\n<style>\n.a { background: var(--color-primary); color: white; }\n</style>\n",
        )
        assert white_labels_on_primary(tmp_path) == {"A.vue :: .a": 1}

    def test_color_before_background_and_other_white_forms_fire(self, tmp_path: Path) -> None:
        self._w(
            tmp_path,
            "b.css",
            ".a { color: #FFF; background-color: var(--color-primary-hover); }\n"
            ".b { color: rgb(255, 255, 255); background-image: linear-gradient(var(--color-primary), red); }\n"
            "@media (min-width: 1px) { .c { background: var(--color-primary, #36f); color: #ffffff !important; } }\n",
        )
        assert white_labels_on_primary(tmp_path) == {"b.css :: .a": 1, "b.css :: .b": 1, "b.css :: .c": 1}

    def test_an_inline_style_fires(self, tmp_path: Path) -> None:
        self._w(
            tmp_path,
            "C.vue",
            '<template><b style="background: var(--color-primary); color: #fff" /></template>\n',
        )
        assert white_labels_on_primary(tmp_path) == {"C.vue :: inline style": 1}

    def test_the_token_other_fills_and_comments_do_not_fire(self, tmp_path: Path) -> None:
        self._w(
            tmp_path,
            "D.vue",
            "<template><b/></template>\n<style>\n"
            ".a { background: var(--color-primary); color: var(--text-on-primary); }\n"
            ".b { background: var(--color-info-solid); color: white; }\n"
            ".c { background: var(--color-primary); }\n.d { color: white; }\n"
            ".e { background: var(--color-primary); color: var(--faildash-on-accent); }\n"
            "/* .f { background: var(--color-primary); color: white; } */\n"
            ".g { border-color: var(--color-primary); color: white; }\n</style>\n",
        )
        assert white_labels_on_primary(tmp_path) == {}

    def test_a_neighbouring_rule_is_not_read_as_the_same_rule(self, tmp_path: Path) -> None:
        self._w(
            tmp_path,
            "e.css",
            ".a { background: var(--color-primary); }\n.b { color: white; }\n",
        )
        assert white_labels_on_primary(tmp_path) == {}


def test_no_primary_fill_carries_a_literal_white_label_beyond_the_pinned_ones() -> None:
    root = repo_root() / _FRONTEND_SRC
    assert root.is_dir(), f"{_FRONTEND_SRC} has moved; this guard reads it by path"
    REACH_FILES.examined(repo_root())
    now = white_labels_on_primary(root)
    new = {k: v for k, v in now.items() if v > PINS.get(k, 0)}
    assert not new, (
        f"a literal white label sits on a --color-primary fill (#20425): {new}. "
        "The primary is white in High Contrast Dark and pale in Dark: use color: var(--text-on-primary)."
    )
    stale = {k: v for k, v in PINS.items() if now.get(k, 0) < v}
    assert not stale, f"pinned primary-fill rules are fixed or gone: {stale}; delete them from PINS (#20425)."
