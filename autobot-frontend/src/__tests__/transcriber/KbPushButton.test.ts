// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Every user-visible string in the KB push control is a locale key (#17535),
 * and a failed push says so.
 *
 * The component rendered six English literals and imported no `useI18n`. Three
 * were template text, one was a `placeholder` attribute, and two were string
 * literals inside an interpolation -- which is why the repo's bare-literal
 * detector would have reported three of six had it been pointed at this tree:
 * it reads template text nodes and strips interpolations wholesale. These tests
 * assert the rendered output against `en.json`, so all six are covered by one
 * mechanism regardless of which template position they occupied.
 *
 * The push failure is here too. `push()` logged the error and told the user
 * nothing; the form closed on success and stayed open on failure, so the only
 * signal was a control that did not move.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import de from '@/i18n/locales/de.json'

const kbPush = vi.fn()
const kbStatus = vi.fn()

vi.mock('@/composables/transcriber/useTranscriberApi', () => ({
  useTranscriberApi: () => ({ kbPush, kbStatus }),
}))

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))

import KbPushButton from '@/components/transcriber/KbPushButton.vue'

const KB = en.transcriber.kbPush

// vue-i18n 11 requires app.use(); the component calls useI18n(), so a real
// plugin is installed with the real en.json rather than a stub -- the tests
// assert against the shipped wording, which a stub would let drift.
const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

// German is loaded for one test that no English assertion can do. See
// `renders in German`, below.
const deI18n = createI18n({ legacy: false, locale: 'de', fallbackLocale: 'en', messages: { en, de } })

async function mountButton(pushed: boolean, plugin = i18n) {
  kbStatus.mockResolvedValue({ pushed })
  const wrapper = mount(KbPushButton, {
    props: { recordingId: 7 },
    global: { plugins: [plugin] },
  })
  await flushPromises()
  return wrapper
}

function byText(wrapper: ReturnType<typeof mount>, text: string) {
  return wrapper.findAll('button').find(b => b.text().includes(text))
}

describe('KbPushButton strings and failure reporting (#17535)', () => {
  beforeEach(() => {
    kbPush.mockReset()
    kbStatus.mockReset()
  })

  it('renders the not-yet-pushed label from the locale file', async () => {
    const wrapper = await mountButton(false)

    expect(wrapper.text()).toContain(KB.push)
    // Guards the key path itself resolving -- an unresolved key renders as the
    // path in vue-i18n rather than throwing.
    expect(wrapper.text()).not.toContain('transcriber.kbPush')
  })

  it('renders in German, which a hardcoded English literal cannot do', async () => {
    // THE DISCRIMINATING TEST. Every other assertion here compares rendered
    // output against `en.json`, and `en.json` says the same words the removed
    // literals said -- so reverting `t('...push')` to `Push to KB` leaves them
    // all green. Only a non-English locale tells a translated string from an
    // English one, and this is the single mechanism that covers all six of the
    // strings #17535 named, in whichever template position each occupied.
    const wrapper = await mountButton(true, deI18n)
    const DE = de.transcriber.kbPush

    expect(wrapper.text()).toContain(DE.inKnowledgeBase)
    expect(wrapper.text()).toContain(DE.reindex)
    expect(wrapper.text()).not.toContain(KB.inKnowledgeBase)

    await byText(wrapper, DE.reindex)!.trigger('click')
    expect(wrapper.find('input').attributes('placeholder')).toBe(DE.collectionIdPlaceholder)
    expect(byText(wrapper, DE.confirm)).toBeDefined()
  })

  it('renders the in-knowledge-base state and its re-index action from the locale file', async () => {
    const wrapper = await mountButton(true)

    expect(wrapper.text()).toContain(KB.inKnowledgeBase)
    expect(byText(wrapper, KB.reindex)).toBeDefined()
  })

  it('translates the collection placeholder, which the text detector cannot see', async () => {
    const wrapper = await mountButton(false)
    await byText(wrapper, KB.push)!.trigger('click')

    expect(wrapper.find('input').attributes('placeholder')).toBe(KB.collectionIdPlaceholder)
  })

  it('translates the confirm label and its pending form, both interpolated literals before', async () => {
    kbPush.mockImplementation(() => new Promise(() => {}))
    const wrapper = await mountButton(false)
    await byText(wrapper, KB.push)!.trigger('click')

    expect(byText(wrapper, KB.confirm)).toBeDefined()

    await byText(wrapper, KB.confirm)!.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain(KB.pushing)
    expect(wrapper.text()).not.toContain(KB.confirm)
  })

  it('reports a failed push instead of leaving the form unchanged', async () => {
    kbPush.mockRejectedValue(new Error('boom'))
    const wrapper = await mountButton(false)
    await byText(wrapper, KB.push)!.trigger('click')
    await byText(wrapper, KB.confirm)!.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain(KB.pushFailed)
    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
  })

  it('says nothing about failure after a push that worked', async () => {
    // Contrast case: without it, an error line rendered unconditionally
    // satisfies the assertion above.
    kbPush.mockResolvedValue(undefined)
    const wrapper = await mountButton(false)
    await byText(wrapper, KB.push)!.trigger('click')
    await byText(wrapper, KB.confirm)!.trigger('click')
    await flushPromises()

    expect(wrapper.text()).not.toContain(KB.pushFailed)
  })
})
