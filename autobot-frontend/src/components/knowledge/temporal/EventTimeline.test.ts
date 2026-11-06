// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * EventTimeline time text: timestamp, else temporal_expression, else the
 * i18n unknown-time string.
 */

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import EventTimeline from './EventTimeline.vue'
import { formatISOString } from '@/utils/formatHelpers'
import en from '@/i18n/locales/en.json'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

function mountTimeline(timestamp: string | null, temporal_expression: string | null) {
  return mount(EventTimeline, {
    props: {
      loading: false,
      events: [
        {
          id: 'e1',
          name: 'Event',
          description: '',
          event_type: 'general',
          timestamp,
          temporal_expression,
          participants: [],
          entity_name: '',
          causal_links: [],
        },
      ],
    },
    global: { plugins: [i18n], stubs: { Icon: true, CausalChainViewer: true } },
  })
}

function timeText(timestamp: string | null, temporal_expression: string | null): string {
  return mountTimeline(timestamp, temporal_expression).find('.event-time').text()
}

function markerText(timestamp: string | null, temporal_expression: string | null): string {
  return mountTimeline(timestamp, temporal_expression).find('.date-marker').text()
}

describe('EventTimeline time text', () => {
  it('shows the formatted timestamp when it parses', () => {
    const ts = '2025-03-04T05:06:07Z'
    expect(timeText(ts, 'last spring')).toBe(formatISOString(ts))
  })

  it.each([null, 'not-a-date'])('falls back to temporal_expression for timestamp %s', (ts) => {
    expect(timeText(ts, 'last spring')).toBe('last spring')
  })

  it('falls back to the unknown-time text when there is no expression either', () => {
    expect(timeText('not-a-date', null)).toBe(en.knowledge.temporal.events.unknownTime)
    expect(timeText(null, null)).toBe(en.knowledge.temporal.events.unknownTime)
  })
})

describe('EventTimeline day heading', () => {
  it('shows the formatted day when the timestamp parses', () => {
    expect(markerText('2025-03-04T05:06:07Z', 'last spring')).toContain('2025')
  })

  it.each([null, 'not-a-date'])('falls back to temporal_expression for timestamp %s', (ts) => {
    expect(markerText(ts, 'last spring')).toBe('last spring')
  })

  it('is blank rather than the raw text when nothing else is available', () => {
    expect(markerText('not-a-date', null)).toBe('')
  })
})
