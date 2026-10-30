# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One concept, one implementation — fragmentation may shrink, never grow (#12730, #12731).

The design system is advisory rather than enforced, so the same concept is
implemented several incompatible ways and appearance varies by which view you
happen to be in. #12731 records four dimensions of this. Measuring them found
the picture is directionally right and, in one case, far worse than filed:

* **Local CSS.** #12731 describes "2 per-view button-class systems". Buttons
  turned out not to be a special case but a sample of the whole: **381 `.vue`
  components declare their own styles against 16 shared stylesheets**, giving
  5,622 distinct class names in 9,429 rule declarations. `btn` is 116 of those
  names — about 2% of the problem. Other families are as bad or worse per
  name: `status` 114 names, `card` 67, `badge` 58, `result` 56, `progress` 47.
  `empty` (72 files) and `action` (54 files) are the very primitives #12730's
  title names. Shared stylesheets already define `btn-primary`
  (`assets/tailwind.css`, `assets/vue-notus.css`), so those views are
  redefining what already exists, and usage has grown since filing rather than
  shrunk (`btn-primary` 85 -> 210).
* **Notification.** Four entry points — `useToast`, `useNotificationConfig`,
  `NotificationBridge`, `showNotification`. Smaller than #12731's figures,
  which counted word occurrences rather than modules; `useNotification` and
  `$toast` are already gone. The same split exists in the styles: `toast`,
  `message`, `alert` and `notification` are four vocabularies for telling the
  user something, 48 distinct class names across 18 files, so consolidating the
  code without the CSS would leave the visual inconsistency in place.
* **Waiting states.** `loading` (30 names, 83 files), `skeleton` (26) and
  `spinner` (4) are three vocabularies for the same thing, 60 names across 105
  files. #12731 records this as "inconsistent loading"; these are the numbers.
* **Date formatting.** Four approaches: `toLocaleString`, `formatDate`,
  `toLocaleDateString`, `Intl.DateTimeFormat`.
* **z-index.** 52 hardcoded declarations, with no scale, so
  stacking order is decided per file.

This guard does not consolidate any of it — that is many PRs' work across
#12730. It exists so the job is finite: the numbers may only move one way while
that work proceeds.

**Fails in BOTH directions**, matching `python_file_size_known_large.py`
and the contract ratchet. Growth is a regression; an unrecorded *shrink* is
also a failure, because a baseline that drifts below the real number stops
being evidence — lower the constant in the commit that does the work.

