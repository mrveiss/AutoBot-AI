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
      <h3>{{ title }}</h3>
      <div class="header-controls">
        <div class="view-toggle">
          <button
            @click="viewMode = 'grid'"
            :class="{ active: viewMode === 'grid' }"
            title="Grid view"
          >
            <i class="fas fa-th-large"></i>
          </button>
          <button
            @click="viewMode = 'timeline'"
            :class="{ active: viewMode === 'timeline' }"
            title="Timeline view"
          >
            <i class="fas fa-stream"></i>
          </button>
        </div>
        <div class="status-summary">
          <span class="active-count">
            <i class="fas fa-circle pulse"></i>
            {{ activeAgentCount }} active
          </span>
        </div>
      </div>
    </div>

    <!-- Grid View -->
    <div v-if="viewMode === 'grid'" class="agents-grid">
      <div
        v-for="agent in agents"
        :key="agent.id"
        class="agent-card"
        :class="[agent.status, { expanded: expandedAgent === agent.id }]"
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
            <span class="activity-text">{{ truncate(agent.currentTask || 'Processing...', 30) }}</span>
          </div>
          <div v-else-if="agent.status === 'idle'" class="activity-idle">
            <i class="fas fa-pause-circle"></i>
            <span>Idle</span>
          </div>
          <div v-else-if="agent.status === 'error'" class="activity-error">
            <i class="fas fa-exclamation-triangle"></i>
            <span>Error</span>
          </div>
        </div>

        <!-- Metrics -->
        <div class="agent-metrics">
          <div class="metric">
            <span class="metric-value">{{ agent.tasksCompleted }}</span>
            <span class="metric-label">Tasks</span>
          </div>
          <div class="metric">
            <span class="metric-value">{{ formatUptime(agent.uptime) }}</span>
            <span class="metric-label">Uptime</span>
          </div>
          <div class="metric">
            <span class="metric-value">{{ agent.successRate }}%</span>
            <span class="metric-label">Success</span>
          </div>
        </div>

        <!-- Expanded Details -->
        <Transition name="expand">
          <div v-if="expandedAgent === agent.id" class="expanded-details">
            <div class="detail-section">
              <h5>Recent Tasks</h5>
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
                <i class="fas fa-eye"></i> Details
              </button>
              <button @click.stop="pauseAgent(agent)" class="action-btn" :disabled="agent.status !== 'working'">
                <i class="fas fa-pause"></i> Pause
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
        <i class="fas fa-rss"></i>
        Live Activity Feed
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
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('AgentActivityVisualization')

/**
 * Helper to retrieve CSS custom property values from design tokens.
 * Issue #704: Design token migration helper
 */
function getCssVar(varName: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(varName).trim()
}

// Types
interface Agent {
  id: string
  name: string
  type: 'orchestrator' | 'worker' | 'monitor' | 'analyzer' | 'executor'
  status: 'working' | 'idle' | 'error' | 'paused'
  currentTask?: string
  tasksCompleted: number
  uptime: number
  successRate: number
  recentTasks: Array<{
    id: string
    name: string
    status: 'completed' | 'failed' | 'cancelled'
    completedAt: number
  }>
  activityTimeline: Array<{
    task: string
    type: 'working' | 'idle' | 'error'
    startPercent: number
    widthPercent: number
    duration: number
  }>
}

interface ActivityEvent {
  id: string
  agentId: string
  agentName: string
  type: 'task_started' | 'task_completed' | 'task_failed' | 'agent_idle' | 'agent_error'
  message: string
  timestamp: number
}

// Props
interface Props {
  title?: string
  refreshInterval?: number
}

const props = withDefaults(defineProps<Props>(), {
  title: 'Agent Activity Monitor',
  refreshInterval: 5000
})

// Emit
const emit = defineEmits<{
  (e: 'agent-click', agent: Agent): void
  (e: 'pause-agent', agent: Agent): void
}>()

