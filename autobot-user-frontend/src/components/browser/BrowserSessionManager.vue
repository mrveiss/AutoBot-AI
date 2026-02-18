<template>
  <div class="session-manager">
    <!-- Header -->
    <div class="manager-header">
      <div class="flex items-center space-x-3">
        <i class="fas fa-window-restore text-green-600 text-xl"></i>
        <div>
          <h3 class="text-lg font-semibold text-autobot-text-primary">Browser Sessions</h3>
          <p class="text-sm text-autobot-text-muted">Manage persistent browser sessions</p>
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
        <div class="stat-icon bg-autobot-bg-tertiary text-autobot-text-secondary">
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
                <h4 class="session-name">{{ session.title }}</h4>
                <p class="session-url">{{ session.url }}</p>
              </div>
            </div>

            <div class="flex items-center space-x-2">
              <StatusBadge :variant="getStatusVariant(session.status)" size="small">
                {{ session.status.toUpperCase() }}
              </StatusBadge>


            </div>
          </div>

          <!-- Session Info -->
          <div class="session-info">
            <div class="info-grid">
              <div class="info-item">
                <i class="fas fa-calendar text-autobot-text-muted"></i>
                <span class="text-sm text-autobot-text-secondary">Created {{ formatDate(session.created_at) }}</span>
              </div>
              <div class="info-item">
                <i class="fas fa-clock text-autobot-text-muted"></i>
                <span class="text-sm text-autobot-text-secondary">Active {{ formatTimeAgo(session.last_activity) }}</span>
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
              v-if="session.status === 'idle' || session.status === 'error'"
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
              @click="duplicateSession(session.id)"
              class="action-btn"
              title="Duplicate Session"
            >
              <i class="fas fa-copy"></i>
            </button>

            <button
              v-if="session.status !== 'idle'"
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
          <button @click="showCreateModal = false" class="text-autobot-text-muted hover:text-autobot-text-secondary">
            <i class="fas fa-times"></i>
          </button>
        </div>

        <div class="modal-body">
          <div class="form-group">
            <label class="form-label">Starting URL</label>
            <input
              v-model="newSession.url"
              type="url"
              class="form-input"
              placeholder="https://example.com"
            />
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
      launchSession,
      closeSession: closeSessionHandler,
      deleteSession: deleteSessionHandler
    } = useBrowserAutomation()

    const showCreateModal = ref(false)
    const newSession = ref({
      url: 'https://'
    })

    // Computed
    const activeSessions = computed(() =>
      sessions.value.filter(s => s.status === 'active')
    )

    const idleSessions = computed(() =>
      sessions.value.filter(s => s.status === 'idle')
    )

    const persistentSessions = computed(() => [] as typeof sessions.value)

    const sortedSessions = computed(() => {
      return [...sessions.value].sort((a, b) => {
        // Sort by status priority, then by last activity
        const statusPriority: Record<SessionStatus, number> = {
          active: 0,
          idle: 1,
          error: 2
        }

        const priorityDiff = statusPriority[a.status] - statusPriority[b.status]
        if (priorityDiff !== 0) return priorityDiff

        return b.last_activity.localeCompare(a.last_activity)
      })
    })

    const isFormValid = computed(() => {
      return newSession.value.url.trim().startsWith('http')
    })

    // Methods
    const createNewSession = async () => {
      if (!isFormValid.value) return

      await launchSession(newSession.value.url)

      // Reset form
      newSession.value = {
        url: 'https://'
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
        logger.info('Resumed session', { id: sessionId })
      }
    }

    const openSession = (sessionId: string) => {
      const session = sessions.value.find(s => s.id === sessionId)
      if (session) {
        window.open(session.url, `session-${sessionId}`)
        logger.info('Opened session', { id: sessionId })
      }
    }

    const duplicateSession = async (sessionId: string) => {
      const session = sessions.value.find(s => s.id === sessionId)
      if (session) {
        await launchSession(session.url)
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
        case 'error': return 'status-closed'
        default: return ''
      }
    }

    const getStatusVariant = (status: SessionStatus): 'success' | 'warning' | 'danger' | 'info' => {
      switch (status) {
        case 'active': return 'success'
        case 'idle': return 'warning'
        case 'error': return 'danger'
        default: return 'info'
      }
    }

    const getSessionIcon = (status: SessionStatus): string => {
      switch (status) {
        case 'active': return 'fas fa-check-circle'
        case 'idle': return 'fas fa-pause-circle'
        case 'error': return 'fas fa-exclamation-circle'
        default: return 'fas fa-circle'
      }
    }

    const getSessionIconClass = (status: SessionStatus): string => {
      switch (status) {
        case 'active': return 'bg-green-100 text-green-600'
        case 'idle': return 'bg-yellow-100 text-yellow-600'
        case 'error': return 'bg-red-100 text-red-600'
        default: return 'bg-autobot-bg-tertiary text-autobot-text-secondary'
      }
    }

    const formatDate = (dateStr: string): string => {
      return new Intl.DateTimeFormat('en-US', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      }).format(new Date(dateStr))
    }

    const formatTimeAgo = (dateStr: string): string => {
      const seconds = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000)

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
