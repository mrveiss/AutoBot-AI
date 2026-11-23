// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// ChatMessageApproval (#18243, step 5a batch 2): the four inline approval states and their actions.
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { ref } from 'vue'
import en from '@/i18n/locales/en.json'
import ChatMessageApproval from '../ChatMessageApproval.vue'
import { MESSAGE_APPROVAL_KEY } from '@/composables/chat/useMessageApprovalContext'
import type { ChatMessage } from '@/stores/useChatStore'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en }, missingWarn: false, fallbackWarn: false })

function context(over: Record<string, unknown> = {}) {
  return {
    processingApproval: ref(false), showCommentInput: ref(false), activeCommentSessionId: ref<string | null>(null),
    approvalComment: ref(''), pendingApprovalDecision: ref<boolean | null>(null), autoApproveFuture: ref(false),
    rememberForProject: ref(false), currentProjectPath: ref(''), approveCommand: vi.fn(), promptForComment: vi.fn(),
    submitApprovalWithComment: vi.fn(), cancelComment: vi.fn(), permissionStore: { isEnabled: false }, ...over,
  }
}
const pending = { requires_approval: true, command: 'ls -la', command_id: 'c1', terminal_session_id: 's1', risk_level: 'MEDIUM', purpose: 'list' }
const msg = (metadata: Record<string, unknown>) => ({ id: 'm1', sender: 'assistant', content: '', timestamp: 't', metadata }) as unknown as ChatMessage
const render = (metadata: Record<string, unknown>, ctx = context()) =>
  mount(ChatMessageApproval, { props: { message: msg(metadata) }, global: { plugins: [i18n], provide: { [MESSAGE_APPROVAL_KEY as symbol]: ctx } } })

describe('ChatMessageApproval', () => {
  it.each([
    ['pre_approved', 'approval-pre-approved', 'Auto-approved'],
    ['approved', 'approval-approved', 'Command approved'],
    ['denied', 'approval-denied', 'Command denied'],
  ])('shows the decided state %s with its command', (status, cls, title) => {
    const w = render({ approval_status: status, command: 'ls', approval_comment: 'because' })
    expect(w.get('.approval-confirmed').classes()).toContain(cls)
    expect(w.text()).toContain(title)
    expect(w.text()).toContain('ls')
    expect(w.text()).toContain('because')
  })

  it('renders nothing without requires_approval, and nothing pending once decided', () => {
    expect(render({ command: 'ls' }).find('.approval-card').exists()).toBe(false)
    expect(render({ ...pending, approval_status: 'approved' }).find('.approval-request').exists()).toBe(false)
  })

  it('Approve and Deny call the routed approveCommand with the session, command id and summary', async () => {
    const ctx = context()
    const w = render(pending, ctx)
    const [deny, , approve] = w.findAll('.approval-actions button')
    await approve.trigger('click')
    await deny.trigger('click')
    const summary = { command: 'ls -la', risk_level: 'MEDIUM' }
    expect(ctx.approveCommand).toHaveBeenNthCalledWith(1, 's1', true, undefined, 'c1', summary)
    expect(ctx.approveCommand).toHaveBeenNthCalledWith(2, 's1', false, undefined, 'c1', summary)
  })

  it('Comment opens the comment box for that session and is hidden for a graph approval', async () => {
    const ctx = context()
    const w = render(pending, ctx)
    await w.get('button[aria-label="Add comment"]').trigger('click')
    expect(ctx.promptForComment).toHaveBeenCalledWith('s1')
    expect(render({ ...pending, calls: [{}] }).find('button[aria-label="Add comment"]').exists()).toBe(false)
  })

  it('locks every action while an approval is processing or the comment box is open', () => {
    const w = render(pending, context({ processingApproval: ref(true) }))
    for (const b of w.findAll('.approval-actions button')) expect(b.attributes('disabled')).toBeDefined()
    expect(w.find('.approval-processing').exists()).toBe(true)
  })

  it('submits the comment for the pending decision, and blocks an empty one', async () => {
    const ctx = context({ showCommentInput: ref(true), activeCommentSessionId: ref('s1'), pendingApprovalDecision: ref(true) })
    const w = render(pending, ctx)
    const submit = w.findAll('.comment-actions button')[1]
    expect(submit.attributes('disabled')).toBeDefined()
    ctx.approvalComment.value = 'ok'
    await w.vm.$nextTick()
    await submit.trigger('click')
    expect(ctx.submitApprovalWithComment).toHaveBeenCalledWith('s1', true)
  })

  it('shows remember-for-project only when permissions are enabled', () => {
    expect(render(pending).findAll('input[type="checkbox"]')).toHaveLength(1)
    expect(render(pending, context({ permissionStore: { isEnabled: true } })).findAll('input[type="checkbox"]')).toHaveLength(2)
  })

  it('risk badge: an unknown level is not the success tone', () => {
    const badge = (level: string) => render({ ...pending, risk_level: level }).get('.detail-value[data-slot="badge"]').classes().join(' ')
    expect(badge('LOW')).toContain('success')
    expect(badge('WHATEVER')).not.toContain('success')
  })
})
