// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// SemanticVariant — the single canonical presentational colour vocabulary for
// the whole design system (#10885). Badge/Alert/status-pill style props map
// onto this ONE type so a status→colour mapping is defined once instead of
// being re-declared as a `*Variant` union per component.
//
// This is the presentational vocabulary ONLY. Genuinely domain-specific status
// enums (ConnectionStatus, ServiceHealthStatus, ProgressStatus, NodeStatus, …)
// carry meaning beyond colour and MUST keep their own types — do not collapse
// them into this.

export type SemanticVariant = 'neutral' | 'primary' | 'success' | 'warning' | 'danger' | 'info'

// Alias kept for call-sites that read the value as a "colour" rather than a
// component "variant"; identical vocabulary, one source of truth.
export type SemanticColor = SemanticVariant
