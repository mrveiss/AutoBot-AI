<template>
  <div class="workflow-live-dashboard">
    <!-- Connection Status -->
    <div class="connection-bar" :class="connectionStatusClass">
      <i :class="connectionIcon"></i>
      <span>{{ connectionLabel }}</span>
      <button
        v-if="!liveConnected"
        class="btn-reconnect"
        @click="reconnectLiveEvents"
        :disabled="isReconnecting"
      >
        <i class="fas fa-plug"></i> {{ $t('workflow.liveDashboard.reconnect') }}
      </button>
    </div>

    <!-- Summary Stats -->
    <div class="stats-bar">
      <div class="stat-chip">
        <i class="fas fa-play-circle"></i>
        <span class="stat-value">{{ runningCount }}</span>
        <span class="stat-label">{{ $t('workflow.liveDashboard.running') }}</span>
      </div>
      <div class="stat-chip">
        <i class="fas fa-pause-circle"></i>
        <span class="stat-value">{{ pausedCount }}</span>
        <span class="stat-label">{{ $t('workflow.liveDashboard.paused') }}</span>
      </div>
      <div class="stat-chip">
        <i class="fas fa-check-circle"></i>
        <span class="stat-value">{{ completedCount }}</span>
        <span class="stat-label">{{ $t('workflow.liveDashboard.completedRecent') }}</span>
      </div>
      <div class="stat-chip">
        <i class="fas fa-exclamation-circle"></i>
        <span class="stat-value">{{ failedCount }}</span>
        <span class="stat-label">{{ $t('workflow.liveDashboard.failed') }}</span>
      </div>
    </div>

    <!-- Active Execution Cards -->
    <div class="executions-section">
      <div class="section-header">
        <h3>
          <i class="fas fa-bolt"></i>
          {{ $t('workflow.liveDashboard.activeExecutions') }}
        </h3>
        <button class="btn-refresh-sm" @click="$emit('refresh')" :disabled="loading">
          <i class="fas fa-sync-alt" :class="{ 'fa-spin': loading }"></i>
        </button>
      </div>

      <!-- Empty State -->
      <div v-if="!loading && activeWorkflows.length === 0" class="empty-state">
        <i class="fas fa-wind"></i>
        <h4>{{ $t('workflow.liveDashboard.noActiveWorkflows') }}</h4>
        <p>{{ $t('workflow.liveDashboard.noActiveDescription') }}</p>
      </div>

      <!-- Loading -->
      <div v-else-if="loading && activeWorkflows.length === 0" class="loading-state">
        <i class="fas fa-spinner fa-spin"></i>
        <span>{{ $t('workflow.liveDashboard.loading') }}</span>
      </div>

      <!-- Workflow Cards -->
      <div v-else class="execution-grid">
        <div
          v-for="wf in activeWorkflows"
          :key="wf.workflow_id"
          class="execution-card"
          :class="getCardClass(wf)"
          @click="$emit('select-workflow', wf.workflow_id)"
        >
          <div class="card-header">
            <div class="card-title-row">
              <span class="card-name">{{ wf.name }}</span>
              <span class="status-badge" :class="getStatusBadgeClass(wf)">
                <i :class="getStatusIcon(wf)"></i>
                {{ getStatusLabel(wf) }}
              </span>
            </div>
            <span class="card-desc">{{ wf.description }}</span>
          </div>

          <!-- Progress Bar -->
          <div class="card-progress">
            <div class="progress-track">
              <div
                class="progress-fill"
                :style="{ width: getProgressPercent(wf) + '%' }"
                :class="getProgressClass(wf)"
              ></div>
            </div>
            <div class="progress-meta">
              <span class="step-counter">
                {{ $t('workflow.liveDashboard.stepOf', {
                  current: wf.current_step + 1,
                  total: wf.total_steps
                }) }}
              </span>
              <span class="progress-pct">{{ Math.round(getProgressPercent(wf)) }}%</span>
            </div>
          </div>

          <!-- Step Timeline -->
          <div class="step-timeline">
            <div
              v-for="(step, i) in wf.steps.slice(0, maxVisibleSteps)"
              :key="step.step_id"
              class="timeline-dot"
              :class="step.status"
              :title="step.description || $t('workflow.liveDashboard.stepN', { n: i + 1 })"
            >
              <i v-if="step.status === 'completed'" class="fas fa-check"></i>
              <i v-else-if="step.status === 'failed'" class="fas fa-times"></i>
              <i v-else-if="step.status === 'executing'" class="fas fa-spinner fa-spin"></i>
              <i v-else-if="step.status === 'waiting_approval'" class="fas fa-hand-paper"></i>
              <i v-else-if="step.status === 'paused'" class="fas fa-pause"></i>
              <span v-else class="dot-number">{{ i + 1 }}</span>
            </div>
            <span v-if="wf.steps.length > maxVisibleSteps" class="timeline-overflow">
              +{{ wf.steps.length - maxVisibleSteps }}
            </span>
          </div>

          <!-- Card Footer -->
          <div class="card-footer">
            <div class="footer-meta">
              <span v-if="wf.automation_mode" class="mode-tag">
                <i class="fas fa-cog"></i> {{ wf.automation_mode }}
              </span>
              <span v-if="wf.phase" class="phase-tag">
                <i class="fas fa-layer-group"></i> {{ wf.phase }}
              </span>
            </div>
            <div class="footer-time">
              <i class="fas fa-clock"></i>
              <span>{{ formatElapsed(wf) }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Agent Observability Panel -->
    <AgentObservabilityPanel
      :agent-performance="agentPerformance"
      :agent-capabilities="agentCapabilities"
      :loading="loadingCapabilities"
      @refresh="$emit('refresh-agents')"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { createLogger } from '@/utils/debugUtils';
import { useLiveEvents, type LiveEvent } from '@/composables/useLiveEvents';
import AgentObservabilityPanel from './AgentObservabilityPanel.vue';
import type {
  ActiveWorkflow,
  AgentPerformance,
  AgentCapability,
} from '@/composables/useWorkflowBuilder';

const logger = createLogger('WorkflowLiveDashboard');
const { t } = useI18n();

const props = defineProps<{
  activeWorkflows: ActiveWorkflow[];
  agentPerformance: Record<string, AgentPerformance>;
  agentCapabilities: Record<string, AgentCapability>;
  loading: boolean;
  loadingCapabilities: boolean;
}>();

const emit = defineEmits<{
  (e: 'refresh'): void;
  (e: 'refresh-agents'): void;
  (e: 'select-workflow', id: string): void;
  (e: 'workflow-update', data: Record<string, unknown>): void;
}>();

const maxVisibleSteps = 10;

// Live event connection
const { subscribe, isConnected: liveConnected, connectionState, connect } = useLiveEvents();
const isReconnecting = ref(false);

const connectionStatusClass = computed(() => {
  if (liveConnected.value) return 'connected';
  if (connectionState.value === 'connecting') return 'connecting';
  return 'disconnected';
});

const connectionIcon = computed(() => {
  if (liveConnected.value) return 'fas fa-circle connected-dot';
  if (connectionState.value === 'connecting') return 'fas fa-spinner fa-spin';
  return 'fas fa-circle disconnected-dot';
});

const connectionLabel = computed(() => {
  if (liveConnected.value) return t('workflow.liveDashboard.connectionLive');
  if (connectionState.value === 'connecting') return t('workflow.liveDashboard.connectionConnecting');
  return t('workflow.liveDashboard.connectionDisconnected');
});

async function reconnectLiveEvents(): Promise<void> {
  isReconnecting.value = true;
  try {
    await connect();
  } finally {
    isReconnecting.value = false;
  }
}

// Summary stats
const runningCount = computed(() =>
  props.activeWorkflows.filter(
    wf => !wf.is_paused && !wf.is_cancelled && !wf.completed_at,
  ).length,
);

const pausedCount = computed(() =>
  props.activeWorkflows.filter(wf => wf.is_paused).length,
);

const completedCount = computed(() =>
  props.activeWorkflows.filter(wf => wf.completed_at && !wf.is_cancelled).length,
);

const failedCount = computed(() =>
  props.activeWorkflows.filter(wf =>
    wf.steps.some(s => s.status === 'failed'),
  ).length,
);

// Card helpers
function getCardClass(wf: ActiveWorkflow): string {
  if (wf.is_cancelled) return 'card-cancelled';
  if (wf.is_paused) return 'card-paused';
  if (wf.completed_at) return 'card-completed';
  if (wf.steps.some(s => s.status === 'failed')) return 'card-failed';
  return 'card-running';
}

function getStatusBadgeClass(wf: ActiveWorkflow): string {
  if (wf.is_cancelled) return 'badge-cancelled';
  if (wf.is_paused) return 'badge-paused';
  if (wf.completed_at) return 'badge-completed';
  if (wf.steps.some(s => s.status === 'failed')) return 'badge-failed';
  if (wf.steps.some(s => s.status === 'executing')) return 'badge-running';
  return 'badge-pending';
}

function getStatusIcon(wf: ActiveWorkflow): string {
  if (wf.is_cancelled) return 'fas fa-ban';
  if (wf.is_paused) return 'fas fa-pause';
  if (wf.completed_at) return 'fas fa-check';
  if (wf.steps.some(s => s.status === 'failed')) return 'fas fa-exclamation-triangle';
  if (wf.steps.some(s => s.status === 'executing')) return 'fas fa-spinner fa-spin';
  return 'fas fa-hourglass-half';
}

function getStatusLabel(wf: ActiveWorkflow): string {
  if (wf.is_cancelled) return t('workflow.liveDashboard.cancelled');
  if (wf.is_paused) return t('workflow.liveDashboard.paused');
  if (wf.completed_at) return t('workflow.liveDashboard.completedRecent');
  if (wf.steps.some(s => s.status === 'failed')) return t('workflow.liveDashboard.failed');
  if (wf.steps.some(s => s.status === 'executing')) return t('workflow.liveDashboard.running');
  return t('workflow.liveDashboard.pending');
}

function getProgressPercent(wf: ActiveWorkflow): number {
  if (wf.total_steps === 0) return 0;
  const done = wf.steps.filter(
    s => s.status === 'completed' || s.status === 'skipped',
  ).length;
  return (done / wf.total_steps) * 100;
}

function getProgressClass(wf: ActiveWorkflow): string {
  if (wf.steps.some(s => s.status === 'failed')) return 'progress-failed';
  if (wf.is_paused) return 'progress-paused';
  if (wf.completed_at) return 'progress-completed';
  return 'progress-active';
}

function formatElapsed(wf: ActiveWorkflow): string {
  if (!wf.started_at) return '--';
  const start = new Date(wf.started_at).getTime();
  const end = wf.completed_at
    ? new Date(wf.completed_at).getTime()
    : Date.now();
  const sec = Math.floor((end - start) / 1000);
  if (sec < 60) return `${sec}s`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ${sec % 60}s`;
  const hr = Math.floor(min / 60);
  return `${hr}h ${min % 60}m`;
}

// Live event subscription for workflow updates
let unsubGlobal: (() => void) | undefined;

onMounted(() => {
  unsubGlobal = subscribe('global', (event: LiveEvent) => {
    if (
      event.event_type === 'workflow_status_update' ||
      event.event_type === 'step_completed' ||
      event.event_type === 'workflow_completed'
    ) {
      logger.info('Received live workflow event:', event.event_type);
      emit('workflow-update', event.payload);
      emit('refresh');
    }
  });
});

onUnmounted(() => {
  if (unsubGlobal) {
    unsubGlobal();
  }
});
</script>

<style scoped>
.workflow-live-dashboard {
  display: flex;
  flex-direction: column;
  gap: 20px;
  height: 100%;
  overflow-y: auto;
}

/* Connection Bar */
.connection-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
}

.connection-bar.connected {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.connection-bar.connecting {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.connection-bar.disconnected {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.connected-dot { color: var(--color-success); font-size: 8px; }
.disconnected-dot { color: var(--color-error); font-size: 8px; }

.btn-reconnect {
  margin-left: auto;
  padding: 4px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 12px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
}

.btn-reconnect:hover:not(:disabled) {
  background: var(--bg-hover);
}

.btn-reconnect:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Stats Bar */
.stats-bar {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.stat-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 10px;
  flex: 1;
  min-width: 140px;
}

.stat-chip i {
  font-size: 16px;
  color: var(--text-secondary);
}

.stat-chip:nth-child(1) i { color: var(--color-success); }
.stat-chip:nth-child(2) i { color: var(--color-warning); }
.stat-chip:nth-child(3) i { color: var(--color-info); }
.stat-chip:nth-child(4) i { color: var(--color-error); }

.stat-value {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
}

.stat-label {
  font-size: 12px;
  color: var(--text-tertiary);
}

/* Section Header */
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.section-header h3 {
  margin: 0;
  font-size: 15px;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 10px;
}

.section-header h3 i {
  color: var(--color-primary);
}

.btn-refresh-sm {
  width: 32px;
  height: 32px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.btn-refresh-sm:hover:not(:disabled) {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.btn-refresh-sm:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Empty / Loading States */
.empty-state,
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 24px;
  color: var(--text-tertiary);
  text-align: center;
}

.empty-state i,
.loading-state i {
  font-size: 40px;
  margin-bottom: 12px;
}

.empty-state h4 {
  margin: 0 0 6px;
  color: var(--text-primary);
  font-size: 15px;
}

.empty-state p {
  margin: 0;
  font-size: 13px;
}

/* Execution Grid */
.execution-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 16px;
}

/* Execution Card */
.execution-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 18px;
  cursor: pointer;
  transition: border-color 0.2s, box-shadow 0.2s;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.execution-card:hover {
  border-color: var(--color-primary);
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
}

.execution-card.card-running { border-left: 3px solid var(--color-success); }
.execution-card.card-paused { border-left: 3px solid var(--color-warning); }
.execution-card.card-completed { border-left: 3px solid var(--color-info); }
.execution-card.card-failed { border-left: 3px solid var(--color-error); }
.execution-card.card-cancelled { border-left: 3px solid var(--text-muted); }

.card-header {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.card-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.card-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.card-desc {
  font-size: 12px;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Status Badge */
.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 500;
  white-space: nowrap;
  flex-shrink: 0;
}

.badge-running { background: var(--color-success-bg); color: var(--color-success); }
.badge-paused { background: var(--color-warning-bg); color: var(--color-warning); }
.badge-completed { background: var(--color-info-bg); color: var(--color-info); }
.badge-failed { background: var(--color-error-bg); color: var(--color-error); }
.badge-cancelled { background: var(--bg-tertiary); color: var(--text-muted); }
.badge-pending { background: var(--bg-tertiary); color: var(--text-tertiary); }

/* Progress */
.card-progress {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.progress-track {
  height: 6px;
  background: var(--bg-tertiary);
  border-radius: 3px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.4s ease;
}

.progress-active { background: var(--color-success); }
.progress-paused { background: var(--color-warning); }
.progress-completed { background: var(--color-info); }
.progress-failed { background: var(--color-error); }

.progress-meta {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: var(--text-tertiary);
}

/* Step Timeline */
.step-timeline {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
}

.timeline-dot {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  border: 2px solid var(--border-default);
  background: var(--bg-tertiary);
  color: var(--text-tertiary);
  flex-shrink: 0;
}

.timeline-dot.completed {
  background: var(--color-success);
  border-color: var(--color-success);
  color: white;
}

.timeline-dot.failed {
  background: var(--color-error);
  border-color: var(--color-error);
  color: white;
}

.timeline-dot.executing {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: white;
}

.timeline-dot.waiting_approval {
  background: var(--color-warning);
  border-color: var(--color-warning);
  color: white;
}

.timeline-dot.paused {
  background: var(--color-warning-bg);
  border-color: var(--color-warning);
  color: var(--color-warning);
}

.dot-number {
  font-size: 9px;
  font-weight: 600;
}

.timeline-overflow {
  font-size: 11px;
  color: var(--text-muted);
  padding-left: 4px;
}

/* Card Footer */
.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.footer-meta {
  display: flex;
  gap: 8px;
}

.mode-tag,
.phase-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  background: var(--bg-tertiary);
  border-radius: 4px;
  font-size: 11px;
  color: var(--text-secondary);
  text-transform: capitalize;
}

.footer-time {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--text-tertiary);
}
</style>
