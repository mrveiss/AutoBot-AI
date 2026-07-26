// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
import { describe, it, expect } from 'vitest'
import {
  formatCategoryName,
  formatFileSize,
  formatBytes,
  formatUptime,
  formatDuration
} from '@/utils/formatHelpers'

describe('formatCategoryName', () => {
  it('title-cases underscore/hyphen separated categories', () => {
    expect(formatCategoryName('system_commands')).toBe('System Commands')
    expect(formatCategoryName('auto-bot-docs')).toBe('Auto Bot Docs')
  })

  it('returns empty string for falsy input', () => {
    expect(formatCategoryName('')).toBe('')
    expect(formatCategoryName(undefined as unknown as string)).toBe('')
    expect(formatCategoryName(null as unknown as string)).toBe('')
  })

  // #10208: backend-sourced category values aren't guaranteed strings at
  // runtime; the formatter must coerce, not throw "split is not a function".
  it('does not throw on non-string input (coerces via String)', () => {
    expect(() => formatCategoryName(42 as unknown as string)).not.toThrow()
    expect(formatCategoryName(42 as unknown as string)).toBe('42')
    expect(() => formatCategoryName({ a: 1 } as unknown as string)).not.toThrow()
    expect(() => formatCategoryName(['x', 'y'] as unknown as string)).not.toThrow()
  })
})

// ---------------------------------------------------------------------------
// #12737 fork-convergence: each converged call site must keep byte-for-byte
// output. Below, the ORIGINAL local implementation is inlined and asserted
// equal to the parameterized canonical helper across representative values.
// ---------------------------------------------------------------------------

const BYTE_SAMPLES = [0, 1, 512, 1023, 1024, 1536, 1048576, 1500000, 5242880, 1.5e12]
const SECOND_SAMPLES = [0, 0.5, 1, 30, 59, 59.9, 60, 90.5, 125, 3599, 3661, 90061]
const MS_SAMPLES = [0, 1, 500, 999, 1000, 1500, 59999, 60000, 90000, 3600000, 5400000]

