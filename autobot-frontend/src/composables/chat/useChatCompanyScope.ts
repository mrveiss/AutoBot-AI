// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * useChatCompanyScope -- the chat list follows the active company (#21997).
 *
 * The backend returns the active company's chats plus the Unassigned ones (chats that carry no
 * company). This reloads the list in place when the top-bar company changes, closes an open chat
 * that belongs to another company, and assigns one Unassigned chat to a company on a person's
 * explicit request through the existing ApiClient.assignChatCompany. Nothing is ever assigned
 * automatically.
 */
import { computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useChatStore } from '@/stores/useChatStore'
import { useChatController } from '@/models/controllers'
import { useLlcCompanyStore } from '@/stores/useLlcCompanyStore'
import { useNotificationBus } from '@/composables/useNotificationBus'
import ApiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useChatCompanyScope')

export function useChatCompanyScope() {
  const { t } = useI18n()
  const store = useChatStore()
  const controller = useChatController()
  const companyStore = useLlcCompanyStore()
  const { showToast } = useNotificationBus()

  /** An Unassigned chat is visible in every company, so the one that was open stays open. */
  function isOpenUnassigned(id: string | null): boolean {
    return !!id && store.sessions.some((s) => s.id === id && s.unassigned)
  }

  /** Close the open chat unless it is Unassigned, then reload; the reload reopens only a chat the new list still has. */
  async function reloadForCompany(): Promise<void> {
    if (!isOpenUnassigned(store.currentSessionId)) store.currentSessionId = null
    await controller.loadChatSessions(true)
  }

  // The assignment picker needs the companies even when the chat is opened before any Company OS page.
  if (!companyStore.hasCompanies) void companyStore.fetchCompanies()

  watch(() => companyStore.selectedCompanyId, (next, prev) => {
    if (next !== prev) void reloadForCompany()
  })

  async function assignToCompany(sessionId: string, companyId: string): Promise<boolean> {
    try {
      await ApiClient.assignChatCompany(sessionId, companyId)
    } catch (error) {
      logger.error('Failed to assign chat to a company:', error)
      showToast(t('chat.sidebar.assignFailed'), 'error')
      return false
    }
    const name = companyStore.companies.find((c) => c.id === companyId)?.name ?? ''
    showToast(t('chat.sidebar.assignedSuccess', { company: name }), 'success')
    await controller.loadChatSessions(true) // assigning X while viewing Y keeps Y open
    return true
  }

  const companies = computed(() => companyStore.companies)
  return { companies, assignToCompany, reloadForCompany }
}
