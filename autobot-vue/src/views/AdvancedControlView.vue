<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<template>
  <div class="advanced-control-view">
    <!-- Sidebar Navigation -->
    <aside class="control-sidebar">
      <div class="sidebar-header">
        <h3><i class="fas fa-gamepad"></i> Session Control</h3>
      </div>

      <!-- Category Navigation -->
      <nav class="category-nav">
        <div
          class="category-item"
          :class="{ active: activeSection === 'overview' }"
          @click="activeSection = 'overview'"
        >
          <i class="fas fa-tachometer-alt"></i>
          <span>Overview</span>
        </div>

        <div class="category-divider">
          <span>Desktop Streaming</span>
        </div>

        <div
          class="category-item"
          :class="{ active: activeSection === 'sessions' }"
          @click="activeSection = 'sessions'"
        >
          <i class="fas fa-desktop"></i>
          <span>Active Sessions</span>
          <span class="count" v-if="sessionCount > 0">{{ sessionCount }}</span>
        </div>

        <div
          class="category-item"
          :class="{ active: activeSection === 'create-session' }"
          @click="activeSection = 'create-session'"
        >
          <i class="fas fa-plus-circle"></i>
          <span>New Session</span>
        </div>

        <div class="category-divider">
          <span>Takeover Management</span>
        </div>

        <div
          class="category-item"
          :class="{ active: activeSection === 'pending' }"
          @click="activeSection = 'pending'"
        >
          <i class="fas fa-clock"></i>
          <span>Pending Requests</span>
          <span class="count alert" v-if="pendingCount > 0">{{ pendingCount }}</span>
        </div>

        <div
          class="category-item"
          :class="{ active: activeSection === 'active-takeovers' }"
          @click="activeSection = 'active-takeovers'"
        >
          <i class="fas fa-hand-paper"></i>
          <span>Active Takeovers</span>
          <span class="count" v-if="activeCount > 0">{{ activeCount }}</span>
        </div>

        <div class="category-divider">
          <span>System</span>
        </div>

        <div
          class="category-item"
          :class="{ active: activeSection === 'capabilities' }"
          @click="activeSection = 'capabilities'"
        >
          <i class="fas fa-cogs"></i>
          <span>Capabilities</span>
        </div>
      </nav>

      <!-- Quick Actions -->
      <div class="sidebar-actions">
        <button @click="loadAllData" class="btn-refresh" :disabled="loading">
          <i class="fas fa-sync-alt" :class="{ 'fa-spin': loading }"></i>
          Refresh
        </button>
        <button
          @click="handleEmergencyStop"
          class="btn-emergency"
          :disabled="emergencyLoading"
        >
          <i class="fas fa-stop-circle"></i>
          Emergency Stop
        </button>
      </div>
    </aside>

    <!-- Main Content -->
    <main class="control-content">
      <!-- Header -->
      <header class="content-header">
        <div class="header-left">
          <h2>{{ sectionTitle }}</h2>
          <span class="subtitle">{{ sectionDescription }}</span>
        </div>
        <div class="header-actions">
          <div class="status-badge" :class="systemStatusClass">
            <i :class="systemStatusIcon"></i>
            <span>{{ systemStatusLabel }}</span>
          </div>
        </div>
      </header>

      <!-- Loading State -->
      <div v-if="loading && !hasData" class="loading-container">
        <LoadingSpinner size="lg" />
        <p>Loading advanced control data...</p>
      </div>

      <!-- Error State -->
      <div v-else-if="error" class="error-container">
        <div class="error-icon">
          <i class="fas fa-exclamation-triangle"></i>
        </div>
        <h3>Failed to Load Data</h3>
        <p>{{ error }}</p>
        <button @click="loadAllData" class="btn-primary">
          <i class="fas fa-redo"></i> Retry
        </button>
      </div>

      <!-- Content Sections -->
      <div v-else class="content-body">
        <!-- Overview Section -->
        <section v-if="activeSection === 'overview'" class="section-overview">
          <div class="stats-grid">
            <div class="stat-card">
              <div class="stat-icon">
                <i class="fas fa-desktop"></i>
              </div>
              <div class="stat-info">
                <span class="stat-value">{{ sessionCount }}</span>
                <span class="stat-label">Active Sessions</span>
              </div>
            </div>

            <div class="stat-card" :class="{ alert: pendingCount > 0 }">
              <div class="stat-icon">
                <i class="fas fa-clock"></i>
              </div>
              <div class="stat-info">
                <span class="stat-value">{{ pendingCount }}</span>
                <span class="stat-label">Pending Requests</span>
              </div>
            </div>

            <div class="stat-card" :class="{ active: activeCount > 0 }">
              <div class="stat-icon">
                <i class="fas fa-hand-paper"></i>
              </div>
              <div class="stat-info">
                <span class="stat-value">{{ activeCount }}</span>
                <span class="stat-label">Active Takeovers</span>
              </div>
            </div>

            <div class="stat-card">
              <div class="stat-icon">
                <i class="fas fa-pause-circle"></i>
              </div>
              <div class="stat-info">
                <span class="stat-value">{{ pausedTasksCount }}</span>
                <span class="stat-label">Paused Tasks</span>
              </div>
            </div>
          </div>

          <div class="overview-sections">
            <div class="overview-card" v-if="systemHealth">
              <h4><i class="fas fa-heartbeat"></i> System Health</h4>
              <div class="health-grid">
                <div class="health-item">
                  <span class="label">Desktop Streaming</span>
                  <span class="value" :class="{ available: systemHealth.desktop_streaming_available }">
                    {{ systemHealth.desktop_streaming_available ? 'Available' : 'Unavailable' }}
                  </span>
                </div>
                <div class="health-item">
                  <span class="label">noVNC</span>
                  <span class="value" :class="{ available: systemHealth.novnc_available }">
                    {{ systemHealth.novnc_available ? 'Available' : 'Unavailable' }}
                  </span>
                </div>
              </div>
            </div>

            <div class="overview-card" v-if="resourceUsage">
              <h4><i class="fas fa-server"></i> Resource Usage</h4>
              <div class="resource-grid">
                <div class="resource-item">
                  <span class="label">CPU</span>
                  <div class="progress-bar">
                    <div class="progress" :style="{ width: `${resourceUsage.cpu_percent}%` }"></div>
                  </div>
                  <span class="value">{{ resourceUsage.cpu_percent.toFixed(1) }}%</span>
                </div>
                <div class="resource-item">
                  <span class="label">Memory</span>
                  <div class="progress-bar">
                    <div class="progress" :style="{ width: `${resourceUsage.memory_percent}%` }"></div>
                  </div>
                  <span class="value">{{ resourceUsage.memory_percent.toFixed(1) }}%</span>
                </div>
                <div class="resource-item">
                  <span class="label">Disk</span>
                  <div class="progress-bar">
                    <div class="progress" :style="{ width: `${resourceUsage.disk_usage}%` }"></div>
                  </div>
                  <span class="value">{{ resourceUsage.disk_usage.toFixed(1) }}%</span>
                </div>
              </div>
            </div>
          </div>
        </section>

        <!-- Sessions List Section -->
        <section v-if="activeSection === 'sessions'" class="section-sessions">
          <SessionsList
            :sessions="streamingSessions"
            :loading="sessionsLoading"
            @terminate="handleTerminateSession"
            @refresh="loadStreamingSessions"
          />
        </section>

        <!-- Create Session Section -->
        <section v-if="activeSection === 'create-session'" class="section-create">
          <SessionCreationWizard
            :capabilities="capabilities"
            :loading="createSessionLoading"
            @create="handleCreateSession"
          />
        </section>

        <!-- Pending Takeovers Section -->
        <section v-if="activeSection === 'pending'" class="section-pending">
          <TakeoverRequestManager
            :requests="pendingTakeovers"
            :loading="takeoverLoading"
            @approve="handleApproveTakeover"
            @refresh="loadPendingTakeovers"
          />
        </section>

        <!-- Active Takeovers Section -->
        <section v-if="activeSection === 'active-takeovers'" class="section-active">
          <SessionControlPanel
            :sessions="activeTakeovers"
            :loading="takeoverLoading"
            @pause="handlePauseSession"
            @resume="handleResumeSession"
            @complete="handleCompleteSession"
            @execute-action="handleExecuteAction"
            @refresh="loadActiveTakeovers"
          />
        </section>

        <!-- Capabilities Section -->
        <section v-if="activeSection === 'capabilities'" class="section-capabilities">
          <CapabilitiesDisplay
            :capabilities="capabilities"
            :control-info="controlInfo"
            :loading="capabilitiesLoading"
            @refresh="loadCapabilities"
          />
        </section>
      </div>
    </main>

    <!-- Emergency Stop Confirmation Modal -->
    <BaseModal
      v-model="showEmergencyModal"
      title="Confirm Emergency Stop"
      size="medium"
    >
      <div class="emergency-modal-content">
        <div class="warning-icon">
          <i class="fas fa-exclamation-triangle"></i>
        </div>
        <p>
          This will immediately stop all autonomous operations and initiate an emergency takeover.
          <strong>This action cannot be undone.</strong>
        </p>
        <p>Are you sure you want to proceed?</p>
      </div>
      <template #actions>
        <button @click="showEmergencyModal = false" class="btn-secondary">Cancel</button>
        <button @click="confirmEmergencyStop" class="btn-danger" :disabled="emergencyLoading">
          <i class="fas fa-stop-circle"></i>
          {{ emergencyLoading ? 'Stopping...' : 'Confirm Emergency Stop' }}
        </button>
      </template>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { createLogger } from '@/utils/debugUtils';
