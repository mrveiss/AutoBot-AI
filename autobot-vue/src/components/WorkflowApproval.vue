<template>
  <div class="workflow-approval">
    <!-- Active Workflows List -->
    <div class="workflows-section">
      <h3 class="section-title">
        <i class="fas fa-project-diagram"></i>
        Active Workflows
      </h3>

      <div v-if="loading" class="loading">
        <i class="fas fa-spinner fa-spin"></i>
        Loading workflows...
      </div>

      <EmptyState
        v-else-if="workflows.length === 0"
        icon="fas fa-info-circle"
        message="No active workflows"
      />

      <div v-else class="workflows-list">
        <div
          v-for="workflow in workflows"
          :key="workflow.workflow_id"
          class="workflow-card"
          :class="{ 'selected': selectedWorkflowId === workflow.workflow_id }"
          @click="selectWorkflow(workflow.workflow_id)"
         tabindex="0" @keyup.enter="($event.target as HTMLElement)?.click()" @keyup.space="($event.target as HTMLElement)?.click()">
          <div class="workflow-header">
            <div class="workflow-title">
              <i class="fas fa-cogs"></i>
              {{ workflow.user_message }}
            </div>
            <div class="workflow-status" :class="workflow.status">
              {{ workflow.status }}
            </div>
          </div>

          <div class="workflow-meta">
            <div class="meta-item">
              <i class="fas fa-layer-group"></i>
              {{ workflow.current_step + 1 }}/{{ workflow.total_steps }} steps
            </div>
            <div class="meta-item">
              <i class="fas fa-clock"></i>
              {{ workflow.estimated_duration }}
            </div>
            <div class="meta-item">
              <i class="fas fa-users"></i>
              {{ workflow.agents_involved.join(', ') }}
            </div>
          </div>

          <div class="workflow-progress">
            <div class="progress-bar">
              <div
                class="progress-fill"
                :style="{ width: (workflow.current_step / workflow.total_steps * 100) + '%' }"
              ></div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Workflow Details -->
    <div v-if="selectedWorkflow" class="workflow-details">
      <h3 class="section-title">
        <i class="fas fa-tasks"></i>
        Workflow Details
      </h3>

      <div class="workflow-info">
        <div class="info-row">
          <span class="label">Classification:</span>
          <span class="value classification" :class="selectedWorkflow.classification">
            {{ selectedWorkflow.classification }}
          </span>
        </div>
        <div class="info-row">
          <span class="label">Created:</span>
          <span class="value">{{ formatDate(selectedWorkflow.created_at) }}</span>
        </div>
        <div class="info-row">
          <span class="label">Status:</span>
          <span class="value status" :class="selectedWorkflow.status">
            {{ selectedWorkflow.status }}
          </span>
        </div>
      </div>

      <!-- Workflow Steps -->
      <div class="workflow-steps">
        <h4>Workflow Steps</h4>
        <div class="steps-list">
          <div
            v-for="(step, index) in workflowSteps"
            :key="step.step_id"
            class="step-card"
            :class="{
              'current': index === selectedWorkflow.current_step,
              'completed': step.status === 'completed',
              'waiting-approval': step.status === 'waiting_approval',
              'failed': step.status === 'failed'
            }"
          >
            <div class="step-header">
              <div class="step-number">{{ index + 1 }}</div>
              <div class="step-content">
                <div class="step-title">{{ step.description }}</div>
                <div class="step-meta">
                  <span class="agent-type">{{ step.agent_type }}</span>
                  <span class="step-status">{{ step.status }}</span>
                  <span v-if="step.requires_approval" class="approval-required">
                    <i class="fas fa-user-check"></i>
                    Approval Required
                  </span>
                </div>
              </div>
              <div class="step-status-icon">
                <i v-if="step.status === 'completed'" class="fas fa-check-circle text-success"></i>
                <i v-else-if="step.status === 'waiting_approval'" class="fas fa-clock text-warning"></i>
                <i v-else-if="step.status === 'in_progress'" class="fas fa-spinner fa-spin text-info"></i>
                <i v-else-if="step.status === 'failed'" class="fas fa-times-circle text-danger"></i>
                <i v-else class="fas fa-circle text-muted"></i>
              </div>
            </div>

            <!-- Approval Interface -->
            <div v-if="step.status === 'waiting_approval'" class="approval-interface">
              <div class="approval-message">
                <i class="fas fa-exclamation-triangle"></i>
                This step requires your approval to continue.
              </div>

              <div class="approval-details">
                <p><strong>Agent:</strong> {{ step.agent_type }}</p>
                <p><strong>Action:</strong> {{ step.action }}</p>
                <p v-if="step.result"><strong>Result:</strong> {{ step.result }}</p>
              </div>

              <div class="approval-actions">
                <BaseButton
                  variant="success"
                  @click="approveStep(selectedWorkflow.workflow_id, step.step_id)"
                  :disabled="approvingSteps.has(step.step_id)"
                >
                  <i class="fas fa-check"></i>
                  Approve
                </BaseButton>
                <BaseButton
                  variant="danger"
                  @click="denyStep(selectedWorkflow.workflow_id, step.step_id)"
                  :disabled="approvingSteps.has(step.step_id)"
                >
                  <i class="fas fa-times"></i>
                  Deny
                </BaseButton>
              </div>
            </div>

            <!-- Step Result -->
            <div v-if="step.result && step.status !== 'waiting_approval'" class="step-result">
              <div class="result-label">Result:</div>
              <div class="result-content">{{ step.result }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Workflow Actions -->
      <div class="workflow-actions">
        <BaseButton
          v-if="selectedWorkflow.status === 'executing' || selectedWorkflow.status === 'waiting_approval'"
          variant="danger"
          @click="cancelWorkflow(selectedWorkflow.workflow_id)"
        >
          <i class="fas fa-stop"></i>
          Cancel Workflow
        </BaseButton>

        <BaseButton
          variant="secondary"
          @click="refreshWorkflows"
        >
          <i class="fas fa-sync"></i>
          Refresh
        </BaseButton>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { apiService } from '../services/api.js'
import type { WorkflowResponse } from '@/types/models'
import { formatDateTime as formatDate } from '@/utils/formatHelpers'
import EmptyState from '@/components/ui/EmptyState.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('WorkflowApproval')

// Types
interface Workflow {
  workflow_id: string
  user_message: string
  classification: string
  total_steps: number
  current_step: number
  status: string
  created_at: string
  estimated_duration: string
  agents_involved: string[]
}

interface WorkflowStep {
  step_id: string
  description: string
  status: string
  requires_approval: boolean
  agent_type: string
  action: string
  started_at?: string
  completed_at?: string
  result?: string
}

// Reactive state
const loading = ref(false)
const workflows = ref<Workflow[]>([])
const selectedWorkflowId = ref<string | null>(null)
const selectedWorkflow = ref<Workflow | null>(null)
const workflowSteps = ref<WorkflowStep[]>([])
const approvingSteps = ref(new Set<string>())
const refreshInterval = ref<number | null>(null)

// Computed
// NOTE: formatDate removed - now using formatDateTime from @/utils/formatHelpers

// Methods
const loadWorkflows = async () => {
  try {
    loading.value = true
    const response = await apiService.get('/api/workflow/workflows') as { workflows?: any[] }
    workflows.value = response.workflows || []
  } catch (error) {
    logger.error('Failed to load workflows:', error)
  } finally {
    loading.value = false
  }
}

const selectWorkflow = async (workflowId: string) => {
  if (selectedWorkflowId.value === workflowId) return

  selectedWorkflowId.value = workflowId

  try {
    // Get workflow details
    const workflowResponse = await apiService.get(`/api/workflow/workflow/${workflowId}`) as WorkflowResponse
    selectedWorkflow.value = workflowResponse.workflow as unknown as Workflow
    workflowSteps.value = (workflowResponse.workflow.steps || []) as unknown as WorkflowStep[]
  } catch (error) {
    logger.error('Failed to load workflow details:', error)
  }
}

const approveStep = async (workflowId: string, stepId: string) => {
  try {
    approvingSteps.value.add(stepId)

    await apiService.post(`/api/workflow/workflow/${workflowId}/approve`, {
      workflow_id: workflowId,
      step_id: stepId,
      approved: true,
      user_input: null,
      timestamp: Date.now()
    })

    // Refresh workflow details
    await selectWorkflow(workflowId)

  } catch (error) {
    logger.error('Failed to approve step:', error)
  } finally {
    approvingSteps.value.delete(stepId)
  }
}

const denyStep = async (workflowId: string, stepId: string) => {
  try {
    approvingSteps.value.add(stepId)

    await apiService.post(`/api/workflow/workflow/${workflowId}/approve`, {
      workflow_id: workflowId,
      step_id: stepId,
      approved: false,
      user_input: null,
      timestamp: Date.now()
    })

    // Refresh workflow details
    await selectWorkflow(workflowId)

  } catch (error) {
    logger.error('Failed to deny step:', error)
  } finally {
    approvingSteps.value.delete(stepId)
  }
}

const cancelWorkflow = async (workflowId: string) => {
  if (!confirm('Are you sure you want to cancel this workflow?')) {
    return
  }

  try {
    await apiService.delete(`/api/workflow/workflow/${workflowId}`)
    await loadWorkflows()

    // Clear selection if cancelled workflow was selected
    if (selectedWorkflowId.value === workflowId) {
      selectedWorkflowId.value = null
      selectedWorkflow.value = null
      workflowSteps.value = []
    }
  } catch (error) {
    logger.error('Failed to cancel workflow:', error)
  }
}

const refreshWorkflows = async () => {
  await loadWorkflows()

  // Refresh selected workflow details
  if (selectedWorkflowId.value) {
    await selectWorkflow(selectedWorkflowId.value)
  }
}

// Lifecycle
onMounted(() => {
  loadWorkflows()

  // Set up auto-refresh
  refreshInterval.value = window.setInterval(() => {
    refreshWorkflows()
  }, 5000) // Refresh every 5 seconds
})

onUnmounted(() => {
  if (refreshInterval.value) {
    clearInterval(refreshInterval.value)
  }
})
</script>

<style scoped>
.workflow-approval {
  display: flex;
  gap: var(--spacing-5);
  height: 100%;
  padding: var(--spacing-5);
}

.workflows-section {
  flex: 1;
  min-width: 400px;
}

.workflow-details {
  flex: 2;
  min-width: 600px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  margin-bottom: var(--spacing-4);
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.section-title i {
  color: var(--color-primary);
}

.loading {
  text-align: center;
  padding: var(--spacing-10);
  color: var(--text-secondary);
}

.workflows-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.workflow-card {
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
  cursor: pointer;
  transition: var(--transition-all);
  background: var(--bg-card);
}

.workflow-card:hover {
  border-color: var(--color-primary);
  box-shadow: var(--shadow-sm);
}

.workflow-card.selected {
  border-color: var(--color-primary);
  background: var(--color-primary-bg);
}

.workflow-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--spacing-3);
}

