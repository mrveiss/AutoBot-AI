// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3'
import { ref } from 'vue'
import LanguageSwitcher from './LanguageSwitcher.vue'
import { localeOptions } from '../utils/locales'

const options = localeOptions(['en', 'de', 'lv', 'ar', 'he'])

const meta: Meta<typeof LanguageSwitcher> = {
  title: 'Kit/LanguageSwitcher',
  component: LanguageSwitcher,
  args: { modelValue: 'en', options, label: 'Language' },
}
export default meta

type Story = StoryObj<typeof LanguageSwitcher>

const render: Story['render'] = (args) => ({
  components: { LanguageSwitcher },
  setup: () => ({ args, code: ref(args.modelValue) }),
  template: '<LanguageSwitcher v-bind="args" v-model="code" /> <p>{{ code }}</p>',
})

/** A labelled native select, as the SLM sidebar uses it. */
export const Select: Story = { render }

/** A globe button opening a listbox, for a nav bar. */
export const Menu: Story = { args: { variant: 'menu' }, render }