import { useToast } from '@/composables/useToast';
import {
  advancedControlApiClient,
  type StreamingSession,
  type StreamingCapabilities,
  type PendingTakeoverRequest,
  type ActiveTakeoverSession,
  type TakeoverApprovalRequest,
  type TakeoverActionRequest,
  type TakeoverCompletionRequest,
  type ResourceUsage,
  type SystemHealthResponse,
  type AdvancedControlInfo,
} from '@/utils/AdvancedControlApiClient';
import LoadingSpinner from '@/components/ui/LoadingSpinner.vue';
import BaseModal from '@/components/ui/BaseModal.vue';
import SessionsList from '@/components/advanced-control/SessionsList.vue';
import SessionCreationWizard from '@/components/advanced-control/SessionCreationWizard.vue';
import TakeoverRequestManager from '@/components/advanced-control/TakeoverRequestManager.vue';
import SessionControlPanel from '@/components/advanced-control/SessionControlPanel.vue';
import CapabilitiesDisplay from '@/components/advanced-control/CapabilitiesDisplay.vue';

const logger = createLogger('AdvancedControlView');
const { showToast } = useToast();

// State
const loading = ref(false);
const error = ref<string | null>(null);
const activeSection = ref<
  'overview' | 'sessions' | 'create-session' | 'pending' | 'active-takeovers' | 'capabilities'
