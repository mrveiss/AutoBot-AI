<template>
  <div class="orchestration-visualizer">
    <!-- Status Overview -->
    <div class="status-panel">
      <h3><Icon name="network-wired" /> {{ $t('workflow.orchestration.statusTitle') }}</h3>
      <div class="status-grid">
        <div class="status-card" :class="{ healthy: status?.status === 'operational' }">
          <div class="card-icon"><Icon name="heartbeat" /></div>
          <div class="card-info">
            <span class="card-value">{{ status?.status || 'Unknown' }}</span>
            <span class="card-label">{{ $t('workflow.orchestration.systemStatus') }}</span>
          </div>
        </div>
        <div class="status-card">
          <div class="card-icon"><Icon name="tasks" /></div>
          <div class="card-info">
            <span class="card-value">{{ status?.active_workflows || 0 }}</span>
            <span class="card-label">{{ $t('workflow.orchestration.activeWorkflows') }}</span>
          </div>
        </div>
        <div class="status-card">
          <div class="card-icon"><Icon name="users" /></div>
          <div class="card-info">
            <span class="card-value">{{ status?.total_agents || 0 }}</span>
            <span class="card-label">{{ $t('workflow.orchestration.totalAgents') }}</span>
          </div>
        </div>
        <div class="status-card">
          <div class="card-icon"><Icon name="layer-group" /></div>
          <div class="card-info">
            <span class="card-value">{{ status?.max_parallel_tasks || 0 }}</span>
            <span class="card-label">{{ $t('workflow.orchestration.maxParallel') }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Capabilities -->
    <div v-if="status?.capabilities" class="capabilities-panel">
      <h4><Icon name="check-double" /> {{ $t('workflow.orchestration.capabilities') }}</h4>
      <div class="capabilities-list">
        <div class="capability-item" :class="{ enabled: status.capabilities.agent_coordination }">
          <Icon name="users-cog" />
          <span>{{ $t('workflow.orchestration.agentCoordination') }}</span>
        </div>
        <div class="capability-item" :class="{ enabled: status.capabilities.performance_tracking }">
          <Icon name="chart-line" />
          <span>{{ $t('workflow.orchestration.performanceTracking') }}</span>
        </div>
        <div class="capability-item" :class="{ enabled: status.capabilities.automatic_failover }">
          <Icon name="sync-alt" />
          <span>{{ $t('workflow.orchestration.automaticFailover') }}</span>
        </div>
        <div class="capability-item" :class="{ enabled: status.capabilities.resource_optimization }">
          <Icon name="bolt" />
          <span>{{ $t('workflow.orchestration.resourceOptimization') }}</span>
        </div>
      </div>
    </div>

    <!-- Execution Strategies -->
    <div class="strategies-panel">
      <h4><Icon name="chess" /> {{ $t('workflow.orchestration.executionStrategies') }}</h4>
      <div v-if="loading" class="loading">
        <Icon name="spinner" class="animate-spin" /> {{ $t('workflow.orchestration.loadingStrategies') }}
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
      <h4><Icon name="project-diagram" /> {{ $t('workflow.orchestration.currentWorkflow', { name: currentWorkflow.name }) }}</h4>
      <div class="workflow-viz">
        <div class="viz-timeline">
          <div v-for="(step, i) in currentWorkflow.steps" :key="step.step_id" class="viz-step" :class="step.status">
            <div class="viz-node">
              <div class="node-circle">
                <Icon name="check" v-if="step.status === 'completed'" />
                <Icon name="times" v-else-if="step.status === 'failed'" />
                <Icon name="spinner" class="animate-spin" v-else-if="step.status === 'executing'" />
                <span v-else>{{ i + 1 }}</span>
              </div>
              <span class="node-label">{{ step.description || $t('workflow.orchestration.stepDefault', { num: i + 1 }) }}</span>
            </div>
            <div v-if="i < currentWorkflow.steps.length - 1" class="viz-connector" :class="step.status"></div>
          </div>
        </div>
        <div class="viz-details">
          <div class="detail-item">
            <span class="label">{{ $t('workflow.orchestration.mode') }}</span>
            <span class="value">{{ currentWorkflow.automation_mode }}</span>
          </div>
          <div class="detail-item">
            <span class="label">{{ $t('workflow.orchestration.progress') }}</span>
            <span class="value">{{ currentWorkflow.current_step + 1 }} / {{ currentWorkflow.total_steps }}</span>
          </div>
          <div class="detail-item">
            <span class="label">{{ $t('workflow.orchestration.status') }}</span>
            <span class="value status-badge" :class="workflowStatusClass">{{ workflowStatusLabel }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- No Workflow -->
    <div v-else class="no-workflow">
      <div class="empty-viz">
        <Icon name="sitemap" />
        <h3>{{ $t('workflow.orchestration.noActiveOrchestration') }}</h3>
        <p>{{ $t('workflow.orchestration.noActiveDescription') }}</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import type { OrchestrationStatus, StrategyInfo, ActiveWorkflow } from '@/composables/useWorkflowBuilder';

const { t } = useI18n();

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
  if (props.currentWorkflow.is_cancelled) return t('workflow.orchestration.cancelled');
  if (props.currentWorkflow.is_paused) return t('workflow.orchestration.paused');
  if (props.currentWorkflow.completed_at) return t('workflow.orchestration.completedStatus');
  return t('workflow.orchestration.running');
});

