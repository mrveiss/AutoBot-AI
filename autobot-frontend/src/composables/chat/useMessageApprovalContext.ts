// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * ONE approval state for the whole message stream (#18243, step 5a batch 2).
 *
 * Before the split, ChatMessages.vue called `useCommandApproval()` once, so the comment box,
 * the "processing" lock and the auto-approve toggles were shared by every pending card. The
 * stream provides that single instance here and each ChatMessageApproval injects it, so the
 * split keeps exactly that behaviour (a per-card instance would not).
 */
import { inject, provide, type InjectionKey } from 'vue'
import { useCommandApproval } from '@/composables/useCommandApproval'
import { useApprovalRouting } from '@/composables/useGraphApproval'
import { usePermissionStore } from '@/stores/usePermissionStore'

type CommandApproval = ReturnType<typeof useCommandApproval>

export interface MessageApprovalContext extends Omit<CommandApproval, 'approveCommand'> {
  /** A graph-interrupt card posts to /chats/{id}/resume; any other card keeps the terminal route (#20195). */
  approveCommand: ReturnType<typeof useApprovalRouting>
  permissionStore: ReturnType<typeof usePermissionStore>
}

export const MESSAGE_APPROVAL_KEY: InjectionKey<MessageApprovalContext> = Symbol('message-approval')

export function provideMessageApproval(): MessageApprovalContext {
  const { approveCommand, ...rest } = useCommandApproval()
  const context: MessageApprovalContext = {
    ...rest,
    approveCommand: useApprovalRouting(approveCommand),
    permissionStore: usePermissionStore(),
  }
  provide(MESSAGE_APPROVAL_KEY, context)
  return context
}

export function useMessageApproval(): MessageApprovalContext {
  const context = inject(MESSAGE_APPROVAL_KEY)
  if (!context) throw new Error('useMessageApproval needs provideMessageApproval() in an ancestor')
  return context
}
