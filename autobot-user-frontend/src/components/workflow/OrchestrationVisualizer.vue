<template>
  <div class="orchestration-visualizer">
    <!-- Status Overview -->
    <div class="status-panel">
      <h3><i class="fas fa-network-wired"></i> Orchestration Status</h3>
      <div class="status-grid">
        <div class="status-card" :class="{ healthy: status?.status === 'operational' }">
          <div class="card-icon"><i class="fas fa-heartbeat"></i></div>
          <div class="card-info">
            <span class="card-value">{{ status?.status || 'Unknown' }}</span>
            <span class="card-label">System Status</span>
          </div>
        </div>
        <div class="status-card">
          <div class="card-icon"><i class="fas fa-tasks"></i></div>
          <div class="card-info">
            <span class="card-value">{{ status?.active_workflows || 0 }}</span>
            <span class="card-label">Active Workflows</span>
          </div>
        </div>
        <div class="status-card">
          <div class="card-icon"><i class="fas fa-users"></i></div>
          <div class="card-info">
            <span class="card-value">{{ status?.total_agents || 0 }}</span>
            <span class="card-label">Total Agents</span>
          </div>
        </div>
        <div class="status-card">
          <div class="card-icon"><i class="fas fa-layer-group"></i></div>
          <div class="card-info">
            <span class="card-value">{{ status?.max_parallel_tasks || 0 }}</span>
            <span class="card-label">Max Parallel</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Capabilities -->
    <div v-if="status?.capabilities" class="capabilities-panel">
      <h4><i class="fas fa-check-double"></i> Capabilities</h4>
      <div class="capabilities-list">
        <div class="capability-item" :class="{ enabled: status.capabilities.agent_coordination }">
          <i class="fas fa-users-cog"></i>
          <span>Agent Coordination</span>
        </div>
        <div class="capability-item" :class="{ enabled: status.capabilities.performance_tracking }">
          <i class="fas fa-chart-line"></i>
          <span>Performance Tracking</span>
        </div>
        <div class="capability-item" :class="{ enabled: status.capabilities.automatic_failover }">
          <i class="fas fa-sync-alt"></i>
          <span>Automatic Failover</span>
        </div>
        <div class="capability-item" :class="{ enabled: status.capabilities.resource_optimization }">
          <i class="fas fa-bolt"></i>
          <span>Resource Optimization</span>
        </div>
      </div>
    </div>

    <!-- Execution Strategies -->
    <div class="strategies-panel">
      <h4><i class="fas fa-chess"></i> Execution Strategies</h4>
      <div v-if="loading" class="loading">
        <i class="fas fa-spinner fa-spin"></i> Loading strategies...
      </div>
      <div v-else class="strategies-grid">
        <div v-for="(strategy, key) in strategies" :key="key" class="strategy-card" :class="{ active: activeStrategy === key }">
          <div class="strategy-icon"><i :class="getStrategyIcon(String(key))"></i></div>
          <div class="strategy-info">
            <span class="strategy-name">{{ strategy.name }}</span>
            <p class="strategy-desc">{{ strategy.description }}</p>
            <span class="strategy-best">{{ strategy.best_for }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Current Workflow Visualization -->
    <div v-if="currentWorkflow" class="visualization-panel">
      <h4><i class="fas fa-project-diagram"></i> Current Workflow: {{ currentWorkflow.name }}</h4>
      <div class="workflow-viz">
        <div class="viz-timeline">
          <div v-for="(step, i) in currentWorkflow.steps" :key="step.step_id" class="viz-step" :class="step.status">
            <div class="viz-node">
              <div class="node-circle">
                <i v-if="step.status === 'completed'" class="fas fa-check"></i>
                <i v-else-if="step.status === 'failed'" class="fas fa-times"></i>
                <i v-else-if="step.status === 'executing'" class="fas fa-spinner fa-spin"></i>
                <span v-else>{{ i + 1 }}</span>
              </div>
              <span class="node-label">{{ step.description || `Step ${i + 1}` }}</span>
            </div>
            <div v-if="i < currentWorkflow.steps.length - 1" class="viz-connector" :class="step.status"></div>
          </div>
        </div>
        <div class="viz-details">
          <div class="detail-item">
            <span class="label">Mode</span>
            <span class="value">{{ currentWorkflow.automation_mode }}</span>
          </div>
          <div class="detail-item">
            <span class="label">Progress</span>
            <span class="value">{{ currentWorkflow.current_step + 1 }} / {{ currentWorkflow.total_steps }}</span>
          </div>
          <div class="detail-item">
            <span class="label">Status</span>
            <span class="value status-badge" :class="workflowStatusClass">{{ workflowStatusLabel }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- No Workflow -->
    <div v-else class="no-workflow">
      <div class="empty-viz">
        <i class="fas fa-sitemap"></i>
        <h3>No Active Orchestration</h3>
        <p>Start a workflow to see real-time orchestration visualization</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { OrchestrationStatus, StrategyInfo, ActiveWorkflow } from '@/composables/useWorkflowBuilder';

const props = defineProps<{
  status: OrchestrationStatus | null;
  strategies: Record<string, StrategyInfo>;
  currentWorkflow: ActiveWorkflow | null;
  loading: boolean;
}>();

const activeStrategy = computed(() => {
  if (!props.currentWorkflow) return null;
  // Could derive from workflow context
  return 'sequential';
});

const workflowStatusClass = computed(() => {
  if (!props.currentWorkflow) return '';
  if (props.currentWorkflow.is_cancelled) return 'cancelled';
  if (props.currentWorkflow.is_paused) return 'paused';
  if (props.currentWorkflow.completed_at) return 'completed';
  return 'running';
});

const workflowStatusLabel = computed(() => {
  if (!props.currentWorkflow) return '';
  if (props.currentWorkflow.is_cancelled) return 'Cancelled';
  if (props.currentWorkflow.is_paused) return 'Paused';
  if (props.currentWorkflow.completed_at) return 'Completed';
  return 'Running';
});

function getStrategyIcon(strategy: string): string {
  const icons: Record<string, string> = {
    sequential: 'fas fa-arrow-right',
    parallel: 'fas fa-columns',
    pipeline: 'fas fa-stream',
    collaborative: 'fas fa-users',
    adaptive: 'fas fa-random'
  };
  return icons[strategy] || 'fas fa-cog';
}
</script>

<style scoped>
.orchestration-visualizer { display: flex; flex-direction: column; gap: 24px; height: 100%; overflow-y: auto; }

.status-panel h3, .capabilities-panel h4, .strategies-panel h4, .visualization-panel h4 {
  margin: 0 0 16px; font-size: 15px; color: var(--text-primary); display: flex; align-items: center; gap: 10px;
}
.status-panel h3 i, .capabilities-panel h4 i, .strategies-panel h4 i, .visualization-panel h4 i { color: var(--color-primary); }

.status-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; }
.status-card { display: flex; align-items: center; gap: 14px; padding: 16px; background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 10px; }
.status-card.healthy { border-color: var(--color-success); }
.card-icon { width: 44px; height: 44px; border-radius: 10px; background: var(--bg-tertiary); display: flex; align-items: center; justify-content: center; font-size: 18px; color: var(--text-secondary); }
.status-card.healthy .card-icon { background: var(--color-success-bg); color: var(--color-success); }
.card-value { display: block; font-size: 18px; font-weight: 600; color: var(--text-primary); text-transform: capitalize; }
.card-label { font-size: 12px; color: var(--text-tertiary); }

.capabilities-panel { background: var(--bg-secondary); border-radius: 10px; padding: 20px; }
.capabilities-list { display: flex; flex-wrap: wrap; gap: 12px; }
.capability-item { display: flex; align-items: center; gap: 8px; padding: 8px 14px; background: var(--bg-tertiary); border-radius: 20px; font-size: 13px; color: var(--text-muted); }
.capability-item.enabled { background: var(--color-success-bg); color: var(--color-success); }
.capability-item i { font-size: 14px; }

.strategies-panel { background: var(--bg-secondary); border-radius: 10px; padding: 20px; }
.loading { color: var(--text-tertiary); font-size: 13px; }
.strategies-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; }
.strategy-card { display: flex; gap: 12px; padding: 14px; background: var(--bg-tertiary); border: 1px solid transparent; border-radius: 8px; transition: all 0.2s; }
.strategy-card.active { border-color: var(--color-primary); background: var(--color-primary-bg); }
.strategy-icon { width: 36px; height: 36px; border-radius: 8px; background: var(--bg-secondary); display: flex; align-items: center; justify-content: center; color: var(--text-secondary); flex-shrink: 0; }
.strategy-card.active .strategy-icon { background: var(--color-primary); color: white; }
.strategy-name { display: block; font-size: 14px; font-weight: 500; color: var(--text-primary); margin-bottom: 4px; }
.strategy-desc { margin: 0 0 6px; font-size: 12px; color: var(--text-secondary); line-height: 1.4; }
.strategy-best { font-size: 11px; color: var(--text-muted); font-style: italic; }

