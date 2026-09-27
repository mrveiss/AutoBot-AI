// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The dashboard subscribes to the channel its workflows actually publish on,
 * and acts on what arrives (#17364).
 *
 * #17358 (`aa2111a0fa`) moved all seven `api/workflow.py` publishes from
 * `global` to `workflow:{workflow_id}`, correctly -- `global` admits every
 * authenticated client. Nothing subscribed to the new channel, so the events
 * kept being published to a channel nobody listened to and the active-workflow
 * list silently stopped refreshing itself on completion. Manual refresh still
 * worked, which is why it went unnoticed.
 *
 * WHY THESE ASSERT THE EMIT AND NOT THE RECEIPT. The PR that moved the channel
 * checked that `@workflow-update` was unbound in the parent and concluded the
 * change was behaviour-neutral. That was true of one of the two emits and false
 * of the other: `@refresh="refreshAll"` is bound, and it is the same handler
 * the manual button uses. Receiving an event and acting on it came apart, so a
 * test that only proves the callback ran would have passed through this bug.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

type Callback = (event: { event_type: string; payload: Record<string, unknown> }) => void

const { subscribed, subscribe } = vi.hoisted(() => {
  const subscribed = new Map<string, { callback: Callback; unsubscribe: ReturnType<typeof vi.fn> }>()
  return {
    subscribed,
    subscribe: vi.fn((channel: string, callback: Callback) => {
      const unsubscribe = vi.fn()
      subscribed.set(channel, { callback, unsubscribe })
      return unsubscribe
    }),
  }
})

vi.mock('@/composables/useEventBus', () => ({
  useEventBus: () => ({
    subscribe,
    isConnected: { value: true },
    connectionState: { value: 'connected' },
    connect: vi.fn(),
  }),
}))

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ info: vi.fn(), warn: vi.fn(), error: vi.fn(), debug: vi.fn() }),
}))

import WorkflowLiveDashboard from '../WorkflowLiveDashboard.vue'

function workflow(id: string) {
  return {
    workflow_id: id,
    name: `wf-${id}`,
    description: '',
    session_id: 's',
    steps: [],
    current_step: 0,
    total_steps: 0,
    is_paused: false,
    is_cancelled: false,
    automation_mode: 'semi_auto',
  }
}

function mountWith(ids: string[]) {
  const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
  return mount(WorkflowLiveDashboard, {
    global: { plugins: [i18n] },
    props: {
      activeWorkflows: ids.map(workflow),
      agentPerformance: {},
      agentCapabilities: {},
      loading: false,
      loadingCapabilities: false,
    },
  })
}

describe('WorkflowLiveDashboard subscriptions', () => {
  beforeEach(() => {
    subscribed.clear()
    subscribe.mockClear()
  })

  it('subscribes per workflow, not to global', () => {
    mountWith(['wf-a', 'wf-b'])

    expect([...subscribed.keys()].sort()).toEqual(['workflow:wf-a', 'workflow:wf-b'])
    expect(subscribed.has('global')).toBe(false)
  })

  it('emits refresh when a workflow completes', () => {
    // The assertion that matters: the handler ran, not that the event arrived.
    const dashboard = mountWith(['wf-a'])

    subscribed.get('workflow:wf-a')!.callback({ event_type: 'workflow_completed', payload: { id: 'wf-a' } })

    expect(dashboard.emitted('refresh')).toHaveLength(1)
  })

  it('emits refresh for a status update and a completed step too', () => {
    const dashboard = mountWith(['wf-a'])
    const fire = subscribed.get('workflow:wf-a')!.callback

    fire({ event_type: 'workflow_status_update', payload: {} })
    fire({ event_type: 'step_completed', payload: {} })

    expect(dashboard.emitted('refresh')).toHaveLength(2)
  })

  it('ignores an event type it does not handle', () => {
    // Negative control: without this, the assertions above are satisfied by a
    // handler that emits `refresh` for anything at all, including the noise
    // that shares the channel.
    const dashboard = mountWith(['wf-a'])

    subscribed.get('workflow:wf-a')!.callback({ event_type: 'agent_heartbeat', payload: {} })

    expect(dashboard.emitted('refresh')).toBeUndefined()
  })

  it('unsubscribes a workflow that leaves the list', async () => {
    const dashboard = mountWith(['wf-a', 'wf-b'])
    const goneHandle = subscribed.get('workflow:wf-b')!.unsubscribe

    await dashboard.setProps({ activeWorkflows: [workflow('wf-a')] })

    expect(goneHandle).toHaveBeenCalledTimes(1)
    expect(subscribed.get('workflow:wf-a')!.unsubscribe).not.toHaveBeenCalled()
  })

  it('subscribes a workflow that joins the list, without resubscribing the others', async () => {
    const dashboard = mountWith(['wf-a'])
    subscribe.mockClear()

    await dashboard.setProps({ activeWorkflows: [workflow('wf-a'), workflow('wf-c')] })

    expect(subscribe).toHaveBeenCalledTimes(1)
    expect(subscribe).toHaveBeenCalledWith('workflow:wf-c', expect.any(Function))
  })

  it('unsubscribes everything on unmount', () => {
    // The leak this guards: without it the subscription set grows for the life
    // of the session and a long-lived dashboard never gives any of them back.
    const dashboard = mountWith(['wf-a', 'wf-b'])
    const handles = [...subscribed.values()].map((entry) => entry.unsubscribe)

    dashboard.unmount()

    for (const handle of handles) {
      expect(handle).toHaveBeenCalledTimes(1)
    }
  })
})
