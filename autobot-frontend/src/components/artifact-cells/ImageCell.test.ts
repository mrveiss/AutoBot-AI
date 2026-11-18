// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #13424 — ImageCell only renders image URLs it can trust
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import ImageCell from './ImageCell.vue'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en: {} }, missingWarn: false })

const mountCell = (urls: string[]) =>
  mount(ImageCell, {
    props: { richPayload: { images: urls.map((url) => ({ url })) } },
    global: { stubs: { Icon: true, Teleport: true }, plugins: [i18n] },
  })

const sources = (urls: string[]) =>
  mountCell(urls)
    .findAll('img.generated-image')
    .map((img) => img.attributes('src'))

describe('ImageCell.vue image URL allowlist', () => {
  it('renders png/jpeg/webp data URLs and http(s) URLs', () => {
    const urls = [
      'data:image/png;base64,AAAA',
      'data:image/jpeg;base64,AAAA',
      'data:image/webp;base64,AAAA',
      'https://cdn.example/x.png',
    ]
    expect(sources(urls)).toEqual(urls)
  })

  it('drops svg, html and script URLs', () => {
    const bad = [
      'data:image/svg+xml;base64,PHN2Zz4=',
      'data:text/html;base64,PGh0bWw+',
      'javascript:alert(1)',
      'data:image/png,not-base64',
    ]
    expect(sources([...bad, 'https://cdn.example/ok.png'])).toEqual(['https://cdn.example/ok.png'])
  })
})
