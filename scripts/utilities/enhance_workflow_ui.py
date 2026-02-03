#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Enhance Workflow UI with additional features
Adds workflow notifications and better user experience

NOTE: Long methods (create_workflow_notification_component, create_workflow_progress_widget)
are ACCEPTABLE EXCEPTIONS per Issue #490 - template generators with low cyclomatic complexity.
"""


def create_workflow_notification_component():
    """Create a workflow notification component for real-time updates."""

    component_content = """<template>
  <div class="workflow-notifications" v-if="notifications.length > 0">
    <div class="notifications-header">
      <h4>
        <i class="fas fa-bell"></i>
        Workflow Notifications
        <span class="notification-count">{{ notifications.length }}</span>
      </h4>
      <button @click="clearAllNotifications" class="btn-clear">
        <i class="fas fa-times"></i>
        Clear All
      </button>
    </div>

    <div class="notifications-list">
      <div
        v-for="notification in notifications"
        :key="notification.id"
        class="notification-item"
        :class="notification.type"
      >
        <div class="notification-icon">
          <i :class="getNotificationIcon(notification.type)"></i>
        </div>

        <div class="notification-content">
          <div class="notification-title">{{ notification.title }}</div>
          <div class="notification-message">{{ notification.message }}</div>
          <div class="notification-time">{{ formatTime(notification.timestamp) }}</div>
        </div>

        <div class="notification-actions">
          <button
            v-if="notification.actionRequired"
            @click="handleNotificationAction(notification)"
            class="btn-action"
          >
            {{ notification.actionText }}
          </button>

          <button @click="dismissNotification(notification.id)" class="btn-dismiss">
            <i class="fas fa-times"></i>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { apiService } from '../services/api.js'
import {
  getNotificationIcon,
  formatTimestamp,
  createNotification,
  getNotificationTimeout
} from '../utils/workflowComponents'

// Props
const props = defineProps({
  workflowId: String
})

// Reactive state
const notifications = ref([])
const eventSource = ref(null)

// Methods (using utility functions)
const formatTime = formatTimestamp

const addNotification = (notification) => {
  const fullNotification = createNotification(
    notification.type,
    notification.title,
    notification.message,
    notification
  )

  notifications.value.unshift(fullNotification)

  // Auto-dismiss based on notification type
  const timeout = getNotificationTimeout(notification.type)
  if (timeout > 0) {
    setTimeout(() => {
      dismissNotification(fullNotification.id)
    }, timeout)
  }
}

const dismissNotification = (id) => {
  const index = notifications.value.findIndex(n => n.id === id)
  if (index > -1) {
    notifications.value.splice(index, 1)
  }
}

const clearAllNotifications = () => {
  notifications.value = []
}

const handleNotificationAction = (notification) => {
  if (notification.type === 'approval') {
    // Handle approval action
    approveWorkflowStep(notification.workflowId, notification.stepId)
  }

  dismissNotification(notification.id)
}

const approveWorkflowStep = async (workflowId, stepId) => {
  try {
    await apiService.post(`/api/workflow/workflow/${workflowId}/approve`, {
      workflow_id: workflowId,
      step_id: stepId,
      approved: true,
      timestamp: Date.now()
    })

    addNotification({
      type: 'success',
      title: 'Step Approved',
      message: `Workflow step ${stepId} has been approved and will continue execution.`
    })

  } catch (error) {
    addNotification({
      type: 'error',
      title: 'Approval Failed',
      message: `Failed to approve workflow step: ${error.message}`
    })
  }
}

// Simulate real-time notifications (in production, use WebSocket)
const startNotificationPolling = () => {
  // Example notifications for demonstration
  setTimeout(() => {
    addNotification({
      type: 'info',
      title: 'Workflow Started',
      message: 'Network scanning tool research workflow has begun.'
    })
  }, 2000)

  setTimeout(() => {
    addNotification({
      type: 'progress',
      title: 'Research In Progress',
      message: 'Searching for network scanning tools...'
    })
  }, 5000)

  setTimeout(() => {
    addNotification({
      type: 'approval',
      title: 'User Approval Required',
      message: 'Please select which tool to install: nmap, masscan, or zmap.',
      actionRequired: true,
      actionText: 'Review Options',
      workflowId: props.workflowId,
      stepId: 'step_3'
    })
  }, 8000)
}

// Lifecycle
onMounted(() => {
  if (props.workflowId) {
    startNotificationPolling()
  }
})

onUnmounted(() => {
  if (eventSource.value) {
    eventSource.value.close()
  }
})

// Expose methods for parent component
defineExpose({
  addNotification,
  clearAllNotifications
})
</script>

<style scoped>
.workflow-notifications {
  position: fixed;
  top: 20px;
  right: 20px;
  width: 400px;
  max-height: 600px;
  background: white;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  z-index: 1000;
  overflow: hidden;
}

