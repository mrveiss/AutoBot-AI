// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #19938: the "Plan before building" quick action opens the Org Chart in planner mode with the
// workflow_area entry point, and renders nothing where there is no company to open it for.

import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const push = vi.fn()
let params: Record<string, unknown> = {}

vi.mock('vue-router', () => ({
  useRoute: () => ({ params }),
  useRouter: () => ({ push }),
}))

import PlanBeforeBuildingAction from '../PlanBeforeBuildingAction.vue'

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })
const mountAction = () => mount(PlanBeforeBuildingAction, { global: { plugins: [i18n], stubs: { Icon: true } } })

describe('PlanBeforeBuildingAction', () => {
  it('opens the company org chart in planner mode with the workflow_area entry point', async () => {
    params = { companyId: 'c1' }
    const w = mountAction()
    expect(w.text()).toContain(en.workflow.views.planBeforeBuilding)
    await w.find('[data-testid="plan-before-building"]').trigger('click')
    expect(push).toHaveBeenCalledWith({
      path: '/llc/companies/c1/org-chart',
      query: { view: 'planner', entry_point: 'workflow_area' },
    })
  })

  it('renders nothing outside a company', () => {
    params = {}
    expect(mountAction().find('[data-testid="plan-before-building"]').exists()).toBe(false)
  })
})
