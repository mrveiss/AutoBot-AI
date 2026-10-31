# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A ``.icon`` rule in a component that renders ``Icon`` must size it with width/height (#19875).

**The defect.** ``Icon.vue`` renders ``<svg class="icon icon-md">`` and sizes it with the scoped
``.icon-xs..icon-xl`` classes (fixed ``width``/``height`` in rem). It has no ``font-size``
dependency, so the ``.icon { font-size: X }`` rules carried over from the ``<i class="fa">`` era
(#19491) changed nothing: a 48px placeholder icon rendered at 1.25rem.

**Why not one fix in Icon.** Making the svg ``1em`` would resize all 253 files that render
``Icon``, every one of which picks a size with the ``size`` prop; the font-size rules are the
exception, so each is retargeted to ``width``/``height`` at its own rule.

**The boundary.** The count is every rule, in a ``.vue`` file under ``autobot-frontend/src``
whose ``<template>`` renders ``<Icon``, whose selector names the bare ``.icon`` class and whose
declarations set ``font-size`` but neither ``width`` nor ``height``. A file that renders no
``Icon`` is out of scope (its ``.icon`` may be a text glyph that font-size does size). The user
app is the only app that has ``Icon``: ``autobot-slm-frontend/src`` renders none.

**The pin.** Rules in files held by open pull requests when this landed, so they could not be
edited here. Pinned per file and selector, down-only against the base (#19283).
"""

from __future__ import annotations

import re
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._ratchet_base import base_table, raised_entries
from repo_tests._reach import declare

_FRONTEND_SRC = "autobot-frontend/src"
_TEMPLATE = re.compile(r"<template>(.*)</template>", re.S)
_RENDERS_ICON = re.compile(r"<Icon[\s>/]")
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
_STYLE = re.compile(r"<style[^>]*>(.*?)</style>", re.S)
_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")
_ICON_CLASS = re.compile(r"(?<![\w-])\.icon(?![\w-])")
_FONT_SIZE = re.compile(r"(?<![\w-])font-size\s*:")
_BOX_SIZE = re.compile(r"(?<![\w-])(?:width|height)\s*:")

# Measured on the base this landed on: rules in files held by open PRs. Delete an entry when fixed.
PINS = {
    "components/audit/AuditTimeline.vue :: .loading-state .icon, .empty-state .icon": 1,
    "components/charts/FunctionCallGraph.vue :: .orphaned-empty .icon": 1,
    "components/chat/VoiceConversationOverlay.vue :: .voice-overlay__lang-badge .icon": 1,
    "components/chat/VoiceConversationPanel.vue :: .voice-panel__lang-badge .icon": 1,
    "components/knowledge/KnowledgeBatchToolbar.vue :: .toolbar-info .icon": 1,
    "components/knowledge/KnowledgeBrowser.vue :: .file-info > .icon": 1,
    "components/knowledge/KnowledgeBrowser.vue :: .loading-more .icon": 1,
    "components/knowledge/KnowledgeBrowser.vue :: .loading-state .icon, .error-state .icon, .placeholder-state .icon": 1,
    "components/knowledge/KnowledgeBrowser.vue :: .refresh-status-btn .icon": 1,
    "components/knowledge/KnowledgeBrowser.vue :: .toolbar-info .icon": 1,
    "components/knowledge/KnowledgeGraph.vue :: .relation-target .icon": 1,
    "components/knowledge/KnowledgeMainCategories.vue :: .populate-btn .icon": 1,
    "components/knowledge/KnowledgeUpload.vue :: .drop-icon-wrapper .icon": 1,
    "components/knowledge/KnowledgeUpload.vue :: .method-header .icon": 1,
    "components/knowledge/KnowledgeUpload.vue :: .suggested-category .icon": 1,
    "components/knowledge/KnowledgeVerificationQueue.vue :: .loading-state .icon": 1,
    "components/knowledge/panels/SourcePreviewPanel.vue :: .empty-state .icon": 1,
    "components/knowledge/temporal/EventTimeline.vue :: .loading-state .icon, .empty-state .icon": 1,
    "components/knowledge/temporal/EventTimeline.vue :: .timeline-dot .icon": 2,
    "components/profile/ProfileModal.vue :: .tab-btn .icon": 1,
    "components/ui/HostSelectionDialog.vue :: .default-badge .icon": 1,
    "components/ui/HostSelectionDialog.vue :: .loading-state .icon, .empty-state .icon": 1,
    "components/vision/ScreenCaptureViewer.vue :: .no-elements .icon": 1,
    "components/visualizations/ServiceMessageTimeline.vue :: .smt-route .icon": 1,
    "components/workflow/PhaseProgressionIndicator.vue :: .loading-spinner .icon": 1,
    "components/workflow/PhaseProgressionIndicator.vue :: .no-data-content .icon": 1,
    "components/workflow/WorkflowCanvas.vue :: .empty-state .icon": 1,
    "components/workflow/WorkflowHistory.vue :: .empty-state .icon": 1,
    "components/workflow/WorkflowRunner.vue :: .empty-list .icon": 1,
    "components/workflow/WorkflowRunner.vue :: .no-selection .icon": 1,
}

REACH_VUE_FILES = declare(
    "icon-font-size-rule-vue-files",
    discover=lambda root: [p.relative_to(root).as_posix() for p in vue_files(root / _FRONTEND_SRC)],
    roots=(_FRONTEND_SRC,),
    floor=444,  # population 464 when measured
    growth=40,
    skips=0,
    what=".vue files scanned for .icon rules that set font-size only",
)


def vue_files(root: Path) -> list[Path]:
    return sorted(root.rglob("*.vue"))


def font_size_only_icon_rules(root: Path) -> dict[str, int]:
    """``{"<file> :: <selector>": occurrences}`` for every ``.icon`` rule that sizes by font-size only."""
    found: dict[str, int] = {}
    for path in vue_files(root):
        source = path.read_text(encoding="utf-8")
        template = _TEMPLATE.search(source)
        if template is None or not _RENDERS_ICON.search(_HTML_COMMENT.sub("", template.group(1))):
            continue
        for css in _STYLE.findall(source):
            for selector, body in _RULE.findall(_COMMENT.sub("", css)):
                if _ICON_CLASS.search(selector) and _FONT_SIZE.search(body) and not _BOX_SIZE.search(body):
                    key = f"{path.relative_to(root).as_posix()} :: {' '.join(selector.split())}"
                    found[key] = found.get(key, 0) + 1
    return found


class TestTheDetectorWorksBeforeItsOutputIsRead:
    def _w(self, root: Path, rel: str, body: str) -> None:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")

    def test_control_a_font_size_only_icon_rule_fires(self, tmp_path: Path) -> None:
        self._w(
            tmp_path,
            "A.vue",
            "<template><Icon name='x' /></template>\n<style>\n.a .icon { font-size: 48px; color: red; }\n</style>\n",
        )
        assert font_size_only_icon_rules(tmp_path) == {"A.vue :: .a .icon": 1}

    def test_width_or_height_clears_it(self, tmp_path: Path) -> None:
        self._w(
            tmp_path,
            "B.vue",
            "<template><Icon name='x' /></template>\n<style>\n.a .icon { width: 48px; height: 48px; }\n"
            ".b .icon { font-size: 1rem; width: 1rem; }\n</style>\n",
        )
        assert font_size_only_icon_rules(tmp_path) == {}

    def test_a_nested_at_rule_is_read(self, tmp_path: Path) -> None:
        self._w(
            tmp_path,
            "C.vue",
            "<template><Icon name='x' /></template>\n<style>\n@media (min-width: 1px) { .a .icon { font-size: 2rem; } }\n"
            "</style>\n",
        )
        assert font_size_only_icon_rules(tmp_path) == {"C.vue :: .a .icon": 1}

    def test_a_file_that_renders_no_icon_component_is_out_of_scope(self, tmp_path: Path) -> None:
        self._w(
            tmp_path,
            "D.vue",
            "<template><span class='icon'>*</span></template>\n<style>.a .icon { font-size: 2rem; }</style>\n",
        )
        self._w(
            tmp_path,
            "E.vue",
            "<template><!-- <Icon name='x' /> --><div /></template>\n<style>.a .icon { font-size: 2rem; }</style>\n",
        )
        assert font_size_only_icon_rules(tmp_path) == {}

    def test_other_class_names_and_properties_do_not_match(self, tmp_path: Path) -> None:
        self._w(
            tmp_path,
            "F.vue",
            "<template><Icon name='x' /></template>\n<style>\n.stat-icon { font-size: 2rem; }\n"
            ".icon-md { font-size: 2rem; }\n.a .icon { line-height: 1; min-width: 1px; }\n"
            "/* .a .icon { font-size: 1rem; } */\n</style>\n",
        )
        assert font_size_only_icon_rules(tmp_path) == {}


def test_no_icon_rule_sizes_by_font_size_beyond_the_pinned_ones() -> None:
    root = repo_root() / _FRONTEND_SRC
    assert root.is_dir(), f"{_FRONTEND_SRC} has moved; this guard reads it by path"
    REACH_VUE_FILES.examined(repo_root())
    now = font_size_only_icon_rules(root)
    new = {k: v for k, v in now.items() if v > PINS.get(k, 0)}
    assert not new, (
        f"`.icon` rules set font-size on an Icon, which Icon ignores (#19875): {new}. "
        "Icon is an svg sized by width/height: set both, or use the Icon size prop."
    )
    stale = {k: v for k, v in PINS.items() if now.get(k, 0) < v}
    assert not stale, f"pinned icon rules are fixed or gone: {stale}; lower or delete them in PINS (#19875)."


def test_the_pin_was_not_raised_against_the_base() -> None:
    base = base_table(repo_root(), ("repo_tests/icon_rule_sets_font_size_only_19875_test.py",), "PINS")
    if not base:
        return  # new at this base
    raised = raised_entries(PINS, base)
    assert not raised, f"PINS entries rose or were added against the base (#19875): {raised}; the pin only goes down."
