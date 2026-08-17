// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #13963: the "open this workflow" link contract shared by the Company OS org
// canvas (producer) and WorkflowBuilderView (consumer).
//
// Worth testing on its own because the failure mode is silent: a link that
// carries a workflow the consumer cannot parse still navigates, still lands on
// the automation module, and simply opens nothing. Nobody sees an error — the
// click just does less than it promised.

import { describe, it, expect } from 'vitest'
import { workflowIdFromQuery, WORKFLOW_QUERY_KEY } from '../workflowDeepLink'

describe('workflowIdFromQuery (#13963)', () => {
  it('reads the workflow the link names', () => {
    expect(workflowIdFromQuery({ [WORKFLOW_QUERY_KEY]: 'wf-quarterly' })).toBe('wf-quarterly')
  })

  it('takes the first when the key repeats', () => {
    // vue-router types a repeated query parameter as an array. Opening one
    // workflow is the only sensible reading, and throwing would break a link a
    // user can produce by accident.
    expect(workflowIdFromQuery({ [WORKFLOW_QUERY_KEY]: ['wf-a', 'wf-b'] })).toBe('wf-a')
  })

  it('keeps a namespaced id intact', () => {
    expect(workflowIdFromQuery({ [WORKFLOW_QUERY_KEY]: 'team:oncall:v2' })).toBe('team:oncall:v2')
  })

  it('asks for nothing when the key is absent', () => {
    expect(workflowIdFromQuery({})).toBeNull()
    expect(workflowIdFromQuery(undefined)).toBeNull()
    expect(workflowIdFromQuery({ section: 'runner' })).toBeNull()
  })

  it('treats an empty or whitespace value as no request', () => {
    // `?workflow=` is reachable by hand-editing the URL. Loading a workflow
    // named '' would 404 against the API and read as a broken feature.
    expect(workflowIdFromQuery({ [WORKFLOW_QUERY_KEY]: '' })).toBeNull()
    expect(workflowIdFromQuery({ [WORKFLOW_QUERY_KEY]: '   ' })).toBeNull()
    expect(workflowIdFromQuery({ [WORKFLOW_QUERY_KEY]: [] })).toBeNull()
  })

  it('ignores a null or non-string value', () => {
    expect(workflowIdFromQuery({ [WORKFLOW_QUERY_KEY]: null })).toBeNull()
    expect(workflowIdFromQuery({ [WORKFLOW_QUERY_KEY]: undefined })).toBeNull()
  })

  it('trims surrounding whitespace rather than passing it through', () => {
    expect(workflowIdFromQuery({ [WORKFLOW_QUERY_KEY]: '  wf-a  ' })).toBe('wf-a')
  })
})
