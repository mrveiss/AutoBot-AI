// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import type { Meta } from '@storybook/vue3'
import NodeHealthCard from './NodeHealthCard.vue'

const meta = {
  title: 'Orchestration/NodeHealthCard',
  component: NodeHealthCard,
  tags: ['autodocs'],
  argTypes: {
    status: {
      control: { type: 'select' },
      options: ['healthy', 'degraded', 'unhealthy', 'offline', 'online'],
    },
    isExpanded: { control: 'boolean' },
    showExpandIcon: { control: 'boolean' },
    showRestartButton: { control: 'boolean' },
    isRestartingAll: { control: 'boolean' },
  },
} satisfies Meta<typeof NodeHealthCard>

export default meta

export const Healthy = {
  args: {
    nodeId: 'node-prod-01',
    hostname: 'prod-01.autobot.internal',
    ipAddress: '192.168.1.10',
    status: 'healthy',
    runningCount: 12,
    stoppedCount: 0,
    failedCount: 0,
    totalServices: 12,
    isExpanded: false,
    showExpandIcon: true,
    showRestartButton: false,
    isRestartingAll: false,
    restartProgress: null,
  },
}

export const Degraded = {
  args: {
    nodeId: 'node-prod-02',
    hostname: 'prod-02.autobot.internal',
    ipAddress: '192.168.1.11',
    status: 'degraded',
    runningCount: 9,
    stoppedCount: 2,
    failedCount: 1,
    totalServices: 12,
    isExpanded: false,
    showExpandIcon: true,
    showRestartButton: true,
    isRestartingAll: false,
    restartProgress: null,
  },
}

export const Restarting = {
  args: {
    nodeId: 'node-prod-03',
    hostname: 'prod-03.autobot.internal',
    ipAddress: '192.168.1.12',
    status: 'healthy',
    runningCount: 12,
    stoppedCount: 0,
    failedCount: 0,
    totalServices: 12,
    isExpanded: true,
    showExpandIcon: true,
    showRestartButton: true,
    isRestartingAll: true,
    restartProgress: { total: 12, completed: 7 },
  },
}
