// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Storybook Stories for AgentTaskDetail (GH#6626)
 *
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 */

import type { Meta } from '@storybook/vue3'
import AgentTaskDetail from './AgentTaskDetail.vue'
import type { AgentTask } from '@/types/models'

const meta: Meta<typeof AgentTaskDetail> = {
  title: 'Agents/AgentTaskDetail',
  component: AgentTaskDetail,
  tags: ['autodocs'],
  argTypes: {
    task: {
      description: 'Agent task object to display',
      control: 'object',
    },
  },
}

export default meta

// Abstained task sample
const abstainedTask: AgentTask = {
  id: 'task-abc-123',
  description: 'Analyze complex code patterns in authentication module',
  status: 'abstained',
  priority: 'high',
  created_at: '2025-06-01T09:30:00Z',
  started_at: '2025-06-01T09:30:15Z',
  completed_at: '2025-06-01T09:45:30Z',
  estimated_duration: 600000,
  actual_duration: 915000,
  abstained: true,
  abstention_reason: 'confidence below 0.6 for 5 consecutive iterations',
}

// Completed task sample
const completedTask: AgentTask = {
  id: 'task-def-456',
  description: 'Refactor user profile component',
  status: 'completed',
  priority: 'medium',
  created_at: '2025-06-01T08:00:00Z',
  started_at: '2025-06-01T08:00:10Z',
  completed_at: '2025-06-01T08:25:45Z',
  estimated_duration: 1200000,
  actual_duration: 1535000,
  result: {
    files_modified: 3,
    lines_changed: 127,
    tests_passed: 15,
  },
}

// Failed task sample
const failedTask: AgentTask = {
  id: 'task-ghi-789',
  description: 'Deploy microservice to production',
  status: 'failed',
  priority: 'urgent',
  created_at: '2025-06-01T10:00:00Z',
  started_at: '2025-06-01T10:00:05Z',
  completed_at: '2025-06-01T10:03:22Z',
  estimated_duration: 300000,
  actual_duration: 197000,
  error_message: 'Connection timeout: could not reach deployment target at 10.0.1.50:8080',
}

export const Abstained = {
  args: {
    task: abstainedTask,
  },
}

export const Completed = {
  args: {
    task: completedTask,
  },
}

export const Failed = {
  args: {
    task: failedTask,
  },
}

export const Running = {
  args: {
    task: {
      id: 'task-jkl-012',
      description: 'Running batch data analysis',
      status: 'running' as const,
      priority: 'low' as const,
      created_at: '2025-06-01T11:00:00Z',
      started_at: '2025-06-01T11:00:08Z',
      estimated_duration: 1800000,
    },
  },
}

export const AbstainedWithLongReason = {
  args: {
    task: {
      ...abstainedTask,
      abstention_reason:
        'Agent attempted multiple approaches (pattern matching, AST analysis, heuristic detection) but could not achieve confidence threshold of 0.7. Maximum confidence reached was 0.58 after 12 iterations. Suggests manual code review or domain expert consultation.',
    },
  },
}
