// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * useAutomationPacing paces workflow steps and never lets a pacing timer
 * outlive its scope (#16396, #17942).
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { effectScope, ref } from 'vue'
import {
  buildAutomationSteps,
  exampleWorkflow,
  useAutomationPacing,
  workflowStartedLines,
  FIRST_STEP_DELAY_MS,
  NEXT_STEP_DELAY_MS,
  STEP_OFFER_DELAY_MS,
  type AutomationStep
} from '../useAutomationPacing'

const t = (key: string, params?: Record<string, unknown>) => `${key}${params ? JSON.stringify(params) : ''}`

const step = (n: number): AutomationStep => ({ stepNumber: n, totalSteps: 2, command: `cmd${n}` })

function setup(paused = false) {
  const queue = ref<AutomationStep[]>([step(1), step(2)])
  const currentStep = ref(0)
  const onStepDue = vi.fn()
  const scope = effectScope()
  const pacing = scope.run(() =>
    useAutomationPacing({ queue, paused: ref(paused), currentStep, onStepDue })
  )!
  return { queue, currentStep, onStepDue, scope, pacing }
}

describe('useAutomationPacing (#16396, #17942)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('offers the head of the queue once the offer delay passes', () => {
    const { queue, onStepDue, pacing } = setup()
    pacing.processNextAutomationStep()

    expect(queue.value.map((s) => s.stepNumber)).toEqual([2])
    vi.advanceTimersByTime(STEP_OFFER_DELAY_MS - 1)
    expect(onStepDue).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1)
    expect(onStepDue).toHaveBeenCalledWith(step(1))
    expect(vi.getTimerCount()).toBe(0)
  })

  it('does nothing while paused', () => {
    const { queue, pacing } = setup(true)
    pacing.processNextAutomationStep()

    expect(queue.value).toHaveLength(2)
    expect(vi.getTimerCount()).toBe(0)
  })

  it('advances the step counter and offers the next step after both delays', () => {
    const { currentStep, onStepDue, pacing } = setup()
    pacing.scheduleNextAutomationStep()

    expect(currentStep.value).toBe(1)
    vi.advanceTimersByTime(NEXT_STEP_DELAY_MS + STEP_OFFER_DELAY_MS)
    expect(onStepDue).toHaveBeenCalledWith(step(1))
  })

  it('fires no pacing callback after its scope is disposed', () => {
    const { onStepDue, scope, pacing } = setup()
    pacing.startFirstAutomationStep()
    pacing.scheduleNextAutomationStep()
    expect(vi.getTimerCount()).toBe(2)

    scope.stop()

    expect(vi.getTimerCount()).toBe(0)
    vi.advanceTimersByTime(FIRST_STEP_DELAY_MS + NEXT_STEP_DELAY_MS + STEP_OFFER_DELAY_MS)
    expect(onStepDue).not.toHaveBeenCalled()
  })

  it('clears a step offer already dequeued when the scope is disposed', () => {
    const { onStepDue, scope, pacing } = setup()
    pacing.processNextAutomationStep()

    scope.stop()
    vi.advanceTimersByTime(STEP_OFFER_DELAY_MS)

    expect(onStepDue).not.toHaveBeenCalled()
  })
})

describe('buildAutomationSteps / workflowStartedLines / exampleWorkflow (#17942)', () => {
  const workflow = {
    steps: [
      { command: 'ls', description: 'List' },
      { command: 'pwd', requiresConfirmation: false }
    ]
  }

  it('numbers steps, defaults confirmation to required and the description to a translated fallback', () => {
    const steps = buildAutomationSteps(workflow, t)

    expect(steps.map((s) => [s.stepNumber, s.totalSteps])).toEqual([[1, 2], [2, 2]])
    expect(steps[0].requiresConfirmation).toBe(true)
    expect(steps[1].requiresConfirmation).toBe(false)
    expect(steps[1].description).toBe('terminal.automation.executeStep{"command":"pwd"}')
  })

  it('announces a nameless workflow under the translated fallback name', () => {
    const [started, planned] = workflowStartedLines(workflow, t)

    expect(started).toMatchObject({
      type: 'system_message',
      content: 'terminal.automation.started{"name":"terminal.automation.unnamedWorkflow"}'
    })
    expect(planned).toMatchObject({ type: 'workflow_info', content: 'terminal.automation.stepsPlanned{"count":2}' })
  })

  it('builds the demo workflow from translated text, with only the verify step unconfirmed', () => {
    const demo = exampleWorkflow(t)

    expect(demo.name).toBe('terminal.automation.example.name')
    expect(demo.steps.map((s) => s.requiresConfirmation)).toEqual([true, true, true, false])
    expect(demo.steps[0]).toEqual({
      command: 'sudo apt update',
      description: 'terminal.automation.example.updateDesc',
      explanation: 'terminal.automation.example.updateExpl',
      requiresConfirmation: true
    })
  })
})
