<template>
  <div class="session-manager">
    <!-- Header -->
    <div class="manager-header">
      <div class="flex items-center space-x-3">
        <i class="fas fa-window-restore text-green-600 text-xl"></i>
        <div>
          <h3 class="text-lg font-semibold text-gray-800">Browser Sessions</h3>
          <p class="text-sm text-gray-500">Manage persistent browser sessions</p>
        </div>
      </div>

      <div class="flex items-center space-x-2">
        <BaseButton
          variant="primary"
          size="sm"
          @click="showCreateModal = true"
        >
          <i class="fas fa-plus mr-1"></i>
          New Session
        </BaseButton>
      </div>
    </div>

    <!-- Stats -->
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-icon bg-green-100 text-green-600">
          <i class="fas fa-check-circle"></i>
        </div>
        <div>
          <div class="stat-value">{{ activeSessions.length }}</div>
          <div class="stat-label">Active</div>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-icon bg-yellow-100 text-yellow-600">
          <i class="fas fa-pause-circle"></i>
        </div>
        <div>
          <div class="stat-value">{{ idleSessions.length }}</div>
          <div class="stat-label">Idle</div>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-icon bg-blue-100 text-blue-600">
          <i class="fas fa-save"></i>
        </div>
        <div>
          <div class="stat-value">{{ persistentSessions.length }}</div>
          <div class="stat-label">Persistent</div>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-icon bg-gray-100 text-gray-600">
          <i class="fas fa-window-restore"></i>
        </div>
        <div>
          <div class="stat-value">{{ sessions.length }}</div>
          <div class="stat-label">Total</div>
        </div>
      </div>
    </div>

    <!-- Sessions List -->
    <div class="sessions-list">
      <div v-if="sessions.length === 0" class="empty-state">
        <EmptyState
          icon="fas fa-window-restore"
          title="No Sessions"
          message="Create a browser session to get started"
        >
          <template #actions>
            <BaseButton variant="primary" @click="showCreateModal = true">
              <i class="fas fa-plus mr-2"></i>
              Create Session
            </BaseButton>
          </template>
        </EmptyState>
      </div>

      <div v-else class="sessions-grid">
        <div
          v-for="session in sortedSessions"
          :key="session.id"
          class="session-card"
          :class="getSessionStatusClass(session.status)"
        >
          <!-- Session Header -->
          <div class="session-header">
            <div class="flex items-center space-x-3 flex-1">
              <div class="session-icon" :class="getSessionIconClass(session.status)">
                <i :class="getSessionIcon(session.status)"></i>
              </div>
              <div class="flex-1">
                <h4 class="session-name">{{ session.name }}</h4>
                <p class="session-url">{{ session.url }}</p>
              </div>
            </div>

            <div class="flex items-center space-x-2">
              <StatusBadge :variant="getStatusVariant(session.status)" size="small">
                {{ session.status.toUpperCase() }}
              </StatusBadge>

              <div v-if="session.persistent" class="persistent-badge" title="Persistent Session">
                <i class="fas fa-thumbtack"></i>
              </div>
            </div>
          </div>

          <!-- Session Info -->
          <div class="session-info">
            <div class="info-grid">
              <div class="info-item">
                <i class="fas fa-calendar text-gray-400"></i>
                <span class="text-sm text-gray-600">Created {{ formatDate(session.createdAt) }}</span>
              </div>
              <div class="info-item">
                <i class="fas fa-clock text-gray-400"></i>
                <span class="text-sm text-gray-600">Active {{ formatTimeAgo(session.lastActivityAt) }}</span>
              </div>
              <div v-if="session.cookies" class="info-item">
                <i class="fas fa-cookie text-gray-400"></i>
                <span class="text-sm text-gray-600">{{ session.cookies.length }} cookies</span>
              </div>
            </div>
          </div>

          <!-- Session Actions -->
          <div class="session-actions">
            <BaseButton
              v-if="session.status === 'active'"
              variant="outline"
              size="sm"
              @click="pauseSession(session.id)"
            >
              <i class="fas fa-pause mr-1"></i>
              Pause
            </BaseButton>

            <BaseButton
              v-if="session.status === 'idle' || session.status === 'closed'"
              variant="primary"
              size="sm"
              @click="resumeSession(session.id)"
            >
              <i class="fas fa-play mr-1"></i>
              Resume
            </BaseButton>

            <BaseButton
              variant="outline"
              size="sm"
              @click="openSession(session.id)"
            >
              <i class="fas fa-external-link-alt mr-1"></i>
              Open
            </BaseButton>

            <button
              @click="togglePersistent(session.id)"
              class="action-btn"
              :title="session.persistent ? 'Remove Persistence' : 'Make Persistent'"
            >
              <i class="fas fa-thumbtack" :class="{ 'text-blue-600': session.persistent }"></i>
            </button>

            <button
              @click="duplicateSession(session.id)"
              class="action-btn"
              title="Duplicate Session"
            >
              <i class="fas fa-copy"></i>
            </button>

            <button
              v-if="session.status !== 'closed'"
              @click="closeSession(session.id)"
              class="action-btn"
              title="Close Session"
            >
              <i class="fas fa-times"></i>
            </button>

            <button
              @click="deleteSession(session.id)"
              class="action-btn text-red-600"
              title="Delete Session"
            >
              <i class="fas fa-trash"></i>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Create Session Modal -->
    <div v-if="showCreateModal" class="modal-overlay" @click.self="showCreateModal = false">
      <div class="modal-content">
        <div class="modal-header">
          <h3 class="text-lg font-semibold">Create Browser Session</h3>
          <button @click="showCreateModal = false" class="text-gray-400 hover:text-gray-600">
            <i class="fas fa-times"></i>
          </button>
        </div>

        <div class="modal-body">
          <div class="form-group">
            <label class="form-label">Session Name</label>
            <input
              v-model="newSession.name"
              type="text"
              class="form-input"
              placeholder="e.g., Development Testing, Admin Panel"
              @keyup.enter="createNewSession"
            />
          </div>

          <div class="form-group">
            <label class="form-label">Starting URL</label>
            <input
              v-model="newSession.url"
              type="url"
              class="form-input"
              placeholder="https://example.com"
            />
          </div>

          <div class="form-group">
            <label class="flex items-center space-x-2 cursor-pointer">
              <input
                v-model="newSession.persistent"
                type="checkbox"
                class="form-checkbox"
              />
              <span class="text-sm font-medium text-gray-700">Make this session persistent</span>
            </label>
            <p class="text-xs text-gray-500 mt-1">
              Persistent sessions will be saved and restored across browser restarts
            </p>
          </div>
        </div>

        <div class="modal-footer">
          <BaseButton variant="outline" @click="showCreateModal = false">
            Cancel
          </BaseButton>
          <BaseButton
            variant="primary"
            @click="createNewSession"
            :disabled="!isFormValid"
          >
            <i class="fas fa-plus mr-1"></i>
            Create Session
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
import type { SessionStatus } from '@/types/browser'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('BrowserSessionManager')

