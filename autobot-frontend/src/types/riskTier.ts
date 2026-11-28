// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * The risk tier the backend sends as `risk_tier` (#13422): the four-rung ladder from
 * autobot_shared/risk_tier.py, generated as `components['schemas']['RiskTier']`. The kit's
 * RiskBadge has its own copy of the union, because it cannot import app types; the check
 * below fails vue-tsc if the two ever differ in either direction.
 */
import type { RiskTier as KitRiskTier } from '@autobot/ui'
import type { components } from '@/types/generated/api'

export type RiskTier = components['schemas']['RiskTier']

type Same<A, B> = [A] extends [B] ? ([B] extends [A] ? true : false) : false
/** Compile-time only: `true` is assignable only while the kit and generated ladders match. */
export const RISK_TIER_MATCHES_KIT: Same<RiskTier, KitRiskTier> = true
