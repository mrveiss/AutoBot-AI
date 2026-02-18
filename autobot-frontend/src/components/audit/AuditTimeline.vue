<template>
  <div class="audit-timeline">
    <!-- Timeline Header -->
    <div class="timeline-header">
      <div class="header-content">
        <h3>
          <i class="fas fa-clock-rotate-left"></i>
          <span v-if="type === 'session'">Session Trail: {{ entityId }}</span>
          <span v-else>User Activity: {{ entityId }}</span>
        </h3>
        <span class="entry-count">{{ entries.length }} events</span>
      </div>
      <button class="btn btn-icon" @click="$emit('close')">
        <i class="fas fa-times"></i>
      </button>
    </div>

    <!-- Timeline Content -->
    <div class="timeline-content">
      <div v-if="loading" class="loading-state">
        <i class="fas fa-spinner fa-spin"></i>
        <span>Loading timeline...</span>
      </div>

      <div v-else-if="entries.length === 0" class="empty-state">
        <i class="fas fa-inbox"></i>
        <span>No audit events found</span>
      </div>

      <div v-else class="timeline-list">
        <div
          v-for="(entry, index) in entries"
          :key="entry.id"
          :class="['timeline-item', `result-${entry.result}`]"
        >
          <!-- Timeline Node -->
          <div class="timeline-node">
            <div :class="['node-dot', `dot-${entry.result}`]">
              <i :class="resultIcon(entry.result)"></i>
            </div>
            <div v-if="index < entries.length - 1" class="node-line"></div>
          </div>

          <!-- Timeline Entry Content -->
          <div class="timeline-entry">
            <div class="entry-header">
              <span class="entry-time">{{ formatTime(entry.timestamp) }}</span>
              <span :class="['result-badge', `badge-${entry.result}`]">
                {{ entry.result }}
              </span>
            </div>
            <div class="entry-operation">
              {{ formatOperationName(entry.operation) }}
            </div>
            <div class="entry-meta">
              <span v-if="type === 'session' && entry.user_id" class="meta-item">
                <i class="fas fa-user"></i>
                {{ entry.user_id }}
              </span>
              <span v-if="type === 'user' && entry.session_id" class="meta-item">
                <i class="fas fa-fingerprint"></i>
                {{ truncateId(entry.session_id) }}
              </span>
              <span v-if="entry.vm_name" class="meta-item">
                <i class="fas fa-server"></i>
                {{ entry.vm_name }}
              </span>
              <span v-if="entry.ip_address" class="meta-item">
                <i class="fas fa-network-wired"></i>
                {{ entry.ip_address }}
              </span>
            </div>
            <div v-if="entry.error_message" class="entry-error">
              <i class="fas fa-exclamation-circle"></i>
              {{ entry.error_message }}
            </div>
            <button
              v-if="hasDetails(entry)"
              class="details-toggle"
              @click="toggleDetails(entry.id)"
            >
              <i :class="expandedIds.has(entry.id) ? 'fas fa-chevron-up' : 'fas fa-chevron-down'"></i>
              {{ expandedIds.has(entry.id) ? 'Hide Details' : 'Show Details' }}
            </button>
            <div v-if="expandedIds.has(entry.id) && hasDetails(entry)" class="entry-details">
              <pre>{{ formatDetails(entry.details) }}</pre>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Timeline Footer -->
    <div class="timeline-footer">
      <span class="time-range">
        <template v-if="entries.length > 0">
          {{ formatDateRange }}
        </template>
      </span>
      <button class="btn btn-secondary" @click="$emit('refresh')">
        <i class="fas fa-sync-alt" :class="{ 'fa-spin': loading }"></i>
        Refresh
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { AuditEntry } from '@/types/audit'
import { AUDIT_RESULT_CONFIG } from '@/types/audit'

interface Props {
  type: 'session' | 'user'
  entityId: string
  entries: AuditEntry[]
  loading?: boolean
}

interface Emits {
  (e: 'close'): void
  (e: 'refresh'): void
}

const props = withDefaults(defineProps<Props>(), {
  loading: false
})

defineEmits<Emits>()

const expandedIds = ref<Set<string>>(new Set())

const formatDateRange = computed(() => {
  if (props.entries.length === 0) return ''

  const dates = props.entries.map((e) => new Date(e.timestamp))
  const earliest = new Date(Math.min(...dates.map((d) => d.getTime())))
  const latest = new Date(Math.max(...dates.map((d) => d.getTime())))

  const formatDate = (d: Date) => d.toLocaleDateString()

  if (formatDate(earliest) === formatDate(latest)) {
    return formatDate(earliest)
  }
  return `${formatDate(earliest)} - ${formatDate(latest)}`
})

function formatTime(timestamp: string): string {
  const date = new Date(timestamp)
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function formatOperationName(operation: string): string {
  return operation
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase())
}

