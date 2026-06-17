// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Composable: useAgentActivityData
 *
 * Encapsulates all backend fetch logic for the AgentActivityVisualization
 * component (#6079).
 *
 * Responsibilities:
 *  - Fetch `/agents/status` via fetchWithAuth → populate `agents`
 *  - Fetch `/analytics/agents/tasks/recent` via fetchWithAuth → populate `recentEvents`
 *  - Fall back to generated sample data when either API is unavailable
 *  - Expose `agents`, `recentEvents`, `fetchAgents`, `fetchEvents`, and `refresh`
 *    so the component owns zero fetching logic
 */

import { ref } from 'vue'
import apiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'
import { getApiBase } from '@/config/ssot-config'

const logger = createLogger('useAgentActivityData')

// ── Shared Types ─────────────────────────────────────────────────────────────

export interface Agent {
  id: string
  name: string
  type: 'orchestrator' | 'worker' | 'monitor' | 'analyzer' | 'executor'
  // #9724: 'abstained' added — AgentActivityVisualization renders this state
  status: 'working' | 'idle' | 'error' | 'paused' | 'abstained'
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

export interface ActivityEvent {
  id: string
  agentId: string
  agentName: string
  type: 'task_started' | 'task_completed' | 'task_failed' | 'agent_idle' | 'agent_error'
  message: string
  timestamp: number
}

// ── Sample-data helpers ───────────────────────────────────────────────────────

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

// ── Composable ────────────────────────────────────────────────────────────────

export function useAgentActivityData() {
  const agents = ref<Agent[]>([])
  const recentEvents = ref<ActivityEvent[]>([])

  async function fetchAgents(): Promise<void> {
    try {
      const data = await apiClient.get<{ agents?: Agent[] }>(`${getApiBase()}/agents/status`)
      if (data.agents) {
        agents.value = data.agents
        return
      }
    } catch {
      logger.warn('Failed to fetch agents, using sample data')
    }

    agents.value = getSampleAgents()
  }

  async function fetchEvents(): Promise<void> {
    try {
      // Issue #552: Fixed path - backend uses /api/analytics/agents/tasks/recent
      // (analytics_agents.py has prefix="/agents" and is included into analytics.py router)
      const data = await apiClient.get<{ tasks?: unknown[]; data?: { tasks?: unknown[] } }>(
        `${getApiBase()}/analytics/agents/tasks/recent?limit=10`
      )
      // Backend returns tasks, not events - adapt response structure
      if (data.tasks || data.data?.tasks) {
        type RawTask = { id?: string; task_id?: string; status?: string; agent_id?: string; completed_at?: string; started_at?: string; details?: string; description?: string }
        const tasks = (data.tasks || data.data?.tasks) as RawTask[]
        recentEvents.value = tasks.map((task: RawTask) => ({
          id: task.id || task.task_id || crypto.randomUUID(),
          type: (task.status === 'completed' ? 'task_completed' : 'task_started') as ActivityEvent['type'],
          agentId: task.agent_id ?? '',
          agentName: task.agent_id ?? '',
          message: task.details || task.description || '',
          timestamp: task.completed_at
            ? new Date(task.completed_at).getTime()
            : task.started_at
              ? new Date(task.started_at).getTime()
              : Date.now()
        }))
        return
      }
    } catch {
      logger.warn('Failed to fetch events, using sample data')
    }

    recentEvents.value = getSampleEvents()
  }

  async function refresh(): Promise<void> {
    await Promise.all([fetchAgents(), fetchEvents()])
  }

  return {
    agents,
    recentEvents,
    fetchAgents,
    fetchEvents,
    refresh
  }
}
