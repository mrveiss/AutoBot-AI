<template>
  <div>
    <!-- Advanced Step Confirmation Modal Component would go here -->
    <!-- For now, we'll emit events to parent to handle advanced modal -->
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('WorkflowAutomation')

interface WorkflowStep {
  stepNumber: number
  totalSteps: number
  command: string
  description?: string
  explanation?: string
  requiresConfirmation?: boolean
}

interface WorkflowData {
  name: string
  steps: Array<{
    command: string
    description?: string
    explanation?: string
    requiresConfirmation?: boolean
  }>
}

interface ProcessInfo {
  pid: number
  command: string
  startTime: Date
}

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
  (e: 'add-output-line', line: any): void
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

// Automation Control Methods
const toggleAutomationPause = () => {
  automationPaused.value = !automationPaused.value

  if (automationPaused.value) {
    // Pause automation - user takes control
    emit('add-output-line', {
      content: '⏸️ AUTOMATION PAUSED - Manual control activated. Type commands freely.',
      type: 'system_message',
      timestamp: new Date()
    })

    // Notify backend about pause
    emit('send-automation-control', 'pause')

  } else {
    // Resume automation
    emit('add-output-line', {
      content: '▶️ AUTOMATION RESUMED - Continuing workflow execution.',
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
    content: `🤖 AI WORKFLOW: About to execute "${stepInfo.command}"`,
    type: 'system_message',
    timestamp: new Date()
  })

  emit('add-output-line', {
    content: `📋 Step ${stepInfo.stepNumber}/${stepInfo.totalSteps}: ${stepInfo.description}`,
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
      content: `⏭️ SKIPPED: ${pendingWorkflowStep.value.command}`,
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
    content: '👤 MANUAL CONTROL TAKEN - Complete your manual steps, then click RESUME to continue workflow.',
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
    content: `🤖 AUTOMATED: ${command}`,
    type: 'automated_command',
    timestamp: new Date()
  })

  // Execute the command
  emit('execute-automated-command', command)

  // Track the automated process
  emit('add-running-process', `[AUTO] ${command}`)
}

const processNextAutomationStep = () => {
  if (automationQueue.value.length > 0 && !automationPaused.value) {
    const queue = [...automationQueue.value]
    const nextStep = queue.shift()
    automationQueue.value = queue

    if (nextStep) {
      // Small delay between steps for readability
      setTimeout(() => {
        requestManualStepConfirmation(nextStep)
      }, 1000)
    }
  }
}

const scheduleNextAutomationStep = () => {
  currentWorkflowStep.value++

  // Small delay before next step
  setTimeout(() => {
    processNextAutomationStep()
  }, 2000)
}

// API Integration for Workflow Automation
const startAutomatedWorkflow = (workflowData: WorkflowData) => {
  hasAutomatedWorkflow.value = true
  automationPaused.value = false
  currentWorkflowStep.value = 0
  workflowSteps.value = workflowData.steps?.map((step, index) => ({
    stepNumber: index + 1,
    totalSteps: workflowData.steps.length,
    command: step.command,
    description: step.description || `Execute: ${step.command}`,
    explanation: step.explanation,
    requiresConfirmation: step.requiresConfirmation !== false // Default to true
  })) || []

  // Clear any previous automation queue
  automationQueue.value = []

  // Add all steps to automation queue
  const queue = workflowData.steps.map((step, index) => ({
    stepNumber: index + 1,
    totalSteps: workflowData.steps.length,
    command: step.command,
    description: step.description || `Execute: ${step.command}`,
    explanation: step.explanation,
    requiresConfirmation: step.requiresConfirmation !== false // Default to true
  }))
  automationQueue.value = queue

  emit('add-output-line', {
    content: `🚀 AUTOMATED WORKFLOW STARTED: ${workflowData.name || 'Unnamed Workflow'}`,
    type: 'system_message',
    timestamp: new Date()
  })

  emit('add-output-line', {
    content: `📋 ${workflowSteps.value.length} steps planned. Use PAUSE button to take manual control at any time.`,
    type: 'workflow_info',
    timestamp: new Date()
  })

  // Start the first step
  setTimeout(() => {
    processNextAutomationStep()
  }, 1500)
}

// Example workflow for testing
const startExampleWorkflow = () => {
  const exampleWorkflow: WorkflowData = {
    name: "System Update and Package Installation",
    steps: [
      {
        command: "sudo apt update",
        description: "Update package repositories",
        explanation: "This updates the list of available packages from configured repositories.",
        requiresConfirmation: true
      },
      {
        command: "sudo apt upgrade -y",
        description: "Upgrade installed packages",
        explanation: "This upgrades all installed packages to their latest versions.",
        requiresConfirmation: true
      },
      {
        command: "sudo apt install -y git curl wget",
        description: "Install essential tools",
        explanation: "Install commonly needed development tools.",
        requiresConfirmation: true
      },
      {
        command: "git --version && curl --version",
        description: "Verify installations",
        explanation: "Check that the tools were installed correctly.",
        requiresConfirmation: false
      }
    ]
  }

  startAutomatedWorkflow(exampleWorkflow)
}

// Listen for workflow events from backend
const handleWorkflowMessage = (message: string) => {
  try {
    const data = JSON.parse(message)

    if (data.type === 'start_workflow') {
      startAutomatedWorkflow(data.workflow)
    } else if (data.type === 'pause_workflow') {
      automationPaused.value = true
      emit('add-output-line', {
        content: '⏸️ WORKFLOW PAUSED BY SYSTEM',
        type: 'system_message',
        timestamp: new Date()
      })
    } else if (data.type === 'resume_workflow') {
      automationPaused.value = false
      emit('add-output-line', {
        content: '▶️ WORKFLOW RESUMED BY SYSTEM',
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
const executeConfirmedStep = (stepData: any) => {
  emit('add-output-line', {
    content: `🤖 EXECUTING: ${stepData.command}`,
    type: 'system_message',
    timestamp: new Date()
  })
  executeAutomatedCommand(stepData.command)
  scheduleNextAutomationStep()
}

const skipCurrentStep = (stepIndex: number) => {
  emit('add-output-line', {
    content: `⏭️ STEP ${stepIndex + 1} SKIPPED BY USER`,
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

const saveCustomWorkflow = (workflowData: any) => {
  emit('add-output-line', {
    content: `💾 WORKFLOW SAVED: ${workflowData.name}`,
    type: 'system_message',
    timestamp: new Date()
  })
}

const updateWorkflowSteps = (newSteps: WorkflowStep[]) => {
  workflowSteps.value = newSteps
  emit('add-output-line', {
    content: `📋 WORKFLOW UPDATED: ${newSteps.length} steps configured`,
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
