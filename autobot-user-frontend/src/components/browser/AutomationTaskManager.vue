<template>
  <div class="automation-task-manager">
    <!-- Header -->
    <div class="manager-header">
      <div class="flex items-center space-x-3">
        <i class="fas fa-tasks text-blue-600 text-xl"></i>
        <div>
          <h3 class="text-lg font-semibold text-gray-800">Automation Tasks</h3>
          <p class="text-sm text-gray-500">Manage and monitor browser automation tasks</p>
        </div>
      </div>

      <div class="flex items-center space-x-2">
        <BaseButton
          variant="outline"
          size="sm"
          @click="clearCompleted"
          :disabled="completedTasks.length === 0"
        >
          <i class="fas fa-trash mr-1"></i>
          Clear Completed
        </BaseButton>
        <BaseButton
          variant="primary"
          size="sm"
          @click="showCreateModal = true"
        >
          <i class="fas fa-plus mr-1"></i>
          New Task
        </BaseButton>
      </div>
    </div>

    <!-- Stats Overview -->
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-icon bg-blue-100 text-blue-600">
          <i class="fas fa-clock"></i>
        </div>
        <div>
          <div class="stat-value">{{ queuedTasks.length }}</div>
          <div class="stat-label">Queued</div>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-icon bg-yellow-100 text-yellow-600">
          <i class="fas fa-spinner"></i>
        </div>
        <div>
          <div class="stat-value">{{ runningTasks.length }}</div>
          <div class="stat-label">Running</div>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-icon bg-green-100 text-green-600">
          <i class="fas fa-check"></i>
        </div>
        <div>
          <div class="stat-value">{{ completedTasks.length }}</div>
          <div class="stat-label">Completed</div>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-icon bg-red-100 text-red-600">
          <i class="fas fa-times"></i>
        </div>
        <div>
          <div class="stat-value">{{ failedTasks.length }}</div>
          <div class="stat-label">Failed</div>
        </div>
      </div>
    </div>

    <!-- Task List -->
    <div class="task-list">
      <div v-if="tasks.length === 0" class="empty-state">
        <EmptyState
          icon="fas fa-tasks"
          title="No Tasks Yet"
          message="Create your first automation task to get started"
        >
          <template #actions>
            <BaseButton variant="primary" @click="showCreateModal = true">
              <i class="fas fa-plus mr-2"></i>
              Create Task
            </BaseButton>
          </template>
        </EmptyState>
      </div>

      <div v-else class="task-items">
        <div
          v-for="task in sortedTasks"
          :key="task.id"
          class="task-item"
          :class="getTaskStatusClass(task.status)"
        >
          <!-- Task Header -->
          <div class="task-header">
            <div class="flex items-center space-x-3 flex-1">
              <div class="task-type-icon" :class="getTaskTypeIconClass(task.type)">
                <i :class="getTaskTypeIcon(task.type)"></i>
              </div>
              <div class="flex-1">
                <h4 class="task-name">{{ task.name }}</h4>
                <p v-if="task.description" class="task-description">{{ task.description }}</p>
              </div>
            </div>

            <div class="flex items-center space-x-3">
              <StatusBadge :variant="getStatusVariant(task.status)" size="small">
                {{ task.status.toUpperCase() }}
              </StatusBadge>

              <button
                v-if="task.status === 'queued' || task.status === 'running'"
                @click="cancelTask(task.id)"
                class="action-btn text-red-600"
                title="Cancel Task"
              >
                <i class="fas fa-times"></i>
              </button>

              <button
                @click="toggleTaskDetails(task.id)"
                class="action-btn"
                title="Toggle Details"
              >
                <i class="fas" :class="expandedTasks.has(task.id) ? 'fa-chevron-up' : 'fa-chevron-down'"></i>
              </button>
            </div>
          </div>

          <!-- Progress Bar -->
          <div v-if="task.status === 'running' && task.progress !== undefined" class="progress-bar">
            <div class="progress-fill" :style="{ width: `${task.progress}%` }"></div>
          </div>

          <!-- Task Details (Expandable) -->
          <div v-if="expandedTasks.has(task.id)" class="task-details">
            <div class="details-grid">
              <div class="detail-item">
                <span class="detail-label">Task ID:</span>
                <span class="detail-value font-mono text-xs">{{ task.id }}</span>
              </div>
              <div class="detail-item">
                <span class="detail-label">Type:</span>
                <span class="detail-value">{{ task.type }}</span>
              </div>
              <div class="detail-item">
                <span class="detail-label">Created:</span>
                <span class="detail-value">{{ formatDate(task.createdAt) }}</span>
              </div>
              <div v-if="task.completedAt" class="detail-item">
                <span class="detail-label">Completed:</span>
                <span class="detail-value">{{ formatDate(task.completedAt) }}</span>
              </div>
            </div>

            <!-- Task Parameters -->
            <div v-if="Object.keys(task.params).length > 0" class="mt-3">
              <h5 class="text-sm font-medium text-gray-700 mb-2">Parameters:</h5>
              <pre class="params-display">{{ JSON.stringify(task.params, null, 2) }}</pre>
            </div>

            <!-- Task Result -->
            <div v-if="task.result" class="mt-3">
              <h5 class="text-sm font-medium text-gray-700 mb-2">Result:</h5>
              <pre class="result-display">{{ JSON.stringify(task.result, null, 2) }}</pre>
            </div>

            <!-- Task Error -->
            <div v-if="task.error" class="mt-3">
              <div class="error-display">
                <i class="fas fa-exclamation-triangle mr-2"></i>
                {{ task.error }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Create Task Modal -->
    <div v-if="showCreateModal" class="modal-overlay" @click.self="showCreateModal = false">
      <div class="modal-content">
        <div class="modal-header">
          <h3 class="text-lg font-semibold">Create Automation Task</h3>
          <button @click="showCreateModal = false" class="text-gray-400 hover:text-gray-600">
            <i class="fas fa-times"></i>
          </button>
        </div>

        <div class="modal-body">
          <div class="form-group">
            <label class="form-label">Task Type</label>
            <select v-model="newTask.type" class="form-select">
              <option value="navigate">Navigate to URL</option>
              <option value="screenshot">Capture Screenshot</option>
              <option value="search">Web Search</option>
              <option value="test">Run Frontend Test</option>
            </select>
          </div>

          <div class="form-group">
            <label class="form-label">Task Name</label>
            <input v-model="newTask.name" type="text" class="form-input" placeholder="Enter task name" />
          </div>

          <div class="form-group">
            <label class="form-label">Description (Optional)</label>
            <textarea v-model="newTask.description" class="form-textarea" rows="2" placeholder="Task description"></textarea>
          </div>

          <!-- Dynamic fields based on task type -->
          <div v-if="newTask.type === 'navigate'" class="form-group">
            <label class="form-label">URL</label>
            <input v-model="newTask.url" type="url" class="form-input" placeholder="https://example.com" />
          </div>

          <div v-if="newTask.type === 'screenshot'" class="form-group">
            <label class="form-label">URL</label>
            <input v-model="newTask.url" type="url" class="form-input" placeholder="https://example.com" />
          </div>

          <div v-if="newTask.type === 'search'" class="form-group">
            <label class="form-label">Search Query</label>
            <input v-model="newTask.query" type="text" class="form-input" placeholder="Enter search query" />
          </div>
        </div>

        <div class="modal-footer">
          <BaseButton variant="outline" @click="showCreateModal = false">
            Cancel
          </BaseButton>
          <BaseButton variant="primary" @click="createNewTask" :disabled="!isTaskValid">
            <i class="fas fa-plus mr-1"></i>
            Create Task
          </BaseButton>
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import { ref, computed } from 'vue'
import { useBrowserAutomation } from '@/composables/useBrowserAutomation'
import BaseButton from '@/components/base/BaseButton.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import type { TaskType, TaskStatus } from '@/types/browser'

export default {
  name: 'AutomationTaskManager',
  components: {
    BaseButton,
    StatusBadge,
    EmptyState
  },
  setup() {
    const {
      tasks,
      createTask,
      cancelTask: cancelTaskHandler,
      clearCompletedTasks
    } = useBrowserAutomation()

    const showCreateModal = ref(false)
    const expandedTasks = ref(new Set<string>())

    const newTask = ref({
      type: 'navigate' as TaskType,
      name: '',
      description: '',
      url: '',
      query: ''
    })

    // Computed task lists
    const queuedTasks = computed(() => tasks.value.filter(t => t.status === 'queued'))
    const runningTasks = computed(() => tasks.value.filter(t => t.status === 'running'))
    const completedTasks = computed(() => tasks.value.filter(t => t.status === 'completed'))
    const failedTasks = computed(() => tasks.value.filter(t => t.status === 'failed'))

    const sortedTasks = computed(() => {
      return [...tasks.value].sort((a, b) => {
        // Sort by status priority, then by creation date
        const statusPriority: Record<TaskStatus, number> = {
          running: 0,
          queued: 1,
          failed: 2,
          cancelled: 3,
          completed: 4
        }

        const priorityDiff = statusPriority[a.status] - statusPriority[b.status]
        if (priorityDiff !== 0) return priorityDiff

        return b.createdAt.getTime() - a.createdAt.getTime()
      })
    })

    const isTaskValid = computed(() => {
      if (!newTask.value.name.trim()) return false

      if (newTask.value.type === 'navigate' || newTask.value.type === 'screenshot') {
        return !!newTask.value.url.trim()
      }

      if (newTask.value.type === 'search') {
        return !!newTask.value.query.trim()
      }

      return true
    })

    // Methods
    const createNewTask = async () => {
      const params: Record<string, unknown> = {}

      if (newTask.value.type === 'navigate' || newTask.value.type === 'screenshot') {
        params.url = newTask.value.url
      }

      if (newTask.value.type === 'search') {
        params.query = newTask.value.query
      }

      await createTask(
        newTask.value.type,
        newTask.value.name,
        params,
        newTask.value.description || undefined
      )

      // Reset form
      newTask.value = {
        type: 'navigate',
        name: '',
        description: '',
        url: '',
        query: ''
      }

      showCreateModal.value = false
    }

    const cancelTask = (taskId: string) => {
      cancelTaskHandler(taskId)
    }

    const clearCompleted = () => {
      clearCompletedTasks()
    }

    const toggleTaskDetails = (taskId: string) => {
      if (expandedTasks.value.has(taskId)) {
        expandedTasks.value.delete(taskId)
      } else {
        expandedTasks.value.add(taskId)
      }
    }

    const getTaskStatusClass = (status: TaskStatus): string => {
      switch (status) {
        case 'running': return 'status-running'
        case 'completed': return 'status-completed'
        case 'failed': return 'status-failed'
        case 'cancelled': return 'status-cancelled'
        default: return ''
      }
    }

    const getStatusVariant = (status: TaskStatus): 'success' | 'warning' | 'danger' | 'info' => {
      switch (status) {
        case 'completed': return 'success'
        case 'running': return 'warning'
        case 'failed': return 'danger'
        default: return 'info'
      }
    }

    const getTaskTypeIcon = (type: TaskType): string => {
      switch (type) {
        case 'navigate': return 'fas fa-compass'
        case 'screenshot': return 'fas fa-camera'
        case 'search': return 'fas fa-search'
        case 'test': return 'fas fa-vials'
        case 'script': return 'fas fa-code'
        default: return 'fas fa-cog'
      }
    }

    const getTaskTypeIconClass = (type: TaskType): string => {
      switch (type) {
        case 'navigate': return 'bg-blue-100 text-blue-600'
        case 'screenshot': return 'bg-purple-100 text-purple-600'
        case 'search': return 'bg-green-100 text-green-600'
        case 'test': return 'bg-yellow-100 text-yellow-600'
        case 'script': return 'bg-indigo-100 text-indigo-600'
        default: return 'bg-gray-100 text-gray-600'
      }
    }

    const formatDate = (date: Date): string => {
      return new Intl.DateTimeFormat('en-US', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      }).format(date)
    }

    return {
      tasks,
      queuedTasks,
      runningTasks,
      completedTasks,
      failedTasks,
      sortedTasks,
      showCreateModal,
      expandedTasks,
      newTask,
      isTaskValid,
      createNewTask,
      cancelTask,
      clearCompleted,
      toggleTaskDetails,
      getTaskStatusClass,
      getStatusVariant,
      getTaskTypeIcon,
      getTaskTypeIconClass,
      formatDate
    }
  }
}
</script>

