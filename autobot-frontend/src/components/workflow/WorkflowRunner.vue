<template>
  <div class="workflow-runner">
    <!-- Workflow List -->
    <div class="runner-sidebar">
      <div class="sidebar-header">
        <h4><i class="fas fa-tasks"></i> Active Workflows</h4>
        <button class="btn-refresh" @click="$emit('refresh')" :disabled="loading">
          <i class="fas fa-sync-alt" :class="{ 'fa-spin': loading }"></i>
        </button>
      </div>
      <div v-if="workflows.length === 0" class="empty-list">
        <i class="fas fa-inbox"></i>
        <p>No active workflows</p>
      </div>
      <div v-else class="workflow-list">
        <div v-for="wf in workflows" :key="wf.workflow_id" class="workflow-item"
             :class="{ active: currentWorkflow?.workflow_id === wf.workflow_id, paused: wf.is_paused }"
             @click="selectWorkflow(wf)">
          <div class="wf-status" :class="getStatusClass(wf)">
            <i :class="getStatusIcon(wf)"></i>
          </div>
          <div class="wf-info">
            <span class="wf-name">{{ wf.name }}</span>
            <span class="wf-progress">Step {{ wf.current_step + 1 }} / {{ wf.total_steps }}</span>
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
        <i class="fas fa-hand-pointer"></i>
        <h3>Select a Workflow</h3>
        <p>Choose an active workflow from the list to view details and control execution</p>
      </div>

      <template v-else>
        <!-- Workflow Header -->
        <div class="workflow-header">
          <div class="header-info">
            <h2>{{ currentWorkflow.name }}</h2>
            <p>{{ currentWorkflow.description }}</p>
            <div class="header-meta">
              <span><i class="fas fa-calendar"></i> Started {{ formatTime(currentWorkflow.started_at) }}</span>
              <span><i class="fas fa-cog"></i> {{ currentWorkflow.automation_mode }}</span>
            </div>
          </div>
          <div class="header-actions">
            <button v-if="currentWorkflow.is_paused" class="btn-success" @click="$emit('resume-workflow', currentWorkflow.workflow_id)">
              <i class="fas fa-play"></i> Resume
            </button>
            <button v-else class="btn-warning" @click="$emit('pause-workflow', currentWorkflow.workflow_id)">
              <i class="fas fa-pause"></i> Pause
            </button>
            <button class="btn-danger" @click="$emit('cancel-workflow', currentWorkflow.workflow_id)">
              <i class="fas fa-stop"></i> Cancel
            </button>
          </div>
        </div>

        <!-- Progress Overview -->
        <div class="progress-overview">
          <div class="progress-bar-large">
            <div class="progress-fill" :style="{ width: getProgress(currentWorkflow) + '%' }"></div>
          </div>
          <div class="progress-stats">
            <div class="stat"><span class="value">{{ currentWorkflow.current_step + 1 }}</span><span class="label">Current</span></div>
            <div class="stat"><span class="value">{{ currentWorkflow.total_steps }}</span><span class="label">Total</span></div>
            <div class="stat"><span class="value">{{ completedSteps }}</span><span class="label">Completed</span></div>
            <div class="stat"><span class="value">{{ failedSteps }}</span><span class="label">Failed</span></div>
          </div>
        </div>

        <!-- Steps List -->
        <div class="steps-container">
          <h4><i class="fas fa-list-ol"></i> Execution Steps</h4>
          <div class="steps-list">
            <div v-for="(step, i) in currentWorkflow.steps" :key="step.step_id" class="step-item" :class="step.status">
              <div class="step-indicator">
                <div class="step-icon" :class="step.status">
                  <i v-if="step.status === 'completed'" class="fas fa-check"></i>
                  <i v-else-if="step.status === 'failed'" class="fas fa-times"></i>
                  <i v-else-if="step.status === 'executing'" class="fas fa-spinner fa-spin"></i>
                  <i v-else-if="step.status === 'waiting_approval'" class="fas fa-clock"></i>
                  <i v-else-if="step.status === 'skipped'" class="fas fa-forward"></i>
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
                  <span class="risk" :class="step.risk_level"><i class="fas fa-shield-alt"></i> {{ step.risk_level }}</span>
                  <span v-if="step.started_at"><i class="fas fa-play"></i> {{ formatTime(step.started_at) }}</span>
                  <span v-if="step.completed_at"><i class="fas fa-check"></i> {{ formatTime(step.completed_at) }}</span>
                </div>
                <!-- Approval Actions -->
                <div v-if="step.status === 'waiting_approval' && step.requires_confirmation" class="step-actions">
                  <button class="btn-success btn-sm" @click="$emit('approve-step', currentWorkflow.workflow_id, step.step_id)">
                    <i class="fas fa-check"></i> Approve
                  </button>
                  <button class="btn-secondary btn-sm" @click="$emit('skip-step', currentWorkflow.workflow_id, step.step_id)">
                    <i class="fas fa-forward"></i> Skip
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
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { ActiveWorkflow } from '@/composables/useWorkflowBuilder';

