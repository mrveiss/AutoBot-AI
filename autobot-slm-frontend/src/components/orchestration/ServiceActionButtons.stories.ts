// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

import type { Meta } from '@storybook/vue3'
import ServiceActionButtons from './ServiceActionButtons.vue'

const meta = {
  title: 'Orchestration/ServiceActionButtons',
  component: ServiceActionButtons,
  tags: ['autodocs'],
  argTypes: {
    status: {
      control: { type: 'select' },
      options: ['running', 'stopped', 'failed', 'unknown'],
    },
    size: { control: { type: 'select' }, options: ['sm', 'md'] },
    isActionInProgress: { control: 'boolean' },
  },
} satisfies Meta<typeof ServiceActionButtons>

export default meta

export const Running = {
  args: {
    serviceName: 'autobot-backend',
    nodeId: 'node-01',
    status: 'running',
    isActionInProgress: false,
    activeAction: null,
    size: 'md',
  },
}

export const Stopped = {
  args: {
    serviceName: 'autobot-backend',
    nodeId: 'node-01',
    status: 'stopped',
    isActionInProgress: false,
    activeAction: null,
    size: 'md',
  },
}

export const ActionInProgress = {
  args: {
    serviceName: 'autobot-backend',
    nodeId: 'node-01',
    status: 'running',
    isActionInProgress: true,
    activeAction: { nodeId: 'node-01', serviceName: 'autobot-backend', action: 'restart' },
    size: 'md',
  },
}

export const Small = {
  args: {
    serviceName: 'redis',
    nodeId: 'node-02',
    status: 'running',
    isActionInProgress: false,
    activeAction: null,
    size: 'sm',
  },
}
