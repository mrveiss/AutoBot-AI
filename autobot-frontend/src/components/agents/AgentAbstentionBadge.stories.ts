// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Storybook Stories for AgentAbstentionBadge (GH#6626)
 *
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 */

import type { Meta } from '@storybook/vue3'
import AgentAbstentionBadge from './AgentAbstentionBadge.vue'
import type { AgentTask } from '@/types/models'

const meta: Meta<typeof AgentAbstentionBadge> = {
  title: 'Agents/AgentAbstentionBadge',
  component: AgentAbstentionBadge,
  tags: ['autodocs'],
  argTypes: {
    task: {
      description: 'Agent task object with abstention status',
      control: 'object',
    },
    label: {
      description: 'Badge label text',
      control: 'text',
    },
    showTooltip: {
      description: 'Whether to show tooltip on hover',
      control: 'boolean',
    },
  },
}

export default meta

// Sample abstained task
const abstainedTask: AgentTask = {
  id: 'task-123',
  description: 'Analyze code complexity for legacy module',
  status: 'abstained',
  priority: 'medium',
  created_at: '2025-06-01T10:00:00Z',
  completed_at: '2025-06-01T10:15:00Z',
  abstained: true,
  abstention_reason: 'confidence below 0.6 for 5 consecutive iterations',
  actual_duration: 900000,
}

export const Default = {
  args: {
    task: abstainedTask,
  },
}

export const CustomLabel = {
  args: {
    task: abstainedTask,
    label: 'Low Confidence',
  },
}

export const NoTooltip = {
  args: {
    task: abstainedTask,
    showTooltip: false,
  },
}

export const LongReason = {
  args: {
    task: {
      ...abstainedTask,
      abstention_reason:
        'Agent could not determine the correct approach after analyzing multiple possible solutions. Confidence scores remained below threshold (0.45-0.55) for 8 consecutive iterations. Requires human review.',
    },
  },
}