const props = defineProps<{ workflows: ActiveWorkflow[]; currentWorkflow: ActiveWorkflow | null; loading: boolean }>();
const emit = defineEmits<{
  (e: 'start-workflow', id: string): void;
  (e: 'pause-workflow', id: string): void;
  (e: 'resume-workflow', id: string): void;
  (e: 'cancel-workflow', id: string): void;
  (e: 'approve-step', wfId: string, stepId: string): void;
  (e: 'skip-step', wfId: string, stepId: string): void;
  (e: 'refresh'): void;
}>();

const completedSteps = computed(() => props.currentWorkflow?.steps.filter(s => s.status === 'completed').length ?? 0);
const failedSteps = computed(() => props.currentWorkflow?.steps.filter(s => s.status === 'failed').length ?? 0);

function selectWorkflow(wf: ActiveWorkflow) {
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

function getStatusIcon(wf: ActiveWorkflow): string {
  if (wf.is_cancelled) return 'fas fa-times';
  if (wf.is_paused) return 'fas fa-pause';
  if (wf.completed_at) return 'fas fa-check';
  return 'fas fa-spinner fa-spin';
}

function formatStatus(status: string): string {
  return status.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
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
.workflow-runner { display: flex; height: 100%; gap: 0; background: var(--bg-primary); border-radius: 8px; overflow: hidden; }

.runner-sidebar { width: 300px; min-width: 300px; background: var(--bg-secondary); border-right: 1px solid var(--border-default); display: flex; flex-direction: column; }
.sidebar-header { display: flex; justify-content: space-between; align-items: center; padding: 16px; border-bottom: 1px solid var(--border-default); }
.sidebar-header h4 { margin: 0; font-size: 14px; color: var(--text-primary); display: flex; align-items: center; gap: 8px; }
.sidebar-header h4 i { color: var(--color-primary); }
.btn-refresh { padding: 6px; background: transparent; border: none; color: var(--text-tertiary); cursor: pointer; border-radius: 4px; }
.btn-refresh:hover:not(:disabled) { background: var(--bg-hover); }
.btn-refresh:disabled { opacity: 0.5; }

.empty-list { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; color: var(--text-muted); padding: 20px; }
.empty-list i { font-size: 32px; margin-bottom: 12px; }

.workflow-list { flex: 1; overflow-y: auto; padding: 8px; }
.workflow-item { padding: 12px; background: var(--bg-tertiary); border-radius: 8px; margin-bottom: 8px; cursor: pointer; transition: all 0.15s; }
.workflow-item:hover { background: var(--bg-hover); }
.workflow-item.active { background: var(--color-primary-bg); border: 1px solid var(--color-primary); }
.workflow-item.paused { opacity: 0.7; }
.workflow-item { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
.wf-status { width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 12px; }
.wf-status.running { background: var(--color-success-bg); color: var(--color-success); }
.wf-status.paused { background: var(--color-warning-bg); color: var(--color-warning); }
.wf-status.completed { background: var(--color-info-bg); color: var(--color-info); }
.wf-status.cancelled { background: var(--color-error-bg); color: var(--color-error); }
.wf-info { flex: 1; min-width: 0; }
.wf-name { display: block; font-size: 13px; font-weight: 500; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.wf-progress { font-size: 11px; color: var(--text-tertiary); }
.wf-progress-bar { width: 100%; height: 4px; background: var(--bg-secondary); border-radius: 2px; overflow: hidden; }
.wf-progress-bar .progress-fill { height: 100%; background: var(--color-primary); transition: width 0.3s; }

.runner-main { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.no-selection { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; color: var(--text-tertiary); padding: 40px; }
.no-selection i { font-size: 48px; margin-bottom: 16px; }
.no-selection h3 { margin: 0 0 8px; color: var(--text-primary); }

.workflow-header { display: flex; justify-content: space-between; align-items: flex-start; padding: 20px; background: var(--bg-secondary); border-bottom: 1px solid var(--border-default); }
.header-info h2 { margin: 0 0 4px; font-size: 18px; color: var(--text-primary); }
.header-info p { margin: 0 0 10px; font-size: 13px; color: var(--text-secondary); }
.header-meta { display: flex; gap: 16px; font-size: 12px; color: var(--text-tertiary); }
.header-meta span { display: flex; align-items: center; gap: 6px; }
.header-actions { display: flex; gap: 10px; }

.progress-overview { padding: 20px; background: var(--bg-secondary); }
.progress-bar-large { height: 8px; background: var(--bg-tertiary); border-radius: 4px; overflow: hidden; margin-bottom: 16px; }
.progress-bar-large .progress-fill { height: 100%; background: var(--color-primary); transition: width 0.3s; }
.progress-stats { display: flex; justify-content: space-around; }
.progress-stats .stat { text-align: center; }
.progress-stats .value { display: block; font-size: 24px; font-weight: 600; color: var(--text-primary); }
.progress-stats .label { font-size: 12px; color: var(--text-tertiary); }

.steps-container { flex: 1; overflow-y: auto; padding: 20px; }
.steps-container h4 { margin: 0 0 16px; font-size: 14px; color: var(--text-primary); display: flex; align-items: center; gap: 8px; }
.steps-container h4 i { color: var(--color-primary); }

.steps-list { display: flex; flex-direction: column; }
.step-item { display: flex; gap: 16px; padding-bottom: 16px; }
.step-indicator { display: flex; flex-direction: column; align-items: center; }
.step-icon { width: 32px; height: 32px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 600; background: var(--bg-tertiary); color: var(--text-tertiary); }
.step-icon.completed { background: var(--color-success); color: white; }
.step-icon.failed { background: var(--color-error); color: white; }
.step-icon.executing { background: var(--color-primary); color: white; }
.step-icon.waiting_approval { background: var(--color-warning); color: white; }
.step-icon.skipped { background: var(--bg-tertiary); color: var(--text-muted); }
.step-line { width: 2px; flex: 1; min-height: 20px; background: var(--border-default); margin-top: 4px; }
.step-line.completed { background: var(--color-success); }

.step-content { flex: 1; padding: 8px 16px; background: var(--bg-secondary); border-radius: 8px; border-left: 3px solid var(--border-default); }
.step-item.completed .step-content { border-left-color: var(--color-success); }
.step-item.failed .step-content { border-left-color: var(--color-error); }
.step-item.executing .step-content { border-left-color: var(--color-primary); }
.step-item.waiting_approval .step-content { border-left-color: var(--color-warning); }

.step-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.step-desc { font-size: 14px; font-weight: 500; color: var(--text-primary); }
.step-status { font-size: 11px; padding: 2px 8px; border-radius: 10px; background: var(--bg-tertiary); color: var(--text-tertiary); }
.step-status.completed { background: var(--color-success-bg); color: var(--color-success); }
.step-status.failed { background: var(--color-error-bg); color: var(--color-error); }
.step-status.executing { background: var(--color-primary-bg); color: var(--color-primary); }
.step-status.waiting_approval { background: var(--color-warning-bg); color: var(--color-warning); }

.step-command { display: block; padding: 8px 10px; background: var(--bg-tertiary); border-radius: 4px; font-size: 12px; color: var(--text-secondary); margin-bottom: 8px; overflow-x: auto; }
.step-meta { display: flex; gap: 12px; font-size: 11px; color: var(--text-tertiary); }
.step-meta span { display: flex; align-items: center; gap: 4px; }
.step-meta .risk { padding: 2px 6px; border-radius: 8px; }
.step-meta .risk.low { background: var(--color-success-bg); color: var(--color-success); }
.step-meta .risk.medium { background: var(--color-warning-bg); color: var(--color-warning); }
.step-meta .risk.high { background: var(--color-error-bg); color: var(--color-error); }

.step-actions { display: flex; gap: 8px; margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--border-default); }
.step-result { margin-top: 12px; padding: 10px; background: var(--bg-tertiary); border-radius: 4px; }
.step-result.error { background: var(--color-error-bg); }
.step-result pre { margin: 0; font-size: 11px; color: var(--text-secondary); white-space: pre-wrap; word-break: break-all; max-height: 150px; overflow-y: auto; }

.btn-success { padding: 8px 16px; background: var(--color-success); color: white; border: none; border-radius: 6px; font-size: 13px; font-weight: 500; cursor: pointer; display: inline-flex; align-items: center; gap: 6px; }
.btn-success:hover { filter: brightness(1.1); }
.btn-warning { padding: 8px 16px; background: var(--color-warning); color: white; border: none; border-radius: 6px; font-size: 13px; font-weight: 500; cursor: pointer; display: inline-flex; align-items: center; gap: 6px; }
.btn-warning:hover { filter: brightness(1.1); }
.btn-danger { padding: 8px 16px; background: var(--color-error); color: white; border: none; border-radius: 6px; font-size: 13px; font-weight: 500; cursor: pointer; display: inline-flex; align-items: center; gap: 6px; }
.btn-danger:hover { filter: brightness(1.1); }
.btn-secondary { padding: 8px 16px; background: var(--bg-tertiary); color: var(--text-secondary); border: 1px solid var(--border-default); border-radius: 6px; font-size: 13px; cursor: pointer; display: inline-flex; align-items: center; gap: 6px; }
.btn-secondary:hover { background: var(--bg-hover); }
.btn-sm { padding: 6px 12px; font-size: 12px; }
</style>
