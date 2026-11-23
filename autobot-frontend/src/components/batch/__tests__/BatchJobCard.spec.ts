// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// BatchJobCard (#21662): the job's progress is the kit's BaseProgress, not a native <progress>.
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import BatchJobCard from '../BatchJobCard.vue'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const job = { job_id: 'abcdef123456', name: 'Reindex', job_type: 'backup', status: 'running', progress: 42, created_at: null, started_at: null, completed_at: null, error_message: null }

describe('BatchJobCard progress', () => {
  it('renders the kit progressbar named for the job, at the job progress, in the status variant', () => {
    const w = mount(BatchJobCard, { props: { job: job as never }, global: { plugins: [i18n] } })
    const bar = w.get('[role="progressbar"]')
    expect(bar.attributes('aria-valuenow')).toBe('42')
    expect(bar.attributes('aria-label')).toBe(en.batchJobs.progressLabel.replace('{name}', 'Reindex'))
    expect(bar.classes()).toContain('aui-progress--info')
    expect(w.find('progress').exists()).toBe(false)
  })
})
