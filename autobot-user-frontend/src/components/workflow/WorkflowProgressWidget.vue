<template>
  <div class="workflow-progress-widget" v-if="activeWorkflow">
    <div class="widget-header" @click="toggleExpanded" tabindex="0" @keyup.enter="$event.target.click()" @keyup.space="$event.target.click()">
      <div class="workflow-info">
        <div class="workflow-title">
          <i class="fas fa-cogs"></i>
          {{ activeWorkflow.user_message }}
        </div>
        <div class="workflow-progress">
          <div class="progress-bar">
            <div
              class="progress-fill"
              :style="{ width: progressPercentage + '%' }"
            ></div>
          </div>
          <span class="progress-text">
            {{ currentStep }}/{{ totalSteps }} - {{ activeWorkflow.status }}
          </span>
        </div>
      </div>

      <div class="widget-controls">
        <button v-if="hasApprovalPending" @click.stop="openApprovals" class="btn-approval" aria-label="Warning">
          <i class="fas fa-exclamation-circle"></i>
          Approval Required
        </button>
        <button @click.stop="toggleExpanded" class="btn-toggle" aria-label="Expand">
          <i :class="expanded ? 'fas fa-chevron-up' : 'fas fa-chevron-down'"></i>
        </button>
      </div>
    </div>

    <div v-if="expanded" class="widget-content">
      <div class="workflow-details">
        <div class="detail-row">
          <span class="label">Classification:</span>
          <span class="value" :class="activeWorkflow.classification">
            {{ activeWorkflow.classification }}
          </span>
        </div>
        <div class="detail-row">
          <span class="label">Estimated Duration:</span>
          <span class="value">{{ activeWorkflow.estimated_duration }}</span>
        </div>
        <div class="detail-row">
          <span class="label">Agents Involved:</span>
          <span class="value">{{ activeWorkflow.agents_involved.join(', ') }}</span>
        </div>
      </div>

      <div class="current-step" v-if="currentStepInfo">
        <h5>Current Step:</h5>
        <div class="step-info">
          <div class="step-title">{{ currentStepInfo.description }}</div>
          <div class="step-meta">
            <span class="agent">{{ currentStepInfo.agent_type }}</span>
            <span class="status" :class="currentStepInfo.status">
              {{ currentStepInfo.status }}
            </span>
          </div>
        </div>
      </div>

      <div class="widget-actions">
        <button @click="openFullWorkflowView" class="btn-view" aria-label="Button">
          <i class="fas fa-external-link-alt"></i>
          View Full Workflow
        </button>
        <button @click="cancelWorkflow" class="btn-cancel" aria-label="Cancel">
          <i class="fas fa-stop"></i>
          Cancel
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { createLogger } from '@/utils/debugUtils'
import { apiService } from '@/services/api'

const logger = createLogger('WorkflowProgressWidget')

// Props
const props = defineProps({
  workflowId: String
})

// Emits
const emit = defineEmits(['open-full-view', 'workflow-cancelled'])

// Reactive state
const activeWorkflow = ref(null)
const workflowSteps = ref([])
const expanded = ref(false)
const refreshInterval = ref(null)

// Computed properties
const progressPercentage = computed(() => {
  if (!activeWorkflow.value) return 0
  return (activeWorkflow.value.current_step / activeWorkflow.value.total_steps) * 100
})

const currentStep = computed(() => {
  return activeWorkflow.value ? activeWorkflow.value.current_step + 1 : 0
})

const totalSteps = computed(() => {
  return activeWorkflow.value ? activeWorkflow.value.total_steps : 0
})

const currentStepInfo = computed(() => {
  if (!workflowSteps.value || !activeWorkflow.value) return null
  return workflowSteps.value[activeWorkflow.value.current_step] || null
})

const hasApprovalPending = computed(() => {
  return currentStepInfo.value && currentStepInfo.value.status === 'waiting_approval'
})

// Methods
const loadWorkflowData = async () => {
  if (!props.workflowId) return

  try {
    const response = await apiService.get(`/api/workflow/workflow/${props.workflowId}`)
    activeWorkflow.value = response.workflow
    workflowSteps.value = response.workflow.steps || []
  } catch (error) {
    logger.error('Failed to load workflow data:', error)
  }
}

const toggleExpanded = () => {
  expanded.value = !expanded.value
}

