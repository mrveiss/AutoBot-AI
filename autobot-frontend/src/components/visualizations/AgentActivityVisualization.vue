<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  AgentActivityVisualization.vue - Real-time agent activity visualization
  Displays active agents, their states, and current activities
  Issue #62: Enhanced Visualizations
-->
<template>
  <div class="agent-activity-viz">
    <div class="viz-header">
      <h3>{{ title || t('visualizations.agentActivity.defaultTitle') }}</h3>
      <div class="header-controls">
        <div class="view-toggle">
          <button
            @click="viewMode = 'grid'"
            :class="{ active: viewMode === 'grid' }"
            :title="t('visualizations.agentActivity.gridView')"
          >
            <Icon name="th-large" />
          </button>
          <button
            @click="viewMode = 'timeline'"
            :class="{ active: viewMode === 'timeline' }"
            :title="t('visualizations.agentActivity.timelineView')"
          >
            <Icon name="stream" />
          </button>
        </div>
        <div class="status-summary">
          <span class="active-count">
            <Icon name="circle" class="pulse" />
            {{ t('visualizations.agentActivity.activeCount', { count: activeAgentCount }) }}
          </span>
        </div>
      </div>
    </div>

    <!-- BUG1: visible empty/error state instead of fabricated sample data -->
    <div v-if="loaded && agents.length === 0" class="agents-empty-state">
      <Icon :name="error ? 'exclamation-triangle' : 'pause-circle'" class="empty-icon" />
      <p>{{ error ? 'Unable to load agent activity right now.' : 'No active agents.' }}</p>
    </div>

    <!-- Grid View -->
    <div v-else-if="viewMode === 'grid'" class="agents-grid">
      <div
        v-for="agent in agents"
        :key="agent.id"
        class="agent-card"
        :class="[agent.status, { expanded: isAgentExpanded(agent.id) }]"
        @click="toggleExpand(agent.id)"
      >
        <!-- Agent Avatar -->
        <div class="agent-avatar" :class="agent.type">
          <span class="avatar-icon">{{ getAgentIcon(agent.type) }}</span>
          <div class="status-ring" :class="agent.status"></div>
        </div>

        <!-- Agent Info -->
        <div class="agent-info">
          <h4 class="agent-name">{{ agent.name }}</h4>
          <span class="agent-type">{{ formatAgentType(agent.type) }}</span>
        </div>

        <!-- Current Activity -->
        <div class="current-activity">
          <div v-if="agent.status === 'working'" class="activity-indicator">
            <div class="activity-pulse"></div>
            <span class="activity-text">{{ truncate(agent.currentTask || t('visualizations.agentActivity.processing'), 30) }}</span>
          </div>
          <div v-else-if="agent.status === 'idle'" class="activity-idle">
            <Icon name="pause-circle" />
            <span>{{ t('visualizations.agentActivity.idle') }}</span>
          </div>
          <div v-else-if="agent.status === 'abstained'" class="activity-abstained">
            <Icon name="help-circle" />
            <span>{{ t('visualizations.agentActivity.abstained') }}</span>
          </div>
          <div v-else-if="agent.status === 'error'" class="activity-error">
            <div class="error-badge">
              <Icon name="exclamation-triangle" />
              <span>{{ t('visualizations.agentActivity.error') }}</span>
            </div>
            <!-- TASK 8: actionable CTA on error cards -->
            <button class="view-logs-btn" @click.stop="viewLogs(agent)">
              <Icon name="eye" /> View Logs
            </button>
          </div>
        </div>

        <!-- Metrics -->
        <div class="agent-metrics">
          <div class="metric">
            <span class="metric-value">{{ agent.tasksCompleted }}</span>
            <span class="metric-label">{{ t('visualizations.agentActivity.tasks') }}</span>
          </div>
          <div class="metric">
            <span class="metric-value">{{ formatUptime(agent.uptime) }}</span>
            <span class="metric-label">{{ t('visualizations.agentActivity.uptime') }}</span>
          </div>
          <div class="metric">
            <!-- TASK 5: success rate is meaningless with zero tasks — show N/A -->
            <span class="metric-value">{{ agent.tasksCompleted === 0 ? 'N/A' : agent.successRate + '%' }}</span>
            <span class="metric-label">{{ t('visualizations.agentActivity.success') }}</span>
          </div>
        </div>

        <!-- Expanded Details -->
        <Transition name="expand">
          <div v-if="isAgentExpanded(agent.id)" class="expanded-details">
            <div class="detail-section">
              <h5>{{ t('visualizations.agentActivity.recentTasks') }}</h5>
              <ul class="task-list">
                <li
                  v-for="task in agent.recentTasks"
                  :key="task.id"
                  :class="task.status"
                >
                  <span class="task-name">{{ task.name }}</span>
                  <span class="task-time">{{ formatTimeAgo(task.completedAt) }}</span>
                </li>
              </ul>
            </div>
            <div class="detail-actions">
              <button @click.stop="viewDetails(agent)" class="action-btn">
                <Icon name="eye" /> {{ t('visualizations.agentActivity.detailsBtn') }}
              </button>
              <button @click.stop="pauseAgent(agent)" class="action-btn" :disabled="agent.status !== 'working'">
                <Icon name="pause" /> {{ t('visualizations.agentActivity.pauseBtn') }}
              </button>
            </div>
          </div>
        </Transition>
      </div>
    </div>

    <!-- Timeline View -->
    <div v-else class="activity-timeline">
      <div class="timeline-header">
        <div class="time-labels">
          <span v-for="hour in timeLabels" :key="hour" class="time-label">{{ hour }}</span>
        </div>
      </div>
      <div class="timeline-content">
        <div
          v-for="agent in agents"
          :key="agent.id"
          class="timeline-row"
        >
          <div class="agent-label">
            <span class="avatar-icon small">{{ getAgentIcon(agent.type) }}</span>
            <span class="name">{{ agent.name }}</span>
          </div>
          <div class="activity-bars">
            <div
              v-for="(activity, idx) in agent.activityTimeline"
              :key="idx"
              class="activity-bar"
              :class="activity.type"
              :style="{
                left: `${activity.startPercent}%`,
                width: `${activity.widthPercent}%`
              }"
              :title="`${activity.task} (${formatDuration(activity.duration)})`"
            ></div>
          </div>
        </div>
      </div>
    </div>

    <!-- Live Activity Feed -->
    <div class="activity-feed">
      <h4>
        <!-- TASK 6: was name="signal" which renders as a music note -->
        <Icon name="activity" />
        {{ t('visualizations.agentActivity.liveActivityFeed') }}
      </h4>
      <div class="feed-items">
        <TransitionGroup name="feed">
          <div
            v-for="event in recentEvents"
            :key="event.id"
            class="feed-item"
            :class="event.type"
          >
            <span class="event-icon">{{ getEventIcon(event.type) }}</span>
            <span class="event-agent">{{ event.agentName }}</span>
            <span class="event-message">{{ event.message }}</span>
            <span class="event-time">{{ formatTimeAgo(event.timestamp) }}</span>
          </div>
        </TransitionGroup>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { getCssVar } from '@/composables/useCssVars'