<style scoped>
.automation-task-manager {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg-surface);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.manager-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-5);
  background: var(--bg-tertiary);
  border-bottom: 1px solid var(--border-light);
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: var(--spacing-4);
  padding: var(--spacing-5);
  background: var(--bg-surface);
}

.stat-card {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-4);
  background: var(--bg-tertiary);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-light);
}

.stat-icon {
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-full);
  font-size: 20px;
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
}

.stat-label {
  font-size: 12px;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.task-list {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-5);
}

.empty-state {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100%;
}

.task-items {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.task-item {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
  transition: all var(--duration-200);
}

.task-item:hover {
  box-shadow: var(--shadow-md);
}

.task-item.status-running {
  border-left: 4px solid #f59e0b;
}

.task-item.status-completed {
  border-left: 4px solid #10b981;
}

.task-item.status-failed {
  border-left: 4px solid #ef4444;
}

.task-item.status-cancelled {
  border-left: 4px solid #6b7280;
  opacity: 0.7;
}

.task-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.task-type-icon {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-md);
  font-size: 18px;
}

.task-name {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.task-description {
  font-size: 14px;
  color: var(--text-secondary);
  margin-top: var(--spacing-1);
}

.action-btn {
  padding: var(--spacing-2);
  background: transparent;
  border: none;
  cursor: pointer;
  color: var(--text-secondary);
  transition: color var(--duration-200);
}

.action-btn:hover {
  color: var(--text-primary);
}

.progress-bar {
  margin-top: var(--spacing-3);
  height: 6px;
  background: var(--bg-surface);
  border-radius: var(--radius-full);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #3b82f6, #8b5cf6);
  transition: width var(--duration-300);
}

.task-details {
  margin-top: var(--spacing-4);
  padding-top: var(--spacing-4);
  border-top: 1px solid var(--border-light);
}

.details-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--spacing-3);
}