.notifications-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  background: #f8f9fa;
  border-bottom: 1px solid #dee2e6;
}

.notifications-header h4 {
  margin: 0;
  font-size: 16px;
  color: #333;
  display: flex;
  align-items: center;
  gap: 8px;
}

.notification-count {
  background: #007bff;
  color: white;
  border-radius: 12px;
  padding: 2px 8px;
  font-size: 12px;
  font-weight: 600;
}

.btn-clear {
  background: none;
  border: none;
  color: #6c757d;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 4px;
}

.btn-clear:hover {
  background: #e9ecef;
  color: #495057;
}

.notifications-list {
  max-height: 500px;
  overflow-y: auto;
}

.notification-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 16px;
  border-bottom: 1px solid #f1f3f4;
  transition: background 0.2s;
}

.notification-item:hover {
  background: #f8f9fa;
}

.notification-item.info { border-left: 4px solid #17a2b8; }
.notification-item.success { border-left: 4px solid #28a745; }
.notification-item.warning { border-left: 4px solid #ffc107; }
.notification-item.error { border-left: 4px solid #dc3545; }
.notification-item.approval { border-left: 4px solid #fd7e14; }
.notification-item.progress { border-left: 4px solid #6f42c1; }

.notification-icon {
  font-size: 20px;
  width: 24px;
  text-align: center;
  margin-top: 2px;
}

.notification-item.info .notification-icon { color: #17a2b8; }
.notification-item.success .notification-icon { color: #28a745; }
.notification-item.warning .notification-icon { color: #ffc107; }
.notification-item.error .notification-icon { color: #dc3545; }
.notification-item.approval .notification-icon { color: #fd7e14; }
.notification-item.progress .notification-icon { color: #6f42c1; }

.notification-content {
  flex: 1;
}

.notification-title {
  font-weight: 600;
  color: #333;
  margin-bottom: 4px;
}

.notification-message {
  color: #666;
  font-size: 14px;
  line-height: 1.4;
  margin-bottom: 4px;
}

.notification-time {
  font-size: 12px;
  color: #999;
}

.notification-actions {
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-items: flex-end;
}

.btn-action {
  background: #007bff;
  color: white;
  border: none;
  padding: 6px 12px;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
}

.btn-action:hover {
  background: #0056b3;
}

.btn-dismiss {
  background: none;
  border: none;
  color: #6c757d;
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
}

.btn-dismiss:hover {
  background: #f1f3f4;
  color: #495057;
}
</style>"""

    return component_content


def create_workflow_progress_widget():
    """Create a compact workflow progress widget."""

    widget_content = """<template>
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
import {
  calculateProgress,
  formatProgressText,
  getClassificationClass
} from '../utils/workflowComponents'

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

// Computed properties (using utility functions)
const progressPercentage = computed(() => {
  if (!activeWorkflow.value) return 0
  return calculateProgress(
    activeWorkflow.value.current_step,
    activeWorkflow.value.total_steps
  )
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
</style>"""

    return widget_content


def main():
    """Create enhanced UI components for workflow orchestration."""

    print("🎨 Creating Enhanced Workflow UI Components")
    print("=" * 60)

    # Create notification component
    notification_component = create_workflow_notification_component()

    with open(
        "/home/kali/Desktop/AutoBot/autobot-vue/src/components/WorkflowNotifications.vue",
        "w",
    ) as f:
        f.write(notification_component)

    print("✅ Created WorkflowNotifications.vue")
    print("   - Real-time workflow notifications")
    print("   - User approval prompts")
    print("   - Progress updates")
    print("   - Auto-dismiss for info notifications")

    # Create progress widget
    progress_widget = create_workflow_progress_widget()

    with open(
        "/home/kali/Desktop/AutoBot/autobot-vue/src/components/WorkflowProgressWidget.vue",
        "w",
    ) as f:
        f.write(progress_widget)

    print("✅ Created WorkflowProgressWidget.vue")
    print("   - Compact floating progress widget")
    print("   - Expandable workflow details")
    print("   - Quick approval actions")
    print("   - Cancel workflow capability")

    print("\n📋 Usage Instructions:")
    print("1. Import components in your main App.vue:")
    print(
        "   import WorkflowNotifications from './components/WorkflowNotifications.vue'"
    )
    print(
        "   import WorkflowProgressWidget from './components/WorkflowProgressWidget.vue'"
    )
    print("")
    print("2. Add to template:")
    print("   <WorkflowNotifications :workflow-id='activeWorkflowId' />")
    print("   <WorkflowProgressWidget :workflow-id='activeWorkflowId' />")
    print("")
    print("3. These will provide:")
    print("   - Floating notifications for workflow events")
    print("   - Compact progress widget in bottom-right corner")
    print("   - Real-time updates and user interaction")

    print("\n🎉 Enhanced UI Components Created Successfully!")
    print("   AutoBot now has professional workflow orchestration UI!")


if __name__ == "__main__":
    main()