import { useExpansion } from '@/composables/useExpansion'
import { usePollingJob } from '@/composables/usePollingJob'
import { useAgentActivityData, type Agent, type ActivityEvent } from '@/composables/visualizations/useAgentActivityData'

const { t } = useI18n()
const router = useRouter()

// Props
interface Props {
  title?: string
  refreshInterval?: number
}

const props = withDefaults(defineProps<Props>(), {
  title: undefined,
  refreshInterval: 5000
})

// Emit
const emit = defineEmits<{
  (e: 'agent-click', agent: Agent): void
  (e: 'pause-agent', agent: Agent): void
}>()

// State
const viewMode = ref<'grid' | 'timeline'>('grid')
const { isExpanded: isAgentExpanded, expand: expandAgent, collapseAll: collapseAllAgents } = useExpansion<string>()
const { agents, recentEvents, error, loaded, fetchAgents, fetchEvents } = useAgentActivityData()

// Computed
const activeAgentCount = computed(() => {
  return agents.value.filter(a => a.status === 'working').length
})

const timeLabels = computed(() => {
  const now = new Date()
  const labels: string[] = []
  for (let i = 5; i >= 0; i--) {
    const hour = new Date(now.getTime() - i * 60 * 60 * 1000)
    labels.push(hour.getHours().toString().padStart(2, '0') + ':00')
  }
  return labels
})

// Methods
function getAgentIcon(type: string): string {
  const icons: Record<string, string> = {
    orchestrator: '🎭',
    worker: '⚙️',
    monitor: '👁️',
    analyzer: '🔍',
    executor: '🚀'
  }
  return icons[type] || '🤖'
}

