// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * A workflow graph written out in plain words for the Handbook (#18431). The graph is the
 * company model's own (`GET /company-os/workflows/{id}/graph`); nothing here is invented, each
 * line is one node and what its typed edges do ("If it fails: retry 2x then ...").
 */
import type { components } from '@/types/generated/api'

type GraphSpec = components['schemas']['GraphSpec']
type NodeSpec = components['schemas']['NodeSpec']
type TransitionSpec = components['schemas']['TransitionSpec']

export type Translate = (key: string, params?: Record<string, unknown>) => string

export interface GraphNames {
  process: (key: string) => string
  workflow: (id: string) => string
}

export interface StepLine {
  key: string
  title: string
  outcomes: string[]
}

function nodeTitle(node: NodeSpec, names: GraphNames, t: Translate): string {
  if (node.kind === 'start') return t('llc.handbook.step.start')
  if (node.kind === 'end') return t(`llc.handbook.step.end.${node.end_outcome ?? 'done'}`)
  if (node.kind === 'meta_skill') {
    return t('llc.handbook.step.metaSkill', { name: node.label || names.workflow(node.meta_skill_id ?? node.key) })
  }
  return node.label || names.process(node.process_key ?? node.key)
}

function outcomeText(tr: TransitionSpec, target: string, names: GraphNames, t: Translate): string {
  const to = { target }
  if (tr.kind === 'handoff') return t('llc.handbook.step.handoff', { workflow: names.workflow(tr.handoff_workflow_id ?? '') })
  if (tr.kind === 'if') return t('llc.handbook.step.if', { condition: tr.condition ?? '', ...to })
  if (tr.kind === 'timeout') return t('llc.handbook.step.timeout', { seconds: tr.timeout_seconds ?? 0, ...to })
  if (tr.kind === 'failure') {
    return tr.retry_max ? t('llc.handbook.step.failureRetry', { n: tr.retry_max, ...to }) : t('llc.handbook.step.failure', to)
  }
  return t(`llc.handbook.step.${tr.kind === 'else' ? 'else' : 'success'}`, to)
}

/** Nodes from the start node outward, then any the walk did not reach, in stored order. */
function orderNodes(graph: GraphSpec): NodeSpec[] {
  const nodes = graph.nodes ?? []
  const byKey = new Map(nodes.map((n) => [n.key, n]))
  const seen = new Set<string>()
  const queue = nodes.filter((n) => n.kind === 'start').map((n) => n.key)
  const ordered: NodeSpec[] = []
  while (queue.length > 0) {
    const key = queue.shift() as string
    const node = byKey.get(key)
    if (!node || seen.has(key)) continue
    seen.add(key)
    ordered.push(node)
    for (const tr of graph.transitions ?? []) if (tr.from_node === key && tr.to_node) queue.push(tr.to_node)
  }
  return [...ordered, ...nodes.filter((n) => !seen.has(n.key))]
}

export function graphSteps(graph: GraphSpec, names: GraphNames, t: Translate): StepLine[] {
  const byKey = new Map((graph.nodes ?? []).map((n) => [n.key, n]))
  const titleOf = (key: string | null | undefined): string => {
    const node = key ? byKey.get(key) : undefined
    return node ? nodeTitle(node, names, t) : (key ?? '')
  }
  return orderNodes(graph).map((node) => ({
    key: node.key,
    title: nodeTitle(node, names, t),
    outcomes: (graph.transitions ?? [])
      .filter((tr) => tr.from_node === node.key)
      .map((tr) => outcomeText(tr, titleOf(tr.to_node), names, t)),
  }))
}
