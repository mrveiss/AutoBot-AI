// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// Regression test for #11980: the Audit Log tab panel must render at the
// page level (gated by activeTab === 'audit'), NOT nested under the
// plugin-detail overlay's v-if="selectedPlugin". Previously the audit panel
// lived inside <BaseModal> so it only appeared while a plugin detail was open,
// which is impossible from the audit tab — the tab rendered empty.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { ref } from 'vue'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

// ---------------------------------------------------------------------------
// Module mocks
// ---------------------------------------------------------------------------

vi.mock('vue-router', () => ({
  useRoute: () => ({ path: '/plugins' }),
}))

vi.mock('@/composables/usePlugins', () => ({
  usePlugins: () => ({
    plugins: ref([]),
    discovered: ref([]),
    loading: ref(false),
    error: ref(null),
    listPlugins: vi.fn().mockResolvedValue(undefined),
    discoverPlugins: vi.fn().mockResolvedValue(undefined),
    loadPlugin: vi.fn(),
    unloadPlugin: vi.fn(),
    reloadPlugin: vi.fn(),
    enablePlugin: vi.fn(),
    disablePlugin: vi.fn(),
    getPluginConfig: vi.fn(),
    updatePluginConfig: vi.fn(),
    getCapabilities: vi.fn(),
  }),
}))

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

import PluginsView from '../PluginsView.vue'

// Identifiable stub so we can assert the audit panel mounted.
const CapabilityAuditLogStub = {
  name: 'CapabilityAuditLog',
  template: '<div data-testid="audit-log">audit</div>',
}

function mountView() {
  return mount(PluginsView, {
    global: {
      plugins: [i18n],
      stubs: {
        BaseModal: { template: '<div><slot /></div>' },
        CapabilityAuditLog: CapabilityAuditLogStub,
        CapabilityApprovalDialog: true,
        PluginInstallModal: true,
        TrustTierBadge: true,
        SchemaForm: true,
        'router-link': true,
        'router-view': true,
      },
    },
  })
}

describe('PluginsView.vue — Audit Log tab (#11980)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('does not render the audit panel on the installed tab', () => {
    const wrapper = mountView()
    expect(wrapper.find('[data-testid="audit-log"]').exists()).toBe(false)
  })

  it('renders the audit panel when the audit tab is active WITHOUT a selectedPlugin', async () => {
    const wrapper = mountView()

    // Activate the audit tab (last tab button).
    const auditBtn = wrapper.findAll('.tab-btn').at(-1)!
    await auditBtn.trigger('click')

    // Panel renders at page level, no plugin detail was opened.
    expect(wrapper.vm.selectedPlugin).toBeNull()
    expect(wrapper.find('[data-testid="audit-log"]').exists()).toBe(true)
  })
})