function formatAgentType(type: string): string {
  return type.charAt(0).toUpperCase() + type.slice(1) + ' Agent'
}

function formatUptime(seconds: number): string {
  if (seconds < 60) return `${seconds}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`
  return `${Math.floor(seconds / 3600)}h`
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.floor(ms / 60000)}m`
}

function formatTimeAgo(timestamp: number): string {
  const seconds = Math.floor((Date.now() - timestamp) / 1000)
  if (seconds < 60) return `${seconds}s ago`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  return `${Math.floor(seconds / 3600)}h ago`
}

function truncate(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text
  return text.slice(0, maxLength - 1) + '…'
}

function getEventIcon(type: string): string {
  const icons: Record<string, string> = {
    task_started: '▶️',
    task_completed: '✅',
    task_failed: '❌',
    agent_idle: '⏸️',
    agent_error: '⚠️'
  }
  return icons[type] || '📌'
}

function toggleExpand(agentId: string) {
  const wasExpanded = isAgentExpanded(agentId)
  collapseAllAgents()
  if (!wasExpanded) expandAgent(agentId)
}

function viewDetails(agent: Agent) {
  emit('agent-click', agent)
}

// TASK 8: open the per-agent activity diary (logs) for a failed agent
function viewLogs(agent: Agent) {
  router.push({ path: '/agents/activity', query: { agent: agent.id } })
}

function pauseAgent(agent: Agent) {
  emit('pause-agent', agent)
}

// Simulate real-time updates
function simulateActivity() {
  // Add random events
  if (Math.random() > 0.7) {
    const agent = agents.value[Math.floor(Math.random() * agents.value.length)]
    const eventTypes: ActivityEvent['type'][] = ['task_started', 'task_completed', 'task_failed']
    const type = eventTypes[Math.floor(Math.random() * eventTypes.length)]

    const event: ActivityEvent = {
      id: `e${Date.now()}`,
      agentId: agent.id,
      agentName: agent.name,
      type,
      message: type === 'task_completed' ? 'Completed task successfully' :
               type === 'task_started' ? 'Started new task' : 'Task failed',
      timestamp: Date.now()
    }

    recentEvents.value = [event, ...recentEvents.value.slice(0, 9)]
  }

  // Update working agents' task counts
  agents.value.forEach(agent => {
    if (agent.status === 'working' && Math.random() > 0.9) {
      agent.tasksCompleted++
    }
  })
}

// Lifecycle
const { start: _startRefresh, stop: _stopRefresh } = usePollingJob(
  async () => { simulateActivity(); return null },
  { intervalMs: props.refreshInterval || 0, maxAttempts: Number.MAX_SAFE_INTEGER }
)

onMounted(async () => {
  await Promise.all([fetchAgents(), fetchEvents()])

  if (props.refreshInterval > 0) {
    _startRefresh('')
  }
})

onUnmounted(() => {
  _stopRefresh()
})

// Expose
defineExpose({
  refresh: () => Promise.all([fetchAgents(), fetchEvents()]),
  getCssVar
})
</script>

<style scoped>
/**
 * Issue #704: Migrated to design tokens
 * All hardcoded colors replaced with CSS custom properties from design-tokens.css
 */

/* BUG1: empty/error state for the agent activity widget */
.agents-empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-2);
  padding: var(--spacing-8) var(--spacing-4);
  color: var(--text-secondary);
  text-align: center;
}

.agents-empty-state .empty-icon {
  width: 32px;
  height: 32px;
  opacity: 0.7;
}

.agent-activity-viz {
  background: var(--bg-secondary-alpha);
  border-radius: var(--radius-xl);
  padding: var(--spacing-5);
  border: 1px solid var(--border-subtle);
}

.viz-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-5);
  padding-bottom: var(--spacing-4);
  border-bottom: 1px solid var(--border-subtle);
}

.viz-header h3 {
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin: var(--spacing-0);
}

.header-controls {
  display: flex;
  gap: var(--spacing-4);
  align-items: center;
}

.view-toggle {
  display: flex;
  background: var(--bg-tertiary-alpha);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.view-toggle button {
  padding: var(--spacing-2) var(--spacing-3);
  background: transparent;
  border: none;
  color: var(--text-tertiary);
  cursor: pointer;
  transition: all var(--duration-200);
}

.view-toggle button:hover {
  color: var(--text-secondary);
}

.view-toggle button.active {
  background: var(--color-info);
  color: var(--text-on-primary);
}

.status-summary {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.active-count {
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
  font-size: var(--text-sm);
  color: var(--color-success);
}

.active-count i.pulse {
  animation: pulse 2s infinite;
  font-size: 8px;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

/* Grid View */
.agents-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-6);
}

.agent-card {
  background: rgba(15, 23, 42, 0.5);
  border-radius: var(--radius-xl);
  padding: var(--spacing-4);
  border: 1px solid rgba(71, 85, 105, 0.3);
  cursor: pointer;
  transition: all var(--duration-200);
}

.agent-card:hover {
  border-color: rgba(59, 130, 246, 0.5);
  transform: translateY(-2px);
}

.agent-card.working {
  border-left: 3px solid var(--color-info);
}

.agent-card.idle {
  border-left: 3px solid var(--text-tertiary);
}

/* TASK 8: make the error state more visually prominent */
.agent-card.error {
  border: 2px solid var(--color-error);
  background: rgba(220, 38, 38, 0.08);
}

.activity-error {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--spacing-2);
}

.activity-error .error-badge {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-1);
}

.view-logs-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-1);
  padding: var(--spacing-1) var(--spacing-2);
  font-size: var(--text-xs);
  font-weight: 500;
  color: var(--color-error);
  background: transparent;
  border: 1px solid var(--color-error);
  border-radius: var(--radius-md, 6px);
  cursor: pointer;
  transition: background var(--duration-150) var(--ease-in-out);
}

.view-logs-btn:hover {
  background: rgba(220, 38, 38, 0.12);
}

.view-logs-btn .icon {
  width: 12px;
  height: 12px;
}

.agent-card.paused {
  border-left: 3px solid var(--color-warning);
}

.agent-avatar {
  width: 48px;
  height: 48px;
  border-radius: var(--radius-xl);
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  margin-bottom: var(--spacing-3);
}

.agent-avatar.orchestrator {
  background: var(--chart-purple);
}

.agent-avatar.worker {
  background: var(--color-primary);
}

.agent-avatar.monitor {
  background: var(--color-success);
}

.agent-avatar.analyzer {
  background: var(--color-warning);
}

.agent-avatar.executor {
  background: var(--color-error);
}

.avatar-icon {
  font-size: 22px;
}

.avatar-icon.small {
  font-size: var(--text-sm);
}

.status-ring {
  position: absolute;
  bottom: -2px;
  right: -2px;
  width: 14px;
  height: 14px;
  border-radius: var(--radius-full);
  border: 2px solid var(--bg-primary);
}

.status-ring.working {
  background: var(--color-info);
  animation: blink 1s infinite;
}

.status-ring.idle {
  background: var(--text-tertiary);
}

.status-ring.error {
  background: var(--color-error);
}

.status-ring.paused {
  background: var(--color-warning);
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.agent-info {
  margin-bottom: var(--spacing-3);
}

.agent-name {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin: 0 0 var(--spacing-1) 0;
}

.agent-type {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.current-activity {
  padding: var(--spacing-2) var(--spacing-3);
  background: rgba(51, 65, 85, 0.3);
  border-radius: var(--radius-md);
  margin-bottom: var(--spacing-3);
}

.activity-indicator {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.activity-pulse {
  width: 8px;
  height: 8px;
  border-radius: var(--radius-full);
  background: var(--color-info);
  animation: pulse 1.5s infinite;
}

.activity-text {
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.activity-idle,
.activity-error,
.activity-abstained {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-size: var(--text-xs);
}

.activity-idle {
  color: var(--text-tertiary);
}

.activity-abstained {
  color: oklch(0.5 0.15 85);
}

.activity-error {
  color: var(--color-error-light);
}

.agent-metrics {
  display: flex;
  justify-content: space-between;
}

.metric {
  text-align: center;
}

.metric-value {
  display: block;
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.metric-label {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
}

/* Expanded Details */
.expanded-details {
  margin-top: var(--spacing-4);
  padding-top: var(--spacing-4);
  border-top: 1px solid rgba(71, 85, 105, 0.3);
}

.detail-section h5 {
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  color: var(--text-secondary);
  margin: 0 0 var(--spacing-2) 0;
}

.task-list {
  list-style: none;
  padding: var(--spacing-0);
  margin: 0 0 var(--spacing-3) 0;
}

.task-list li {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-1-5) var(--spacing-2);
  background: rgba(51, 65, 85, 0.3);
  border-radius: var(--radius-default);
  margin-bottom: var(--spacing-1);
  font-size: var(--text-xs);
}

.task-list li.completed {
  border-left: 2px solid var(--color-success);
}

.task-list li.failed {
  border-left: 2px solid var(--color-error);
}

.task-name {
  color: var(--text-primary);
}

.task-time {
  color: var(--text-tertiary);
}

.detail-actions {
  display: flex;
  gap: var(--spacing-2);
}

.action-btn {
  flex: 1;
  padding: var(--spacing-2);
  background: var(--color-info-bg);
  border: 1px solid rgba(59, 130, 246, 0.3);
  border-radius: var(--radius-md);
  color: var(--chart-blue-light);
  font-size: var(--text-xs);
  cursor: pointer;
  transition: all var(--duration-200);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-1-5);
}

.action-btn:hover:not(:disabled) {
  background: rgba(59, 130, 246, 0.3);
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Timeline View */
.activity-timeline {
  margin-bottom: var(--spacing-6);
}

.timeline-header {
  margin-bottom: var(--spacing-2);
}

.time-labels {
  display: flex;
  justify-content: space-between;
  /* 140px is a fixed timeline-layout offset, not a spacing-scale value */
  padding-left: 140px;
}

.time-label {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.timeline-content {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.timeline-row {
  display: flex;
  align-items: center;
  height: 36px;
}

.agent-label {
  width: 130px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding-right: var(--spacing-2-5);
}

.agent-label .name {
  font-size: var(--text-xs);
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.activity-bars {
  flex: 1;
  height: 24px;
  background: rgba(51, 65, 85, 0.3);
  border-radius: var(--radius-default);
  position: relative;
  overflow: hidden;
}

.activity-bar {
  position: absolute;
  height: 100%;
  border-radius: var(--radius-sm);
  transition: all var(--duration-300);
}

.activity-bar.working {
  background: var(--color-primary);
}

.activity-bar.idle {
  background: rgba(100, 116, 139, 0.5);
}

.activity-bar.error {
  background: var(--color-error);
}

/* Activity Feed */
.activity-feed {
  background: rgba(15, 23, 42, 0.5);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
}

.activity-feed h4 {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin: 0 0 var(--spacing-3) 0;
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.activity-feed h4 i {
  color: var(--color-warning);
}

.feed-items {
  max-height: 200px;
  overflow-y: auto;
}

.feed-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
  padding: var(--spacing-2-5);
  background: rgba(51, 65, 85, 0.3);
  border-radius: var(--radius-md);
  margin-bottom: var(--spacing-1-5);
  font-size: var(--text-xs);
}

.event-icon {
  flex-shrink: 0;
}

.event-agent {
  color: var(--chart-blue-light);
  font-weight: var(--font-medium);
  flex-shrink: 0;
}

.event-message {
  color: var(--text-secondary);
  flex: 1;
}

.event-time {
  color: var(--text-tertiary);
  font-size: var(--text-xs);
  flex-shrink: 0;
}

/* Transitions */
.expand-enter-active,
.expand-leave-active {
  transition: all var(--duration-300) var(--ease-in-out);
}

.expand-enter-from,
.expand-leave-to {
  opacity: 0;
  max-height: 0;
  overflow: hidden;
}

.expand-enter-to,
.expand-leave-from {
  max-height: 200px;
}

.feed-enter-active,
.feed-leave-active {
  transition: all var(--duration-300) var(--ease-in-out);
}

.feed-enter-from {
  opacity: 0;
  transform: translateX(-20px);
}

.feed-leave-to {
  opacity: 0;
  transform: translateX(20px);
}

/* Responsive */
@media (max-width: 768px) {
  .viz-header {
    flex-direction: column;
    gap: var(--spacing-3);
    align-items: stretch;
  }

  .header-controls {
    justify-content: space-between;
  }

  .agents-grid {
    grid-template-columns: 1fr;
  }

  .timeline-row {
    flex-direction: column;
    height: auto;
    gap: var(--spacing-1);
  }

  .agent-label {
    width: 100%;
    padding-bottom: var(--spacing-1);
  }

  .activity-bars {
    width: 100%;
    height: 20px;
  }
}
</style>