export default {
  name: 'BrowserSessionManager',
  components: {
    BaseButton,
    StatusBadge,
    EmptyState
  },
  setup() {
    const {
      sessions,
      createSession,
      closeSession: closeSessionHandler,
      deleteSession: deleteSessionHandler,
      updateSessionActivity
    } = useBrowserAutomation()

    const showCreateModal = ref(false)
    const newSession = ref({
      name: '',
      url: 'https://',
      persistent: false
    })

    // Computed
    const activeSessions = computed(() =>
      sessions.value.filter(s => s.status === 'active')
    )

    const idleSessions = computed(() =>
      sessions.value.filter(s => s.status === 'idle')
    )

    const persistentSessions = computed(() =>
      sessions.value.filter(s => s.persistent)
    )

    const sortedSessions = computed(() => {
      return [...sessions.value].sort((a, b) => {
        // Sort by status priority, then by last activity
        const statusPriority: Record<SessionStatus, number> = {
          active: 0,
          idle: 1,
          closed: 2
        }

        const priorityDiff = statusPriority[a.status] - statusPriority[b.status]
        if (priorityDiff !== 0) return priorityDiff

        return b.lastActivityAt.getTime() - a.lastActivityAt.getTime()
      })
    })

    const isFormValid = computed(() => {
      return newSession.value.name.trim() && newSession.value.url.trim().startsWith('http')
    })

    // Methods
    const createNewSession = () => {
      if (!isFormValid.value) return

      createSession(
        newSession.value.name,
        newSession.value.url,
        newSession.value.persistent
      )

      // Reset form
      newSession.value = {
        name: '',
        url: 'https://',
        persistent: false
      }

      showCreateModal.value = false
      logger.info('Created new session')
    }

    const pauseSession = (sessionId: string) => {
      const session = sessions.value.find(s => s.id === sessionId)
      if (session) {
        session.status = 'idle'
        logger.info('Paused session', { id: sessionId })
      }
    }

    const resumeSession = (sessionId: string) => {
      const session = sessions.value.find(s => s.id === sessionId)
      if (session) {
        session.status = 'active'
        updateSessionActivity(sessionId)
        logger.info('Resumed session', { id: sessionId })
      }
    }

    const openSession = (sessionId: string) => {
      const session = sessions.value.find(s => s.id === sessionId)
      if (session) {
        window.open(session.url, `session-${sessionId}`)
        updateSessionActivity(sessionId)
        logger.info('Opened session', { id: sessionId })
      }
    }

    const togglePersistent = (sessionId: string) => {
      const session = sessions.value.find(s => s.id === sessionId)
      if (session) {
        session.persistent = !session.persistent
        logger.info('Toggled persistent', { id: sessionId, persistent: session.persistent })
      }
    }

    const duplicateSession = (sessionId: string) => {
      const session = sessions.value.find(s => s.id === sessionId)
      if (session) {
        createSession(
          `${session.name} (Copy)`,
          session.url,
          session.persistent
        )
        logger.info('Duplicated session', { id: sessionId })
      }
    }

    const closeSession = (sessionId: string) => {
      closeSessionHandler(sessionId)
      logger.info('Closed session', { id: sessionId })
    }

    const deleteSession = (sessionId: string) => {
      if (confirm('Are you sure you want to delete this session?')) {
        deleteSessionHandler(sessionId)
        logger.info('Deleted session', { id: sessionId })
      }
    }

    const getSessionStatusClass = (status: SessionStatus): string => {
      switch (status) {
        case 'active': return 'status-active'
        case 'idle': return 'status-idle'
        case 'closed': return 'status-closed'
        default: return ''
      }
    }

    const getStatusVariant = (status: SessionStatus): 'success' | 'warning' | 'danger' | 'info' => {
      switch (status) {
        case 'active': return 'success'
        case 'idle': return 'warning'
        case 'closed': return 'info'
        default: return 'info'
      }
    }

    const getSessionIcon = (status: SessionStatus): string => {
      switch (status) {
        case 'active': return 'fas fa-check-circle'
        case 'idle': return 'fas fa-pause-circle'
        case 'closed': return 'fas fa-times-circle'
        default: return 'fas fa-circle'
      }
    }

    const getSessionIconClass = (status: SessionStatus): string => {
      switch (status) {
        case 'active': return 'bg-green-100 text-green-600'
        case 'idle': return 'bg-yellow-100 text-yellow-600'
        case 'closed': return 'bg-gray-100 text-gray-600'
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

    const formatTimeAgo = (date: Date): string => {
      const seconds = Math.floor((Date.now() - date.getTime()) / 1000)

      if (seconds < 60) return `${seconds}s ago`
      if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
      if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
      return `${Math.floor(seconds / 86400)}d ago`
    }

    return {
      sessions,
      showCreateModal,
      newSession,
      activeSessions,
      idleSessions,
      persistentSessions,
      sortedSessions,
      isFormValid,
      createNewSession,
      pauseSession,
      resumeSession,
      openSession,
      togglePersistent,
      duplicateSession,
      closeSession,
      deleteSession,
      getSessionStatusClass,
      getStatusVariant,
      getSessionIcon,
      getSessionIconClass,
      formatDate,
      formatTimeAgo
    }
  }
}
</script>

<style scoped>
.session-manager {
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

.sessions-list {
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

.sessions-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: var(--spacing-4);
}

.session-card {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
  transition: all var(--duration-200);
}

.session-card:hover {
  box-shadow: var(--shadow-md);
}

.session-card.status-active {
  border-left: 4px solid #10b981;
}

.session-card.status-idle {
  border-left: 4px solid #f59e0b;
}

.session-card.status-closed {
  border-left: 4px solid #6b7280;
  opacity: 0.7;
}

.session-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--spacing-3);
}

.session-icon {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-md);
  font-size: 18px;
}

