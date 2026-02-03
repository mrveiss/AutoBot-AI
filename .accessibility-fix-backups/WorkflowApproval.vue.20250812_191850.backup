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

      <div v-else-if="workflows.length === 0" class="no-workflows">
        <i class="fas fa-info-circle"></i>
        No active workflows
      </div>

      <div v-else class="workflows-list">
        <div
          v-for="workflow in workflows"
          :key="workflow.workflow_id"
          class="workflow-card"
          :class="{ 'selected': selectedWorkflowId === workflow.workflow_id }"
          @click="selectWorkflow(workflow.workflow_id)"
        >
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
                <button
                  class="btn btn-success"
                  @click="approveStep(selectedWorkflow.workflow_id, step.step_id)"
                  :disabled="approvingSteps.has(step.step_id)"
                >
                  <i class="fas fa-check"></i>
                  Approve
                </button>
                <button
                  class="btn btn-danger"
                  @click="denyStep(selectedWorkflow.workflow_id, step.step_id)"
                  :disabled="approvingSteps.has(step.step_id)"
                >
                  <i class="fas fa-times"></i>
                  Deny
                </button>
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
        <button
          v-if="selectedWorkflow.status === 'executing' || selectedWorkflow.status === 'waiting_approval'"
          class="btn btn-danger"
          @click="cancelWorkflow(selectedWorkflow.workflow_id)"
        >
          <i class="fas fa-stop"></i>
          Cancel Workflow
        </button>

        <button
          class="btn btn-secondary"
          @click="refreshWorkflows"
        >
          <i class="fas fa-sync"></i>
          Refresh
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { apiService } from '../services/api.js'

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
const formatDate = (dateString: string) => {
  return new Date(dateString).toLocaleString()
}

// Methods
const loadWorkflows = async () => {
  try {
    loading.value = true
    const response = await apiService.get('/api/workflow/workflows')
    workflows.value = response.workflows || []
  } catch (error) {
    console.error('Failed to load workflows:', error)
  } finally {
    loading.value = false
  }
}

const selectWorkflow = async (workflowId: string) => {
  if (selectedWorkflowId.value === workflowId) return

  selectedWorkflowId.value = workflowId

  try {
    // Get workflow details
    const workflowResponse = await apiService.get(`/api/workflow/workflow/${workflowId}`)
    selectedWorkflow.value = workflowResponse.workflow
    workflowSteps.value = workflowResponse.workflow.steps || []
  } catch (error) {
    console.error('Failed to load workflow details:', error)
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
    console.error('Failed to approve step:', error)
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
    console.error('Failed to deny step:', error)
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
    console.error('Failed to cancel workflow:', error)
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
  gap: 20px;
  height: 100%;
  padding: 20px;
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
  gap: 8px;
  margin-bottom: 16px;
  font-size: 1.2em;
  font-weight: 600;
  color: #333;
}

.section-title i {
  color: #007bff;
}

.loading, .no-workflows {
  text-align: center;
  padding: 40px;
  color: #666;
}

.workflows-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.workflow-card {
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 16px;
  cursor: pointer;
  transition: all 0.2s;
  background: white;
}

.workflow-card:hover {
  border-color: #007bff;
  box-shadow: 0 2px 4px rgba(0, 123, 255, 0.1);
}

.workflow-card.selected {
  border-color: #007bff;
  background: #f8f9ff;
}

.workflow-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;
}

.workflow-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: #333;
  flex: 1;
}

.workflow-status {
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 0.8em;
  font-weight: 600;
  text-transform: uppercase;
}

.workflow-status.planned { background: #e3f2fd; color: #1976d2; }
.workflow-status.executing { background: #fff3e0; color: #f57c00; }
.workflow-status.completed { background: #e8f5e8; color: #2e7d32; }
.workflow-status.failed { background: #ffebee; color: #d32f2f; }
.workflow-status.cancelled { background: #f5f5f5; color: #757575; }

.workflow-meta {
  display: flex;
  gap: 16px;
  margin-bottom: 12px;
  font-size: 0.9em;
  color: #666;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.workflow-progress {
  margin-top: 8px;
}

.progress-bar {
  height: 4px;
  background: #eee;
  border-radius: 2px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: #007bff;
  transition: width 0.3s;
}

.workflow-info {
  background: #f8f9fa;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 20px;
}

.info-row {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
}

.info-row:last-child {
  margin-bottom: 0;
}

.label {
  font-weight: 600;
  color: #333;
}

.value {
  color: #666;
}

.classification.simple { color: #2e7d32; }
.classification.research { color: #1976d2; }
.classification.install { color: #f57c00; }
.classification.complex { color: #d32f2f; }

.status.planned { color: #1976d2; }
.status.executing { color: #f57c00; }
.status.completed { color: #2e7d32; }
.status.failed { color: #d32f2f; }
.status.cancelled { color: #757575; }

.workflow-steps {
  margin-bottom: 20px;
}

.workflow-steps h4 {
  margin-bottom: 16px;
  color: #333;
}

.steps-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.step-card {
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 16px;
  background: white;
}

.step-card.current {
  border-color: #007bff;
  background: #f8f9ff;
}

.step-card.completed {
  border-color: #28a745;
  background: #f8fff8;
}

.step-card.waiting-approval {
  border-color: #ffc107;
  background: #fffdf0;
}

.step-card.failed {
  border-color: #dc3545;
  background: #fff8f8;
}

.step-header {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.step-number {
  background: #007bff;
  color: white;
  border-radius: 50%;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.8em;
  font-weight: 600;
  flex-shrink: 0;
}

.step-content {
  flex: 1;
}

.step-title {
  font-weight: 600;
  color: #333;
  margin-bottom: 4px;
}

.step-meta {
  display: flex;
  gap: 12px;
  font-size: 0.8em;
  color: #666;
}

.agent-type {
  background: #e9ecef;
  padding: 2px 6px;
  border-radius: 3px;
  font-weight: 600;
}

.step-status {
  text-transform: uppercase;
  font-weight: 600;
}

.approval-required {
  color: #ffc107;
  font-weight: 600;
}

.step-status-icon {
  font-size: 1.2em;
}

.text-success { color: #28a745; }
.text-warning { color: #ffc107; }
.text-info { color: #17a2b8; }
.text-danger { color: #dc3545; }
.text-muted { color: #6c757d; }

.approval-interface {
  margin-top: 16px;
  padding: 16px;
  background: #fff3cd;
  border-radius: 6px;
  border: 1px solid #ffeaa7;
}

.approval-message {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  font-weight: 600;
  color: #856404;
}

.approval-details {
  margin-bottom: 16px;
  font-size: 0.9em;
}

.approval-details p {
  margin: 4px 0;
}

.approval-actions {
  display: flex;
  gap: 12px;
}

.step-result {
  margin-top: 12px;
  padding: 12px;
  background: #f8f9fa;
  border-radius: 6px;
}

.result-label {
  font-weight: 600;
  color: #333;
  margin-bottom: 4px;
}

.result-content {
  color: #666;
  font-size: 0.9em;
}

.workflow-actions {
  display: flex;
  gap: 12px;
}

.btn {
  padding: 8px 16px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: all 0.2s;
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-success {
  background: #28a745;
  color: white;
}

.btn-success:hover:not(:disabled) {
  background: #218838;
}

.btn-danger {
  background: #dc3545;
  color: white;
}

.btn-danger:hover:not(:disabled) {
  background: #c82333;
}

.btn-secondary {
  background: #6c757d;
  color: white;
}

.btn-secondary:hover:not(:disabled) {
  background: #5a6268;
}
</style>
