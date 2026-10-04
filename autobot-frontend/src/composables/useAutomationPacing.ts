// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * useAutomationPacing Composable
 *
 * The one home for terminal workflow-automation pacing (#17942): the step
 * queue, the step counter and the readability delays between steps. Used by
 * TerminalWindow and WorkflowAutomation, which each carried their own copy.
 *
 * Every pacing timer is tracked and cleared when the owning scope is disposed
 * (#16396) — a step that comes due after unmount never fires into dead state.
 */

import { onScopeDispose, getCurrentScope, type Ref } from 'vue'

/** Delay before a dequeued step is offered for confirmation. */
export const STEP_OFFER_DELAY_MS = 1000
/** Delay after a step completes before the next one is dequeued. */
export const NEXT_STEP_DELAY_MS = 2000
/** Delay before the first step of a freshly started workflow. */
export const FIRST_STEP_DELAY_MS = 1500

export interface AutomationStep {
  stepNumber: number
  totalSteps: number
  command: string
  description?: string
  explanation?: string
  requiresConfirmation?: boolean
}

export interface AutomationWorkflow {
  name?: string
  steps: Array<{
    command: string
    description?: string
    explanation?: string
    requiresConfirmation?: boolean
  }>
}

export interface AutomationOutputLine {
  content: string
  type: string
  timestamp: Date
}

type Translate = (key: string, params?: Record<string, unknown>) => string

/** Number a workflow's steps into the queue shape; confirmation defaults to required. */
export function buildAutomationSteps(workflow: AutomationWorkflow, t: Translate): AutomationStep[] {
  const total = workflow.steps.length
  return workflow.steps.map((step, index) => ({
    stepNumber: index + 1,
    totalSteps: total,
    command: step.command,
    description: step.description || t('terminal.automation.executeStep', { command: step.command }),
    explanation: step.explanation,
    requiresConfirmation: step.requiresConfirmation !== false
  }))
}

/** The two output lines announcing a started workflow. */
export function workflowStartedLines(workflow: AutomationWorkflow, t: Translate): AutomationOutputLine[] {
  const name = workflow.name || t('terminal.automation.unnamedWorkflow')
  return [
    { content: t('terminal.automation.started', { name }), type: 'system_message', timestamp: new Date() },
    { content: t('terminal.automation.stepsPlanned', { count: workflow.steps.length }), type: 'workflow_info', timestamp: new Date() }
  ]
}

/** The built-in demo workflow behind the terminal's "Test Workflow" button. */
export function exampleWorkflow(t: Translate): AutomationWorkflow {
  const step = (command: string, description: string, explanation: string, requiresConfirmation = true) => ({
    command,
    description,
    explanation,
    requiresConfirmation
  })
  return {
    name: t('terminal.automation.example.name'),
    steps: [
      step('sudo apt update', t('terminal.automation.example.updateDesc'), t('terminal.automation.example.updateExpl')),
      step('sudo apt upgrade -y', t('terminal.automation.example.upgradeDesc'), t('terminal.automation.example.upgradeExpl')),
      step('sudo apt install -y git curl wget', t('terminal.automation.example.installDesc'), t('terminal.automation.example.installExpl')),
      step('git --version && curl --version', t('terminal.automation.example.verifyDesc'), t('terminal.automation.example.verifyExpl'), false)
    ]
  }
}

interface PacingOptions {
  queue: Ref<AutomationStep[]>
  paused: Ref<boolean>
  currentStep: Ref<number>
  onStepDue: (step: AutomationStep) => void
}

export function useAutomationPacing({ queue, paused, currentStep, onStepDue }: PacingOptions) {
  const pending = new Set<ReturnType<typeof setTimeout>>()

  /** setTimeout whose handle is held until it fires or the scope is disposed. */
  const scheduleTracked = (fn: () => void, ms: number) => {
    const id = setTimeout(() => {
      pending.delete(id)
      fn()
    }, ms)
    pending.add(id)
  }

  const cancelPending = () => {
    for (const id of pending) clearTimeout(id)
    pending.clear()
  }

  const processNextAutomationStep = () => {
    if (queue.value.length === 0 || paused.value) return
    const [next, ...rest] = queue.value
    queue.value = rest
    scheduleTracked(() => onStepDue(next), STEP_OFFER_DELAY_MS)
  }

  const scheduleNextAutomationStep = () => {
    currentStep.value++
    scheduleTracked(processNextAutomationStep, NEXT_STEP_DELAY_MS)
  }

  const startFirstAutomationStep = () => scheduleTracked(processNextAutomationStep, FIRST_STEP_DELAY_MS)

  if (getCurrentScope()) onScopeDispose(cancelPending)

  return {
    processNextAutomationStep,
    scheduleNextAutomationStep,
    startFirstAutomationStep,
    scheduleTracked,
    cancelPending
  }
}
