// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * `v-permission` admits every administrative role (#14937).
 *
 * The directive short-circuited on `role === 'admin'`, so a superadmin -- who
 * passes every backend `require_role("admin", "superadmin")` gate -- had
 * admin-only controls hidden. The permission used below is in no role's map on
 * purpose: only the administrative short-circuit can show it, so a pass proves
 * that branch rather than a map lookup that happens to agree.
 */

import { describe, it, expect, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h, withDirectives } from 'vue'
import { vPermission } from '@/directives/permission'

/** A permission no role map carries -- reachable only through the admin short-circuit. */
const UNMAPPED = 'reports:export'

function renderWith(role: string | null, permission: string): HTMLElement {
  if (role === null) localStorage.removeItem('autobot_user')
  else localStorage.setItem('autobot_user', JSON.stringify({ role }))
  const Probe = defineComponent({
    render: () => withDirectives(h('button', 'x'), [[vPermission, permission]]),
  })
  return mount(Probe).find('button').element as HTMLElement
}

afterEach(() => {
  localStorage.clear()
})

describe('v-permission and administrative roles (#14937)', () => {
  it.each(['admin', 'superadmin', 'SuperAdmin'])('shows an admin-only control to %s', (role) => {
    const el = renderWith(role, UNMAPPED)
    expect(el.style.display).not.toBe('none')
    expect(el.classList.contains('permission-hidden')).toBe(false)
  })

  it.each(['user', 'operator', 'readonly'])('still hides it from %s', (role) => {
    expect(renderWith(role, UNMAPPED).style.display).toBe('none')
  })

  it('hides it when nobody is signed in -- there is no guest role to fall back to', () => {
    expect(renderWith(null, UNMAPPED).style.display).toBe('none')
  })

  it('still shows the signed-out set when nobody is signed in', () => {
    expect(renderWith(null, 'chat:use').style.display).not.toBe('none')
  })
})
