// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// #20519: the one place an agent is given a label a person can tell apart.
//
// Names are not unique within a company (the server stores whatever it is given and
// existing rows are not rewritten), so every list and picker labels through here:
// the name alone when it is unique, the name plus the role or adapter when two agents
// share a name, and a short id suffix only when even that is shared. Whether an agent
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

/** Display label for every agent in `agents`, keyed by `id`. */
export function agentLabelMap(agents: readonly LabelledAgent[]): Map<string, string> {
  const byName = countBy(agents, nameKey)
  const byNameAndQualifier = countBy(agents, (a) => `${nameKey(a)}\u0000${qualifier(a).toLowerCase()}`)
  const labels = new Map<string, string>()
  for (const a of agents) {
    if ((byName.get(nameKey(a)) ?? 0) < 2) {
      labels.set(a.id, a.name)
      continue
    }
    const q = qualifier(a)
    const base = q ? `${a.name}${SEPARATOR}${q}` : a.name
    const clash = (byNameAndQualifier.get(`${nameKey(a)}\u0000${q.toLowerCase()}`) ?? 0) > 1
    labels.set(a.id, clash ? `${base} #${a.id.slice(-SUFFIX_LENGTH)}` : base)
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
