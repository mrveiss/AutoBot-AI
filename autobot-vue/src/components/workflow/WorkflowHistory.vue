<template>
  <div class="workflow-history">
    <!-- Filters -->
    <div class="history-filters">
      <div class="search-box">
        <i class="fas fa-search"></i>
        <input v-model="searchQuery" placeholder="Search workflows..." />
      </div>
      <div class="filter-group">
        <select v-model="statusFilter">
          <option value="">All Status</option>
          <option value="completed">Completed</option>
          <option value="failed">Failed</option>
          <option value="cancelled">Cancelled</option>
        </select>
        <select v-model="sortOrder">
          <option value="newest">Newest First</option>
          <option value="oldest">Oldest First</option>
          <option value="name">Name A-Z</option>
        </select>
      </div>
    </div>

    <!-- History List -->
    <div v-if="filteredWorkflows.length === 0" class="empty-state">
      <i class="fas fa-history"></i>
      <h3>No Workflow History</h3>
      <p>Completed workflows will appear here</p>
    </div>

    <div v-else class="history-list">
      <div v-for="wf in filteredWorkflows" :key="wf.workflow_id" class="history-item" @click="$emit('view-workflow', wf.workflow_id)">
        <div class="item-status" :class="getStatusClass(wf)">
          <i :class="getStatusIcon(wf)"></i>
        </div>
        <div class="item-info">
          <span class="item-name">{{ wf.name }}</span>
          <span class="item-desc">{{ wf.description }}</span>
          <div class="item-meta">
            <span><i class="fas fa-list-ol"></i> {{ wf.total_steps }} steps</span>
            <span><i class="fas fa-clock"></i> {{ formatDuration(wf) }}</span>
            <span><i class="fas fa-calendar"></i> {{ formatDate(wf.created_at) }}</span>
          </div>
        </div>
        <div class="item-stats">
          <div class="stat success"><span>{{ getCompletedCount(wf) }}</span> passed</div>
          <div class="stat failed" v-if="getFailedCount(wf) > 0"><span>{{ getFailedCount(wf) }}</span> failed</div>
          <div class="stat skipped" v-if="getSkippedCount(wf) > 0"><span>{{ getSkippedCount(wf) }}</span> skipped</div>
        </div>
        <div class="item-actions">
          <button class="btn-icon" @click.stop="$emit('view-workflow', wf.workflow_id)" title="View Details">
            <i class="fas fa-eye"></i>
          </button>
          <button class="btn-icon" @click.stop="$emit('re-run', wf.workflow_id)" title="Re-run">
            <i class="fas fa-redo"></i>
          </button>
        </div>
      </div>
    </div>

    <!-- Pagination -->
    <div v-if="totalPages > 1" class="pagination">
      <button :disabled="currentPage === 1" @click="currentPage--"><i class="fas fa-chevron-left"></i></button>
      <span>Page {{ currentPage }} of {{ totalPages }}</span>
      <button :disabled="currentPage === totalPages" @click="currentPage++"><i class="fas fa-chevron-right"></i></button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import type { ActiveWorkflow } from '@/composables/useWorkflowBuilder';

const props = defineProps<{ workflows: ActiveWorkflow[] }>();
defineEmits<{ (e: 'view-workflow', id: string): void; (e: 're-run', id: string): void }>();

const searchQuery = ref('');
const statusFilter = ref('');
const sortOrder = ref('newest');
const currentPage = ref(1);
const perPage = 10;

const filteredWorkflows = computed(() => {
  let result = [...props.workflows].filter(wf => wf.completed_at || wf.is_cancelled);
  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase();
    result = result.filter(wf => wf.name.toLowerCase().includes(q) || wf.description.toLowerCase().includes(q));
  }
  if (statusFilter.value) {
    result = result.filter(wf => {
      if (statusFilter.value === 'completed') return wf.completed_at && !wf.is_cancelled && getFailedCount(wf) === 0;
      if (statusFilter.value === 'failed') return getFailedCount(wf) > 0;
      if (statusFilter.value === 'cancelled') return wf.is_cancelled;
      return true;
    });
  }
  result.sort((a, b) => {
    if (sortOrder.value === 'newest') return new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime();
    if (sortOrder.value === 'oldest') return new Date(a.created_at || 0).getTime() - new Date(b.created_at || 0).getTime();
    return a.name.localeCompare(b.name);
  });
  const start = (currentPage.value - 1) * perPage;
  return result.slice(start, start + perPage);
});

const totalPages = computed(() => Math.ceil(props.workflows.filter(wf => wf.completed_at || wf.is_cancelled).length / perPage));

