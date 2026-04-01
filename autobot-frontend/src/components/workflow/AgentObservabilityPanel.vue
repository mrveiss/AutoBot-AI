<template>
  <div class="agent-observability-panel">
    <div class="panel-header">
      <h3>
        <i class="fas fa-users-cog"></i>
        {{ $t('workflow.agentObservability.title') }}
      </h3>
      <button class="btn-refresh-sm" @click="$emit('refresh')" :disabled="loading">
        <i class="fas fa-sync-alt" :class="{ 'fa-spin': loading }"></i>
      </button>
    </div>

    <!-- Loading -->
    <div v-if="loading && agentList.length === 0" class="loading-state">
      <i class="fas fa-spinner fa-spin"></i>
      <span>{{ $t('workflow.agentObservability.loading') }}</span>
    </div>

    <!-- Empty -->
    <div v-else-if="agentList.length === 0" class="empty-state">
      <i class="fas fa-robot"></i>
      <h4>{{ $t('workflow.agentObservability.noAgents') }}</h4>
      <p>{{ $t('workflow.agentObservability.noAgentsDescription') }}</p>
    </div>

    <!-- Agent Cards -->
    <div v-else class="agents-grid">
      <div
        v-for="agent in agentList"
        :key="agent.name"
        class="agent-card"
      >
        <div class="agent-header">
          <div class="agent-identity">
            <div class="agent-avatar" :class="getReliabilityClass(agent.reliabilityScore)">
              <i class="fas fa-robot"></i>
            </div>
            <div class="agent-name-block">
              <span class="agent-name">{{ agent.name }}</span>
              <span class="agent-tasks-summary">
                {{ $t('workflow.agentObservability.tasksCompleted', { count: agent.totalTasks }) }}
              </span>
            </div>
          </div>
          <div class="reliability-badge" :class="getReliabilityClass(agent.reliabilityScore)">
            {{ formatPercent(agent.reliabilityScore) }}
          </div>
        </div>

        <!-- Metrics Row -->
        <div class="metrics-row">
          <div class="metric">
            <span class="metric-value success">{{ agent.successfulTasks }}</span>
            <span class="metric-label">{{ $t('workflow.agentObservability.success') }}</span>
          </div>
          <div class="metric">
            <span class="metric-value failed">{{ agent.failedTasks }}</span>
            <span class="metric-label">{{ $t('workflow.agentObservability.failed') }}</span>
          </div>
          <div class="metric">
            <span class="metric-value">{{ formatDuration(agent.avgDuration) }}</span>
            <span class="metric-label">{{ $t('workflow.agentObservability.avgTime') }}</span>
          </div>
        </div>

        <!-- Reliability Bar -->
        <div class="reliability-bar-container">
          <div class="reliability-bar">
            <div
              class="reliability-fill"
              :style="{ width: formatPercent(agent.reliabilityScore) }"
              :class="getReliabilityClass(agent.reliabilityScore)"
            ></div>
          </div>
        </div>

        <!-- Capabilities -->
        <div v-if="agent.capabilities.length > 0" class="capabilities-row">
          <span
            v-for="cap in agent.capabilities.slice(0, maxVisibleCapabilities)"
            :key="cap"
            class="capability-tag"
          >
            {{ cap }}
          </span>
          <span v-if="agent.capabilities.length > maxVisibleCapabilities" class="capability-overflow">
            +{{ agent.capabilities.length - maxVisibleCapabilities }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { AgentPerformance, AgentCapability } from '@/composables/useWorkflowBuilder';

const props = defineProps<{
  agentPerformance: Record<string, AgentPerformance>;
  agentCapabilities: Record<string, AgentCapability>;
  loading: boolean;
}>();

defineEmits<{
  (e: 'refresh'): void;
}>();

const maxVisibleCapabilities = 4;

interface AgentSummary {
  name: string;
  totalTasks: number;
  successfulTasks: number;
  failedTasks: number;
  avgDuration: number;
  reliabilityScore: number;
  capabilities: string[];
}

const agentList = computed<AgentSummary[]>(() => {
  const map = new Map<string, AgentSummary>();

  // Merge performance data
  for (const [key, perf] of Object.entries(props.agentPerformance)) {
    map.set(key, {
      name: perf.agent_name || key,
      totalTasks: perf.total_tasks,
      successfulTasks: perf.successful_tasks,
      failedTasks: perf.failed_tasks,
      avgDuration: perf.average_duration,
      reliabilityScore: perf.reliability_score,
      capabilities: [],
    });
  }

  // Merge capability data
  for (const [key, cap] of Object.entries(props.agentCapabilities)) {
    const existing = map.get(key);
    if (existing) {
      existing.capabilities = cap.capabilities || [];
    } else {
      map.set(key, {
        name: cap.agent || key,
        totalTasks: cap.performance?.total_tasks || 0,
        successfulTasks: 0,
        failedTasks: 0,
        avgDuration: 0,
        reliabilityScore: cap.performance?.reliability || 0,
        capabilities: cap.capabilities || [],
      });
    }
  }

  return [...map.values()].sort((a, b) => b.totalTasks - a.totalTasks);
});

function getReliabilityClass(score: number): string {
  if (score >= 0.9) return 'reliability-high';
  if (score >= 0.7) return 'reliability-medium';
  return 'reliability-low';
}

function formatPercent(score: number): string {
  return `${Math.round(score * 100)}%`;
}

function formatDuration(seconds: number): string {
  if (seconds === 0) return '--';
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const min = Math.floor(seconds / 60);
  return `${min}m ${Math.round(seconds % 60)}s`;
}
</script>

<style scoped>
.agent-observability-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.panel-header h3 {
  margin: 0;
  font-size: 15px;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 10px;
}

.panel-header h3 i {
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

/* Empty / Loading */
.empty-state,
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 24px;
  color: var(--text-tertiary);
  text-align: center;
}

.empty-state i,
.loading-state i {
  font-size: 36px;
  margin-bottom: 10px;
}

.empty-state h4 {
  margin: 0 0 4px;
  color: var(--text-primary);
  font-size: 14px;
}

.empty-state p {
  margin: 0;
  font-size: 12px;
}

/* Agents Grid */
.agents-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 14px;
}