.visualization-panel { background: var(--bg-secondary); border-radius: 10px; padding: 20px; }
.workflow-viz { display: flex; flex-direction: column; gap: 20px; }
.viz-timeline { display: flex; align-items: flex-start; gap: 0; overflow-x: auto; padding: 16px 0; }
.viz-step { display: flex; align-items: center; }
.viz-node { display: flex; flex-direction: column; align-items: center; gap: 8px; min-width: 80px; }
.node-circle { width: 40px; height: 40px; border-radius: 50%; background: var(--bg-tertiary); display: flex; align-items: center; justify-content: center; font-size: 14px; font-weight: 600; color: var(--text-tertiary); border: 2px solid var(--border-default); }
.viz-step.completed .node-circle { background: var(--color-success); color: white; border-color: var(--color-success); }
.viz-step.failed .node-circle { background: var(--color-error); color: white; border-color: var(--color-error); }
.viz-step.executing .node-circle { background: var(--color-primary); color: white; border-color: var(--color-primary); }
.node-label { font-size: 11px; color: var(--text-secondary); text-align: center; max-width: 100px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.viz-connector { width: 40px; height: 2px; background: var(--border-default); margin-top: 20px; }
.viz-connector.completed { background: var(--color-success); }

.viz-details { display: flex; gap: 24px; padding: 16px; background: var(--bg-tertiary); border-radius: 8px; }
.detail-item { display: flex; flex-direction: column; gap: 4px; }
.detail-item .label { font-size: 11px; color: var(--text-tertiary); text-transform: uppercase; }
.detail-item .value { font-size: 14px; font-weight: 500; color: var(--text-primary); }
.status-badge { padding: 2px 10px; border-radius: 12px; font-size: 12px; }
.status-badge.running { background: var(--color-success-bg); color: var(--color-success); }
.status-badge.paused { background: var(--color-warning-bg); color: var(--color-warning); }
.status-badge.completed { background: var(--color-info-bg); color: var(--color-info); }
.status-badge.cancelled { background: var(--color-error-bg); color: var(--color-error); }

.no-workflow { flex: 1; display: flex; align-items: center; justify-content: center; }
.empty-viz { text-align: center; padding: 40px; }
.empty-viz i { font-size: 48px; color: var(--text-muted); margin-bottom: 16px; }
.empty-viz h3 { margin: 0 0 8px; color: var(--text-primary); }
.empty-viz p { margin: 0; color: var(--text-tertiary); }
</style>
