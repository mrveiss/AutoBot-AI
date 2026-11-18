// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * @autobot/ui — shared duration-formatting vocabulary (#14908).
 *
 * `DurationStyle` was declared identically in both apps. `formatDuration` and the other
 * byte/uptime formatters that take it live beside it in `./format.ts`.
 */

/** Numeric duration-formatting style accepted by `formatDuration(value, { style })`. */
export type DurationStyle = 'msSeconds2dp' | 'secondsCompact' | 'clock' | 'msMinutes' | 'msCompound' | 'msSeconds1dp' | 'msSecondsMinutes' | 'msMinutesSeconds'
