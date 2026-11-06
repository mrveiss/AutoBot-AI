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

function timeText(timestamp: string | null, temporal_expression: string | null): string {
  const wrapper = mount(EventTimeline, {
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
  return wrapper.find('.event-time').text()
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
