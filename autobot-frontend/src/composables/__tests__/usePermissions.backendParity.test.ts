// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * #16491: the frontend's role -> permission map is the backend's, generated from
 * `autobot_shared/auth/permissions.py::ROLE_PERMISSIONS` -- not a hand-curated
 * copy. Each row below is a grant the old hand-curated sets got wrong: they gave
 * `operator`, `analyst` and `editor` the `user` set, and `readonly` a download it
 * does not hold on the backend.
 */

import { describe, it, expect, vi, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h, withDirectives } from 'vue'

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ error: vi.fn(), info: vi.fn(), warn: vi.fn(), debug: vi.fn() }),
}))

import { getPermissionsForRole, ROLE_PERMISSIONS } from '@/composables/usePermissions'
import { vPermission } from '@/directives/permission'
import { ROLE_PERMISSIONS as GENERATED, type Permission, type Role } from '@/types/_generated/workflow'

describe('usePermissions backend parity (#16491)', () => {
  it('re-exports the generated backend map itself, not a copy', () => {
    expect(ROLE_PERMISSIONS).toBe(GENERATED)
  })

  it.each<[Role, Permission, Role]>([
    ['readonly', 'files.download', 'user'],
    ['user', 'knowledge.write', 'editor'],
    ['user', 'agent.execute', 'operator'],
    ['user', 'files.upload', 'editor'],
  ])('%s lacks %s, which %s holds -- as on the backend', (without, permission, holder) => {
    expect(getPermissionsForRole(without)).not.toContain(permission)
    expect(getPermissionsForRole(holder)).toContain(permission)
  })
})

describe('v-permission reads the generated map (#16491)', () => {
  afterEach(() => {
    localStorage.clear()
  })

  function renderWith(role: string, permission: string): HTMLElement {
    localStorage.setItem('autobot_user', JSON.stringify({ role }))
    const Probe = defineComponent({
      render: () => withDirectives(h('button', 'x'), [[vPermission, permission]]),
    })
    return mount(Probe).find('button').element as HTMLElement
  }

  it('shows an editor the knowledge.write control and hides it from a user', () => {
    expect(renderWith('editor', 'knowledge.write').style.display).not.toBe('none')
    expect(renderWith('user', 'knowledge.write').style.display).toBe('none')
  })
})
