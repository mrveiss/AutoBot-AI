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
    "bg-red-50": 3,  # #16253 SystemStatusNotification severities onto theme tokens (5 -> 3)
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
    "text-green-600": 17,  # #16253 SystemStatusNotification severities onto theme tokens (20 -> 18)
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
    "slm:bg-amber-100": 4,  # #20644 SLM Vision/Batch views retired: 19 -> 18
    "slm:bg-amber-200": 3,  # #20644 SLM Vision/Batch views retired: 4 -> 3
    "slm:bg-amber-300": 1,
    "slm:bg-amber-500": 1,
    "slm:bg-amber-500/10": 1,
    "slm:bg-amber-500/15": 1,
    "slm:bg-amber-500/20": 2,
    "slm:bg-amber-900/30": 1,
    "slm:bg-blue-100": 28,  # #20644 SLM Vision/Batch views retired: 52 -> 50
    "slm:bg-blue-200": 4,
    "slm:bg-blue-50": 7,  # #18863 SLM notices onto BaseAlert (19 -> 17)
    "slm:bg-blue-500": 4,  # #14777 batch 2: 12 -> 11; #20644 SLM Vision/Batch views retired: 11 -> 10
    "slm:bg-blue-600": 23,
    "slm:bg-blue-700": 14,
    "slm:bg-blue-900/30": 1,
    "slm:bg-cyan-100": 1,
    "slm:bg-cyan-50": 1,
    "slm:bg-cyan-500": 2,
    "slm:bg-cyan-500/20": 1,  # #17562: 2 -> 1
    "slm:bg-emerald-400": 1,
    "slm:bg-emerald-500/20": 2,
    "slm:bg-emerald-600": 3,
    "slm:bg-emerald-700": 1,
    "slm:bg-gray-100": 88,  # #20644 SLM Vision/Batch views retired: 197 -> 193
    "slm:bg-gray-200": 25,  # #20644 SLM Vision/Batch views retired: 92 -> 91
    "slm:bg-gray-300": 1,
    "slm:bg-gray-400": 17,  # #20644 SLM Vision/Batch views retired: 41 -> 40
    "slm:bg-gray-50": 80,  # #20644 SLM Vision/Batch views retired: 235 -> 233
    "slm:bg-gray-500": 2,
    "slm:bg-gray-500/20": 2,  # #17562: 4 -> 2
    "slm:bg-gray-600": 5,  # #14777 batch 2: 9 -> 8
    "slm:bg-gray-700": 6,  # #14777 batch 2: 12 -> 10
    "slm:bg-gray-800": 22,  # #14777: 26 -> 22, SLM dialogs moved onto the kit BaseModal
    "slm:bg-gray-900": 21,  # #14777 batch 2: 31 -> 30
    "slm:bg-gray-950": 1,
    "slm:bg-green-100": 28,  # #20644 SLM Vision/Batch views retired: 62 -> 60
    "slm:bg-green-200": 1,
    "slm:bg-green-50": 9,  # #18863 SLM notices onto BaseAlert (18 -> 17)
    "slm:bg-green-500": 11,  # #20644 SLM Vision/Batch views retired: 55 -> 54
    "slm:bg-green-600": 3,
    "slm:bg-green-700": 3,
    "slm:bg-indigo-100": 2,
    "slm:bg-indigo-200": 1,
    "slm:bg-indigo-50": 1,
    "slm:bg-indigo-600": 1,
    "slm:bg-indigo-700": 1,
    "slm:bg-orange-100": 13,  # #14777: 16 -> 15, SLM dialogs moved onto the kit BaseModal
    "slm:bg-orange-200": 2,
    "slm:bg-orange-50": 1,
    "slm:bg-orange-500": 2,
    "slm:bg-orange-600": 4,
    "slm:bg-orange-700": 4,
    "slm:bg-purple-100": 5,
    "slm:bg-purple-200": 3,
    "slm:bg-purple-50": 1,
    "slm:bg-purple-500": 3,
    "slm:bg-purple-600": 2,
    "slm:bg-purple-700": 2,
    "slm:bg-purple-900/30": 1,
    "slm:bg-red-100": 33,  # #20644 SLM Vision/Batch views retired: 69 -> 66
    "slm:bg-red-200": 5,  # #20644 SLM Vision/Batch views retired: 10 -> 9
    "slm:bg-red-400": 1,
    "slm:bg-red-50": 8,  # #20644 SLM Vision/Batch views retired: 27 -> 26
    "slm:bg-red-500": 8,  # #20644 SLM Vision/Batch views retired: 46 -> 45
    "slm:bg-red-500/20": 2,
    "slm:bg-red-600": 3,
    "slm:bg-red-700": 4,
    "slm:bg-red-800": 1,
    "slm:bg-red-900/30": 1,
    "slm:bg-slate-900": 2,
    "slm:bg-yellow-100": 21,  # #20644 SLM Vision/Batch views retired: 38 -> 37
    "slm:bg-yellow-400": 1,
    "slm:bg-yellow-50": 2,  # #18863 SLM notices onto BaseAlert (17 -> 6)
    "slm:bg-yellow-500": 4,  # #18863 SLM notices onto BaseAlert (21 -> 20)
    "slm:border-amber-500/30": 5,
    "slm:border-blue-100": 1,
    "slm:border-blue-200": 2,  # #18863 SLM notices onto BaseAlert (9 -> 7)
    "slm:border-blue-300": 1,
    "slm:border-blue-400": 1,
    "slm:border-blue-500": 15,
    "slm:border-blue-500/30": 1,  # #17562: 2 -> 1
    "slm:border-blue-600": 1,
    "slm:border-cyan-500/30": 1,  # #17562: 2 -> 1
    "slm:border-emerald-500/30": 2,
    "slm:border-gray-100": 12,  # #17562: 55 -> 54
    "slm:border-gray-200": 73,  # #20644 SLM Vision/Batch views retired: 305 -> 290
    "slm:border-gray-300": 104,  # #14780 BaseSwitch: 340 -> 322; #20644 SLM Vision/Batch views retired: 322 -> 315
    "slm:border-gray-50": 4,
    "slm:border-gray-500": 1,
    "slm:border-gray-500/30": 2,  # #17562: 4 -> 2
    "slm:border-gray-600": 14,
    "slm:border-gray-700": 23,  # #14777 batch 2: 27 -> 26  # #17562: 26 -> 23
    "slm:border-gray-700/50": 1,
    "slm:border-gray-800": 3,  # #17562: 5 -> 3
    "slm:border-green-200": 1,  # #18863 SLM notices onto BaseAlert (4 -> 3)
    "slm:border-green-300": 6,
    "slm:border-orange-200": 1,
    "slm:border-purple-500/30": 1,  # #17562: 2 -> 1
    "slm:border-red-200": 1,  # #18819: 77 -> 6, hand-rolled notices moved to the kit BaseAlert
    "slm:border-red-300": 6,
    "slm:border-red-500/30": 3,
    "slm:border-yellow-200": 1,  # #18863 SLM notices onto BaseAlert (13 -> 4)
    "slm:border-yellow-300": 3,  # #18819: 4 -> 3, hand-rolled notices moved to the kit BaseAlert
    "slm:divide-gray-100": 2,
    "slm:divide-gray-200": 25,
    "slm:placeholder-gray-500": 1,
    "slm:ring-blue-500": 2,
    "slm:text-amber-200": 1,
    "slm:text-amber-300": 4,
    "slm:text-amber-400": 2,
    "slm:text-amber-600": 6,  # #18863 SLM notices onto BaseAlert (22 -> 18)
    "slm:text-amber-700": 7,  # #20644 SLM Vision/Batch views retired: 19 -> 18
    "slm:text-amber-800": 3,  # #18863 SLM notices onto BaseAlert (8 -> 6)
    "slm:text-blue-300": 1,  # #17562: 2 -> 1
    "slm:text-blue-400": 3,
    "slm:text-blue-600": 24,  # #20644 SLM Vision/Batch views retired: 44 -> 42
    "slm:text-blue-700": 19,  # #18863 SLM notices onto BaseAlert (39 -> 37)
    "slm:text-blue-800": 11,  # #20644 SLM Vision/Batch views retired: 23 -> 22
    "slm:text-blue-900": 1,  # #18863 SLM notices onto BaseAlert (2 -> 1)
    "slm:text-cyan-300": 1,  # #17562: 2 -> 1
    "slm:text-cyan-400": 4,
    "slm:text-cyan-600": 1,
    "slm:text-cyan-800": 2,
    "slm:text-cyan-900": 1,
    "slm:text-emerald-300": 2,
    "slm:text-emerald-400": 2,
    "slm:text-gray-100": 11,  # #14777: 14 -> 12, SLM dialogs moved onto the kit BaseModal
    "slm:text-gray-200": 5,  # #17562: 6 -> 5
    "slm:text-gray-300": 39,  # #14777 batch 2: 51 -> 50  # #17562: 50 -> 46
    "slm:text-gray-400": 104,  # #20644 SLM Vision/Batch views retired: 208 -> 205
    "slm:text-gray-500": 402,  # #20644 SLM Vision/Batch views retired: 866 -> 853
    "slm:text-gray-600": 100,  # #20644 SLM Vision/Batch views retired: 264 -> 251
    "slm:text-gray-700": 164,  # #18734: 431 -> 428; #20644 SLM Vision/Batch views retired: 428 -> 421
    "slm:text-gray-800": 24,  # #20644 SLM Vision/Batch views retired: 40 -> 36
    "slm:text-gray-900": 146,  # #20644 SLM Vision/Batch views retired: 437 -> 422
    "slm:text-green-300": 3,
    "slm:text-green-400": 2,
    "slm:text-green-500": 1,  # #18863 SLM notices onto BaseAlert (5 -> 2)
    "slm:text-green-600": 30,  # #20644 SLM Vision/Batch views retired: 66 -> 64
    "slm:text-green-700": 21,  # #18863 SLM notices onto BaseAlert (73 -> 47)
    "slm:text-green-800": 17,  # #20644 SLM Vision/Batch views retired: 26 -> 25
    "slm:text-green-900": 1,  # #18863 SLM notices onto BaseAlert (2 -> 1)
    "slm:text-indigo-700": 3,
    "slm:text-orange-600": 13,  # #14777: 18 -> 17, SLM dialogs moved onto the kit BaseModal
    "slm:text-orange-700": 6,
    "slm:text-orange-800": 5,
    "slm:text-purple-300": 1,  # #17562: 2 -> 1
    "slm:text-purple-400": 1,
    "slm:text-purple-600": 2,
    "slm:text-purple-700": 4,
    "slm:text-purple-800": 2,
    "slm:text-purple-900": 1,
    "slm:text-red-300": 3,
    "slm:text-red-400": 3,
    "slm:text-red-500": 5,  # #18819: 23 -> 12, hand-rolled notices moved to the kit BaseAlert
    "slm:text-red-600": 35,  # #20644 SLM Vision/Batch views retired: 85 -> 81
    "slm:text-red-700": 33,  # #20644 SLM Vision/Batch views retired: 71 -> 70
    "slm:text-red-800": 13,  # #20644 SLM Vision/Batch views retired: 31 -> 30
    "slm:text-slate-400": 1,
    "slm:text-yellow-300": 1,
    "slm:text-yellow-400": 2,
    "slm:text-yellow-600": 18,  # #18863 SLM notices onto BaseAlert (40 -> 32)
    "slm:text-yellow-700": 11,  # #18863 SLM notices onto BaseAlert (32 -> 24)
    "slm:text-yellow-800": 13,  # #20644 SLM Vision/Batch views retired: 19 -> 18
}

# No hand-maintained total (#19283): a raised entry is caught by comparing each entry with this
# table at the base commit (repo_tests/_ratchet_base.py), so PRs lowering different entries
# never edit a shared line.