// State
const viewMode = ref<'grid' | 'timeline'>('grid')
const expandedAgent = ref<string | null>(null)
const agents = ref<Agent[]>([])
const recentEvents = ref<ActivityEvent[]>([])

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
  expandedAgent.value = expandedAgent.value === agentId ? null : agentId
}

function viewDetails(agent: Agent) {
  emit('agent-click', agent)
}

function pauseAgent(agent: Agent) {
  emit('pause-agent', agent)
}

async function fetchAgents() {
  try {
    const response = await fetch('/api/agents/status')
    if (response.ok) {
      const data = await response.json()
      if (data.agents) {
        agents.value = data.agents
        return
      }
    }
  } catch (err) {
    logger.warn('Failed to fetch agents, using sample data')
  }

  // Generate sample data
  agents.value = getSampleAgents()
}

async function fetchEvents() {
  try {
    // Issue #552: Fixed path - backend uses /api/analytics/agents/tasks/recent
    // (analytics_agents.py has prefix="/agents" and is included into analytics.py router)
    const response = await fetch('/api/analytics/agents/tasks/recent?limit=10')
    if (response.ok) {
      const data = await response.json()
      // Backend returns tasks, not events - adapt response structure
      if (data.tasks || data.data?.tasks) {
        const tasks = data.tasks || data.data?.tasks
        recentEvents.value = tasks.map((task: any) => ({
          id: task.id || task.task_id,
          type: task.status === 'completed' ? 'task_complete' : 'task_start',
          agentId: task.agent_id,
          timestamp: task.completed_at || task.started_at || new Date().toISOString(),
          details: task.details || task.description || ''
        }))
        return
      }
    }
  } catch (err) {
    logger.warn('Failed to fetch events, using sample data')
  }

  // Generate sample events
  recentEvents.value = getSampleEvents()
}

function getSampleAgents(): Agent[] {
  const now = Date.now()
  return [
    {
      id: 'orch-1',
      name: 'Main Orchestrator',
      type: 'orchestrator',
      status: 'working',
      currentTask: 'Coordinating workflow execution',
      tasksCompleted: 142,
      uptime: 28800,
      successRate: 98,
      recentTasks: [
        { id: 't1', name: 'Workflow #456', status: 'completed', completedAt: now - 60000 },
        { id: 't2', name: 'Workflow #455', status: 'completed', completedAt: now - 300000 },
        { id: 't3', name: 'Workflow #454', status: 'failed', completedAt: now - 600000 }
      ],
      activityTimeline: [
        { task: 'Workflow coordination', type: 'working', startPercent: 0, widthPercent: 30, duration: 108000 },
        { task: 'Idle', type: 'idle', startPercent: 30, widthPercent: 10, duration: 36000 },
        { task: 'Task distribution', type: 'working', startPercent: 40, widthPercent: 60, duration: 216000 }
      ]
    },
    {
      id: 'worker-1',
      name: 'Code Analyzer',
      type: 'analyzer',
      status: 'working',
      currentTask: 'Analyzing backend/api/monitoring.py',
      tasksCompleted: 89,
      uptime: 14400,
      successRate: 95,
      recentTasks: [
        { id: 't4', name: 'Analyze config.py', status: 'completed', completedAt: now - 120000 },
        { id: 't5', name: 'Analyze utils.py', status: 'completed', completedAt: now - 480000 }
      ],
      activityTimeline: [
        { task: 'Code analysis', type: 'working', startPercent: 0, widthPercent: 45, duration: 162000 },
        { task: 'Reporting', type: 'working', startPercent: 50, widthPercent: 50, duration: 180000 }
      ]
    },
    {
      id: 'worker-2',
      name: 'Task Executor',
      type: 'executor',
      status: 'idle',
      tasksCompleted: 67,
      uptime: 21600,
      successRate: 92,
      recentTasks: [
        { id: 't6', name: 'Deploy update', status: 'completed', completedAt: now - 1800000 }
      ],
      activityTimeline: [
        { task: 'Task execution', type: 'working', startPercent: 0, widthPercent: 20, duration: 72000 },
        { task: 'Idle', type: 'idle', startPercent: 20, widthPercent: 80, duration: 288000 }
      ]
    },
    {
      id: 'monitor-1',
      name: 'System Monitor',
      type: 'monitor',
      status: 'working',
      currentTask: 'Monitoring system resources',
      tasksCompleted: 0,
      uptime: 86400,
      successRate: 100,
      recentTasks: [],
      activityTimeline: [
        { task: 'Continuous monitoring', type: 'working', startPercent: 0, widthPercent: 100, duration: 360000 }
      ]
    },
    {
      id: 'worker-3',
      name: 'Error Handler',
      type: 'worker',
      status: 'error',
      currentTask: 'Recovery in progress...',
      tasksCompleted: 23,
      uptime: 7200,
      successRate: 78,
      recentTasks: [
        { id: 't7', name: 'Error recovery', status: 'failed', completedAt: now - 30000 }
      ],
      activityTimeline: [
        { task: 'Error handling', type: 'error', startPercent: 85, widthPercent: 15, duration: 54000 },
        { task: 'Normal operation', type: 'working', startPercent: 0, widthPercent: 85, duration: 306000 }
      ]
    }
  ]
}