.detail-item {
  display: flex;
  flex-direction: column;
}

.detail-label {
  font-size: 12px;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: var(--spacing-1);
}

.detail-value {
  font-size: 14px;
  color: var(--text-primary);
}

.params-display,
.result-display {
  font-family: 'Courier New', monospace;
  font-size: 12px;
  background: var(--bg-surface);
  padding: var(--spacing-3);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-light);
  overflow-x: auto;
  max-height: 200px;
  overflow-y: auto;
}

.error-display {
  background: #fef2f2;
  color: #dc2626;
  padding: var(--spacing-3);
  border-radius: var(--radius-md);
  border: 1px solid #fecaca;
  font-size: 14px;
}

/* Modal Styles */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: var(--spacing-4);
}

.modal-content {
  background: var(--bg-surface);
  border-radius: var(--radius-lg);
  width: 100%;
  max-width: 500px;
  box-shadow: var(--shadow-2xl);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-5);
  border-bottom: 1px solid var(--border-light);
}

.modal-body {
  padding: var(--spacing-5);
  max-height: 60vh;
  overflow-y: auto;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-3);
  padding: var(--spacing-5);
  border-top: 1px solid var(--border-light);
}

.form-group {
  margin-bottom: var(--spacing-4);
}

.form-label {
  display: block;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: var(--spacing-2);
}

.form-input,
.form-select,
.form-textarea {
  width: 100%;
  padding: var(--spacing-2-5) var(--spacing-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  font-size: 14px;
  background: var(--bg-tertiary);
  color: var(--text-primary);
  transition: border-color var(--duration-200);
}

.form-input:focus,
.form-select:focus,
.form-textarea:focus {
  outline: none;
  border-color: var(--color-primary);
}
</style>