.workflow-title {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  flex: 1;
}

.workflow-status {
  padding: var(--spacing-1) var(--spacing-2);
  border-radius: var(--radius-default);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  text-transform: uppercase;
}

.workflow-status.planned { background: var(--color-info-bg); color: var(--color-info); }
.workflow-status.executing { background: var(--color-warning-bg); color: var(--color-warning); }
.workflow-status.completed { background: var(--color-success-bg); color: var(--color-success); }
.workflow-status.failed { background: var(--color-error-bg); color: var(--color-error); }
.workflow-status.cancelled { background: var(--bg-tertiary); color: var(--text-tertiary); }

.workflow-meta {
  display: flex;
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-3);
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.meta-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
}

.workflow-progress {
  margin-top: var(--spacing-2);
}

.progress-bar {
  height: 4px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-xs);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: var(--color-primary);
  transition: width var(--duration-300) var(--ease-out);
}

.workflow-info {
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
  margin-bottom: var(--spacing-5);
}

.info-row {
  display: flex;
  justify-content: space-between;
  margin-bottom: var(--spacing-2);
}

.info-row:last-child {
  margin-bottom: 0;
}

.label {
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.value {
  color: var(--text-secondary);
}

.classification.simple { color: var(--color-success); }
.classification.research { color: var(--color-info); }
.classification.install { color: var(--color-warning); }
.classification.complex { color: var(--color-error); }

.status.planned { color: var(--color-info); }
.status.executing { color: var(--color-warning); }
.status.completed { color: var(--color-success); }
.status.failed { color: var(--color-error); }
.status.cancelled { color: var(--text-tertiary); }

.workflow-steps {
  margin-bottom: var(--spacing-5);
}

.workflow-steps h4 {
  margin-bottom: var(--spacing-4);
  color: var(--text-primary);
}

.steps-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.step-card {
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
  background: var(--bg-card);
}

.step-card.current {
  border-color: var(--color-primary);
  background: var(--color-primary-bg);
}

.step-card.completed {
  border-color: var(--color-success);
  background: var(--color-success-bg);
}

.step-card.waiting-approval {
  border-color: var(--color-warning);
  background: var(--color-warning-bg);
}

.step-card.failed {
  border-color: var(--color-error);
  background: var(--color-error-bg);
}

.step-header {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-3);
}

