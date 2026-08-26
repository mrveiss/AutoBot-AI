// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The toast tells the user WHICH failure happened (#15073).
 *
 * The backend used to answer both "the command never ran" and "the command ran
 * and a step after it raised" with the same `{status: 'error', error:
 * 'Command execution failed'}`, and this composable rendered that prose
 * straight into a toast — untranslated, and wrong half the time.
 *
 * These tests assert the distinction at the surface the user actually reads:
 * two backend outcomes, two different translated messages. Asserting only
 * "a toast appeared" would pass against the bug itself.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { defineComponent, h } from 'vue'
import { mount } from '@vue/test-utils'

import { ApiClient } from '@/utils/ApiClient'
import i18n, { loadLocaleMessages } from '@/i18n'
import { useToast } from '@/composables/useToast'
import { useCommandApproval } from '@/composables/useCommandApproval'

const EXECUTION_FAILED_KEY = 'ui.commandPermission.executionFailed'
const POST_EXECUTION_FAILED_KEY = 'ui.commandPermission.postExecutionFailed'

/** The composable reads pinia stores, so it has to run inside a component. */
function mountApproval() {
  let api!: ReturnType<typeof useCommandApproval>
  mount(
    defineComponent({
      setup() {
        api = useCommandApproval()
        return () => h('span')
      }
    })
  )
  return api
}

function toastMessages(): string[] {
  return useToast().toasts.value.map(toast => toast.message)
}

describe('useCommandApproval — execution vs post-execution failure', () => {
  beforeEach(async () => {
    setActivePinia(createPinia())
    await loadLocaleMessages('en')
    i18n.global.locale.value = 'en'
    useToast().clearAllToasts()
    vi.restoreAllMocks()
  })

  it('warns that the command RAN when post-processing is what failed', async () => {
    vi.spyOn(ApiClient.prototype, 'post').mockResolvedValue({
      status: 'completed_with_errors',
      error_code: 'postExecutionFailed',
      command_status: 'success',
      stdout: 'hello from the pty\n',
      return_code: 0,
      post_execution_error: "TypeError: add_message() got an unexpected keyword argument 'role'"
    } as never)

    await mountApproval().approveCommand('term-1', true, undefined, 'cmd-1')

    expect(toastMessages()).toContain(i18n.global.t(POST_EXECUTION_FAILED_KEY))
    expect(toastMessages()).not.toContain(i18n.global.t(EXECUTION_FAILED_KEY))
  })

  it('reports an execution failure when the command never produced a result', async () => {
    vi.spyOn(ApiClient.prototype, 'post').mockResolvedValue({
      status: 'error',
      error_code: 'executionFailed',
      error: 'Command execution failed'
    } as never)

    await mountApproval().approveCommand('term-1', true, undefined, 'cmd-1')

    expect(toastMessages()).toContain(i18n.global.t(EXECUTION_FAILED_KEY))
    expect(toastMessages()).not.toContain(i18n.global.t(POST_EXECUTION_FAILED_KEY))
  })

  it('gives the two outcomes different words, in the user’s language', () => {
    const executionFailed = i18n.global.t(EXECUTION_FAILED_KEY)
    const postExecutionFailed = i18n.global.t(POST_EXECUTION_FAILED_KEY)

    // A translation that resolved to its own key path would make the two
    // assertions above pass while showing the user `ui.commandPermission.…`.
    expect(executionFailed).not.toContain('ui.commandPermission')
    expect(postExecutionFailed).not.toContain('ui.commandPermission')
    expect(executionFailed).not.toBe(postExecutionFailed)
  })

  it('falls back to the backend detail for an outcome it has no translation for', async () => {
    vi.spyOn(ApiClient.prototype, 'post').mockResolvedValue({
      status: 'error',
      error: 'No pending approval'
    } as never)

    await mountApproval().approveCommand('term-1', true, undefined, 'cmd-1')

    expect(toastMessages()).toContain('No pending approval')
  })
})
