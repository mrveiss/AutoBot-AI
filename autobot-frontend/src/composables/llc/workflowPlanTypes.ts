// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Workflow Planner types and pure helpers (#19938).
 *
 * Every shape comes from the generated API types; nothing is re-declared by hand. The helpers
 * hold the planner's pure rules (which statuses the screens can show, how a map edit builds its
 * PUT body) so the components stay thin and the rules are testable without mounting.
 */
import type { components } from '@/types/generated/api'

type S = components['schemas']

export type Plan = S['CompanyWorkflowPlan']
export type PlanSummary = S['PlanSummary']
export type PlanStatus = S['WorkflowPlanStatus']
export type Lane = S['Lane']
export type Step = S['Step']
export type Edge = S['Edge']
export type SubStep = S['SubStep']
export type EdgeCase = S['EdgeCase']
export type StepMetric = S['StepMetric']
export type Label = S['Label']
export type MetricSource = S['MetricSource']
export type GateResponse = S['GateResponse']
export type GateItem = S['GateItem']
export type PlanConversion = S['PlanConversion']
export type WorkflowDraft = S['WorkflowDraft']
export type MapBody = S['MapBody']
export type MapResponse = S['MapResponse']
export type OneNumberBody = S['OneNumberBody']
export type BreakdownBody = S['BreakdownBody']
export type PlanCreate = S['PlanCreate']

/** Statuses whose map, metrics and labels can still be edited; approved and converted are read-only. */
export const ACTIVE_STATUSES: readonly PlanStatus[] = ['draft', 'measured', 'labeled'] as const
export const STATUS_ORDER: readonly PlanStatus[] = [
  'draft',
  'measured',
  'labeled',
  'approved',
  'converted',
] as const
export const LABELS: readonly Label[] = ['ai', 'automation', 'by_hand'] as const

/** Design tokens the three labels use until dedicated label tokens exist (#13935 D6). */
export const LABEL_COLOR_VAR: Record<Label, string> = {
  ai: 'var(--color-purple)',
  automation: 'var(--color-info)',
  by_hand: 'var(--color-warning)',
}

export function isActiveStatus(status: PlanStatus): boolean {
  return ACTIVE_STATUSES.includes(status)
}

/** ApiClient throws `HTTP <status>: <detail>`; a 404 on the list route is the flag being off. */
export function isNotFoundError(err: unknown): boolean {
  return err instanceof Error && /^HTTP 404\b/.test(err.message)
}

export function slugKey(prefix: string, taken: readonly string[]): string {
  let n = taken.length + 1
  while (taken.includes(`${prefix}-${n}`)) n += 1
  return `${prefix}-${n}`
}

export function mapBodyOf(plan: Plan): MapBody {
  return { lanes: plan.lanes ?? [], steps: plan.steps ?? [], edges: plan.edges ?? [] }
}

export function withLane(plan: Plan, name: string): MapBody {
  const map = mapBodyOf(plan)
  const lanes = map.lanes ?? []
  const lane: Lane = {
    key: slugKey('lane', lanes.map((l) => l.key)),
    name,
    holder_kind: 'user',
    position: lanes.length,
  }
  return { ...map, lanes: [...lanes, lane] }
}

/** A new step is chained after the plan's last step, so the map stays one connected flow. */
export function withStep(plan: Plan, label: string, laneKey: string): MapBody {
  const map = mapBodyOf(plan)
  const steps = map.steps ?? []
  const step: Step = {
    key: slugKey('step', steps.map((s) => s.key)),
    lane_key: laneKey,
    label,
    position: steps.length,
  }
  const last = steps[steps.length - 1]
  const edges = last ? [...(map.edges ?? []), { from_step: last.key, to_step: step.key }] : map.edges
  return { ...map, steps: [...steps, step], edges }
}

export function metricFor(plan: Plan, stepKey: string): StepMetric | undefined {
  return (plan.step_metrics ?? []).find((m) => m.step_key === stepKey)
}

export function subStepsFor(plan: Plan, stepKey: string): SubStep[] {
  return (plan.sub_steps ?? []).filter((s) => s.step_key === stepKey)
}

export function edgeCasesFor(plan: Plan, stepKey: string): EdgeCase[] {
  return (plan.edge_cases ?? []).filter((c) => c.step_key === stepKey)
}

export function laneName(plan: Plan, laneKey: string): string {
  return (plan.lanes ?? []).find((l) => l.key === laneKey)?.name ?? laneKey
}

/** Today's flow: a new sub-step is added as "current", unlabelled until the owner decides. */
export function breakdownWith(plan: Plan, stepKey: string, label: string): BreakdownBody {
  const subs = subStepsFor(plan, stepKey)
  const added = {
    key: slugKey('sub', (plan.sub_steps ?? []).map((s) => s.key)),
    label,
    state: 'current' as const,
  }
  const kept = subs.map((s) => ({
    key: s.key,
    label: s.label,
    state: s.state,
    classification: s.classification ?? null,
    rationale: s.rationale ?? null,
    tool_action: s.tool_action ?? null,
    replaces: s.replaces ?? [],
  }))
  const cases = edgeCasesFor(plan, stepKey).map((c) => ({
    key: c.key,
    description: c.description,
    classification: c.classification,
    handling: c.handling ?? null,
    sub_step_key: c.sub_step_key ?? null,
  }))
  return { sub_steps: [...kept, added], edge_cases: cases }
}

const ENTRY_POINTS: readonly PlanCreate['entry_point'][] = ['org_chart', 'wizard_exit', 'workflow_area', 'replan']

/** The entry point a deep link names; anything unknown is the Org Chart. */
export function plannerEntryPoint(raw: unknown): PlanCreate['entry_point'] {
  return ENTRY_POINTS.find((e) => e === raw) ?? 'org_chart'
}