function getStrategyIcon(strategy: string): string {
  const icons: Record<string, string> = {
    sequential: 'arrow-right',
    parallel: 'columns',
    pipeline: 'stream',
    collaborative: 'users',
    adaptive: 'random'
  };
  return icons[strategy] || 'cog';
}
</script>

<style scoped>
.orchestration-visualizer { display: flex; flex-direction: column; gap: var(--spacing-6); height: 100%; overflow-y: auto; }

.status-panel h3, .capabilities-panel h4, .strategies-panel h4, .visualization-panel h4 {
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-4); font-size: 15px; color: var(--text-primary); display: flex; align-items: center; gap: var(--spacing-2-5);
}
.status-panel h3 i, .capabilities-panel h4 i, .strategies-panel h4 i, .visualization-panel h4 i { color: var(--color-primary); }

.status-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: var(--spacing-4); }
.status-card { display: flex; align-items: center; gap: var(--spacing-3-5); padding: var(--spacing-4); background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: var(--radius-xl); }
.status-card.healthy { border-color: var(--color-success); }
.card-icon { width: 44px; height: 44px; border-radius: var(--radius-xl); background: var(--bg-tertiary); display: flex; align-items: center; justify-content: center; font-size: var(--text-lg); color: var(--text-secondary); }
.status-card.healthy .card-icon { background: var(--color-success-bg); color: var(--color-success); }
.card-value { display: block; font-size: var(--text-lg); font-weight: 600; color: var(--text-primary); text-transform: capitalize; }
.card-label { font-size: var(--text-xs); color: var(--text-tertiary); }

.capabilities-panel { background: var(--bg-secondary); border-radius: var(--radius-xl); padding: var(--spacing-5); }
.capabilities-list { display: flex; flex-wrap: wrap; gap: var(--spacing-3); }
.capability-item { display: flex; align-items: center; gap: var(--spacing-2); padding: var(--spacing-2) var(--spacing-3-5); background: var(--bg-tertiary); border-radius: var(--radius-2xl); font-size: var(--text-sm); color: var(--text-muted); }
.capability-item.enabled { background: var(--color-success-bg); color: var(--color-success); }
.capability-item i { font-size: var(--text-sm); }