.session-name {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--spacing-1);
}

.session-url {
  font-size: 12px;
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.persistent-badge {
  padding: 4px 8px;
  background: #dbeafe;
  color: #1e40af;
  border-radius: var(--radius-sm);
  font-size: 12px;
}

.session-info {
  padding: var(--spacing-3);
  background: var(--bg-surface);
  border-radius: var(--radius-md);
  margin-bottom: var(--spacing-3);
}

.info-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: var(--spacing-2);
}

.info-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.session-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-2);
}

.action-btn {
  padding: var(--spacing-2) var(--spacing-3);
  background: transparent;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  cursor: pointer;
  color: var(--text-secondary);
  transition: all var(--duration-200);
}

.action-btn:hover {
  background: var(--bg-surface);
  color: var(--text-primary);
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

.form-input {
  width: 100%;
  padding: var(--spacing-2-5) var(--spacing-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  font-size: 14px;
  background: var(--bg-tertiary);
  color: var(--text-primary);
  transition: border-color var(--duration-200);
}

.form-input:focus {
  outline: none;
  border-color: var(--color-primary);
}

.form-checkbox {
  width: 18px;
  height: 18px;
  border: 2px solid var(--border-default);
  border-radius: var(--radius-sm);
  cursor: pointer;
}
</style>