function resultIcon(result: string): string {
  const config = AUDIT_RESULT_CONFIG[result as keyof typeof AUDIT_RESULT_CONFIG]
  return config?.icon || 'fas fa-question-circle'
}

function truncateId(id: string): string {
  if (id.length <= 12) return id
  return `${id.substring(0, 8)}...`
}

function hasDetails(entry: AuditEntry): boolean {
  return entry.details && Object.keys(entry.details).length > 0
}

function formatDetails(details: Record<string, unknown>): string {
  return JSON.stringify(details, null, 2)
}

function toggleDetails(id: string) {
  if (expandedIds.value.has(id)) {
    expandedIds.value.delete(id)
  } else {
    expandedIds.value.add(id)
  }
}
</script>

<style scoped>
.audit-timeline {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  display: flex;
  flex-direction: column;
  height: 100%;
  max-height: 600px;
}

.timeline-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-4);
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-secondary);
}

.header-content {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
}

.header-content h3 {
  margin: 0;
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.header-content h3 i {
  color: var(--color-primary);
}

.entry-count {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  background: var(--bg-secondary);
  padding: var(--spacing-1) var(--spacing-2);
  border-radius: var(--radius-default);
}

.btn-icon {
  padding: var(--spacing-2);
  background: transparent;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: var(--radius-default);
}

.btn-icon:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.timeline-content {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-4);
}

.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-8);
  color: var(--text-tertiary);
  gap: var(--spacing-2);
}

.loading-state i,
.empty-state i {
  font-size: var(--text-3xl);
}

.timeline-list {
  display: flex;
  flex-direction: column;
}

.timeline-item {
  display: flex;
  gap: var(--spacing-3);
}

.timeline-node {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex-shrink: 0;
}

.node-dot {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-full);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-sm);
}

.dot-success {
  background: rgba(34, 197, 94, 0.1);
  color: rgb(34, 197, 94);
}

.dot-denied {
  background: rgba(239, 68, 68, 0.1);
  color: rgb(239, 68, 68);
}

.dot-failed {
  background: rgba(249, 115, 22, 0.1);
  color: rgb(249, 115, 22);
}

.dot-error {
  background: rgba(234, 179, 8, 0.1);
  color: rgb(234, 179, 8);
}

.node-line {
  flex: 1;
  width: 2px;
  background: var(--border-default);
  min-height: 20px;
}

.timeline-entry {
  flex: 1;
  padding-bottom: var(--spacing-4);
}

.entry-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  margin-bottom: var(--spacing-1);
}

.entry-time {
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-primary);
}

.result-badge {
  display: inline-flex;
  align-items: center;
  padding: var(--spacing-0-5) var(--spacing-2);
  border-radius: var(--radius-default);
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
  text-transform: capitalize;
}

.badge-success {
  background: rgba(34, 197, 94, 0.1);
  color: rgb(34, 197, 94);
}

.badge-denied {
  background: rgba(239, 68, 68, 0.1);
  color: rgb(239, 68, 68);
}

.badge-failed {
  background: rgba(249, 115, 22, 0.1);
  color: rgb(249, 115, 22);
}

.badge-error {
  background: rgba(234, 179, 8, 0.1);
  color: rgb(234, 179, 8);
}

.entry-operation {
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin-bottom: var(--spacing-2);
}

.entry-meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-3);
  margin-bottom: var(--spacing-2);
}

.meta-item {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-1);
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.meta-item i {
  color: var(--text-tertiary);
}

.entry-error {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-2);
  font-size: var(--text-sm);
  color: rgb(239, 68, 68);
  background: rgba(239, 68, 68, 0.1);
  padding: var(--spacing-2);
  border-radius: var(--radius-default);
  margin-bottom: var(--spacing-2);
}

.details-toggle {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-1);
  background: none;
  border: none;
  color: var(--color-primary);
  font-size: var(--text-xs);
  cursor: pointer;
  padding: 0;
}

.details-toggle:hover {
  text-decoration: underline;
}

.entry-details {
  margin-top: var(--spacing-2);
}

.entry-details pre {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  background: var(--bg-secondary);
  padding: var(--spacing-2);
  border-radius: var(--radius-default);
  overflow-x: auto;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
}

.timeline-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-3) var(--spacing-4);
  border-top: 1px solid var(--border-default);
  background: var(--bg-secondary);
}

.time-range {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.btn-secondary {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-default);
  font-size: var(--text-sm);
  color: var(--text-primary);
  cursor: pointer;
  transition: all var(--duration-200) var(--ease-in-out);
}

.btn-secondary:hover {
  background: var(--bg-hover);
}

@media (max-width: 768px) {
  .header-content {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--spacing-1);
  }

  .entry-meta {
    flex-direction: column;
    gap: var(--spacing-1);
  }

  .timeline-footer {
    flex-direction: column;
    gap: var(--spacing-2);
    text-align: center;
  }
}
</style>
