// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * @autobot/ui — the agent-ledger row shapes, declared once for both consoles (#19910).
 *
 * Mirrors `autobot_shared/coordination/ledger_schemas.py`, which the Company OS ledger
 * (`/coordination/ledger/*`) and the SLM admin ledger (`/monitoring/agent-ledger/*`) both
 * serve. Each app's generated `components['schemas']` carries the same fields; a row
 * keeps the schema's open index signature because the backend models allow extras.
 */

type Extra = { [key: string]: unknown }

export type ClaimRow = {
  scope: string
  kind: string
  agent_id: string
  task_id: string
  mode: string
  intent: string
  acquired_at: string
  expires_at: string
  /** Explicit renewals since the claim was acquired. */
  renewals: number
  /** Stamped at write time; null = install-wide or legacy. */
  company_id?: string | null
} & Extra

export type PresenceTaskRow = { id: string; title: string } & Extra

export type PresenceRow = {
  kind: string
  tenant_id: string | null
  name: string
  busy: boolean
  detail?: string | null
  /** Null when idle, or when the agent's kind has no notion of a task. */
  current_task?: PresenceTaskRow | null
  last_seen: number
} & Extra

export type ActivityRow = {
  at: string
  type: string
  scope?: string | null
  agent_id?: string | null
  task_id?: string | null
  detail: string
} & Extra

export type ConflictRow = {
  at: string
  kind: 'release_refused' | 'claim_expired' | 'yield_unanswered' | 'claim_lapsed_during_action'
  scope?: string | null
  agent_id?: string | null
  task_id?: string | null
  /** The holder, for a refused release. */
  other_agent_id?: string | null
  detail: string
} & Extra

export type PeerMessageRow = {
  recipient_kind: string
  recipient_name: string
  pending: number
  senders: string[]
  oldest_at: number
  /** The owning company; set in the install-wide (SLM) view, null in a company's own. */
  tenant_id?: string | null
} & Extra

export type IdleSubscriberRow = {
  subscriber: string
  target_kind: string
  target_name: string
  since: number
  expires_at: number
  /** The owning company; set in the install-wide (SLM) view, null in a company's own. */
  tenant_id?: string | null
} & Extra