.strategies-panel { background: var(--bg-secondary); border-radius: var(--radius-xl); padding: var(--spacing-5); }
.loading { color: var(--text-tertiary); font-size: var(--text-sm); }
.strategies-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: var(--spacing-4); }
.strategy-card { display: flex; gap: var(--spacing-3); padding: var(--spacing-3-5); background: var(--bg-tertiary); border: 1px solid transparent; border-radius: var(--radius-lg); transition: all 0.2s; }
.strategy-card.active { border-color: var(--color-primary); background: var(--color-primary-bg); }
.strategy-icon { width: 36px; height: 36px; border-radius: var(--radius-lg); background: var(--bg-secondary); display: flex; align-items: center; justify-content: center; color: var(--text-secondary); flex-shrink: 0; }
.strategy-card.active .strategy-icon { background: var(--color-primary); color: white; }
.strategy-name { display: block; font-size: var(--text-sm); font-weight: 500; color: var(--text-primary); margin-bottom: var(--spacing-1); }
.strategy-desc { margin: var(--spacing-0) var(--spacing-0) var(--spacing-1-5); font-size: var(--text-xs); color: var(--text-secondary); line-height: 1.4; }
.strategy-best { font-size: var(--text-xs); color: var(--text-muted); font-style: italic; }

.visualization-panel { background: var(--bg-secondary); border-radius: var(--radius-xl); padding: var(--spacing-5); }
.workflow-viz { display: flex; flex-direction: column; gap: var(--spacing-5); }
.viz-timeline { display: flex; align-items: flex-start; gap: var(--spacing-0); overflow-x: auto; padding: var(--spacing-4) var(--spacing-0); }
.viz-step { display: flex; align-items: center; }
.viz-node { display: flex; flex-direction: column; align-items: center; gap: var(--spacing-2); min-width: 80px; }
.node-circle { width: 40px; height: 40px; border-radius: 50%; background: var(--bg-tertiary); display: flex; align-items: center; justify-content: center; font-size: var(--text-sm); font-weight: 600; color: var(--text-tertiary); border: 2px solid var(--border-default); }
.viz-step.completed .node-circle { background: var(--color-success); color: white; border-color: var(--color-success); }
.viz-step.failed .node-circle { background: var(--color-error); color: white; border-color: var(--color-error); }
.viz-step.executing .node-circle { background: var(--color-primary); color: white; border-color: var(--color-primary); }
.node-label { font-size: var(--text-xs); color: var(--text-secondary); text-align: center; max-width: 100px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.viz-connector { width: 40px; height: 2px; background: var(--border-default); margin-top: var(--spacing-5); }
.viz-connector.completed { background: var(--color-success); }

.viz-details { display: flex; gap: var(--spacing-6); padding: var(--spacing-4); background: var(--bg-tertiary); border-radius: var(--radius-lg); }
.detail-item { display: flex; flex-direction: column; gap: var(--spacing-1); }
.detail-item .label { font-size: var(--text-xs); color: var(--text-tertiary); text-transform: uppercase; }
.detail-item .value { font-size: var(--text-sm); font-weight: 500; color: var(--text-primary); }
.status-badge { padding: var(--spacing-0-5) var(--spacing-2-5); border-radius: var(--radius-xl); font-size: var(--text-xs); }
.status-badge.running { background: var(--color-success-bg); color: var(--color-success); }
.status-badge.paused { background: var(--color-warning-bg); color: var(--color-warning); }
.status-badge.completed { background: var(--color-info-bg); color: var(--color-info); }
.status-badge.cancelled { background: var(--color-error-bg); color: var(--color-error); }

.no-workflow { flex: 1; display: flex; align-items: center; justify-content: center; }
.empty-viz { text-align: center; padding: var(--spacing-10); }
.empty-viz i { font-size: var(--text-5xl); color: var(--text-muted); margin-bottom: var(--spacing-4); }
.empty-viz h3 { margin: var(--spacing-0) var(--spacing-0) var(--spacing-2); color: var(--text-primary); }
.empty-viz p { margin: var(--spacing-0); color: var(--text-tertiary); }
</style>
