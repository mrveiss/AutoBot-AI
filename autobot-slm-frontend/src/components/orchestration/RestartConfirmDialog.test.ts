// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * RestartConfirmDialog - the X button, overlay and Escape cannot dismiss the dialog
 * while the restart is processing (CodeRabbit on #18941).
 */

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { BaseModal } from '@autobot/ui'

import RestartConfirmDialog from './RestartConfirmDialog.vue'

function mountDialog(isProcessing: boolean) {
  return mount(RestartConfirmDialog, {
    props: { show: true, message: 'restart?', isProcessing },
    global: { mocks: { $t: (k: string) => k }, stubs: { teleport: true } },
  })
}

describe('RestartConfirmDialog dismissal', () => {
  it('locks the modal while processing', () => {
    expect(mountDialog(true).findComponent(BaseModal).props('locked')).toBe(true)
  })

  it('stays dismissible when idle', () => {
    expect(mountDialog(false).findComponent(BaseModal).props('locked')).toBe(false)
  })
})