function getStatusClass(wf: ActiveWorkflow): string {
  if (wf.is_cancelled) return 'cancelled';
  if (getFailedCount(wf) > 0) return 'failed';
  return 'success';
}

function getStatusIcon(wf: ActiveWorkflow): string {
  if (wf.is_cancelled) return 'fas fa-times';
  if (getFailedCount(wf) > 0) return 'fas fa-exclamation-triangle';
  return 'fas fa-check';
}

function getCompletedCount(wf: ActiveWorkflow): number {
  return wf.steps.filter(s => s.status === 'completed').length;
}

function getFailedCount(wf: ActiveWorkflow): number {
  return wf.steps.filter(s => s.status === 'failed').length;
}

function getSkippedCount(wf: ActiveWorkflow): number {
  return wf.steps.filter(s => s.status === 'skipped').length;
}

function formatDuration(wf: ActiveWorkflow): string {
  if (!wf.started_at || !wf.completed_at) return '-';
  const ms = new Date(wf.completed_at).getTime() - new Date(wf.started_at).getTime();
  const sec = Math.floor(ms / 1000);
  if (sec < 60) return `${sec}s`;
  const min = Math.floor(sec / 60);
  return `${min}m ${sec % 60}s`;
}

function formatDate(date?: string): string {
  if (!date) return '-';
  return new Date(date).toLocaleDateString();
}
</script>

<style scoped>
.workflow-history { height: 100%; display: flex; flex-direction: column; }

.history-filters { display: flex; justify-content: space-between; align-items: center; gap: 16px; margin-bottom: 20px; flex-wrap: wrap; }
.search-box { display: flex; align-items: center; gap: 10px; padding: 10px 14px; background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 8px; flex: 1; min-width: 200px; }
.search-box i { color: var(--text-muted); }
.search-box input { flex: 1; background: none; border: none; color: var(--text-primary); font-size: 14px; outline: none; }
.filter-group { display: flex; gap: 8px; }
.filter-group select { padding: 10px 12px; background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 8px; color: var(--text-primary); font-size: 13px; cursor: pointer; }

.empty-state { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; color: var(--text-tertiary); padding: 40px; }
.empty-state i { font-size: 48px; margin-bottom: 16px; }
.empty-state h3 { margin: 0 0 8px; color: var(--text-primary); }

.history-list { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 12px; }
.history-item { display: flex; align-items: center; gap: 16px; padding: 16px; background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 10px; cursor: pointer; transition: all 0.2s; }
.history-item:hover { border-color: var(--color-primary); box-shadow: 0 2px 8px rgba(0,0,0,0.1); }

.item-status { width: 40px; height: 40px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 16px; flex-shrink: 0; }
.item-status.success { background: var(--color-success-bg); color: var(--color-success); }
.item-status.failed { background: var(--color-error-bg); color: var(--color-error); }
.item-status.cancelled { background: var(--color-warning-bg); color: var(--color-warning); }

.item-info { flex: 1; min-width: 0; }
.item-name { display: block; font-size: 15px; font-weight: 500; color: var(--text-primary); margin-bottom: 2px; }
.item-desc { display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 8px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.item-meta { display: flex; gap: 16px; font-size: 12px; color: var(--text-tertiary); }
.item-meta span { display: flex; align-items: center; gap: 4px; }

.item-stats { display: flex; gap: 12px; }
.item-stats .stat { font-size: 12px; padding: 4px 10px; border-radius: 12px; }
.item-stats .stat span { font-weight: 600; }
.item-stats .success { background: var(--color-success-bg); color: var(--color-success); }
.item-stats .failed { background: var(--color-error-bg); color: var(--color-error); }
.item-stats .skipped { background: var(--bg-tertiary); color: var(--text-tertiary); }

.item-actions { display: flex; gap: 8px; }
.btn-icon { width: 32px; height: 32px; background: var(--bg-tertiary); border: none; border-radius: 6px; color: var(--text-secondary); cursor: pointer; transition: all 0.15s; }
.btn-icon:hover { background: var(--bg-hover); color: var(--text-primary); }

.pagination { display: flex; justify-content: center; align-items: center; gap: 16px; padding: 16px 0; margin-top: auto; }
.pagination button { padding: 8px 12px; background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 6px; color: var(--text-secondary); cursor: pointer; }
.pagination button:hover:not(:disabled) { background: var(--bg-hover); }
.pagination button:disabled { opacity: 0.5; cursor: not-allowed; }
.pagination span { font-size: 13px; color: var(--text-tertiary); }
</style>