Counting is textual. These are `.vue` single-file components mixing template,
script and style, and a Python guard cannot parse them without a TypeScript and
CSS toolchain that CI would then have to keep working. A stable regex that is
slightly over-inclusive is worth more than an exact count that breaks: what is
asserted is the direction of the number, not its absolute truth.
"""

from __future__ import annotations

import collections
import functools
import re
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._ratchet_base import base_tree_texts

_REPO_ROOT = repo_root()
_FRONTEND_SRC = _REPO_ROOT / "autobot-frontend" / "src"

_SOURCE_SUFFIXES = (".ts", ".vue", ".css", ".scss")

# Floor, not a census: a walk that stops matching must fail loudly rather than
# pass by reaching nothing.
_MIN_SOURCE_FILES = 500

# --- The ratchet ---------------------------------------------------------
#
# Lower these as consolidation lands. Never raise one to make a new view pass:
# use the shared definition instead of declaring another local one.

# NOTE (#15455): `distinct_class_names` and `css_rule_declarations` count SIZE,
# not duplication — a legitimate new component raises both, so they freeze the
# design system rather than ratcheting sprawl down. `components_declaring_styles`
# and the per-family counts are the duplication signals and behaved correctly:
# when #15429 added the same banner to three views, this file caught it, and
# consolidating into `assets/main.css` removed 67 lines. The two size metrics
# are kept, at the post-consolidation figures, until #15455 replaces them with a
# duplication measure.
BASELINE = {
    # `.vue` components carrying their own <style> rules. Target is a small
    # number of shared stylesheets, not 381 components each with a private
    # copy of the design system.
    "components_declaring_styles": 362,  # #19903 AC2: the main app ToastContainer retired into the kit (363 -> 362); #19532: the retired main-GUI SettingsPanel (365 -> 364); #19217: the retired main-app web research editors (366 -> 365); #14780 OrgChart drawer: 367 -> 366 (the slide transition CSS left for BaseDrawer); #14778: -1, the local BaseInput fork retired into the kit (on main's 368); #18849: -1, the local BaseButton fork retired into the kit; #18819: -2 (ErrorBanner and ui/BaseAlert retired into the kit BaseAlert);  #14778: BaseTable and DataTable forks left for the kit (-2);  #14776: the local BaseBadge fork left for the kit (376 -> 375), then the local BaseCard + BasePanel (375 -> 373); #18240: App.vue's scoped <style> went with the header split (lowered from 379).; #18354: DarkModeToggle and the main-app LanguageSwitcher left for the kit
    # Earlier #17020: Terminal.vue removed (dead, zero live callers)
    # Distinct class names declared anywhere in the frontend.
    #
    # #16972/#15455: OWNER-APPROVED, ONE-OFF EXCEPTION -- for this counter and
    # css_rule_declarations only, not precedent for recounting any other ratchet
    # in this file (the five duplication counters below stay strict). Raised
    # for #16875's two genuinely new admin pages' own non-duplicated layout,
    # after every actual duplicate was consolidated first (by hand and by
    # cross-referencing sibling admin views) -- this pair is documented above
    # as measuring page SIZE, not duplication, and is interim until #15455
    # replaces them with a real duplication measure.
    "distinct_class_names": 5367,  # #19904 batch 2: 5388 -> 5367, 29 more views onto BaseButton; #19904 batch 1: 5391 -> 5388, per-view .btn* rules retired into BaseButton; #19903 AC2: both app ToastContainers retired into the kit (-14) on 5405; #19903: the retired NotificationConfigModal and the toast/result reuse (-16) on main's 5421; #17562 batch 2: five tables onto BaseTable (-4) on 5425; #19532: the retired main-GUI SettingsPanel (-6); #19217: the retired main-app web research editors (-23) on main's 5454; #17562: six hand-rolled tables onto the kit BaseTable (-12) on main's 5466; #13422: risk-badge, risk-pill, cost-pill and the level-* risk classes left for the kit RiskBadge (-3) on main's 5476; train-85b: #12741 show-more rules moved to TruncationNotice (-3) on main's 5479; train-84: #14780 BaseAvatar (-2) on main's 5481; #17829: the chat input status bar classes became utilities (-3); #14780 drawer adoption: 5492 -> 5484 (SourcePreviewPanel, WorkItemDetail on BaseDrawer); #14778: -10, the local BaseInput fork retired into the kit (on main's 5502); #18242: -1 on main's 5503 (CustomDashboard onto DashboardGrid); #18849: -14, the local BaseButton fork retired into the kit; #18819: -14 (ErrorBanner and ui/BaseAlert retired into the kit BaseAlert);  #14778: BaseTable and DataTable forks left for the kit (-26);  #14776: local BaseBadge retired (5594 -> 5585), then local BaseCard + BasePanel (5585 -> 5557); #17565: App.vue's hand-rolled .skip-links/.skip-link; train-85h merge: main's 5469 + this train's -3
    # replaced by the shared kit SkipLink (lowered from 5615). Earlier: #17020,
    # Terminal.vue removed -- pure deletion of dead code, lowered, not held.
    # #18354: DarkModeToggle and the main-app LanguageSwitcher left for the kit (5611 -> 5594).
    # css_rule_declarations has no constant here (#19283): it is compared with the same
    # measurement over the base commit's tree (test_css_rule_declarations_do_not_rise),
    # so PRs that each remove rules never edit a shared line.
    # Files declaring at least one `.btn-*` CSS rule. Target is 1 — a single
    # shared stylesheet.
    "button_definition_files": 66,  # #19904 batch 2: 79 -> 66, 29 views onto BaseButton, the ones keeping icon or tinted buttons keep those rules; #19904 batch 1: 98 -> 79, 25 views moved to BaseButton; #19217: the retired main-app web research editors (100 -> 99); #18849: 101 -> 100, the local BaseButton fork retired into the kit; Distinct `.btn-*` class names declared anywhere.
    "button_class_names": 79,  # #19904 batch 2: 100 -> 79; #19904 batch 1: 103 -> 100; #18849: 115 -> 103, the local BaseButton fork retired into the kit; Distinct notification entry points. Target is 1 canonical API, the rest
    # thin shims or removed.
    "notification_entry_points": 4,
    # Distinct date-formatting approaches in use.
    "date_format_approaches": 4,
    # Hardcoded `z-index: <number>` declarations, i.e. stacking order decided
    # per file rather than by a scale.
    "hardcoded_zindex_declarations": 47,  # #14780 drawer adoption: 48 -> 47 (SourcePreviewPanel, WorkItemDetail on BaseDrawer); #14778: BaseTable and DataTable forks left for the kit (-1);  #14776: the retired BasePanel's z-index went with it (50 -> 49); #18240: App.vue #mobile-nav z-index: 50 became a utility class (lowered from 51)
}

# Families worth pinning individually, so a regression in one cannot hide
# inside the repo-wide totals. `modal` and `dialog` are listed separately on
# purpose: they are the same concept in two vocabularies (34 files, 39 names
# between them for "a thing that opens over the page"), the same duplicate-
# system shape as `btn` versus `btn-action`, and consolidating them should show
# up as one number falling to zero rather than as noise in the total.
FAMILY_BASELINE = {
    "btn": 80,  # #19904 batch 2: 101 -> 80; #19904 batch 1: 104 -> 101; #18849: 116 -> 104, the local BaseButton fork retired into the kit
    "status": 113,  # #17829: .status-left/.status-right became utilities in ChatInputStatusBar.vue
    "header": 23,  # #14776: local BaseCard + BasePanel merged into the kit card (24 -> 23)
    "card": 57,  # #14776: local BaseCard + BasePanel merged into the kit card (67 -> 57)
    "badge": 50,  # #14776: the local BaseBadge fork left for the kit (58 -> 50)
    "result": 56,
    "progress": 47,
    "stat": 38,
    "panel": 19,  # #14780 drawer adoption: 23 -> 19 (SourcePreviewPanel, WorkItemDetail on BaseDrawer); #14776: local BaseCard + BasePanel merged into the kit card (34 -> 23)
    "form": 26,  # #19217: the retired main-app web research editors (27 -> 26)
    "action": 27,
    "modal": 25,
    "empty": 22,  # #14778: DataTable empty-cell left (23 -> 22)
    "error": 30,  # #18819: -5 (ErrorBanner and ui/BaseAlert retired into the kit BaseAlert);
    "section": 23,
    "summary": 27,
    "text": 28,
    "toggle": 22,  # #19217: the retired main-app web research editors (24 -> 22)
    "field": 17,  # #19217: the retired main-app web research editors (20 -> 17)
    "icon": 12,  # #18354: DarkModeToggle and the main-app LanguageSwitcher left for the kit (16 -> 12)
    "checkbox": 9,
    "sidebar": 9,
    "dropdown": 9,
    "nav": 7,
    "breadcrumb": 6,
    "chip": 5,
    "pagination": 2,  # #14778: DataTable pagination left (4 -> 2)
    # Three vocabularies for "the user is waiting": 60 distinct names across
    # 105 files. #12731 records this as "inconsistent loading"; this is the
    # measurement of it. They should collapse to one.
    "loading": 29,  # #14778: DataTable loading-cell left (30 -> 29)
    "skeleton": 26,
    "spinner": 4,
    "table": 12,  # #14778: BaseTable and DataTable table-* left (18 -> 12)
    "input": 15,  # #14778: 18 -> 15, the local BaseInput fork retired into the kit;
    "dialog": 11,
    "tab": 11,
    "label": 7,  # #14778: 8 -> 7, the local BaseInput fork retired into the kit;
    "grid": 4,
    "title": 4,
    "subtitle": 1,
    # The notification concept splits four ways in CSS as well as in code:
    # 48 distinct names across 18 files for "tell the user something". The
    # code-level split is pinned separately as `notification_entry_points`;
    # these four should collapse together with it.
    "toast": 1,
    "message": 15,
    "alert": 5,  # #18819: 13 -> 5, ui/BaseAlert and ErrorBanner retired into the kit BaseAlert
    "notification": 5,
    "tooltip": 4,
    "hint": 2,
}

_BTN_RULE_RE = re.compile(r"^\s*\.(btn-[a-z0-9-]+)\s*[,{]", re.MULTILINE)
_ANY_RULE_RE = re.compile(r"^\s*\.([a-z][a-z0-9-]*)\s*[,{]", re.MULTILINE)
_STYLE_SUFFIXES = (".vue", ".css", ".scss")
_ZINDEX_RE = re.compile(r"^\s*z-index:\s*-?\d+", re.MULTILINE)

_NOTIFICATION_ENTRY_POINTS = (
    "useToast",
    "useNotificationConfig",
    "NotificationBridge",
    "showNotification",
)

_DATE_FORMAT_APPROACHES = {
    "toLocaleDateString": re.compile(r"\btoLocaleDateString\s*\("),
    "toLocaleString": re.compile(r"\btoLocaleString\s*\("),
    "Intl.DateTimeFormat": re.compile(r"\bIntl\.DateTimeFormat\s*\("),
    "formatDate": re.compile(r"\bformatDate\s*\("),
}


def _is_test(path: Path) -> bool:
    """Test scaffolding is not product surface.

    A spec asserting on a button class or a formatted date is not another
    implementation of the concept; counting it would make the ratchet grow
    whenever someone adds coverage.
    """
    return "__tests__" in path.parts or ".test." in path.name or ".spec." in path.name


def _source_files() -> list[Path]:
    return [
        path
        for path in sorted(_FRONTEND_SRC.rglob("*"))
        if path.suffix in _SOURCE_SUFFIXES
        and path.is_file()
        and "node_modules" not in path.relative_to(_FRONTEND_SRC).parts  # #15510
        and not _is_test(path)
    ]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


@functools.lru_cache(maxsize=1)
def _measure() -> dict[str, int]:
    """Cached: 52 parametrised cases would otherwise each rescan ~1100 files.

    Without this the suite walks the frontend once per test and the whole file
    takes minutes — the pre-push hook timed out at 120s on the uncached
    version. The tree does not change during a run, so one scan is correct.
    """
    return _measure_texts((path, _read(path)) for path in _source_files())


@functools.lru_cache(maxsize=1)
def _measure_base() -> dict[str, int]:
    """The same measurement over the base commit's tree (#19283), with the same file filter."""
    prefix = str(_FRONTEND_SRC.relative_to(_REPO_ROOT))
    items = [
        (Path(rel), text)
        for rel, text in base_tree_texts(_REPO_ROOT, prefix).items()
        if Path(rel).suffix in _SOURCE_SUFFIXES and "node_modules" not in Path(rel).parts and not _is_test(Path(rel))
    ]
    return _measure_texts(items)


