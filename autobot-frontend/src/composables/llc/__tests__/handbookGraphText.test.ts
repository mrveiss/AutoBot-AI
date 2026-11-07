// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/** #18431: every edge kind of a workflow graph is written out, in walk order from the start node. */
import { describe, expect, it } from 'vitest'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import { graphSteps } from '../handbookGraphText'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const t = (key: string, params?: Record<string, unknown>) => i18n.global.t(key, params ?? {})
const names = { process: (k: string) => `P:${k}`, workflow: (id: string) => `W:${id}` }

describe('graphSteps (#18431)', () => {
  it('writes if, else, timeout and handoff edges and orders nodes from the start', () => {
    const steps = graphSteps(
      {
        nodes: [
          { key: 'end', kind: 'end', end_outcome: 'failed' },
          { key: 'chk', kind: 'process', process_key: 'check' },
          { key: 'meta', kind: 'meta_skill', meta_skill_id: 'ms1' },
          { key: 'go', kind: 'start' },
        ],
        transitions: [
          { from_node: 'go', kind: 'success', to_node: 'chk' },
          { from_node: 'chk', kind: 'if', to_node: 'meta', condition: 'all checks pass' },
          { from_node: 'chk', kind: 'else', to_node: 'end' },
          { from_node: 'meta', kind: 'timeout', to_node: 'end', timeout_seconds: 30 },
          { from_node: 'meta', kind: 'handoff', handoff_workflow_id: 'wf-2' },
        ],
      },
      names,
      t,
    )
    expect(steps.map((s) => s.title)).toEqual(['Start', 'P:check', 'Run the meta skill W:ms1', 'Finished: failed'])
    expect(steps[1].outcomes).toEqual([
      'If all checks pass: Run the meta skill W:ms1',
      'Otherwise: Finished: failed',
    ])
    expect(steps[2].outcomes).toEqual([
      'If nothing happens within 30 seconds: Finished: failed',
      'Hands off to the workflow W:wf-2',
    ])
  })

  it('a failure edge without retries has no retry wording; an empty graph has no steps', () => {
    const steps = graphSteps(
      { nodes: [{ key: 'a', kind: 'process', process_key: 'x' }, { key: 'b', kind: 'end' }], transitions: [{ from_node: 'a', kind: 'failure', to_node: 'b' }] },
      names,
      t,
    )
    expect(steps[0].outcomes).toEqual(['If it fails: Finished: done'])
    expect(graphSteps({}, names, t)).toEqual([])
  })
})
