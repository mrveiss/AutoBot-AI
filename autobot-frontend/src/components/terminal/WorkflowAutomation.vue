<template>
  <div>
    <!-- Advanced Step Confirmation Modal Component would go here -->
    <!-- For now, we'll emit events to parent to handle advanced modal -->
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { createLogger } from '@/utils/debugUtils'
import {
  buildAutomationSteps,
  exampleWorkflow,
  useAutomationPacing,
  workflowStartedLines,
  type AutomationOutputLine as TerminalOutputLine,
  type AutomationStep as WorkflowStep,
  type AutomationWorkflow as WorkflowData
} from '@/composables/useAutomationPacing'

const logger = createLogger('WorkflowAutomation')
const { t } = useI18n()

interface Props {
  automationPaused: boolean
  hasAutomatedWorkflow: boolean
  currentWorkflowStep: number
  workflowSteps: WorkflowStep[]
  pendingWorkflowStep: WorkflowStep | null
  automationQueue: WorkflowStep[]
  waitingForUserConfirmation: boolean
}

interface Emits {
  (e: 'update:automation-paused', value: boolean): void
  (e: 'update:has-automated-workflow', value: boolean): void
  (e: 'update:current-workflow-step', value: number): void
  (e: 'update:workflow-steps', value: WorkflowStep[]): void
  (e: 'update:pending-workflow-step', value: WorkflowStep | null): void
  (e: 'update:automation-queue', value: WorkflowStep[]): void
  (e: 'update:waiting-for-user-confirmation', value: boolean): void
  (e: 'send-automation-control', action: string): void
  (e: 'execute-automated-command', command: string): void
  (e: 'add-output-line', line: TerminalOutputLine): void
  (e: 'add-running-process', command: string): void
  (e: 'request-manual-step-confirmation', stepInfo: WorkflowStep): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

// Computed properties for two-way binding
const automationPaused = computed({
  get: () => props.automationPaused,
  set: (value: boolean) => emit('update:automation-paused', value)
})

const hasAutomatedWorkflow = computed({
  get: () => props.hasAutomatedWorkflow,
  set: (value: boolean) => emit('update:has-automated-workflow', value)
})

const currentWorkflowStep = computed({
  get: () => props.currentWorkflowStep,
  set: (value: number) => emit('update:current-workflow-step', value)
})

const workflowSteps = computed({
  get: () => props.workflowSteps,
  set: (value: WorkflowStep[]) => emit('update:workflow-steps', value)
})

const pendingWorkflowStep = computed({
  get: () => props.pendingWorkflowStep,
  set: (value: WorkflowStep | null) => emit('update:pending-workflow-step', value)
})

const automationQueue = computed({
  get: () => props.automationQueue,
  set: (value: WorkflowStep[]) => emit('update:automation-queue', value)
})

const waitingForUserConfirmation = computed({
  get: () => props.waitingForUserConfirmation,
  set: (value: boolean) => emit('update:waiting-for-user-confirmation', value)
})

// Pacing between steps; its timers are cleared on unmount (#16396, #17942)
const { processNextAutomationStep, scheduleNextAutomationStep, startFirstAutomationStep } = useAutomationPacing({
  queue: automationQueue,
  paused: automationPaused,
  currentStep: currentWorkflowStep,
  onStepDue: (step) => requestManualStepConfirmation(step)
})

// Automation Control Methods
const toggleAutomationPause = () => {
  automationPaused.value = !automationPaused.value

  if (automationPaused.value) {
    // Pause automation - user takes control
    emit('add-output-line', {
      content: t('terminal.automation.paused'),
      type: 'system_message',
      timestamp: new Date()
    })

    // Notify backend about pause
    emit('send-automation-control', 'pause')

  } else {
    // Resume automation
    emit('add-output-line', {
      content: t('terminal.automation.resumed'),
      type: 'system_message',
      timestamp: new Date()
    })

    // Resume any pending automation steps
    emit('send-automation-control', 'resume')

    // Continue with next step if available
    if (automationQueue.value.length > 0) {
      processNextAutomationStep()
    }
  }
}

const requestManualStepConfirmation = (stepInfo: WorkflowStep) => {
  pendingWorkflowStep.value = stepInfo
  waitingForUserConfirmation.value = true

  emit('add-output-line', {
    content: t('terminal.automation.aboutToExecute', { command: stepInfo.command }),
    type: 'system_message',
    timestamp: new Date()
  })

  emit('add-output-line', {
    content: t('terminal.automation.stepProgress', { step: stepInfo.stepNumber, total: stepInfo.totalSteps, description: stepInfo.description }),
    type: 'workflow_info',
    timestamp: new Date()
  })

  emit('request-manual-step-confirmation', stepInfo)
}

const confirmWorkflowStep = () => {
  if (pendingWorkflowStep.value) {
    // Execute the pending step
    executeAutomatedCommand(pendingWorkflowStep.value.command)

    // Close modal and continue
    waitingForUserConfirmation.value = false
    pendingWorkflowStep.value = null

    // Schedule next step
    scheduleNextAutomationStep()
  }
}

const skipWorkflowStep = () => {
  if (pendingWorkflowStep.value) {
    emit('add-output-line', {
      content: t('terminal.automation.skipped', { command: pendingWorkflowStep.value.command }),
      type: 'system_message',
      timestamp: new Date()
    })

    // Close modal
    waitingForUserConfirmation.value = false
    pendingWorkflowStep.value = null

    // Continue with next step
    scheduleNextAutomationStep()
  }
}

const takeManualControl = () => {
  // User wants to do manual steps before continuing
  automationPaused.value = true
  waitingForUserConfirmation.value = false

  emit('add-output-line', {
    content: t('terminal.automation.manualControlTaken'),
    type: 'system_message',
    timestamp: new Date()
  })

  // Keep the pending step for later
  if (pendingWorkflowStep.value) {
    const queue = [...automationQueue.value]
    queue.unshift(pendingWorkflowStep.value)
    automationQueue.value = queue
    pendingWorkflowStep.value = null
  }
}

const executeAutomatedCommand = (command: string) => {
  // Mark as automated execution
  emit('add-output-line', {
    content: t('terminal.automation.automated', { command }),
    type: 'automated_command',
    timestamp: new Date()
  })

  // Execute the command
  emit('execute-automated-command', command)

  // Track the automated process
  emit('add-running-process', `[AUTO] ${command}`)
}

// API Integration for Workflow Automation
const startAutomatedWorkflow = (workflowData: WorkflowData) => {
  hasAutomatedWorkflow.value = true
  automationPaused.value = false
  currentWorkflowStep.value = 0
  workflowSteps.value = buildAutomationSteps(workflowData, t)
  automationQueue.value = buildAutomationSteps(workflowData, t)

  for (const line of workflowStartedLines(workflowData, t)) emit('add-output-line', line)

  startFirstAutomationStep()
}

// Example workflow for testing
const startExampleWorkflow = () => startAutomatedWorkflow(exampleWorkflow(t))

// Listen for workflow events from backend
const handleWorkflowMessage = (message: string) => {
  try {
    const data = JSON.parse(message)

    if (data.type === 'start_workflow') {
      startAutomatedWorkflow(data.workflow)
    } else if (data.type === 'pause_workflow') {
      automationPaused.value = true
      emit('add-output-line', {
        content: t('terminal.automation.pausedBySystem'),
        type: 'system_message',
        timestamp: new Date()
      })
    } else if (data.type === 'resume_workflow') {
      automationPaused.value = false
      emit('add-output-line', {
        content: t('terminal.automation.resumedBySystem'),
        type: 'system_message',
        timestamp: new Date()
      })
      processNextAutomationStep()
    }
  } catch (error) {
    logger.warn('Failed to parse workflow message:', error)
  }
}

// Advanced Modal Methods for parent component
const executeConfirmedStep = (stepData: WorkflowStep) => {
  emit('add-output-line', {
    content: t('terminal.automation.executing', { command: stepData.command }),
    type: 'system_message',
    timestamp: new Date()
  })
  executeAutomatedCommand(stepData.command)
  scheduleNextAutomationStep()
}

const skipCurrentStep = (stepIndex: number) => {
  emit('add-output-line', {
    content: t('terminal.automation.stepSkippedByUser', { step: stepIndex + 1 }),
    type: 'system_message',
    timestamp: new Date()
  })
  scheduleNextAutomationStep()
}

const executeAllRemainingSteps = () => {
  automationPaused.value = false
  waitingForUserConfirmation.value = false
  processNextAutomationStep()
}

const saveCustomWorkflow = (workflowData: WorkflowData) => {
  emit('add-output-line', {
    content: t('terminal.automation.workflowSaved', { name: workflowData.name }),
    type: 'system_message',
    timestamp: new Date()
  })
}

const updateWorkflowSteps = (newSteps: WorkflowStep[]) => {
  workflowSteps.value = newSteps
  emit('add-output-line', {
    content: t('terminal.automation.workflowUpdated', { count: newSteps.length }),
    type: 'system_message',
    timestamp: new Date()
  })
}

const closeAdvancedModal = () => {
  waitingForUserConfirmation.value = false
}

// Expose methods for parent component
defineExpose({
  toggleAutomationPause,
  requestManualStepConfirmation,
  confirmWorkflowStep,
  skipWorkflowStep,
  takeManualControl,
  startAutomatedWorkflow,
  startExampleWorkflow,
  handleWorkflowMessage,
  executeConfirmedStep,
  skipCurrentStep,
  executeAllRemainingSteps,
  saveCustomWorkflow,
  updateWorkflowSteps,
  closeAdvancedModal
})
</script>

<style scoped>
/* This component mainly handles logic, minimal styling needed */
</style>