const openApprovals = () => {
  // Navigate to approvals or emit event
  emit('open-full-view', 'approvals')
}

const openFullWorkflowView = () => {
  emit('open-full-view', 'workflow')
}

const cancelWorkflow = async () => {
  if (!confirm('Are you sure you want to cancel this workflow?')) return

  try {
    await apiService.delete(`/api/workflow/workflow/${props.workflowId}`)
    activeWorkflow.value = null
    emit('workflow-cancelled', props.workflowId)
  } catch (error) {
    logger.error('Failed to cancel workflow:', error)
  }
}

// Lifecycle
onMounted(() => {
  loadWorkflowData()

  // Refresh every 3 seconds
  refreshInterval.value = setInterval(() => {
    loadWorkflowData()
  }, 3000)
})

onUnmounted(() => {
  if (refreshInterval.value) {
    clearInterval(refreshInterval.value)
  }
})
</script>

<style scoped>
.workflow-progress-widget {
  position: fixed;
  bottom: var(--spacing-5);
  right: var(--spacing-5);
  width: 400px;
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  z-index: var(--z-toast);
  border: 1px solid var(--border-default);
}

.widget-header {
  display: flex;
  align-items: center;
  padding: var(--spacing-4);
  cursor: pointer;
  border-bottom: 1px solid var(--border-subtle);
}

.widget-header:hover {
  background: var(--bg-hover);
}

.workflow-info {
  flex: 1;
  min-width: 0;
}

.workflow-title {
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin-bottom: var(--spacing-2);
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
  font-size: var(--text-sm);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.workflow-progress {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.progress-bar {
  flex: 1;
  height: 6px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: var(--color-primary);
  transition: width var(--duration-300) var(--ease-out);
}

.progress-text {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  white-space: nowrap;
}

.widget-controls {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  margin-left: var(--spacing-3);
}

.btn-approval {
  background: var(--color-warning);
  color: var(--text-on-warning);
  border: none;
  padding: var(--spacing-1-5) var(--spacing-2-5);
  border-radius: var(--radius-default);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
}

.btn-approval:hover {
  background: var(--color-warning-hover);
}

.btn-toggle {
  background: none;
  border: none;
  color: var(--text-tertiary);
  cursor: pointer;
  padding: var(--spacing-1-5);
  border-radius: var(--radius-default);
}

.btn-toggle:hover {
  background: var(--bg-hover);
  color: var(--text-secondary);
}

.widget-content {
  padding: var(--spacing-4);
}

.workflow-details {
  margin-bottom: var(--spacing-4);
}

.detail-row {
  display: flex;
  justify-content: space-between;
  margin-bottom: var(--spacing-2);
  font-size: var(--text-sm);
}

.label {
  font-weight: var(--font-semibold);
  color: var(--text-secondary);
}

.value {
  color: var(--text-tertiary);
}

.value.simple { color: var(--color-success); }
.value.research { color: var(--color-info); }
.value.install { color: var(--color-warning); }
.value.complex { color: var(--color-error); }

.current-step {
  margin-bottom: var(--spacing-4);
  padding: var(--spacing-3);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
}

.current-step h5 {
  margin: 0 0 var(--spacing-2) 0;
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.step-info .step-title {
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin-bottom: var(--spacing-1);
}

.step-meta {
  display: flex;
  gap: var(--spacing-3);
  font-size: var(--text-xs);
}

.agent {
  background: var(--bg-tertiary);
  padding: var(--spacing-0-5) var(--spacing-1-5);
  border-radius: var(--radius-sm);
  font-weight: var(--font-semibold);
}

.status {
  text-transform: uppercase;
  font-weight: var(--font-semibold);
}

.widget-actions {
  display: flex;
  gap: var(--spacing-2);
}

.btn-view,
.btn-cancel {
  flex: 1;
  padding: var(--spacing-2) var(--spacing-3);
  border: none;
  border-radius: var(--radius-default);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-1);
}

.btn-view {
  background: var(--color-primary);
  color: var(--text-on-primary);
}

.btn-view:hover {
  background: var(--color-primary-hover);
}

.btn-cancel {
  background: var(--color-error);
  color: var(--text-on-error);
}

.btn-cancel:hover {
  background: var(--color-error-hover);
}
</style>