>('overview');

// Data State
const streamingSessions = ref<StreamingSession[]>([]);
const pendingTakeovers = ref<PendingTakeoverRequest[]>([]);
const activeTakeovers = ref<ActiveTakeoverSession[]>([]);
const capabilities = ref<StreamingCapabilities | null>(null);
const controlInfo = ref<AdvancedControlInfo | null>(null);
const systemHealth = ref<SystemHealthResponse | null>(null);
const resourceUsage = ref<ResourceUsage | null>(null);

// Loading States
const sessionsLoading = ref(false);
const takeoverLoading = ref(false);
const capabilitiesLoading = ref(false);
const createSessionLoading = ref(false);
const emergencyLoading = ref(false);

// Modal State
const showEmergencyModal = ref(false);

// WebSocket for real-time updates
let monitoringWs: WebSocket | null = null;
let wsReconnectTimer: ReturnType<typeof setTimeout> | null = null;

// Computed
const hasData = computed(() => systemHealth.value !== null);

const sessionCount = computed(() => streamingSessions.value.length);
const pendingCount = computed(() => pendingTakeovers.value.length);
const activeCount = computed(() => activeTakeovers.value.length);
const pausedTasksCount = computed(() => systemHealth.value?.paused_tasks ?? 0);

const systemStatusClass = computed(() => {
  if (!systemHealth.value) return 'unknown';
  if (systemHealth.value.status === 'unhealthy') return 'error';
  if (activeCount.value > 0) return 'takeover';
  if (pendingCount.value > 0) return 'warning';
  return 'healthy';
});

