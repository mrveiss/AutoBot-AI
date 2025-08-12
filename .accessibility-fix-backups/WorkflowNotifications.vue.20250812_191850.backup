<template>
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

// Props
const props = defineProps({
  workflowId: String
})

// Reactive state
const notifications = ref([])
const eventSource = ref(null)

// Methods
const getNotificationIcon = (type) => {
  const icons = {
    'info': 'fas fa-info-circle',
    'success': 'fas fa-check-circle',
    'warning': 'fas fa-exclamation-triangle',
    'error': 'fas fa-times-circle',
    'approval': 'fas fa-user-check',
    'progress': 'fas fa-sync fa-spin'
  }
  return icons[type] || 'fas fa-bell'
}

const formatTime = (timestamp) => {
  return new Date(timestamp).toLocaleTimeString()
}

const addNotification = (notification) => {
  notifications.value.unshift({
    id: Date.now() + Math.random(),
    timestamp: Date.now(),
    ...notification
  })

  // Auto-remove info notifications after 10 seconds
  if (notification.type === 'info') {
    setTimeout(() => {
      dismissNotification(notification.id)
    }, 10000)
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
</style>