def _measure_texts(items) -> dict[str, int]:
    """The dimensions, from ``(path, text)`` pairs -- the live tree's or the base's."""
    button_files = 0
    button_names: set[str] = set()
    zindex = 0
    notification: set[str] = set()
    dates: set[str] = set()
    components_with_styles = 0
    all_class_names: set[str] = set()
    rule_declarations = 0
    family_names: dict[str, set[str]] = collections.defaultdict(set)

    for path, text in items:
        if path.suffix in _STYLE_SUFFIXES:
            declared = _ANY_RULE_RE.findall(text)
            if declared:
                all_class_names.update(declared)
                for declared_name in declared:
                    family_names[declared_name.split("-")[0]].add(declared_name)
                rule_declarations += len(declared)
                if path.suffix == ".vue":
                    components_with_styles += 1

        names = _BTN_RULE_RE.findall(text)
        if names:
            button_files += 1
            button_names.update(names)

        zindex += len(_ZINDEX_RE.findall(text))

        for entry in _NOTIFICATION_ENTRY_POINTS:
            if re.search(rf"\b{re.escape(entry)}\b", text):
                notification.add(entry)

        for label, pattern in _DATE_FORMAT_APPROACHES.items():
            if pattern.search(text):
                dates.add(label)

    return {
        "components_declaring_styles": components_with_styles,
        "distinct_class_names": len(all_class_names),
        "css_rule_declarations": rule_declarations,
        "button_definition_files": button_files,
        "button_class_names": len(button_names),
        "notification_entry_points": len(notification),
        "date_format_approaches": len(dates),
        "hardcoded_zindex_declarations": zindex,
        **{f"family:{family}": len(names) for family, names in family_names.items()},
    }


