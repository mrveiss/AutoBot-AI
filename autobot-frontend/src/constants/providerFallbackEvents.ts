// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Provider Fallback Event Constants (#11996 / umbrella #11994)
 *
 * Canonical real-time event emitted by the backend when the LLM router falls
 * back from a primary model/provider to a secondary one (rate limit, error,
 * or full-chain exhaustion). Emitted on the "global" live-event channel by
 * `llm_shared/fallback_events.emit_fallback_event` (#11995).
 *
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 */

/**
 * Live-event type string for a provider/model fallback decision (#11995).
 * Matches `events.event_types.PROVIDER_FALLBACK` on the backend.
 */
export const PROVIDER_FALLBACK = 'provider_fallback' as const

/**
 * Payload shape of a PROVIDER_FALLBACK live event (built by
 * `_build_fallback_payload` in `llm_shared/fallback_events.py`).
 */
export interface ProviderFallbackPayload {
  conversation_id: string
  request_id: string | null
  primary_model: string
  primary_provider: string | null
  fallback_model: string | null
  fallback_provider: string | null
  reason: string
  chain_tried: string[]
  degraded_skipped: string[]
  exhausted: boolean
  /** Seconds since epoch (float), as emitted by `time.time()`. */
  timestamp: number
  // Payloads arrive as plain JSON records — extra fields pass through, and the
  // index signature keeps Record<string, unknown> casts valid.
  [key: string]: unknown
}

/**
 * One entry of the `active_fallbacks` array returned by
 * `GET /api/llm/fallback-status` — the reclaimed `llm:fallback:active:*`
 * Redis write (GH#8998 / #11995). Note this is a NARROWER shape than the live
 * event payload (only successful hops are persisted, with an int timestamp).
 */
export interface ActiveFallbackEntry {
  conversation_id: string
  primary_model: string
  fallback_model: string
  primary_provider: string
  fallback_provider: string
  /** Seconds since epoch (int). */
  timestamp: number
  [key: string]: unknown
}

/** One configured fallback chain from `GET /api/llm/fallback-status`. */
export interface ConfiguredFallbackChain {
  primary_model: string
  /** Human-readable chain, e.g. "gpt-4o → claude-3-5-sonnet". */
  fallback_chain: string
  provider: string
  [key: string]: unknown
}

/** Full response shape of `GET /api/llm/fallback-status` (#9421 / #11995). */
export interface FallbackStatusResponse {
  configured_chains: ConfiguredFallbackChain[]
  active_fallbacks: ActiveFallbackEntry[]
}
