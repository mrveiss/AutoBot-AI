// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// #21961 AC2: Light, Dark and Monochrome render a 2px active underline, High contrast 4px.
// Vitest cannot lay out Tailwind, so the width is resolved as the cascade does: the rendered
// active link names the --nav-on-bw token, and the theme's own declaration (else the base
// :root one) supplies the value.
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createRouter, createMemoryHistory } from 'vue-router'
import TopNavLinks from '../TopNavLinks.vue'
import type { NavItem } from '@/config/navItems'

const here = dirname(fileURLToPath(import.meta.url))
const css = (rel: string) => readFileSync(resolve(here, '../../../assets/css', rel), 'utf-8')
const WIDTH = /--nav-on-bw:\s*([^;]+);/
const UTILITY = 'border-b-(length:--nav-on-bw)'

/** theme name -> the stylesheet that may override --nav-on-bw for it (none: the base value). */
const THEMES: Array<[string, string | null, string]> = [
  ['light', null, '2px'],
  ['dark', null, '2px'],
  ['mono', null, '2px'],
  ['contrast', 'themes/contrast.css', '4px'],
  ['contrast-dark', 'themes/contrast-dark.css', '4px'],
]

function themeWidth(file: string | null): string {
  const own = file ? WIDTH.exec(css(file)) : null
  const base = WIDTH.exec(css('design-tokens.css'))
  const found = own ?? base
  if (!found) throw new Error('--nav-on-bw is declared nowhere')
  return found[1].trim()
}

const items: NavItem[] = [
  { to: '/chat', labelKey: 'chat', iconPaths: ['M0 0'] },
  { to: '/knowledge', labelKey: 'knowledge', iconPaths: ['M0 0'] },
] as NavItem[]
const i18n = createI18n({ legacy: false, locale: 'en', messages: { en: { chat: 'Chat', knowledge: 'Knowledge', nav: { mainNavigation: 'Main' } } } })

async function renderRail() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:p(.*)*', component: { render: () => null } }] })
  router.push('/chat')
  await router.isReady()
  return mount(TopNavLinks, { props: { items }, global: { plugins: [i18n, router] } })
}

describe('TopNavLinks active underline width per theme (#21961)', () => {
  it.each(THEMES)('%s renders a %s underline from --nav-on-bw', async (_theme, file, width) => {
    const wrapper = await renderRail()
    const active = wrapper.get('a[aria-current="page"]').element
    expect(active.classList.contains(UTILITY)).toBe(true)
    expect(themeWidth(file)).toBe(width)
  })

  it('draws the same token width on inactive links, so selecting one does not shift the rail', async () => {
    const wrapper = await renderRail()
    const idle = wrapper.findAll('a').find((a) => a.attributes('aria-current') !== 'page')
    expect(idle?.element.classList.contains(UTILITY)).toBe(true)
  })
})