_ADVICE = {
    "components_declaring_styles": "Put the rule in a shared stylesheet rather than another component-local <style> block.",
    "distinct_class_names": "Reuse an existing class rather than coining another name for the same thing.",
    "css_rule_declarations": "Reuse a shared rule rather than redeclaring it locally.",
    "button_definition_files": "Use the shared button styles rather than redeclaring `.btn-*` in another view.",
    "button_class_names": "Reuse an existing button class rather than inventing another name for the same role.",
    "notification_entry_points": "Route through the canonical notification API; additional entry points should be thin shims or removed.",
    "date_format_approaches": "Use the shared date formatter rather than another `toLocale*`/`Intl` call.",
    "hardcoded_zindex_declarations": "Take the value from the z-index scale rather than hardcoding a number.",
}


def test_the_tree_this_guard_reads_is_present() -> None:
    """A moved frontend would make every count zero, and zero passes."""
    assert _FRONTEND_SRC.is_dir(), f"{_FRONTEND_SRC} is missing — this guard is pinned to the wrong path"

    found = len(_source_files())
    assert found >= _MIN_SOURCE_FILES, (
        f"only {found} source file(s) found, expected at least {_MIN_SOURCE_FILES} — the walk has "
        "stopped reaching the frontend, which would make every ratchet below pass by counting nothing"
    )


