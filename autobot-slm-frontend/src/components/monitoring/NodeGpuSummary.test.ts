// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * A node's GPU row never renders an unmeasured GPU as a measured zero (#15226).
 */

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import NodeGpuSummary from './NodeGpuSummary.vue'
import en from '@/locales/en.json'
import type { GPUNodeStatus } from '@/types/slm'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

const RTX = {
  device_type: 'nvidia-gpu',
  index: 0,
  name: 'NVIDIA GeForce RTX 4070 Laptop GPU',
  monitored: true,
  utilization_percent: 12,
  memory_used_mb: 2048,
  memory_total_mb: 8192,
  temperature_celsius: 51,
  power_watts: null,
} as const

function node(state: GPUNodeStatus['state'], devices: GPUNodeStatus['devices'] = []): GPUNodeStatus {
  return { node_id: 'n1', hostname: 'worker-1', node_status: 'online', state, devices, last_heartbeat: null }
}

function text(props: { status?: GPUNodeStatus; unavailable?: boolean }): string {
  return mount(NodeGpuSummary, { props, global: { plugins: [i18n] } }).get('[data-testid="node-gpu-summary"]').text()
}

describe('NodeGpuSummary (#15226)', () => {
  it('says an agent that predates GPU telemetry has not reported', () => {
    expect(text({ status: node('not_reported') })).toBe(en.monitoring.systemMonitor.gpuNotReported)
    expect(text({})).toBe(en.monitoring.systemMonitor.gpuNotReported)
  })

  it('says none when the agent probed and found no GPU', () => {
    expect(text({ status: node('none') })).toBe(en.monitoring.systemMonitor.gpuNone)
  })

  it('shows a card its tool could not read as present but unmonitored, not as 0%', () => {
    const rendered = text({ status: node('present', [{ ...RTX, monitored: false, utilization_percent: null }]) })

    expect(rendered).toContain('1')
    expect(rendered).not.toContain('0%')
  })

  it('shows the measured GPU with its utilisation and VRAM', () => {
    const rendered = text({ status: node('present', [RTX]) })

    expect(rendered).toContain('NVIDIA GeForce RTX 4070 Laptop GPU')
    expect(rendered).toContain('12%')
    expect(rendered).toContain('2.0 / 8.0')
  })

  it('marks an unreadable utilisation as unreadable rather than zero', () => {
    const rendered = text({ status: node('present', [{ ...RTX, utilization_percent: null }]) })

    expect(rendered).toContain(en.monitoring.systemMonitor.gpuUnreadable)
    expect(rendered).not.toContain('0%')
  })

  it('counts the GPUs beyond the first', () => {
    expect(text({ status: node('present', [RTX, { ...RTX, index: 1 }]) })).toContain('+1')
  })

  it('says unavailable when the fleet GPU read failed, whatever the node last said', () => {
    expect(text({ status: node('present', [RTX]), unavailable: true })).toBe(
      en.monitoring.systemMonitor.gpuUnavailable,
    )
  })
})
