// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// #20519: the one place an agent is given a label a person can tell apart.
//
// Names are not unique within a company (the server stores whatever it is given and
// existing rows are not rewritten), so every list and picker labels through here:
// the name alone when it is unique, the name plus the role or adapter when two agents
// share a name, and an id suffix only when even that is shared -- 4 characters, longer
// when two clashing ids end alike (#20706), so no two labels are the same. Whether an agent
// can run is never decided here -- `can_run` / `cannot_run_reason` come from the server.

export interface LabelledAgent {
  /** Stable key within one list (slug or node id, whichever that list uses). */
  id: string
  name: string
  title?: string | null
  adapter_type?: string | null
  can_run?: boolean | null
  cannot_run_reason?: string | null
}

const SEPARATOR = ' — '
const SUFFIX_LENGTH = 4

function qualifier(agent: LabelledAgent): string {
  return (agent.title || agent.adapter_type || '').trim()
}

function nameKey(agent: LabelledAgent): string {
  return agent.name.trim().toLowerCase()
}

function countBy(agents: readonly LabelledAgent[], key: (a: LabelledAgent) => string): Map<string, number> {
  const counts = new Map<string, number>()
  for (const a of agents) counts.set(key(a), (counts.get(key(a)) ?? 0) + 1)
  return counts
}

function clashKey(agent: LabelledAgent): string {
  return `${nameKey(agent)}\u0000${qualifier(agent).toLowerCase()}`
}

/** The shortest id suffix, at least SUFFIX_LENGTH long, that no two of `ids` share. */
function suffixLength(ids: readonly string[]): number {
  const longest = Math.max(...ids.map((id) => id.length))
  let length = SUFFIX_LENGTH
  while (length < longest && new Set(ids.map((id) => id.slice(-length))).size < ids.length) length += 1
  return length
}

/** Display label for every agent in `agents`, keyed by `id`. */
export function agentLabelMap(agents: readonly LabelledAgent[]): Map<string, string> {
  const byName = countBy(agents, nameKey)
  const clashing = new Map<string, string[]>()
  for (const a of agents) clashing.set(clashKey(a), [...(clashing.get(clashKey(a)) ?? []), a.id])
  const labels = new Map<string, string>()
  for (const a of agents) {
    if ((byName.get(nameKey(a)) ?? 0) < 2) {
      labels.set(a.id, a.name)
      continue
    }
    const q = qualifier(a)
    const base = q ? `${a.name}${SEPARATOR}${q}` : a.name
    const peers = clashing.get(clashKey(a)) ?? []
    labels.set(a.id, peers.length > 1 ? `${base} #${a.id.slice(-suffixLength(peers))}` : base)
  }
  return labels
}

/** The label of one agent among its peers, or `fallback` for an id no agent has. */
export function agentLabel(id: string, agents: readonly LabelledAgent[], fallback = id): string {
  return agentLabelMap(agents).get(id) ?? fallback
}

/**
 * Text for an `<option>`: the label, and when the server says the agent cannot run,
 * `cannotRunText` (an i18n string supplied by the caller) so it is not picked blind.
 */
export function agentOptionText(
  agent: LabelledAgent,
  labels: ReadonlyMap<string, string>,
  cannotRunText: string,
): string {
  const label = labels.get(agent.id) ?? agent.name
  return agent.can_run === false ? `${label} (${cannotRunText})` : label
}
