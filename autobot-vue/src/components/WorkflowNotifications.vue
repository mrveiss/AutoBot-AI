<template>
  <div class="workflow-notifications" v-if="notifications.length > 0">
    <div class="notifications-header">
      <h4>
        <i class="fas fa-bell"></i>
        Workflow Notifications
        <span class="notification-count">{{ notifications.length }}</span>
      </h4>
      <button @click="clearAllNotifications" class="btn-clear" aria-label="No">
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
           aria-label="{{ notification.actiontext }}">
            {{ notification.actionText }}
          </button>

          <button @click="dismissNotification(notification.id)" class="btn-dismiss" aria-label="No">
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
import { formatTime } from '@/utils/formatHelpers'

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
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  z-index: var(--z-toast);
  overflow: hidden;
}

.notifications-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-4);
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-default);
}

.notifications-header h4 {
  margin: 0;
  font-size: var(--text-base);
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.notification-count {
  background: var(--color-primary);
  color: var(--text-on-primary);
  border-radius: var(--radius-full);
  padding: var(--spacing-0-5) var(--spacing-2);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
}

.btn-clear {
  background: none;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  padding: var(--spacing-1) var(--spacing-2);
  border-radius: var(--radius-default);
  transition: var(--transition-colors);
}

.btn-clear:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.notifications-list {
  max-height: 500px;
  overflow-y: auto;
}

.notification-item {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-3);
  padding: var(--spacing-4);
  border-bottom: 1px solid var(--border-subtle);
  transition: background var(--duration-200) var(--ease-in-out);
}

.notification-item:hover {
  background: var(--bg-hover);
}

.notification-item.info { border-left: 4px solid var(--color-info); }
.notification-item.success { border-left: 4px solid var(--color-success); }
.notification-item.warning { border-left: 4px solid var(--color-warning); }
.notification-item.error { border-left: 4px solid var(--color-error); }
.notification-item.approval { border-left: 4px solid var(--chart-orange); }
.notification-item.progress { border-left: 4px solid var(--chart-purple); }

.notification-icon {
  font-size: var(--text-xl);
  width: 24px;
  text-align: center;
  margin-top: var(--spacing-0-5);
}

.notification-item.info .notification-icon { color: var(--color-info); }
.notification-item.success .notification-icon { color: var(--color-success); }
.notification-item.warning .notification-icon { color: var(--color-warning); }
.notification-item.error .notification-icon { color: var(--color-error); }
.notification-item.approval .notification-icon { color: var(--chart-orange); }
.notification-item.progress .notification-icon { color: var(--chart-purple); }

.notification-content {
  flex: 1;
}

.notification-title {
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin-bottom: var(--spacing-1);
}

.notification-message {
  color: var(--text-secondary);
  font-size: var(--text-sm);
  line-height: var(--leading-normal);
  margin-bottom: var(--spacing-1);
}

.notification-time {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.notification-actions {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
  align-items: flex-end;
}

.btn-action {
  background: var(--color-primary);
  color: var(--text-on-primary);
  border: none;
  padding: var(--spacing-1-5) var(--spacing-3);
  border-radius: var(--radius-default);
  font-size: var(--text-xs);
  cursor: pointer;
  white-space: nowrap;
  transition: var(--transition-colors);
}

.btn-action:hover {
  background: var(--color-primary-hover);
}

.btn-dismiss {
  background: none;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  padding: var(--spacing-1);
  border-radius: var(--radius-default);
  transition: var(--transition-colors);
}

.btn-dismiss:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}
</style>
