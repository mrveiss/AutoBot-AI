// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * #22144: the noVNC client URL is derived (https scheme, SSOT port, configured path),
 * never assembled from http:// / :6080 / /vnc.html literals at the call site.
 */

import { describe, it, expect } from 'vitest'
import { getConfig } from '@/config/ssot-config'
import {
  buildVncBaseUrl,
  buildVncClientUrl,
  getVncClientPort,
  VNC_CLIENT_PATH,
  VNC_CLIENT_SCHEME,
  DESKTOP_VM_HOST_ID,
  desktopVmEntry,
} from '../vnc-client'

describe('vnc-client URL derivation', () => {
  it('serves noVNC over https because websockify is --ssl-only', () => {
    expect(VNC_CLIENT_SCHEME).toBe('https')
    expect(buildVncBaseUrl({ host: 'box.example.test', vnc_port: 6081 })).toBe('https://box.example.test:6081')
  })

  it.each([
    ['2001:db8::1', 'https://[2001:db8::1]:6081'],
    ['[2001:db8::1]', 'https://[2001:db8::1]:6081'],
    ['192.0.2.5', 'https://192.0.2.5:6081'],
    ['box.example.test', 'https://box.example.test:6081'],
  ])('brackets an IPv6 literal only: %s', (host, expected) => {
    expect(buildVncBaseUrl({ host, vnc_port: 6081 })).toBe(expected)
  })

  it('falls back to the SSOT desktop port, not a literal', () => {
    expect(getVncClientPort({ host: 'box.example.test' })).toBe(getConfig().vnc.desktop.port)
    expect(getVncClientPort({ host: 'box.example.test', vnc_port: null })).toBe(getConfig().vnc.desktop.port)
  })

  it('builds the full client URL from base, configured path and query', () => {
    const url = buildVncClientUrl({ host: 'box.example.test', vnc_port: 6081 })
    expect(url).toBe(`https://box.example.test:6081${VNC_CLIENT_PATH}?autoconnect=true`)
  })

  it("builds the desktop VM entry from the backend's endpoint, never from a frontend host setting", () => {
    const vm = desktopVmEntry({ host: 'desk.example.test', port: 6090 })
    expect(vm).toMatchObject({ id: DESKTOP_VM_HOST_ID, host: 'desk.example.test', vnc_port: 6090 })
    expect(vm.capabilities).toContain('vnc')
    expect(buildVncClientUrl(vm)).toBe(`https://desk.example.test:6090${VNC_CLIENT_PATH}?autoconnect=true`)
  })
})