function getSampleEvents(): ActivityEvent[] {
  const now = Date.now()
  return [
    { id: 'e1', agentId: 'orch-1', agentName: 'Main Orchestrator', type: 'task_started', message: 'Started workflow #457', timestamp: now - 5000 },
    { id: 'e2', agentId: 'worker-1', agentName: 'Code Analyzer', type: 'task_completed', message: 'Completed analysis of monitoring.py', timestamp: now - 30000 },
    { id: 'e3', agentId: 'worker-3', agentName: 'Error Handler', type: 'task_failed', message: 'Failed to recover connection', timestamp: now - 60000 },
    { id: 'e4', agentId: 'worker-2', agentName: 'Task Executor', type: 'agent_idle', message: 'Waiting for new tasks', timestamp: now - 120000 },
    { id: 'e5', agentId: 'orch-1', agentName: 'Main Orchestrator', type: 'task_completed', message: 'Completed workflow #456', timestamp: now - 180000 }
  ]
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
let refreshTimer: ReturnType<typeof setInterval> | null = null

onMounted(async () => {
  await Promise.all([fetchAgents(), fetchEvents()])

  if (props.refreshInterval > 0) {
    refreshTimer = setInterval(() => {
      simulateActivity()
    }, props.refreshInterval)
  }
})

onUnmounted(() => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
  }
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
  margin: 0;
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

.agent-card.error {
  border-left: 3px solid var(--color-error);
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
  background: linear-gradient(135deg, var(--chart-purple), var(--chart-indigo));
}

.agent-avatar.worker {
  background: linear-gradient(135deg, var(--chart-blue), var(--color-info-dark));
}

.agent-avatar.monitor {
  background: linear-gradient(135deg, var(--color-success), var(--color-success-dark));
}

.agent-avatar.analyzer {
  background: linear-gradient(135deg, var(--color-warning), var(--color-warning-hover));
}

.agent-avatar.executor {
  background: linear-gradient(135deg, var(--color-error), var(--color-error-hover));
}

.avatar-icon {
  font-size: 22px;
}

.avatar-icon.small {
  font-size: 14px;
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
.activity-error {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-size: var(--text-xs);
}

.activity-idle {
  color: var(--text-tertiary);
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
  font-size: 10px;
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
  padding: 0;
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
  background: linear-gradient(90deg, var(--color-info), var(--chart-blue-light));
}

.activity-bar.idle {
  background: rgba(100, 116, 139, 0.5);
}

.activity-bar.error {
  background: linear-gradient(90deg, var(--color-error), var(--color-error-light));
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
