<template>
  <div class="workflow-progress-widget" v-if="activeWorkflow">
    <div class="widget-header" @click="toggleExpanded">
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
        <button v-if="hasApprovalPending" @click.stop="openApprovals" class="btn-approval">
          <i class="fas fa-exclamation-circle"></i>
          Approval Required
        </button>
        <button @click.stop="toggleExpanded" class="btn-toggle">
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
        <button @click="openFullWorkflowView" class="btn-view">
          <i class="fas fa-external-link-alt"></i>
          View Full Workflow
        </button>
        <button @click="cancelWorkflow" class="btn-cancel">
          <i class="fas fa-stop"></i>
          Cancel
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { apiService } from '../services/api.js'

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
    console.error('Failed to load workflow data:', error)
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
    console.error('Failed to cancel workflow:', error)
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
  bottom: 20px;
  right: 20px;
  width: 400px;
  background: white;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  z-index: 900;
  border: 1px solid #dee2e6;
}

.widget-header {
  display: flex;
  align-items: center;
  padding: 16px;
  cursor: pointer;
  border-bottom: 1px solid #f1f3f4;
}

.widget-header:hover {
  background: #f8f9fa;
}

.workflow-info {
  flex: 1;
  min-width: 0;
}

.workflow-title {
  font-weight: 600;
  color: #333;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.workflow-progress {
  display: flex;
  align-items: center;
  gap: 8px;
}

.progress-bar {
  flex: 1;
  height: 6px;
  background: #e9ecef;
  border-radius: 3px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: #007bff;
  transition: width 0.3s ease;
}

.progress-text {
  font-size: 12px;
  color: #666;
  white-space: nowrap;
}

.widget-controls {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: 12px;
}

.btn-approval {
  background: #ffc107;
  color: #212529;
  border: none;
  padding: 6px 10px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 4px;
}

.btn-approval:hover {
  background: #ffca2c;
}

.btn-toggle {
  background: none;
  border: none;
  color: #6c757d;
  cursor: pointer;
  padding: 6px;
  border-radius: 4px;
}

.btn-toggle:hover {
  background: #f1f3f4;
  color: #495057;
}

.widget-content {
  padding: 16px;
}

.workflow-details {
  margin-bottom: 16px;
}

.detail-row {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 13px;
}

.label {
  font-weight: 600;
  color: #495057;
}

.value {
  color: #666;
}

.value.simple { color: #28a745; }
.value.research { color: #17a2b8; }
.value.install { color: #ffc107; }
.value.complex { color: #dc3545; }

.current-step {
  margin-bottom: 16px;
  padding: 12px;
  background: #f8f9fa;
  border-radius: 6px;
}

.current-step h5 {
  margin: 0 0 8px 0;
  font-size: 14px;
  color: #495057;
}

.step-info .step-title {
  font-weight: 600;
  color: #333;
  margin-bottom: 4px;
}

.step-meta {
  display: flex;
  gap: 12px;
  font-size: 12px;
}

.agent {
  background: #e9ecef;
  padding: 2px 6px;
  border-radius: 3px;
  font-weight: 600;
}

.status {
  text-transform: uppercase;
  font-weight: 600;
}

.widget-actions {
  display: flex;
  gap: 8px;
}

.btn-view,
.btn-cancel {
  flex: 1;
  padding: 8px 12px;
  border: none;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
}

.btn-view {
  background: #007bff;
  color: white;
}

.btn-view:hover {
  background: #0056b3;
}

.btn-cancel {
  background: #dc3545;
  color: white;
}

.btn-cancel:hover {
  background: #c82333;
}
</style>
