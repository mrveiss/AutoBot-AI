// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// The risk ladder RiskBadge renders (#13422). The backend owns it
// (autobot_shared/risk_tier.py, owner decision 2026-10-12) and sends it as
// `risk_tier`; this is the kit's view of that generated `RiskTier` schema, and
// each app checks at compile time that the two stay identical.

/** Ascending risk tiers. */
export const RISK_TIERS = ['low', 'medium', 'high', 'critical'] as const
export type RiskTier = (typeof RISK_TIERS)[number]
