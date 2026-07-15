<template>
  <div class="workflow-runner">
    <!-- Workflow List -->
    <div class="runner-sidebar">
      <div class="sidebar-header">
        <h4><Icon name="tasks" /> {{ $t('workflow.runner.activeWorkflows') }}</h4>
        <button
          class="btn-refresh"
          @click="$emit('refresh')"
          :disabled="loading"
          :aria-label="$t('common.refresh')"
          :title="$t('common.refresh')"
          type="button"
        >
          <Icon name="sync-alt" />
        </button>
      </div>
      <div v-if="workflows.length === 0" class="empty-list">
        <Icon name="inbox" />
        <p>{{ $t('workflow.runner.noActiveWorkflows') }}</p>
      </div>
      <div v-else class="workflow-list">
        <div v-for="wf in workflows" :key="wf.workflow_id" class="workflow-item"
             :class="{ active: currentWorkflow?.workflow_id === wf.workflow_id, paused: wf.is_paused }"
             @click="selectWorkflow(wf)">
          <div class="wf-status" :class="getStatusClass(wf)">
            <Icon :name="getStatusIcon(wf)" />
          </div>
          <div class="wf-info">
            <span class="wf-name">{{ wf.name }}</span>
            <span class="wf-progress">{{ $t('workflow.runner.stepProgress', { current: wf.current_step + 1, total: wf.total_steps }) }}</span>
          </div>
          <div class="wf-progress-bar">
            <div class="progress-fill" :style="{ width: getProgress(wf) + '%' }"></div>
          </div>
        </div>
      </div>
    </div>

    <!-- Workflow Detail -->
    <div class="runner-main">
      <div v-if="!currentWorkflow" class="no-selection">
        <Icon name="hand-paper" />
        <h3>{{ $t('workflow.runner.selectWorkflow') }}</h3>
        <p>{{ $t('workflow.runner.selectWorkflowDescription') }}</p>
      </div>

      <template v-else>
        <!-- Workflow Header -->
        <div class="workflow-header">
          <div class="header-info">
            <h2>{{ currentWorkflow.name }}</h2>
            <p>{{ currentWorkflow.description }}</p>
            <div class="header-meta">
              <span><Icon name="calendar" /> {{ $t('workflow.runner.started') }} {{ formatTime(currentWorkflow.started_at) }}</span>
              <span><Icon name="cog" /> {{ currentWorkflow.automation_mode }}</span>
              <span v-if="currentWorkflow.phase" class="phase-badge" :class="currentWorkflow.phase">
                <Icon name="project-diagram" /> {{ formatPhase(currentWorkflow.phase) }}
              </span>
              <span v-if="currentWorkflow.active_service" class="service-badge">
                <Icon name="server" /> {{ currentWorkflow.active_service }}
              </span>
            </div>
          </div>
          <div class="header-actions">
            <button class="btn-notif" @click="showNotifConfig = true" :aria-label="$t('workflow.notifications.title')">
              <Icon name="bell" />
            </button>
            <button v-if="currentWorkflow.is_paused" class="btn-success" @click="$emit('resume-workflow', currentWorkflow.workflow_id)">
              <Icon name="play" /> {{ $t('workflow.runner.resume') }}
            </button>
            <button v-else class="btn-warning" @click="$emit('pause-workflow', currentWorkflow.workflow_id)">
              <Icon name="pause" /> {{ $t('workflow.runner.pause') }}
            </button>
            <button class="btn-danger" @click="$emit('cancel-workflow', currentWorkflow.workflow_id)">
              <Icon name="stop" /> {{ $t('workflow.runner.cancel') }}
            </button>
          </div>
        </div>

        <!-- Progress Overview -->
        <div class="progress-overview">
          <div class="progress-bar-large">
            <div class="progress-fill" :style="{ width: getProgress(currentWorkflow) + '%' }"></div>
          </div>
          <div class="progress-stats">
            <div class="stat"><span class="value">{{ currentWorkflow.current_step + 1 }}</span><span class="label">{{ $t('workflow.runner.current') }}</span></div>
            <div class="stat"><span class="value">{{ currentWorkflow.total_steps }}</span><span class="label">{{ $t('workflow.runner.total') }}</span></div>
            <div class="stat"><span class="value">{{ completedSteps }}</span><span class="label">{{ $t('workflow.runner.completed') }}</span></div>
            <div class="stat"><span class="value">{{ failedSteps }}</span><span class="label">{{ $t('workflow.runner.failed') }}</span></div>
          </div>
        </div>

        <!-- Steps List -->
        <div class="steps-container">
          <h4><Icon name="list-ol" /> {{ $t('workflow.runner.executionSteps') }}</h4>
          <div class="steps-list">
            <div v-for="(step, i) in currentWorkflow.steps" :key="step.step_id" class="step-item" :class="step.status">
              <div class="step-indicator">
                <div class="step-icon" :class="step.status">
                  <Icon name="check" v-if="step.status === 'completed'" />
                  <Icon name="times" v-else-if="step.status === 'failed'" />
                  <Icon name="spinner" class="animate-spin" v-else-if="step.status === 'executing'" />
                  <Icon name="clock" v-else-if="step.status === 'waiting_approval'" />
                  <Icon name="forward" v-else-if="step.status === 'skipped'" />
                  <span v-else>{{ i + 1 }}</span>
                </div>
                <div v-if="i < currentWorkflow.steps.length - 1" class="step-line" :class="step.status"></div>
              </div>
              <div class="step-content">
                <div class="step-header">
                  <span class="step-desc">{{ step.description }}</span>
                  <span class="step-status" :class="step.status">{{ formatStatus(step.status) }}</span>
                </div>
                <code class="step-command">{{ step.command }}</code>
                <div class="step-meta">
                  <span class="risk" :class="step.risk_level"><Icon name="shield-alt" /> {{ step.risk_level }}</span>
                  <span v-if="step.started_at"><Icon name="play" /> {{ formatTime(step.started_at) }}</span>
                  <span v-if="step.completed_at"><Icon name="check" /> {{ formatTime(step.completed_at) }}</span>
                </div>
                <!-- Approval Actions -->
                <div v-if="step.status === 'waiting_approval' && step.requires_confirmation" class="step-actions">
                  <button class="btn-success btn-sm" @click="$emit('approve-step', currentWorkflow.workflow_id, step.step_id)">
                    <Icon name="check" /> {{ $t('workflow.runner.approve') }}
                  </button>
                  <button class="btn-secondary btn-sm" @click="$emit('skip-step', currentWorkflow.workflow_id, step.step_id)">
                    <Icon name="forward" /> {{ $t('workflow.runner.skip') }}
                  </button>
                </div>
                <!-- Execution Result -->
                <div v-if="step.execution_result" class="step-result" :class="{ error: step.status === 'failed' }">
                  <pre>{{ formatResult(step.execution_result) }}</pre>
                </div>
              </div>
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- Notification Config Modal (#3139) -->
    <NotificationConfigModal
      v-if="currentWorkflow"
      :visible="showNotifConfig"
      :workflow-id="currentWorkflow.workflow_id"
      @close="showNotifConfig = false"
      @saved="$emit('refresh')"
    />
  </div>
</template>

<script setup lang="ts">
import type { IconName } from '@/components/ui/Icon.vue'
import Icon from '@/components/ui/Icon.vue'
import { ref, computed } from 'vue';
import type { ActiveWorkflow } from '@/composables/useWorkflowBuilder';
import NotificationConfigModal from './NotificationConfigModal.vue';

const props = defineProps<{ workflows: ActiveWorkflow[]; currentWorkflow: ActiveWorkflow | null; loading: boolean }>();
defineEmits<{
  (e: 'start-workflow', id: string): void;
  (e: 'pause-workflow', id: string): void;
  (e: 'resume-workflow', id: string): void;
  (e: 'cancel-workflow', id: string): void;
  (e: 'approve-step', wfId: string, stepId: string): void;
  (e: 'skip-step', wfId: string, stepId: string): void;
  (e: 'refresh'): void;
}>();

const showNotifConfig = ref(false);

const completedSteps = computed(() => props.currentWorkflow?.steps.filter(s => s.status === 'completed').length ?? 0);
const failedSteps = computed(() => props.currentWorkflow?.steps.filter(s => s.status === 'failed').length ?? 0);

function selectWorkflow(_wf: ActiveWorkflow) {
  // Parent should handle selection via props
}

function getProgress(wf: ActiveWorkflow): number {
  if (!wf.total_steps) return 0;
  return Math.round(((wf.current_step + 1) / wf.total_steps) * 100);
}

function getStatusClass(wf: ActiveWorkflow): string {
  if (wf.is_cancelled) return 'cancelled';
  if (wf.is_paused) return 'paused';
  if (wf.completed_at) return 'completed';
  return 'running';
}

function getStatusIcon(wf: ActiveWorkflow): IconName {
  if (wf.is_cancelled) return 'times';
  if (wf.is_paused) return 'pause';
  if (wf.completed_at) return 'check';
  return 'spinner';
}

function formatStatus(status: string): string {
  return status.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
}

function formatPhase(phase: string): string {
  return phase.charAt(0).toUpperCase() + phase.slice(1);
}

function formatTime(timestamp?: string): string {
  if (!timestamp) return '-';
  return new Date(timestamp).toLocaleTimeString();
}

function formatResult(result: Record<string, unknown>): string {
  if (typeof result === 'string') return result;
  return JSON.stringify(result, null, 2).slice(0, 500);
}
</script>

<style scoped>
.workflow-runner { display: flex; height: 100%; gap: var(--spacing-0); background: var(--bg-primary); border-radius: var(--radius-lg); overflow: hidden; }

.runner-sidebar { width: 300px; min-width: 300px; background: var(--bg-secondary); border-right: 1px solid var(--border-default); display: flex; flex-direction: column; }
.sidebar-header { display: flex; justify-content: space-between; align-items: center; padding: var(--spacing-4); border-bottom: 1px solid var(--border-default); }
.sidebar-header h4 { margin: var(--spacing-0); font-size: var(--text-sm); color: var(--text-primary); display: flex; align-items: center; gap: var(--spacing-2); }
.sidebar-header h4 i { color: var(--color-primary); }
.btn-refresh { padding: var(--spacing-1-5); background: transparent; border: none; color: var(--text-tertiary); cursor: pointer; border-radius: var(--radius-default); }
.btn-refresh:hover:not(:disabled) { background: var(--bg-hover); }
.btn-refresh:disabled { opacity: 0.5; }

.empty-list { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; color: var(--text-muted); padding: var(--spacing-5); }
.empty-list i { font-size: 32px; margin-bottom: var(--spacing-3); }

.workflow-list { flex: 1; overflow-y: auto; padding: var(--spacing-2); }
.workflow-item { padding: var(--spacing-3); background: var(--bg-tertiary); border-radius: var(--radius-lg); margin-bottom: var(--spacing-2); cursor: pointer; transition: all 0.15s; }
.workflow-item:hover { background: var(--bg-hover); }
.workflow-item.active { background: var(--color-primary-bg); border: 1px solid var(--color-primary); }
.workflow-item.paused { opacity: 0.7; }
.workflow-item { display: flex; flex-wrap: wrap; align-items: center; gap: var(--spacing-2-5); }
.wf-status { width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: var(--text-xs); }
.wf-status.running { background: var(--color-success-bg); color: var(--color-success); }
.wf-status.paused { background: var(--color-warning-bg); color: var(--color-warning); }
.wf-status.completed { background: var(--color-info-bg); color: var(--color-info); }
.wf-status.cancelled { background: var(--color-error-bg); color: var(--color-error); }
.wf-info { flex: 1; min-width: 0; }
.wf-name { display: block; font-size: var(--text-sm); font-weight: 500; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.wf-progress { font-size: var(--text-xs); color: var(--text-tertiary); }
.wf-progress-bar { width: 100%; height: 4px; background: var(--bg-secondary); border-radius: var(--radius-xs); overflow: hidden; }
.wf-progress-bar .progress-fill { height: 100%; background: var(--color-primary); transition: width 0.3s; }

.runner-main { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.no-selection { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; color: var(--text-tertiary); padding: var(--spacing-10); }
.no-selection i { font-size: var(--text-5xl); margin-bottom: var(--spacing-4); }
.no-selection h3 { margin: var(--spacing-0) var(--spacing-0) var(--spacing-2); color: var(--text-primary); }

.workflow-header { display: flex; justify-content: space-between; align-items: flex-start; padding: var(--spacing-5); background: var(--bg-secondary); border-bottom: 1px solid var(--border-default); }
.header-info h2 { margin: var(--spacing-0) var(--spacing-0) var(--spacing-1); font-size: var(--text-lg); color: var(--text-primary); }
.header-info p { margin: var(--spacing-0) var(--spacing-0) var(--spacing-2-5); font-size: var(--text-sm); color: var(--text-secondary); }
.header-meta { display: flex; gap: var(--spacing-4); font-size: var(--text-xs); color: var(--text-tertiary); flex-wrap: wrap; }
.header-meta span { display: flex; align-items: center; gap: var(--spacing-1-5); }
.phase-badge { padding: var(--spacing-0-5) var(--spacing-2); border-radius: var(--radius-xl); font-weight: 500; background: var(--bg-tertiary); }
.phase-badge.planning { background: var(--color-info-bg); color: var(--color-info); }
.phase-badge.executing { background: var(--color-primary-bg); color: var(--color-primary); }
.phase-badge.validating { background: var(--color-warning-bg); color: var(--color-warning); }
.phase-badge.complete { background: var(--color-success-bg); color: var(--color-success); }
.phase-badge.failed { background: var(--color-error-bg); color: var(--color-error); }
.service-badge { padding: var(--spacing-0-5) var(--spacing-2); border-radius: var(--radius-xl); background: var(--bg-tertiary); color: var(--text-secondary); font-family: monospace; }
.header-actions { display: flex; gap: var(--spacing-2-5); align-items: center; }

.btn-notif {
  padding: var(--spacing-2) var(--spacing-2-5);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  cursor: pointer;
  font-size: var(--text-sm);
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.btn-notif:hover { background: var(--bg-hover); color: var(--color-primary); }

.progress-overview { padding: var(--spacing-5); background: var(--bg-secondary); }
.progress-bar-large { height: 8px; background: var(--bg-tertiary); border-radius: var(--radius-default); overflow: hidden; margin-bottom: var(--spacing-4); }
.progress-bar-large .progress-fill { height: 100%; background: var(--color-primary); transition: width 0.3s; }
.progress-stats { display: flex; justify-content: space-around; }
.progress-stats .stat { text-align: center; }
.progress-stats .value { display: block; font-size: var(--text-2xl); font-weight: 600; color: var(--text-primary); }
.progress-stats .label { font-size: var(--text-xs); color: var(--text-tertiary); }

.steps-container { flex: 1; overflow-y: auto; padding: var(--spacing-5); }
.steps-container h4 { margin: var(--spacing-0) var(--spacing-0) var(--spacing-4); font-size: var(--text-sm); color: var(--text-primary); display: flex; align-items: center; gap: var(--spacing-2); }
.steps-container h4 i { color: var(--color-primary); }

.steps-list { display: flex; flex-direction: column; }
.step-item { display: flex; gap: var(--spacing-4); padding-bottom: var(--spacing-4); }
.step-indicator { display: flex; flex-direction: column; align-items: center; }
.step-icon { width: 32px; height: 32px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: var(--text-xs); font-weight: 600; background: var(--bg-tertiary); color: var(--text-tertiary); }
.step-icon.completed { background: var(--color-success); color: white; }
.step-icon.failed { background: var(--color-error); color: white; }
.step-icon.executing { background: var(--color-primary); color: white; }
.step-icon.waiting_approval { background: var(--color-warning); color: white; }
.step-icon.skipped { background: var(--bg-tertiary); color: var(--text-muted); }
.step-line { width: 2px; flex: 1; min-height: 20px; background: var(--border-default); margin-top: var(--spacing-1); }
.step-line.completed { background: var(--color-success); }

.step-content { flex: 1; padding: var(--spacing-2) var(--spacing-4); background: var(--bg-secondary); border-radius: var(--radius-lg); border-left: 3px solid var(--border-default); }
.step-item.completed .step-content { border-left-color: var(--color-success); }
.step-item.failed .step-content { border-left-color: var(--color-error); }
.step-item.executing .step-content { border-left-color: var(--color-primary); }
.step-item.waiting_approval .step-content { border-left-color: var(--color-warning); }

.step-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--spacing-2); }
.step-desc { font-size: var(--text-sm); font-weight: 500; color: var(--text-primary); }
.step-status { font-size: var(--text-xs); padding: var(--spacing-0-5) var(--spacing-2); border-radius: var(--radius-xl); background: var(--bg-tertiary); color: var(--text-tertiary); }
.step-status.completed { background: var(--color-success-bg); color: var(--color-success); }
.step-status.failed { background: var(--color-error-bg); color: var(--color-error); }
.step-status.executing { background: var(--color-primary-bg); color: var(--color-primary); }
.step-status.waiting_approval { background: var(--color-warning-bg); color: var(--color-warning); }

.step-command { display: block; padding: var(--spacing-2) var(--spacing-2-5); background: var(--bg-tertiary); border-radius: var(--radius-default); font-size: var(--text-xs); color: var(--text-secondary); margin-bottom: var(--spacing-2); overflow-x: auto; }
.step-meta { display: flex; gap: var(--spacing-3); font-size: var(--text-xs); color: var(--text-tertiary); }
.step-meta span { display: flex; align-items: center; gap: var(--spacing-1); }
.step-meta .risk { padding: var(--spacing-0-5) var(--spacing-1-5); border-radius: var(--radius-lg); }
.step-meta .risk.low { background: var(--color-success-bg); color: var(--color-success); }
.step-meta .risk.medium { background: var(--color-warning-bg); color: var(--color-warning); }
.step-meta .risk.high { background: var(--color-error-bg); color: var(--color-error); }

.step-actions { display: flex; gap: var(--spacing-2); margin-top: var(--spacing-3); padding-top: var(--spacing-3); border-top: 1px solid var(--border-default); }
.step-result { margin-top: var(--spacing-3); padding: var(--spacing-2-5); background: var(--bg-tertiary); border-radius: var(--radius-default); }
.step-result.error { background: var(--color-error-bg); }
.step-result pre { margin: var(--spacing-0); font-size: var(--text-xs); color: var(--text-secondary); white-space: pre-wrap; word-break: break-all; max-height: 150px; overflow-y: auto; }

.btn-success { padding: var(--spacing-2) var(--spacing-4); background: var(--color-success); color: white; border: none; border-radius: var(--radius-md); font-size: var(--text-sm); font-weight: 500; cursor: pointer; display: inline-flex; align-items: center; gap: var(--spacing-1-5); }
.btn-success:hover { filter: brightness(1.1); }
.btn-warning { padding: var(--spacing-2) var(--spacing-4); background: var(--color-warning); color: white; border: none; border-radius: var(--radius-md); font-size: var(--text-sm); font-weight: 500; cursor: pointer; display: inline-flex; align-items: center; gap: var(--spacing-1-5); }
.btn-warning:hover { filter: brightness(1.1); }
.btn-danger { padding: var(--spacing-2) var(--spacing-4); background: var(--color-error); color: white; border: none; border-radius: var(--radius-md); font-size: var(--text-sm); font-weight: 500; cursor: pointer; display: inline-flex; align-items: center; gap: var(--spacing-1-5); }
.btn-danger:hover { filter: brightness(1.1); }
.btn-secondary { padding: var(--spacing-2) var(--spacing-4); background: var(--bg-tertiary); color: var(--text-secondary); border: 1px solid var(--border-default); border-radius: var(--radius-md); font-size: var(--text-sm); cursor: pointer; display: inline-flex; align-items: center; gap: var(--spacing-1-5); }
.btn-secondary:hover { background: var(--bg-hover); }
.btn-sm { padding: var(--spacing-1-5) var(--spacing-3); font-size: var(--text-xs); }
</style>
