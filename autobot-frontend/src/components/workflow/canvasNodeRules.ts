// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Declarative colour rules for Company OS canvas nodes (GH#13941).
 *
 * A rule is data: a predicate over the facts a node already carries, plus the
 * presentation it selects (a token-backed swatch class, a shape, and a label).
 * The canvas evaluates one dimension at a time — first matching rule wins, and
 * every dimension ends in a catch-all so a node always resolves to exactly one
 * rule. The legend is derived from the same evaluation, so it can only ever
 * list rules that actually won on a node currently drawn.
 *
 * Presentation only. Nothing here fetches, authorises or persists anything.
 *
 * No new status vocabulary is introduced: the status dimension is generated
 * from `AgentDisplayStatus` (`composables/llc/llcStatus.ts`, the frontend SSOT
 * for the org-chart node status), so widening that union is a compile error
 * here rather than a silently uncoloured node. The repo already carries nine
 * competing status vocabularies (GH#13485); a tenth would be a defect.
 *
 * Lives beside `canvasNode.ts` rather than under `composables/llc/` because
 * these are the canvas's own presentation rules — putting them in the LLC
 * layer would make `WorkflowCanvas.vue` (a workflow component) depend on it at
 * runtime. The only LLC import below is a *type*.
 */

import type { CanvasNode } from './canvasNode'
import type { AgentDisplayStatus } from '@/composables/llc/llcStatus'

/** The dimensions a node can be coloured by, in the order the UI offers them. */
export const RULE_DIMENSIONS = ['status', 'owner', 'tool'] as const

export type CanvasRuleDimension = (typeof RULE_DIMENSIONS)[number]

/**
 * The non-colour half of a rule's signal. Colour is never allowed to be the
 * only differentiator, so every rule also selects a marker shape — and the
 * label text is rendered next to it, on the node and in the legend alike.
 */
export type CanvasRuleShape = 'disc' | 'ring' | 'square' | 'diamond' | 'triangle' | 'bar'

/** The facts a rule may look at. Read off a node's existing `data` bag. */
export interface CanvasNodeFacts {
  /** Org-chart node status, lower-cased. '' when the node carries none. */
  status: string
  /** `data.is_human` — the person/agent discriminator (GH#13936). */
  isHuman: boolean
  /** `data.adapter_type` — the executing tool of an agent. '' when absent. */
  adapterType: string
}

export interface CanvasNodeRule {
  /** Stable identity, unique within its dimension. Rendered as a data attr. */
  id: string
  dimension: CanvasRuleDimension
  /** Enumerable CSS class suffix — `rule-<swatch>` binds the colour token. */
  swatch: string
  shape: CanvasRuleShape
  /** i18n key for the label, or `null` when the label is a data value. */
  labelKey: string | null
  /** Literal label taken from the data (never a UI string), or `null`. */
  labelText: string | null
  matches: (facts: CanvasNodeFacts) => boolean
}

/**
 * Shape per agent status. A `Record` over the SSOT union rather than a list, so
 * a new member of `AgentDisplayStatus` fails type-check here instead of falling
 * through to "unknown" on screen.
 */
const STATUS_SHAPES: Record<AgentDisplayStatus, CanvasRuleShape> = {
  active: 'disc',
  idle: 'ring',
  paused: 'bar',
  error: 'triangle',
  terminated: 'square',
}

/** Catch-all appended to every dimension so a node always resolves to a rule. */
function fallbackRule(
  dimension: CanvasRuleDimension,
  swatch: string,
  shape: CanvasRuleShape,
  labelKey: string,
): CanvasNodeRule {
  return {
    id: swatch,
    dimension,
    swatch,
    shape,
    labelKey,
    labelText: null,
    matches: () => true,
  }
}

/** Status rules, generated from the SSOT union, ordered as declared above. */
export const STATUS_RULES: readonly CanvasNodeRule[] = [
  ...(Object.keys(STATUS_SHAPES) as AgentDisplayStatus[]).map((status) => ({
    id: `status-${status}`,
    dimension: 'status' as const,
    swatch: `status-${status}`,
    shape: STATUS_SHAPES[status],
    labelKey: `llc.canvasRules.status.${status}`,
    labelText: null,
    matches: (facts: CanvasNodeFacts) => facts.status === status,
  })),
  fallbackRule('status', 'status-unknown', 'diamond', 'llc.canvasRules.status.unknown'),
]

/**
 * Owner-kind rules. `is_human` is the discriminator the org chart already
 * carries; a node with neither a human flag nor an adapter has no owner
 * information at all, which is exactly the gap the legend exists to surface.
 */
export const OWNER_RULES: readonly CanvasNodeRule[] = [
  {
    id: 'owner-human',
    dimension: 'owner',
    swatch: 'owner-human',
    shape: 'disc',
    labelKey: 'llc.orgChart.human',
    labelText: null,
    matches: (facts) => facts.isHuman,
  },
  {
    id: 'owner-agent',
    dimension: 'owner',
    swatch: 'owner-agent',
    shape: 'square',
    labelKey: 'llc.orgChart.aiAgent',
    labelText: null,
    matches: (facts) => !facts.isHuman && facts.adapterType !== '',
  },
  fallbackRule('owner', 'owner-unassigned', 'diamond', 'llc.canvasRules.owner.unassigned'),
]

/** Palette slots available to the tool dimension (`--chart-1` … `--chart-8`). */
const TOOL_PALETTE_SIZE = 8

/** Shapes cycled alongside the palette so two tools differ by more than hue. */
const TOOL_SHAPES: readonly CanvasRuleShape[] = [
  'disc',
  'square',
  'diamond',
  'triangle',
  'ring',
  'bar',
]

/**
 * Tool rules are derived from the data, not declared: `adapter_type` is an open
 * set (eight execution adapters today), and enumerating it here would fork a
 * backend vocabulary into the frontend. Labels are therefore the raw data value
 * — not a UI string — while the dimension name and the "no tool" bucket are
 * translated.
 *
 * Ordering is by sorted tool name so the palette assignment is deterministic
 * across renders and machines.
 */
export function toolRules(facts: readonly CanvasNodeFacts[]): CanvasNodeRule[] {
  const tools = [
    ...new Set(facts.filter((f) => !f.isHuman && f.adapterType !== '').map((f) => f.adapterType)),
  ].sort()
  const rules: CanvasNodeRule[] = tools.map((tool, index) => ({
    id: `tool-${tool}`,
    dimension: 'tool' as const,
    swatch: `tool-${(index % TOOL_PALETTE_SIZE) + 1}`,
    shape: TOOL_SHAPES[index % TOOL_SHAPES.length],
    labelKey: null,
    labelText: tool,
    matches: (candidate: CanvasNodeFacts) =>
      !candidate.isHuman && candidate.adapterType === tool,
  }))
  rules.push(fallbackRule('tool', 'tool-none', 'bar', 'llc.canvasRules.tool.none'))
  return rules
}

/** The rule set for one dimension, given the nodes currently on the canvas. */
export function rulesForDimension(
  dimension: CanvasRuleDimension,
  facts: readonly CanvasNodeFacts[],
): readonly CanvasNodeRule[] {
  if (dimension === 'status') return STATUS_RULES
  if (dimension === 'owner') return OWNER_RULES
  return toolRules(facts)
}

/**
 * Facts for a node, or `null` when the node is not one the rules apply to.
 * Only `org-person` nodes carry owner/status/tool facts; workflow authoring
 * nodes are left exactly as they were.
 */
export function orgNodeFacts(node: CanvasNode): CanvasNodeFacts | null {
  if (node.type !== 'org-person') return null
  const data = node.data as Record<string, unknown>
  return {
    status: typeof data.status === 'string' ? data.status.trim().toLowerCase() : '',
    isHuman: data.is_human === true,
    adapterType: typeof data.adapter_type === 'string' ? data.adapter_type.trim() : '',
  }
}

/** First matching rule. The catch-all guarantees a result. */
export function matchRule(
  rules: readonly CanvasNodeRule[],
  facts: CanvasNodeFacts,
): CanvasNodeRule {
  return rules.find((rule) => rule.matches(facts)) ?? rules[rules.length - 1]
}

/**
 * The rules the legend must show: those that *won* on at least one node drawn.
 *
 * Deliberately not `rule.matches(facts)` — a later rule can match a node that
 * an earlier rule already claimed, and listing it would put a swatch in the
 * legend that appears nowhere on the canvas.
 */
export function activeRules(
  rules: readonly CanvasNodeRule[],
  facts: readonly CanvasNodeFacts[],
): CanvasNodeRule[] {
  const won = new Set(facts.map((item) => matchRule(rules, item).id))
  return rules.filter((rule) => won.has(rule.id))
}