const systemStatusIcon = computed(() => {
  const icons: Record<string, string> = {
    healthy: 'fas fa-check-circle',
    warning: 'fas fa-exclamation-circle',
    takeover: 'fas fa-hand-paper',
    error: 'fas fa-times-circle',
    unknown: 'fas fa-question-circle',
  };
  return icons[systemStatusClass.value] || icons.unknown;
});

const systemStatusLabel = computed(() => {
  const labels: Record<string, string> = {
    healthy: 'System Healthy',
    warning: 'Pending Requests',
    takeover: 'Takeover Active',
    error: 'System Error',
    unknown: 'Unknown',
  };
  return labels[systemStatusClass.value] || labels.unknown;
});

const sectionTitle = computed(() => {
  const titles: Record<string, string> = {
    overview: 'Control Overview',
    sessions: 'Desktop Streaming Sessions',
    'create-session': 'Create New Session',
    pending: 'Pending Takeover Requests',
    'active-takeovers': 'Active Takeover Sessions',
    capabilities: 'System Capabilities',
  };
  return titles[activeSection.value] || 'Advanced Control';
});

const sectionDescription = computed(() => {
  const descriptions: Record<string, string> = {
    overview: 'Monitor and manage desktop streaming and takeover operations',
    sessions: 'View and manage active desktop streaming sessions',
    'create-session': 'Create a new desktop streaming session for remote access',
    pending: 'Review and approve pending takeover requests',
    'active-takeovers': 'Control active takeover sessions',
    capabilities: 'View system capabilities and configuration',
  };
  return descriptions[activeSection.value] || '';
});

// Methods
const loadAllData = async () => {
  loading.value = true;
  error.value = null;

  try {
    await Promise.all([
      loadSystemHealth(),
      loadStreamingSessions(),
      loadPendingTakeovers(),
      loadActiveTakeovers(),
      loadCapabilities(),
      loadControlInfo(),
    ]);
  } catch (err) {
    logger.error('Failed to load data:', err);
    error.value = err instanceof Error ? err.message : 'Failed to load advanced control data';
  } finally {
    loading.value = false;
  }
};

const loadSystemHealth = async () => {
  const response = await advancedControlApiClient.getSystemHealth();
  if (response.success && response.data) {
    systemHealth.value = response.data;
  }

  const statusResponse = await advancedControlApiClient.getSystemStatus();
  if (statusResponse.success && statusResponse.data) {
    resourceUsage.value = statusResponse.data.resource_usage;
  }
};

const loadStreamingSessions = async () => {
  sessionsLoading.value = true;
  try {
    const response = await advancedControlApiClient.listStreamingSessions();
    if (response.success && response.data) {
      streamingSessions.value = response.data.sessions;
    }
  } catch (err) {
    logger.error('Failed to load streaming sessions:', err);
  } finally {
    sessionsLoading.value = false;
  }
};

const loadPendingTakeovers = async () => {
  takeoverLoading.value = true;
  try {
    const response = await advancedControlApiClient.getPendingTakeovers();
    if (response.success && response.data) {
      pendingTakeovers.value = response.data.pending_requests;
    }
  } catch (err) {
    logger.error('Failed to load pending takeovers:', err);
  } finally {
    takeoverLoading.value = false;
  }
};

const loadActiveTakeovers = async () => {
  takeoverLoading.value = true;
  try {
    const response = await advancedControlApiClient.getActiveTakeovers();
    if (response.success && response.data) {
      activeTakeovers.value = response.data.active_sessions;
    }
  } catch (err) {
    logger.error('Failed to load active takeovers:', err);
  } finally {
    takeoverLoading.value = false;
  }
};

const loadCapabilities = async () => {
  capabilitiesLoading.value = true;
  try {
    const response = await advancedControlApiClient.getStreamingCapabilities();
    if (response.success && response.data) {
      capabilities.value = response.data;
    }
  } catch (err) {
    logger.error('Failed to load capabilities:', err);
  } finally {
    capabilitiesLoading.value = false;
  }
};

const loadControlInfo = async () => {
  try {
    const response = await advancedControlApiClient.getControlInfo();
    if (response.success && response.data) {
      controlInfo.value = response.data;
    }
  } catch (err) {
    logger.error('Failed to load control info:', err);
  }
};

