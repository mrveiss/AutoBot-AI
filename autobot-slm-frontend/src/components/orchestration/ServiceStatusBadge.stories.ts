// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import type { Meta } from '@storybook/vue3'
import ServiceStatusBadge from './ServiceStatusBadge.vue'

const meta = {
  title: 'Orchestration/ServiceStatusBadge',
  component: ServiceStatusBadge,
  tags: ['autodocs'],
  argTypes: {
    status: { control: 'text' },
    size: { control: { type: 'select' }, options: ['sm', 'md', 'lg'] },
    showText: { control: 'boolean' },
  },
} satisfies Meta<typeof ServiceStatusBadge>

export default meta

export const Running = {
  args: { status: 'running', size: 'md', showText: true },
}

export const Failed = {
  args: { status: 'failed', size: 'md', showText: true },
}

export const Stopped = {
  args: { status: 'stopped', size: 'md', showText: true },
}

export const SmallDotOnly = {
  args: { status: 'active', size: 'sm', showText: false },
}

export const LargeWithText = {
  args: { status: 'healthy', size: 'lg', showText: true },
}
