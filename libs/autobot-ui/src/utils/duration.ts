// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * @autobot/ui — shared duration-formatting vocabulary (#14908).
 *
 * `formatHelpers.ts` is declared once per app because the surrounding
 * formatting logic differs (577 vs 215 lines). `DurationStyle` itself was
 * declared identically in both — the low-risk starting point the issue
 * calls out. Only the type moves here; `formatDuration` and the rest of
 * each app's `formatHelpers.ts` stay per-app pending a full diff.
 */

/** Numeric duration-formatting style accepted by `formatDuration(value, { style })`. */
export type DurationStyle = 'msSeconds2dp' | 'secondsCompact' | 'clock' | 'msMinutes'