describe('formatFileSize / formatBytes canonical default', () => {
  it('renders the documented ladder', () => {
    expect(formatFileSize(0)).toBe('0 Bytes')
    expect(formatFileSize(1023)).toBe('1023 Bytes')
    expect(formatFileSize(1024)).toBe('1 KB')
    expect(formatFileSize(1536)).toBe('1.5 KB')
    expect(formatFileSize(1048576)).toBe('1 MB')
    expect(formatFileSize(1.5e12)).toBe('1.36 TB')
  })

  it('formatBytes is an alias', () => {
    expect(formatBytes(1536)).toBe('1.5 KB')
  })

  // useConversationFiles.ts original (parseFloat, 2 decimals, Bytes ladder)
  it('matches useConversationFiles original output', () => {
    const original = (bytes: number): string => {
      if (bytes === 0) return '0 Bytes'
      const k = 1024
      const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB']
      const i = Math.floor(Math.log(bytes) / Math.log(k))
      return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`
    }
    for (const v of BYTE_SAMPLES.filter((b) => b < 1024 ** 5)) {
      expect(formatFileSize(v)).toBe(original(v))
    }
  })
})

describe('formatBytes options — slm B ladder (BackupsView / CacheSettings)', () => {
  it('matches BackupsView original (B..TB)', () => {
    const original = (bytes: number): string => {
      if (bytes === 0) return '0 B'
      const k = 1024
      const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
      const i = Math.floor(Math.log(bytes) / Math.log(k))
      return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
    }
    const opts = { units: ['B', 'KB', 'MB', 'GB', 'TB'], zeroText: '0 B' }
    for (const v of [0, 1, 512, 1024, 1536, 1048576, 1500000]) {
      expect(formatBytes(v, opts)).toBe(original(v))
    }
  })

  it('matches CacheSettings original (B..GB)', () => {
    const original = (bytes: number): string => {
      if (bytes === 0) return '0 B'
      const k = 1024
      const sizes = ['B', 'KB', 'MB', 'GB']
      const i = Math.floor(Math.log(bytes) / Math.log(k))
      return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
    }
    const opts = { units: ['B', 'KB', 'MB', 'GB'], zeroText: '0 B' }
    for (const v of [0, 1, 512, 1024, 1536, 1048576, 1500000]) {
      expect(formatBytes(v, opts)).toBe(original(v))
    }
  })
})

describe('formatBytes options — manual B/KB/MB (Vision/Video/Redis group C)', () => {
  const opts = {
    units: ['B', 'KB', 'MB'],
    decimals: 1,
    keepTrailingZeros: true,
    integerBase: true
  }
  it('matches the manual <1024/<1MB/else original', () => {
    const original = (bytes: number): string => {
      if (bytes < 1024) return bytes + ' B'
      if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
      return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
    }
    for (const v of BYTE_SAMPLES.filter((b) => b > 0 && b < 1024 ** 4)) {
      expect(formatBytes(v, opts)).toBe(original(v))
    }
    expect(formatBytes(0, opts)).toBe('0 B')
  })

  it('supports nullText for the Redis panel variant', () => {
    expect(formatBytes(null, { ...opts, nullText: '-' })).toBe('-')
    expect(formatBytes(1024, { ...opts, nullText: '-' })).toBe('1.0 KB')
  })
})

describe('formatUptime', () => {
  // AdvancedControlView / AdminMonitoringView / NPUPerformanceMetrics (d h / h m / m)
  it('matches the d/h/m ladder original', () => {
    const original = (seconds: number): string => {
      const days = Math.floor(seconds / 86400)
      const hours = Math.floor((seconds % 86400) / 3600)
      const minutes = Math.floor((seconds % 3600) / 60)
      if (days > 0) return `${days}d ${hours}h`
      if (hours > 0) return `${hours}h ${minutes}m`
      return `${minutes}m`
    }
    for (const v of [0, 59, 60, 3599, 3661, 86400, 90061, 172800]) {
      expect(formatUptime(v)).toBe(original(v))
    }
  })

  it('returns nullText for nullish / negative / NaN', () => {
    expect(formatUptime(null)).toBe('—')
    expect(formatUptime(undefined)).toBe('—')
    expect(formatUptime(-5)).toBe('—')
    expect(formatUptime(NaN)).toBe('—')
  })

  // RedisServiceControl (3-part days line + !seconds -> 'N/A')
  it('matches RedisServiceControl original with options', () => {
    const original = (seconds: number): string => {
      if (!seconds) return 'N/A'
      const days = Math.floor(seconds / 86400)
      const hours = Math.floor((seconds % 86400) / 3600)
      const minutes = Math.floor((seconds % 3600) / 60)
      if (days > 0) return `${days}d ${hours}h ${minutes}m`
      if (hours > 0) return `${hours}h ${minutes}m`
      return `${minutes}m`
    }
    const opts = { nullText: 'N/A', zeroText: 'N/A', daysIncludeMinutes: true }
    for (const v of [0, 59, 60, 3599, 3661, 90061, 172800]) {
      expect(formatUptime(v, opts)).toBe(original(v))
    }
    expect(formatUptime(null, opts)).toBe('N/A')
  })
})

describe('formatDuration — range form (unchanged)', () => {
  it('renders the legacy range ladder', () => {
    expect(formatDuration('2025-01-01T00:00:00Z', '2025-01-01T00:01:30Z')).toBe('1m 30s')
    expect(formatDuration(null, null)).toBe('-')
    expect(formatDuration('2025-01-01T00:00:00Z', '2025-01-01T00:00:00.500Z')).toBe('500ms')
    expect(formatDuration('2025-01-01T00:00:00Z', '2025-01-01T02:05:00Z')).toBe('2h 5m')
  })
})

describe('formatDuration — msSeconds2dp (Analytics / Tracing / PerformanceOverview)', () => {
  it('matches Tracing/PerformanceOverview original', () => {
    const original = (ms: number): string => {
      if (ms < 1000) return `${ms.toFixed(0)}ms`
      return `${(ms / 1000).toFixed(2)}s`
    }
    for (const v of MS_SAMPLES) {
      expect(formatDuration(v, { style: 'msSeconds2dp' })).toBe(original(v))
    }
  })

  it('matches AdvancedAnalytics original (nullText 0ms guard)', () => {
    const original = (ms: number | undefined | null): string => {
      if (!ms) return '0ms'
      if (ms < 1000) return `${ms.toFixed(0)}ms`
      return `${(ms / 1000).toFixed(2)}s`
    }
    const opts = { style: 'msSeconds2dp' as const, nullText: '0ms' }
    for (const v of MS_SAMPLES) {
      expect(formatDuration(v, opts)).toBe(original(v))
    }
    expect(formatDuration(undefined, opts)).toBe(original(undefined))
    expect(formatDuration(null, opts)).toBe(original(null))
  })
})

describe('formatDuration — secondsCompact (AgentObservability / OverseerStep)', () => {
  it('matches OverseerStepMessage original', () => {
    const original = (seconds: number): string => {
      if (seconds < 1) return `${Math.round(seconds * 1000)}ms`
      if (seconds < 60) return `${seconds.toFixed(1)}s`
      const mins = Math.floor(seconds / 60)
      const secs = Math.round(seconds % 60)
      return `${mins}m ${secs}s`
    }
    for (const v of SECOND_SAMPLES) {
      expect(formatDuration(v, { style: 'secondsCompact' })).toBe(original(v))
    }
  })

  it('matches AgentObservabilityPanel original (zeroText --)', () => {
    const original = (seconds: number): string => {
      if (seconds === 0) return '--'
      if (seconds < 1) return `${Math.round(seconds * 1000)}ms`
      if (seconds < 60) return `${seconds.toFixed(1)}s`
      const min = Math.floor(seconds / 60)
      return `${min}m ${Math.round(seconds % 60)}s`
    }
    const opts = { style: 'secondsCompact' as const, zeroText: '--' }
    for (const v of SECOND_SAMPLES) {
      expect(formatDuration(v, opts)).toBe(original(v))
    }
  })
})

describe('formatDuration — clock M:SS (ProjectDetailView / VideoProcessor)', () => {
  it('matches ProjectDetailView original (round + nullText)', () => {
    const original = (seconds: number | null): string => {
      if (seconds === null || Number.isNaN(seconds)) return '—'
      const total = Math.round(seconds)
      const mins = Math.floor(total / 60)
      const secs = total % 60
      return `${mins}:${secs.toString().padStart(2, '0')}`
    }
    const opts = { style: 'clock' as const, nullText: '—' }
    for (const v of SECOND_SAMPLES) {
      expect(formatDuration(v, opts)).toBe(original(v))
    }
    expect(formatDuration(null, opts)).toBe(original(null))
  })

  it('matches VideoProcessor original (floor)', () => {
    const original = (seconds: number): string => {
      const mins = Math.floor(seconds / 60)
      const secs = Math.floor(seconds % 60)
      return `${mins}:${secs.toString().padStart(2, '0')}`
    }
    const opts = { style: 'clock' as const, rounding: 'floor' as const }
    for (const v of SECOND_SAMPLES) {
      expect(formatDuration(v, opts)).toBe(original(v))
    }
  })
})

describe('formatDuration — msMinutes (WorkflowVisualization / AgentActivity)', () => {
  it('matches WorkflowVisualization original (round minutes)', () => {
    const original = (ms: number): string => {
      if (ms < 1000) return `${ms}ms`
      if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
      return `${Math.round(ms / 60000)}m`
    }
    for (const v of MS_SAMPLES) {
      expect(formatDuration(v, { style: 'msMinutes' })).toBe(original(v))
    }
  })

  it('matches AgentActivityVisualization original (floor minutes)', () => {
    const original = (ms: number): string => {
      if (ms < 1000) return `${ms}ms`
      if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
      return `${Math.floor(ms / 60000)}m`
    }
    const opts = { style: 'msMinutes' as const, rounding: 'floor' as const }
    for (const v of MS_SAMPLES) {
      expect(formatDuration(v, opts)).toBe(original(v))
    }
  })
})
