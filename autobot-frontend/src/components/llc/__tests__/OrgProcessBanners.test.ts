// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// #21242: an empty process canvas says which of three different things it is.

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import OrgProcessBanners from '../OrgProcessBanners.vue'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

type Props = InstanceType<typeof OrgProcessBanners>['$props']
const base: Props = { failed: false, attempted: true, nodeCount: 0, workflowsState: 'ready', workflowCount: 2 }
const render = (over: Partial<Props>) => mount(OrgProcessBanners, { props: { ...base, ...over }, global: { plugins: [i18n] } })

describe('OrgProcessBanners (#21242)', () => {
  it('says the process information is unavailable when the fetch failed, whatever else is known', () => {
    const w = render({ failed: true, workflowCount: 0 })

    expect(w.get('[data-testid="canvas-processes-unavailable"]').text()).toBe(en.llc.orgChart.processNodesUnavailable)
    expect(w.get('[data-testid="canvas-processes-unavailable"]').attributes('role')).toBe('alert')
    expect(w.findAll('p')).toHaveLength(1)
  })

  it('says nothing is attached when workflows exist but no role runs one', () => {
    const w = render({})

    expect(w.get('[data-testid="canvas-processes-noneAttached"]').text()).toBe(en.llc.orgChart.processNoneAttached)
    expect(w.find('[data-testid="canvas-processes-unavailable"]').exists()).toBe(false)
  })

  it('says there is nothing to attach when the company has no workflows', () => {
    const w = render({ workflowCount: 0 })

    expect(w.get('[data-testid="canvas-processes-nothingAttachable"]').text()).toBe(en.llc.orgChart.processNothingAttachable)
    expect(w.find('[data-testid="canvas-processes-noneAttached"]').exists()).toBe(false)
  })

  it('says nothing before the request was tried, or once there are process nodes', () => {
    expect(render({ attempted: false }).find('p').exists()).toBe(false)
    expect(render({ nodeCount: 3 }).find('p').exists()).toBe(false)
  })

  it('does not tell the two empties apart while the workflows list is unknown', () => {
    expect(render({ workflowsState: 'loading', workflowCount: 0 }).find('p').exists()).toBe(false)
    expect(render({ workflowsState: 'failed', workflowCount: 0 }).find('p').exists()).toBe(false)
  })
})