// Session handlers
const handleCreateSession = async (request: { user_id: string; resolution: string; depth: number }) => {
  createSessionLoading.value = true;
  try {
    const response = await advancedControlApiClient.createStreamingSession(request);
    if (response.success && response.data) {
      showToast('Streaming session created successfully', 'success');
      await loadStreamingSessions();
      activeSection.value = 'sessions';
    } else {
      showToast(response.error || 'Failed to create session', 'error');
    }
  } catch (err) {
    showToast('Failed to create streaming session', 'error');
    logger.error('Failed to create session:', err);
  } finally {
    createSessionLoading.value = false;
  }
};

const handleTerminateSession = async (sessionId: string) => {
  sessionsLoading.value = true;
  try {
    const response = await advancedControlApiClient.terminateStreamingSession(sessionId);
    if (response.success) {
      showToast('Session terminated', 'success');
      await loadStreamingSessions();
    } else {
      showToast(response.error || 'Failed to terminate session', 'error');
    }
  } catch (err) {
    showToast('Failed to terminate session', 'error');
    logger.error('Failed to terminate session:', err);
  } finally {
    sessionsLoading.value = false;
  }
};

// Takeover handlers
const handleApproveTakeover = async (requestId: string, approval: TakeoverApprovalRequest) => {
  takeoverLoading.value = true;
  try {
    const response = await advancedControlApiClient.approveTakeover(requestId, approval);
    if (response.success) {
      showToast('Takeover approved', 'success');
      await Promise.all([loadPendingTakeovers(), loadActiveTakeovers()]);
      activeSection.value = 'active-takeovers';
    } else {
      showToast(response.error || 'Failed to approve takeover', 'error');
    }
  } catch (err) {
    showToast('Failed to approve takeover', 'error');
    logger.error('Failed to approve takeover:', err);
  } finally {
    takeoverLoading.value = false;
  }
};

const handlePauseSession = async (sessionId: string) => {
  takeoverLoading.value = true;
  try {
    const response = await advancedControlApiClient.pauseTakeoverSession(sessionId);
    if (response.success) {
      showToast('Session paused', 'success');
      await loadActiveTakeovers();
    } else {
      showToast(response.error || 'Failed to pause session', 'error');
    }
  } catch (err) {
    showToast('Failed to pause session', 'error');
    logger.error('Failed to pause session:', err);
  } finally {
    takeoverLoading.value = false;
  }
};

const handleResumeSession = async (sessionId: string) => {
  takeoverLoading.value = true;
  try {
    const response = await advancedControlApiClient.resumeTakeoverSession(sessionId);
    if (response.success) {
      showToast('Session resumed', 'success');
      await loadActiveTakeovers();
    } else {
      showToast(response.error || 'Failed to resume session', 'error');
    }
  } catch (err) {
    showToast('Failed to resume session', 'error');
    logger.error('Failed to resume session:', err);
  } finally {
    takeoverLoading.value = false;
  }
};

const handleCompleteSession = async (sessionId: string, completion: TakeoverCompletionRequest) => {
  takeoverLoading.value = true;
  try {
    const response = await advancedControlApiClient.completeTakeoverSession(sessionId, completion);
    if (response.success) {
      showToast('Takeover session completed', 'success');
      await Promise.all([loadActiveTakeovers(), loadSystemHealth()]);
    } else {
      showToast(response.error || 'Failed to complete session', 'error');
    }
  } catch (err) {
    showToast('Failed to complete session', 'error');
    logger.error('Failed to complete session:', err);
  } finally {
    takeoverLoading.value = false;
  }
};

const handleExecuteAction = async (sessionId: string, action: TakeoverActionRequest) => {
  try {
    const response = await advancedControlApiClient.executeTakeoverAction(sessionId, action);
    if (response.success) {
      showToast('Action executed', 'success');
      await loadActiveTakeovers();
    } else {
      showToast(response.error || 'Failed to execute action', 'error');
    }
  } catch (err) {
    showToast('Failed to execute action', 'error');
    logger.error('Failed to execute action:', err);
  }
};

// Emergency stop handlers
const handleEmergencyStop = () => {
  showEmergencyModal.value = true;
};