@pytest.mark.parametrize("family", sorted(FAMILY_BASELINE))
def test_no_class_family_grows(family: str) -> None:
    """Per-family, so a regression cannot hide inside the repo-wide totals.

    `modal` and `dialog` name the same concept; both are pinned so that merging
    them registers as one family reaching zero rather than as churn in the
    aggregate.
    """
    actual = _measure().get(f"family:{family}", 0)
    baseline = FAMILY_BASELINE[family]

    assert actual <= baseline, (
        f"`.{family}-*` declares {actual} distinct class names, ratchet allows {baseline} "
        f"(#12730, #12731). Reuse an existing `.{family}-*` class rather than coining another."
    )
    assert actual == baseline, (
        f"`.{family}-*` is down to {actual} distinct names but the baseline still says {baseline} — "
        "lower it in the commit that did the work"
    )


@pytest.mark.parametrize("dimension", sorted(BASELINE))
def test_fragmentation_only_shrinks(dimension: str) -> None:
    """Growth is a regression; an unrecorded shrink is a stale baseline."""
    actual = _measure()[dimension]
    baseline = BASELINE[dimension]

    assert (
        actual <= baseline
    ), f"{dimension} is {actual}, ratchet allows {baseline} (#12730, #12731).\n{_ADVICE[dimension]}"
    assert actual == baseline, (
        f"{dimension} is down to {actual} but the baseline still says {baseline} — "
        "lower it in the commit that did the work, so the number stays a deliberate claim"
    )


def test_css_rule_declarations_do_not_rise() -> None:
    """#19283: measured on this tree and on the base commit's; no hand-maintained number.
    Two PRs that each remove rules no longer conflict on one constant."""
    now, base = _measure()["css_rule_declarations"], _measure_base()["css_rule_declarations"]
    assert now <= base, (
        f"css_rule_declarations rose from {base} at the base to {now} (#12730, #12731).\n"
        f"{_ADVICE['css_rule_declarations']}"
    )
