# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Raw Tailwind palette classes in `.vue` markup, frozen (#14580).

Measured at the commit that added this ratchet, by
`repo_tests._raw_palette_detect.scan`: **594 occurrences of 175 distinct classes in
the user frontend**; the SLM control plane then held 6214 occurrences of 211 distinct
classes (keys behind `slm:`), a historical figure: it is now zero (see below).
#14580 and #17566 counted 689 in 66 files and 6,213 in 104 files with a looser
pattern that also read `<style>` blocks; this detector reads markup only, because
`<style>` is `color-no-hex`'s job. A differing figure is a finding, not a rebase.

Keyed by the class literal, so driving one entry to zero is a complete piece of
work: that colour is tokenised everywhere. Shrink-only: the sweep that drains it
is #17566 for the control plane and the per-section redesign work for the user
frontend.

The SLM control plane has no entries: it reached zero in #17566 and `slm:` keys are
not allowed here again; `raw_palette_class_ratchet_14580_test.py` enforces zero for its
`.vue`, `.ts` and `.css` sources (#17567).
"""

from __future__ import annotations

RAW_PALETTE_CLASSES: dict[str, int] = {
    "accent-blue-500": 2,
    "bg-amber-500": 2,
    "bg-amber-600": 1,
    "bg-blue-100": 8,
    "bg-blue-400/10": 2,
    "bg-blue-50": 1,  # #16253 SystemStatusNotification severities onto theme tokens (2 -> 1)
    "bg-blue-500": 7,
    "bg-blue-500/10": 3,
    "bg-blue-500/20": 5,
    "bg-blue-600": 6,  # #14780 BaseAvatar (10 -> 7); #16253 SystemStatusNotification severities (7 -> 6)
    "bg-blue-700": 3,  # #16253 SystemStatusNotification severities onto theme tokens (4 -> 3)
    "bg-blue-900": 3,
    "bg-blue-900/20": 1,
    "bg-cyan-100": 1,
    "bg-cyan-900": 1,
    "bg-emerald-600": 1,
    "bg-gray-100": 1,
    "bg-gray-400/10": 1,
    "bg-gray-50": 2,
    "bg-gray-700": 2,
    "bg-gray-800": 3,
    "bg-green-100": 9,
    "bg-green-400/10": 1,
    "bg-green-50": 2,  # #16253 SystemStatusNotification severities onto theme tokens (3 -> 2)
    "bg-green-500": 9,  # #14780 BaseAvatar: hand-rolled avatars and presence dots left for the kit (11 -> 9)
    "bg-green-500/10": 2,
    "bg-green-600": 3,  # #16253 SystemStatusNotification severities onto theme tokens (5 -> 4)
    "bg-green-700": 1,  # #16253 SystemStatusNotification severities onto theme tokens (3 -> 2)
    "bg-green-900": 2,
    "bg-green-900/30": 3,
    "bg-indigo-100": 2,
    "bg-indigo-50": 2,
    "bg-indigo-600": 1,
    "bg-indigo-700": 1,
    "bg-indigo-900/20": 1,
    "bg-neutral-400": 2,
    "bg-orange-400/10": 1,
    "bg-orange-500": 1,
    "bg-purple-100": 3,
    "bg-purple-400/10": 2,
    "bg-purple-50": 3,
    "bg-purple-500": 1,
    "bg-purple-500/20": 1,
    "bg-purple-900": 1,
    "bg-red-100": 9,
    "bg-red-400/10": 1,
    "bg-red-50": 2,  # #16253 SystemStatusNotification severities onto theme tokens (5 -> 3)
    "bg-red-500": 9,
    "bg-red-500/10": 5,
    "bg-red-500/20": 1,
    "bg-red-500/30": 1,
    "bg-red-600": 3,  # #16253 SystemStatusNotification severities onto theme tokens (5 -> 4)
    "bg-red-700": 3,  # #16253 SystemStatusNotification severities onto theme tokens (5 -> 4)
    "bg-red-900": 2,
    "bg-red-900/30": 3,
    "bg-yellow-100": 7,
    "bg-yellow-400": 1,
    "bg-yellow-400/10": 1,
    "bg-yellow-50": 2,  # #16253 SystemStatusNotification severities onto theme tokens (3 -> 2)
    "bg-yellow-500": 4,  # #14780 BaseAvatar: hand-rolled avatars and presence dots left for the kit (6 -> 4)
    "bg-yellow-500/20": 3,
    "bg-yellow-900": 1,
    "bg-yellow-900/20": 1,
    "bg-yellow-900/30": 1,
    "border-blue-300": 1,
    "border-blue-500": 4,
    "border-blue-500/20": 2,
    "border-blue-500/30": 4,
    "border-blue-500/50": 1,
    "border-gray-200": 2,
    "border-gray-300": 1,
    "border-gray-600": 1,
    "border-gray-700": 2,
    "border-green-200": 1,  # #16253 SystemStatusNotification severities onto theme tokens (2 -> 1)
    "border-green-300": 1,
    "border-green-500": 1,
    "border-green-500/20": 1,
    "border-indigo-200": 2,
    "border-indigo-300": 1,
    "border-indigo-600": 1,
    "border-indigo-700": 1,
    "border-purple-200": 1,
    "border-purple-300": 1,
    "border-purple-500/30": 1,
    "border-red-500": 1,
    "border-red-500/20": 3,
    "border-red-500/50": 1,
    "border-yellow-200": 1,  # #16253 SystemStatusNotification severities onto theme tokens (2 -> 1)
    "border-yellow-300": 1,
    "border-yellow-700": 1,
    "ring-amber-950/50": 1,
    "ring-blue-500": 4,  # #16253 SystemStatusNotification severities onto theme tokens (5 -> 4)
    "ring-green-500": 1,  # #16253 SystemStatusNotification severities onto theme tokens (2 -> 1)
    "ring-indigo-500": 1,  # #16253 SystemStatusNotification severities onto theme tokens (2 -> 1)
    "ring-offset-gray-800": 1,
    "ring-purple-500": 1,
    "ring-red-500": 1,  # #16253 SystemStatusNotification severities onto theme tokens (3 -> 2)
    "text-amber-400": 2,
    "text-amber-600": 2,
    "text-amber-950": 1,
    "text-blue-200": 3,
    "text-blue-300": 1,
    "text-blue-400": 15,  # #16253 SystemStatusNotification severities onto theme tokens (16 -> 15)
    "text-blue-500": 3,
    "text-blue-600": 8,  # #16253 SystemStatusNotification severities onto theme tokens (9 -> 8)
    "text-blue-700": 6,  # #16253 SystemStatusNotification severities onto theme tokens (7 -> 6)
    "text-blue-800": 3,
    "text-cyan-200": 1,
    "text-cyan-400": 1,
    "text-cyan-800": 1,
    "text-emerald-400": 1,
    "text-emerald-600": 1,
    "text-gray-100": 2,
    "text-gray-200": 1,
    "text-gray-300": 1,
    "text-gray-400": 7,
    "text-gray-500": 6,
    "text-gray-600": 1,
    "text-gray-700": 2,
    "text-gray-900": 2,
    "text-green-200": 2,
    "text-green-300": 2,
    "text-green-400": 12,  # #16253 SystemStatusNotification severities onto theme tokens (15 -> 14)
    "text-green-500": 13,
    "text-green-600": 16,  # #16253 SystemStatusNotification severities onto theme tokens (20 -> 18)
    "text-green-700": 4,  # #16253 SystemStatusNotification severities onto theme tokens (5 -> 4)
    "text-green-800": 4,
    "text-green-900": 1,  # #16253 SystemStatusNotification severities onto theme tokens (2 -> 1)
    "text-indigo-400": 1,
    "text-indigo-600": 2,
    "text-indigo-700": 2,
    "text-orange-400": 2,
    "text-orange-500": 4,
    "text-orange-600": 2,
    "text-purple-200": 1,
    "text-purple-400": 5,
    "text-purple-500": 7,
    "text-purple-600": 4,
    "text-purple-700": 3,
    "text-purple-800": 1,
    "text-red-200": 2,
    "text-red-300": 3,
    "text-red-400": 16,  # #16253 SystemStatusNotification severities onto theme tokens (19 -> 18)
    "text-red-500": 7,  # #18819: 9 -> 8, hand-rolled notices moved to the kit BaseAlert
    "text-red-600": 21,  # #16253 SystemStatusNotification severities onto theme tokens (27 -> 23)
    "text-red-700": 5,  # #16253 SystemStatusNotification severities onto theme tokens (6 -> 5)
    "text-red-800": 5,
    "text-yellow-200": 2,
    "text-yellow-300": 1,
    "text-yellow-400": 6,  # #16253 SystemStatusNotification severities onto theme tokens (7 -> 6)
    "text-yellow-600": 8,  # #16253 SystemStatusNotification severities onto theme tokens (11 -> 9)
    "text-yellow-700": 4,  # #16253 SystemStatusNotification severities onto theme tokens (5 -> 4)
    "text-yellow-800": 4,
    # The SLM control plane (#17566).
}

# No hand-maintained total (#19283): a raised entry is caught by comparing each entry with this
# table at the base commit (repo_tests/_ratchet_base.py), so PRs lowering different entries
# never edit a shared line.