/* Agent Card */
.agent-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 10px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  transition: border-color 0.2s;
}

.agent-card:hover {
  border-color: var(--color-primary);
}

.agent-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.agent-identity {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  min-width: 0;
}

.agent-avatar {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  flex-shrink: 0;
}

.agent-avatar.reliability-high {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.agent-avatar.reliability-medium {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.agent-avatar.reliability-low {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.agent-name-block {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.agent-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-tasks-summary {
  font-size: 11px;
  color: var(--text-tertiary);
}

.reliability-badge {
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;
  flex-shrink: 0;
}

.reliability-badge.reliability-high {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.reliability-badge.reliability-medium {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.reliability-badge.reliability-low {
  background: var(--color-error-bg);
  color: var(--color-error);
}

/* Metrics */
.metrics-row {
  display: flex;
  gap: 12px;
}

.metric {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex: 1;
  padding: 8px 0;
  background: var(--bg-tertiary);
  border-radius: 8px;
}

.metric-value {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.metric-value.success { color: var(--color-success); }
.metric-value.failed { color: var(--color-error); }

.metric-label {
  font-size: 10px;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-top: 2px;
}

/* Reliability Bar */
.reliability-bar-container {
  padding: 0 2px;
}

.reliability-bar {
  height: 4px;
  background: var(--bg-tertiary);
  border-radius: 2px;
  overflow: hidden;
}

.reliability-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.4s ease;
}

.reliability-fill.reliability-high { background: var(--color-success); }
.reliability-fill.reliability-medium { background: var(--color-warning); }
.reliability-fill.reliability-low { background: var(--color-error); }

/* Capabilities */
.capabilities-row {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.capability-tag {
  padding: 2px 8px;
  background: var(--bg-tertiary);
  border-radius: 4px;
  font-size: 10px;
  color: var(--text-secondary);
}

.capability-overflow {
  padding: 2px 6px;
  font-size: 10px;
  color: var(--text-muted);
}
</style>