.step-number {
  background: var(--color-primary);
  color: var(--text-on-primary);
  border-radius: var(--radius-full);
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  flex-shrink: 0;
}

.step-content {
  flex: 1;
}

.step-title {
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin-bottom: var(--spacing-1);
}

.step-meta {
  display: flex;
  gap: var(--spacing-3);
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.agent-type {
  background: var(--bg-tertiary);
  padding: var(--spacing-0-5) var(--spacing-1-5);
  border-radius: var(--radius-sm);
  font-weight: var(--font-semibold);
}

.step-status {
  text-transform: uppercase;
  font-weight: var(--font-semibold);
}

.approval-required {
  color: var(--color-warning);
  font-weight: var(--font-semibold);
}

.step-status-icon {
  font-size: var(--text-lg);
}

.text-success { color: var(--color-success); }
.text-warning { color: var(--color-warning); }
.text-info { color: var(--color-info); }
.text-danger { color: var(--color-error); }
.text-muted { color: var(--text-muted); }

.approval-interface {
  margin-top: var(--spacing-4);
  padding: var(--spacing-4);
  background: var(--color-warning-bg);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-warning-border);
}

.approval-message {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  margin-bottom: var(--spacing-3);
  font-weight: var(--font-semibold);
  color: var(--color-warning-dark);
}

.approval-details {
  margin-bottom: var(--spacing-4);
  font-size: var(--text-sm);
}

.approval-details p {
  margin: var(--spacing-1) 0;
}

.approval-actions {
  display: flex;
  gap: var(--spacing-3);
}

.step-result {
  margin-top: var(--spacing-3);
  padding: var(--spacing-3);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
}

.result-label {
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin-bottom: var(--spacing-1);
}

.result-content {
  color: var(--text-secondary);
  font-size: var(--text-sm);
}

.workflow-actions {
  display: flex;
  gap: var(--spacing-3);
}
</style>