const confirmEmergencyStop = async () => {
  emergencyLoading.value = true;
  try {
    const response = await advancedControlApiClient.emergencyStop();
    if (response.success) {
      showToast('Emergency stop activated', 'warning');
      showEmergencyModal.value = false;
      await loadAllData();
    } else {
      showToast(response.error || 'Failed to activate emergency stop', 'error');
    }
  } catch (err) {
    showToast('Failed to activate emergency stop', 'error');
    logger.error('Failed to activate emergency stop:', err);
  } finally {
    emergencyLoading.value = false;
  }
};

// WebSocket connection for real-time updates
const connectMonitoringWebSocket = () => {
  try {
    const wsUrl = advancedControlApiClient.getMonitoringWebSocketUrl();
    monitoringWs = new WebSocket(wsUrl);

    monitoringWs.onopen = () => {
      logger.debug('Monitoring WebSocket connected');
    };

    monitoringWs.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        if (message.type === 'system_health') {
          systemHealth.value = message.data;
        }
      } catch (err) {
        logger.error('Failed to parse WebSocket message:', err);
      }
    };

    monitoringWs.onclose = () => {
      logger.debug('Monitoring WebSocket disconnected');
      wsReconnectTimer = setTimeout(connectMonitoringWebSocket, 5000);
    };

    monitoringWs.onerror = (err) => {
      logger.error('Monitoring WebSocket error:', err);
    };
  } catch (err) {
    logger.error('Failed to connect monitoring WebSocket:', err);
    wsReconnectTimer = setTimeout(connectMonitoringWebSocket, 5000);
  }
};

const disconnectMonitoringWebSocket = () => {
  if (wsReconnectTimer) {
    clearTimeout(wsReconnectTimer);
    wsReconnectTimer = null;
  }
  if (monitoringWs) {
    monitoringWs.close();
    monitoringWs = null;
  }
};

// Lifecycle
onMounted(() => {
  loadAllData();
  connectMonitoringWebSocket();
});

onUnmounted(() => {
  disconnectMonitoringWebSocket();
});
</script>

<style scoped>
.advanced-control-view {
  display: flex;
  height: 100%;
  min-height: 0;
  background: var(--bg-primary);
}

/* Sidebar */
.control-sidebar {
  width: 260px;
  min-width: 260px;
  background: var(--bg-secondary);
  border-right: 1px solid var(--border-default);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sidebar-header {
  padding: 20px;
  border-bottom: 1px solid var(--border-default);
}

.sidebar-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 10px;
}

.sidebar-header i {
  color: var(--color-primary);
}

.category-nav {
  flex: 1;
  overflow-y: auto;
  padding: 12px 0;
}

.category-divider {
  padding: 12px 20px 8px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-muted);
}

.category-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 20px;
  cursor: pointer;
  transition: all 0.15s;
  color: var(--text-secondary);
}

.category-item:hover {
  background: var(--bg-hover);
}

.category-item.active {
  background: var(--color-primary-bg);
  color: var(--color-primary);
}

.category-item i {
  width: 20px;
  text-align: center;
  font-size: 14px;
}

.category-item span:first-of-type:not(.count) {
  flex: 1;
  font-size: 14px;
}

.category-item .count {
  font-size: 12px;
  background: var(--bg-tertiary);
  padding: 2px 8px;
  border-radius: 10px;
  color: var(--text-tertiary);
}

.category-item.active .count {
  background: var(--color-primary);
  color: var(--text-on-primary);
}

.category-item .count.alert {
  background: var(--color-error);
  color: var(--text-on-error);
}

.sidebar-actions {
  padding: 16px 20px;
  border-top: 1px solid var(--border-default);
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.btn-refresh {
  width: 100%;
  padding: 10px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  transition: all 0.2s;
}

.btn-refresh:hover:not(:disabled) {
  background: var(--bg-hover);
}

.btn-refresh:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-emergency {
  width: 100%;
  padding: 10px;
  background: var(--color-error);
  color: var(--text-on-error);
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  transition: all 0.2s;
}

.btn-emergency:hover:not(:disabled) {
  background: var(--color-error-hover, #b91c1c);
}

.btn-emergency:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Main Content */
.control-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
}

.content-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-default);
}

.header-left h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
}

