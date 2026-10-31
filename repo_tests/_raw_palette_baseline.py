# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Raw Tailwind palette classes in `.vue` markup, frozen (#14580).

Measured at the commit that added this ratchet, by
`repo_tests._raw_palette_detect.scan`: **594 occurrences of 175 distinct classes in
the user frontend, 6214 of 211 in the SLM control plane** (keys behind `slm:`).
#14580 and #17566 counted 689 in 66 files and 6,213 in 104 files with a looser
pattern that also read `<style>` blocks; this detector reads markup only, because
`<style>` is `color-no-hex`'s job. A differing figure is a finding, not a rebase.

Keyed by the class literal, so driving one entry to zero is a complete piece of
work: that colour is tokenised everywhere. Shrink-only: the sweep that drains it
is #17566 for the control plane and the per-section redesign work for the user
frontend.
"""

from __future__ import annotations

RAW_PALETTE_CLASSES: dict[str, int] = {
    "accent-blue-500": 2,
    "bg-amber-50": 1,
    "bg-amber-500": 3,
    "bg-amber-600": 1,
    "bg-amber-950": 1,
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
    "bg-green-400/10": 2,
    "bg-green-50": 2,  # #16253 SystemStatusNotification severities onto theme tokens (3 -> 2)
    "bg-green-500": 9,  # #14780 BaseAvatar: hand-rolled avatars and presence dots left for the kit (11 -> 9)
    "bg-green-500/10": 2,
    "bg-green-600": 4,  # #16253 SystemStatusNotification severities onto theme tokens (5 -> 4)
    "bg-green-700": 2,  # #16253 SystemStatusNotification severities onto theme tokens (3 -> 2)
    "bg-green-900": 2,
    "bg-green-900/30": 3,
    "bg-indigo-100": 2,
    "bg-indigo-50": 2,
    "bg-indigo-600": 1,
    "bg-indigo-700": 1,
    "bg-indigo-900/20": 1,
    "bg-neutral-400": 2,
    "bg-orange-400/10": 2,
    "bg-orange-500": 1,
    "bg-purple-100": 3,
    "bg-purple-400/10": 2,
    "bg-purple-50": 3,
    "bg-purple-500": 1,
    "bg-purple-500/20": 1,
    "bg-purple-900": 1,
    "bg-red-100": 9,
    "bg-red-400/10": 1,
    "bg-red-50": 3,  # #16253 SystemStatusNotification severities onto theme tokens (5 -> 3)
    "bg-red-500": 9,
    "bg-red-500/10": 5,
    "bg-red-500/20": 1,
    "bg-red-500/30": 1,
    "bg-red-600": 4,  # #16253 SystemStatusNotification severities onto theme tokens (5 -> 4)
    "bg-red-700": 4,  # #16253 SystemStatusNotification severities onto theme tokens (5 -> 4)
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
    "border-amber-200": 1,
    "border-amber-800": 1,
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
    "border-red-200": 1,  # #16253 SystemStatusNotification severities onto theme tokens (2 -> 1)
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
    "ring-red-500": 2,  # #16253 SystemStatusNotification severities onto theme tokens (3 -> 2)
    "text-amber-200": 1,
    "text-amber-400": 2,
    "text-amber-600": 2,
    "text-amber-800": 1,
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
    "text-green-400": 14,  # #16253 SystemStatusNotification severities onto theme tokens (15 -> 14)
    "text-green-500": 13,
    "text-green-600": 18,  # #16253 SystemStatusNotification severities onto theme tokens (20 -> 18)
    "text-green-700": 4,  # #16253 SystemStatusNotification severities onto theme tokens (5 -> 4)
    "text-green-800": 4,
    "text-green-900": 1,  # #16253 SystemStatusNotification severities onto theme tokens (2 -> 1)
    "text-indigo-400": 1,
    "text-indigo-600": 2,
    "text-indigo-700": 2,
    "text-orange-400": 3,
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
    "text-red-400": 18,  # #16253 SystemStatusNotification severities onto theme tokens (19 -> 18)
    "text-red-500": 8,  # #18819: 9 -> 8, hand-rolled notices moved to the kit BaseAlert
    "text-red-600": 23,  # #16253 SystemStatusNotification severities onto theme tokens (27 -> 23)
    "text-red-700": 5,  # #16253 SystemStatusNotification severities onto theme tokens (6 -> 5)
    "text-red-800": 5,
    "text-yellow-200": 2,
    "text-yellow-300": 1,
    "text-yellow-400": 6,  # #16253 SystemStatusNotification severities onto theme tokens (7 -> 6)
    "text-yellow-600": 9,  # #16253 SystemStatusNotification severities onto theme tokens (11 -> 9)
    "text-yellow-700": 4,  # #16253 SystemStatusNotification severities onto theme tokens (5 -> 4)
    "text-yellow-800": 4,
    # The SLM control plane (#17566).
    "slm:bg-amber-100": 19,
    "slm:bg-amber-200": 4,
    "slm:bg-amber-300": 1,
    "slm:bg-amber-50": 3,  # #18863 SLM notices onto BaseAlert (11 -> 3)
    "slm:bg-amber-500": 9,
    "slm:bg-amber-500/10": 1,
    "slm:bg-amber-500/15": 1,
    "slm:bg-amber-500/20": 2,
    "slm:bg-amber-600": 3,  # #19482: BatchTool banner -> kit PollingPausedAlert (-1)
    "slm:bg-amber-700": 1,  # #19482: BatchTool banner -> kit PollingPausedAlert (-1)
    "slm:bg-amber-900/30": 1,
    "slm:bg-blue-100": 52,  # #18863 SLM notices onto BaseAlert (53 -> 52)
    "slm:bg-blue-200": 4,
    "slm:bg-blue-50": 17,  # #18863 SLM notices onto BaseAlert (19 -> 17)
    "slm:bg-blue-500": 11,  # #14777 batch 2: 12 -> 11
    "slm:bg-blue-600": 36,
    "slm:bg-blue-700": 25,
    "slm:bg-blue-900/30": 1,
    "slm:bg-cyan-100": 1,
    "slm:bg-cyan-50": 1,
    "slm:bg-cyan-500": 2,
    "slm:bg-cyan-500/20": 1,  # #17562: 2 -> 1
    "slm:bg-emerald-400": 1,
    "slm:bg-emerald-500/20": 2,
    "slm:bg-emerald-600": 3,
    "slm:bg-emerald-700": 1,
    "slm:bg-gray-100": 197,  # #14780 BaseDrawer: 199 -> 198; TabbedRouteLayout (#19858): 198 -> 197
    "slm:bg-gray-200": 92,  # #14780 BaseSwitch: 118 -> 100, LoadBalancingView 100 -> 99, #19906 -> 92
    "slm:bg-gray-300": 9,
    "slm:bg-gray-400": 41,
    "slm:bg-gray-50": 235,  # #14780 BasePagination: 249 -> 237; TabbedRouteLayout (#19858): 237 -> 235
    "slm:bg-gray-500": 4,
    "slm:bg-gray-500/20": 2,  # #17562: 4 -> 2
    "slm:bg-gray-600": 8,  # #14777 batch 2: 9 -> 8
    "slm:bg-gray-700": 10,  # #14777 batch 2: 12 -> 10
    "slm:bg-gray-800": 22,  # #14777: 26 -> 22, SLM dialogs moved onto the kit BaseModal
    "slm:bg-gray-900": 30,  # #14777 batch 2: 31 -> 30
    "slm:bg-gray-950": 1,
    "slm:bg-green-100": 62,  # #18819 + #14777: 64 -> 62, kit BaseAlert notices and BaseModal dialogs
    "slm:bg-green-200": 4,
    "slm:bg-green-50": 17,  # #18863 SLM notices onto BaseAlert (18 -> 17)
    "slm:bg-green-500": 55,  # #18863 SLM notices onto BaseAlert (56 -> 55)
    "slm:bg-green-600": 17,
    "slm:bg-green-700": 7,
    "slm:bg-indigo-100": 4,
    "slm:bg-indigo-200": 1,
    "slm:bg-indigo-50": 4,
    "slm:bg-indigo-600": 6,
    "slm:bg-indigo-700": 4,
    "slm:bg-orange-100": 15,  # #14777: 16 -> 15, SLM dialogs moved onto the kit BaseModal
    "slm:bg-orange-200": 2,
    "slm:bg-orange-50": 1,
    "slm:bg-orange-500": 3,
    "slm:bg-orange-600": 5,
    "slm:bg-orange-700": 4,
    "slm:bg-pink-100": 1,
    "slm:bg-purple-100": 11,
    "slm:bg-purple-200": 3,
    "slm:bg-purple-50": 3,
    "slm:bg-purple-500": 4,
    "slm:bg-purple-600": 5,
    "slm:bg-purple-700": 4,
    "slm:bg-purple-900/30": 1,
    "slm:bg-red-100": 69,  # #18819 + #14777: 72 -> 69, kit BaseAlert notices and BaseModal dialogs
    "slm:bg-red-200": 10,
    "slm:bg-red-400": 1,
    "slm:bg-red-50": 27,  # #18819: 102 -> 27, hand-rolled notices moved to the kit BaseAlert
    "slm:bg-red-50/30": 1,
    "slm:bg-red-50/50": 1,
    "slm:bg-red-500": 46,  # #18819: 47 -> 46, the remaining SLM notice banners use the kit BaseAlert
    "slm:bg-red-500/20": 2,
    "slm:bg-red-600": 18,
    "slm:bg-red-700": 12,
    "slm:bg-red-800": 1,
    "slm:bg-red-900/30": 1,
    "slm:bg-slate-900": 2,
    "slm:bg-teal-100": 1,
    "slm:bg-teal-500": 1,
    "slm:bg-teal-600": 1,
    "slm:bg-yellow-100": 38,  # #18819: 39 -> 38, hand-rolled notices moved to the kit BaseAlert
    "slm:bg-yellow-200": 1,
    "slm:bg-yellow-400": 1,
    "slm:bg-yellow-50": 6,  # #18863 SLM notices onto BaseAlert (17 -> 6)
    "slm:bg-yellow-50/50": 1,
    "slm:bg-yellow-500": 20,  # #18863 SLM notices onto BaseAlert (21 -> 20)
    "slm:border-amber-200": 1,  # #18863 SLM notices onto BaseAlert (9 -> 1)
    "slm:border-amber-300": 2,  # #18819: 3 -> 2, hand-rolled notices moved to the kit BaseAlert
    "slm:border-amber-500/30": 5,
    "slm:border-blue-100": 1,
    "slm:border-blue-200": 7,  # #18863 SLM notices onto BaseAlert (9 -> 7)
    "slm:border-blue-300": 2,
    "slm:border-blue-400": 1,
    "slm:border-blue-500": 32,
    "slm:border-blue-500/30": 1,  # #17562: 2 -> 1
    "slm:border-blue-600": 4,
    "slm:border-cyan-500/30": 1,  # #17562: 2 -> 1
    "slm:border-emerald-500/30": 2,
    "slm:border-gray-100": 54,  # #17562: 55 -> 54
    "slm:border-gray-200": 305,  # #14780: 313 -> 309; #19858: -> 307; #17562: -> 305
    "slm:border-gray-300": 322,  # #14780 BaseSwitch: 340 -> 322
    "slm:border-gray-50": 4,
    "slm:border-gray-500": 2,
    "slm:border-gray-500/30": 2,  # #17562: 4 -> 2
    "slm:border-gray-600": 14,
    "slm:border-gray-700": 23,  # #14777 batch 2: 27 -> 26  # #17562: 26 -> 23
    "slm:border-gray-700/50": 1,
    "slm:border-gray-800": 3,  # #17562: 5 -> 3
    "slm:border-green-200": 3,  # #18863 SLM notices onto BaseAlert (4 -> 3)
    "slm:border-green-300": 6,
    "slm:border-green-500": 2,
    "slm:border-indigo-200": 1,
    "slm:border-indigo-300": 1,
    "slm:border-indigo-400": 1,
    "slm:border-indigo-600": 1,
    "slm:border-l-blue-500": 1,
    "slm:border-l-green-500": 1,
    "slm:border-l-purple-500": 1,
    "slm:border-orange-200": 4,
    "slm:border-purple-200": 2,
    "slm:border-purple-500/30": 1,  # #17562: 2 -> 1
    "slm:border-red-200": 6,  # #18819: 77 -> 6, hand-rolled notices moved to the kit BaseAlert
    "slm:border-red-300": 10,
    "slm:border-red-500": 2,
    "slm:border-red-500/30": 3,
    "slm:border-yellow-200": 4,  # #18863 SLM notices onto BaseAlert (13 -> 4)
    "slm:border-yellow-300": 3,  # #18819: 4 -> 3, hand-rolled notices moved to the kit BaseAlert
    "slm:border-yellow-500": 2,
    "slm:divide-gray-100": 12,
    "slm:divide-gray-200": 42,
    "slm:placeholder-gray-500": 1,
    "slm:ring-blue-500": 44,
    "slm:ring-indigo-400": 8,
    "slm:ring-red-200": 1,
    "slm:text-amber-200": 1,
    "slm:text-amber-300": 4,
    "slm:text-amber-400": 3,
    "slm:text-amber-600": 18,  # #18863 SLM notices onto BaseAlert (22 -> 18)
    "slm:text-amber-700": 19,  # #18863 SLM notices onto BaseAlert (25 -> 19)
    "slm:text-amber-800": 6,  # #18863 SLM notices onto BaseAlert (8 -> 6)
    "slm:text-blue-300": 1,  # #17562: 2 -> 1
    "slm:text-blue-400": 4,
    "slm:text-blue-500": 5,  # #18863 SLM notices onto BaseAlert (9 -> 5)
    "slm:text-blue-600": 44,  # #18863 SLM notices onto BaseAlert (48 -> 44)
    "slm:text-blue-700": 37,  # #18863 SLM notices onto BaseAlert (39 -> 37)
    "slm:text-blue-800": 23,  # #18863 SLM notices onto BaseAlert (24 -> 23)
    "slm:text-blue-900": 1,  # #18863 SLM notices onto BaseAlert (2 -> 1)
    "slm:text-cyan-300": 1,  # #17562: 2 -> 1
    "slm:text-cyan-400": 4,
    "slm:text-cyan-600": 1,
    "slm:text-cyan-800": 2,
    "slm:text-cyan-900": 1,
    "slm:text-emerald-300": 2,
    "slm:text-emerald-400": 2,
    "slm:text-gray-100": 12,  # #14777: 14 -> 12, SLM dialogs moved onto the kit BaseModal
    "slm:text-gray-200": 5,  # #17562: 6 -> 5
    "slm:text-gray-300": 46,  # #14777 batch 2: 51 -> 50  # #17562: 50 -> 46
    "slm:text-gray-400": 208,  # #14780 BaseDrawer: 217 -> 214  # #17562: 214 -> 208
    "slm:text-gray-500": 866,  # #14780 BasePagination: 874 -> 869  # #17562: 869 -> 866
    "slm:text-gray-600": 264,  # #14780 BaseDrawer: 268 -> 265; TabbedRouteLayout (#19858): 265 -> 264
    "slm:text-gray-700": 428,  # #18734: 431 -> 428
    "slm:text-gray-800": 40,  # #14777: 43 -> 41, SLM dialogs moved onto the kit BaseModal  # #17562: 41 -> 40
    "slm:text-gray-900": 437,  # #14780 BaseDrawer: 442 -> 439; TabbedRouteLayout (#19858): 439 -> 437
    "slm:text-green-300": 4,
    "slm:text-green-400": 4,
    "slm:text-green-500": 2,  # #18863 SLM notices onto BaseAlert (5 -> 2)
    "slm:text-green-600": 66,  # #18863 SLM notices onto BaseAlert (70 -> 66)
    "slm:text-green-700": 47,  # #18863 SLM notices onto BaseAlert (73 -> 47)
    "slm:text-green-800": 26,  # #18863 SLM notices onto BaseAlert (27 -> 26)
    "slm:text-green-900": 1,  # #18863 SLM notices onto BaseAlert (2 -> 1)
    "slm:text-indigo-700": 8,
    "slm:text-orange-600": 17,  # #14777: 18 -> 17, SLM dialogs moved onto the kit BaseModal
    "slm:text-orange-700": 8,
    "slm:text-orange-800": 6,
    "slm:text-pink-700": 1,
    "slm:text-purple-300": 1,  # #17562: 2 -> 1
    "slm:text-purple-400": 2,
    "slm:text-purple-500": 1,
    "slm:text-purple-600": 7,
    "slm:text-purple-700": 8,
    "slm:text-purple-800": 4,
    "slm:text-purple-900": 1,
    "slm:text-red-300": 4,
    "slm:text-red-400": 4,
    "slm:text-red-500": 12,  # #18819: 23 -> 12, hand-rolled notices moved to the kit BaseAlert
    "slm:text-red-600": 85,  # #18819 + #14777: 96 -> 85, kit BaseAlert notices and BaseModal dialogs
    "slm:text-red-700": 71,  # #18819: 150 -> 71, hand-rolled notices moved to the kit BaseAlert
    "slm:text-red-800": 31,  # #18819: 42 -> 31, hand-rolled notices moved to the kit BaseAlert
    "slm:text-slate-400": 1,
    "slm:text-teal-700": 1,
    "slm:text-yellow-300": 1,
    "slm:text-yellow-400": 2,
    "slm:text-yellow-500": 4,  # #18863 SLM notices onto BaseAlert (7 -> 4)
    "slm:text-yellow-600": 32,  # #18863 SLM notices onto BaseAlert (40 -> 32)
    "slm:text-yellow-700": 24,  # #18863 SLM notices onto BaseAlert (32 -> 24)
    "slm:text-yellow-800": 19,  # #18863 SLM notices onto BaseAlert (27 -> 19)
}

# No hand-maintained total (#19283): a raised entry is caught by comparing each entry with this
# table at the base commit (repo_tests/_ratchet_base.py), so PRs lowering different entries
# never edit a shared line.
