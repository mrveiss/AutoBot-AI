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
    // Issue #552: Fixed path - backend uses /api/agents/tasks/recent
    const response = await fetch('/api/agents/tasks/recent?limit=10')
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
  refresh: () => Promise.all([fetchAgents(), fetchEvents()])
})
</script>

<style scoped>
.agent-activity-viz {
  background: rgba(30, 41, 59, 0.5);
  border-radius: 12px;
  padding: 20px;
  border: 1px solid rgba(71, 85, 105, 0.5);
}

.viz-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid rgba(71, 85, 105, 0.5);
}

.viz-header h3 {
  font-size: 18px;
  font-weight: 600;
  color: #e2e8f0;
  margin: 0;
}

.header-controls {
  display: flex;
  gap: 16px;
  align-items: center;
}

.view-toggle {
  display: flex;
  background: rgba(51, 65, 85, 0.5);
  border-radius: 6px;
  overflow: hidden;
}

.view-toggle button {
  padding: 8px 12px;
  background: transparent;
  border: none;
  color: #64748b;
  cursor: pointer;
  transition: all 0.2s;
}

.view-toggle button:hover {
  color: #94a3b8;
}

.view-toggle button.active {
  background: #3b82f6;
  color: white;
}

.status-summary {
  display: flex;
  align-items: center;
  gap: 8px;
}

.active-count {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #10b981;
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
  gap: 16px;
  margin-bottom: 24px;
}

.agent-card {
  background: rgba(15, 23, 42, 0.5);
  border-radius: 12px;
  padding: 16px;
  border: 1px solid rgba(71, 85, 105, 0.3);
  cursor: pointer;
  transition: all 0.2s;
}

.agent-card:hover {
  border-color: rgba(59, 130, 246, 0.5);
  transform: translateY(-2px);
}

.agent-card.working {
  border-left: 3px solid #3b82f6;
}

.agent-card.idle {
  border-left: 3px solid #64748b;
}

.agent-card.error {
  border-left: 3px solid #ef4444;
}

.agent-card.paused {
  border-left: 3px solid #f59e0b;
}

.agent-avatar {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  margin-bottom: 12px;
}

.agent-avatar.orchestrator {
  background: linear-gradient(135deg, #8b5cf6, #6366f1);
}

.agent-avatar.worker {
  background: linear-gradient(135deg, #3b82f6, #2563eb);
}

.agent-avatar.monitor {
  background: linear-gradient(135deg, #10b981, #059669);
}

.agent-avatar.analyzer {
  background: linear-gradient(135deg, #f59e0b, #d97706);
}

.agent-avatar.executor {
  background: linear-gradient(135deg, #ef4444, #dc2626);
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
  border-radius: 50%;
  border: 2px solid #0f172a;
}

.status-ring.working {
  background: #3b82f6;
  animation: blink 1s infinite;
}

.status-ring.idle {
  background: #64748b;
}

.status-ring.error {
  background: #ef4444;
}

.status-ring.paused {
  background: #f59e0b;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.agent-info {
  margin-bottom: 12px;
}

.agent-name {
  font-size: 14px;
  font-weight: 600;
  color: #e2e8f0;
  margin: 0 0 4px 0;
}

.agent-type {
  font-size: 11px;
  color: #64748b;
}

.current-activity {
  padding: 8px 12px;
  background: rgba(51, 65, 85, 0.3);
  border-radius: 6px;
  margin-bottom: 12px;
}

.activity-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
}

.activity-pulse {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #3b82f6;
  animation: pulse 1.5s infinite;
}

.activity-text {
  font-size: 12px;
  color: #94a3b8;
}

.activity-idle,
.activity-error {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.activity-idle {
  color: #64748b;
}

.activity-error {
  color: #f87171;
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
  font-size: 16px;
  font-weight: 600;
  color: #e2e8f0;
}

.metric-label {
  font-size: 10px;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

/* Expanded Details */
.expanded-details {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid rgba(71, 85, 105, 0.3);
}

.detail-section h5 {
  font-size: 12px;
  font-weight: 600;
  color: #94a3b8;
  margin: 0 0 8px 0;
}

.task-list {
  list-style: none;
  padding: 0;
  margin: 0 0 12px 0;
}

.task-list li {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 8px;
  background: rgba(51, 65, 85, 0.3);
  border-radius: 4px;
  margin-bottom: 4px;
  font-size: 11px;
}

.task-list li.completed {
  border-left: 2px solid #10b981;
}

.task-list li.failed {
  border-left: 2px solid #ef4444;
}

.task-name {
  color: #e2e8f0;
}

.task-time {
  color: #64748b;
}

.detail-actions {
  display: flex;
  gap: 8px;
}

.action-btn {
  flex: 1;
  padding: 8px;
  background: rgba(59, 130, 246, 0.2);
  border: 1px solid rgba(59, 130, 246, 0.3);
  border-radius: 6px;
  color: #60a5fa;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
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
  margin-bottom: 24px;
}

.timeline-header {
  margin-bottom: 8px;
}

.time-labels {
  display: flex;
  justify-content: space-between;
  padding-left: 140px;
}

.time-label {
  font-size: 11px;
  color: #64748b;
}

.timeline-content {
  display: flex;
  flex-direction: column;
  gap: 8px;
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
  gap: 8px;
  padding-right: 10px;
}

.agent-label .name {
  font-size: 12px;
  color: #e2e8f0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.activity-bars {
  flex: 1;
  height: 24px;
  background: rgba(51, 65, 85, 0.3);
  border-radius: 4px;
  position: relative;
  overflow: hidden;
}

.activity-bar {
  position: absolute;
  height: 100%;
  border-radius: 3px;
  transition: all 0.3s;
}

.activity-bar.working {
  background: linear-gradient(90deg, #3b82f6, #60a5fa);
}

.activity-bar.idle {
  background: rgba(100, 116, 139, 0.5);
}

.activity-bar.error {
  background: linear-gradient(90deg, #ef4444, #f87171);
}

/* Activity Feed */
.activity-feed {
  background: rgba(15, 23, 42, 0.5);
  border-radius: 8px;
  padding: 16px;
}

.activity-feed h4 {
  font-size: 14px;
  font-weight: 600;
  color: #e2e8f0;
  margin: 0 0 12px 0;
  display: flex;
  align-items: center;
  gap: 8px;
}

.activity-feed h4 i {
  color: #f59e0b;
}

.feed-items {
  max-height: 200px;
  overflow-y: auto;
}

.feed-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px;
  background: rgba(51, 65, 85, 0.3);
  border-radius: 6px;
  margin-bottom: 6px;
  font-size: 12px;
}

.event-icon {
  flex-shrink: 0;
}

.event-agent {
  color: #60a5fa;
  font-weight: 500;
  flex-shrink: 0;
}

.event-message {
  color: #94a3b8;
  flex: 1;
}

.event-time {
  color: #64748b;
  font-size: 11px;
  flex-shrink: 0;
}

/* Transitions */
.expand-enter-active,
.expand-leave-active {
  transition: all 0.3s ease;
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
  transition: all 0.3s ease;
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
    gap: 12px;
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
    gap: 4px;
  }

  .agent-label {
    width: 100%;
    padding-bottom: 4px;
  }

  .activity-bars {
    width: 100%;
    height: 20px;
  }
}
</style>