.header-left .subtitle {
  font-size: 13px;
  color: var(--text-tertiary);
}

.header-actions {
  display: flex;
  gap: 12px;
  align-items: center;
}

.status-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  border-radius: 20px;
  font-size: 13px;
  font-weight: 500;
}

.status-badge.healthy {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.status-badge.warning {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.status-badge.takeover {
  background: var(--color-primary-bg);
  color: var(--color-primary);
}

.status-badge.error {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.status-badge.unknown {
  background: var(--bg-tertiary);
  color: var(--text-tertiary);
}

/* Loading & Error States */
.loading-container,
.error-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  color: var(--text-tertiary);
  padding: 40px;
}

.error-container .error-icon {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  background: var(--color-error-bg);
  color: var(--color-error);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 28px;
}

.error-container h3 {
  margin: 0;
  color: var(--text-primary);
}

.error-container p {
  margin: 0;
  color: var(--text-secondary);
}

/* Content Body */
.content-body {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}

/* Overview Stats Grid */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}

.stat-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
}

.stat-card.alert {
  border-color: var(--color-error);
}

.stat-card.active {
  border-color: var(--color-primary);
}

.stat-card .stat-icon {
  width: 48px;
  height: 48px;
  border-radius: 10px;
  background: var(--bg-tertiary);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  color: var(--text-secondary);
}

.stat-card.alert .stat-icon {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.stat-card.active .stat-icon {
  background: var(--color-primary-bg);
  color: var(--color-primary);
}

.stat-info {
  display: flex;
  flex-direction: column;
}

.stat-value {
  font-size: 24px;
  font-weight: 600;
  color: var(--text-primary);
}

.stat-label {
  font-size: 13px;
  color: var(--text-tertiary);
}

/* Overview Sections */
.overview-sections {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 24px;
}

.overview-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 20px;
}

.overview-card h4 {
  margin: 0 0 16px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 8px;
}

.overview-card h4 i {
  color: var(--color-primary);
}

.health-grid {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.health-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.health-item .label {
  font-size: 13px;
  color: var(--text-secondary);
}

.health-item .value {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-error);
}

.health-item .value.available {
  color: var(--color-success);
}

.resource-grid {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.resource-item {
  display: flex;
  align-items: center;
  gap: 12px;
}

.resource-item .label {
  width: 60px;
  font-size: 13px;
  color: var(--text-secondary);
}

.resource-item .progress-bar {
  flex: 1;
  height: 8px;
  background: var(--bg-tertiary);
  border-radius: 4px;
  overflow: hidden;
}

.resource-item .progress {
  height: 100%;
  background: var(--color-primary);
  border-radius: 4px;
  transition: width 0.3s ease;
}

.resource-item .value {
  width: 50px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  text-align: right;
}

/* Emergency Modal */
.emergency-modal-content {
  text-align: center;
  padding: 20px;
}

.emergency-modal-content .warning-icon {
  width: 80px;
  height: 80px;
  margin: 0 auto 20px;
  border-radius: 50%;
  background: var(--color-error-bg);
  color: var(--color-error);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 36px;
}

.emergency-modal-content p {
  margin: 0 0 12px;
  color: var(--text-secondary);
}

.emergency-modal-content strong {
  color: var(--color-error);
}

/* Buttons */
.btn-primary {
  padding: 10px 20px;
  background: var(--color-primary);
  color: var(--text-on-primary);
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  transition: all 0.2s;
}

.btn-primary:hover {
  background: var(--color-primary-hover);
}

.btn-secondary {
  padding: 10px 20px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-secondary:hover {
  background: var(--bg-hover);
}

.btn-danger {
  padding: 10px 20px;
  background: var(--color-error);
  color: var(--text-on-error);
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  transition: all 0.2s;
}

.btn-danger:hover:not(:disabled) {
  background: var(--color-error-hover, #b91c1c);
}

.btn-danger:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Responsive */
@media (max-width: 768px) {
  .advanced-control-view {
    flex-direction: column;
  }

  .control-sidebar {
    width: 100%;
    min-width: 100%;
    max-height: 50vh;
  }

  .stats-grid {
    grid-template-columns: 1fr 1fr;
  }

  .overview-sections {
    grid-template-columns: 1fr;
  }
}
</style>
