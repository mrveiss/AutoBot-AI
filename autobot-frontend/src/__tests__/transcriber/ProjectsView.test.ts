// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ProjectsView from '@/views/transcriber/ProjectsView.vue'

// --- API mock ---------------------------------------------------------------
const listProjects = vi.fn()
const createProject = vi.fn()
const deleteProject = vi.fn()

// mockReset:true wipes factories — re-apply implementations in beforeEach.
vi.mock('@/composables/transcriber/useTranscriberApi', () => ({
  useTranscriberApi: () => ({ listProjects, createProject, deleteProject }),
}))

// --- router mock ------------------------------------------------------------
const push = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
}))

function project(id: number, name: string, description = '') {
  return { id, name, description, created_at: '2026-01-02T00:00:00Z', user_id: 'u1' }
}

function mountView() {
  return mount(ProjectsView, { global: { plugins: [createPinia()] } })
}

describe('ProjectsView.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    listProjects.mockResolvedValue([project(1, 'Interviews', 'Q3'), project(2, 'Standups')])
    createProject.mockResolvedValue(project(3, 'New one'))
    deleteProject.mockResolvedValue(undefined)
    push.mockClear()
  })

  it('loads and renders the project list', async () => {
    const wrapper = mountView()
    await flushPromises()

    expect(listProjects).toHaveBeenCalled()
    const cards = wrapper.findAll('.project-card')
    expect(cards).toHaveLength(2)
    expect(wrapper.text()).toContain('Interviews')
    expect(wrapper.text()).toContain('Standups')
  })

  it('shows the empty state when there are no projects', async () => {
    listProjects.mockResolvedValue([])
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.find('.project-card').exists()).toBe(false)
    expect(wrapper.text()).toContain('No projects yet')
  })

  it('shows an error state and can retry', async () => {
    listProjects.mockRejectedValueOnce(new Error('boom'))
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.find('.projects-error').exists()).toBe(true)
    listProjects.mockResolvedValue([project(1, 'Interviews')])
    await wrapper.find('.projects-error button').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('.project-card')).toHaveLength(1)
  })

  it('creates a project and navigates to its detail view', async () => {
    const wrapper = mountView()
    await flushPromises()

    await wrapper.find('.projects-header .btn-primary').trigger('click') // open form
    await wrapper.find('.project-form-field input').setValue('New one')
    await wrapper.find('.project-form').trigger('submit')
    await flushPromises()

    expect(createProject).toHaveBeenCalledWith('New one', '')
    expect(push).toHaveBeenCalledWith({
      name: 'transcriber-project-detail',
      params: { projectId: '3' },
    })
  })

  it('does not submit an empty project name', async () => {
    const wrapper = mountView()
    await flushPromises()

    await wrapper.find('.projects-header .btn-primary').trigger('click')
    await wrapper.find('.project-form').trigger('submit')
    await flushPromises()

    expect(createProject).not.toHaveBeenCalled()
    expect(wrapper.find('.project-form-error').text()).toContain('required')
  })

  it('navigates to a project when its card is clicked', async () => {
    const wrapper = mountView()
    await flushPromises()

    await wrapper.find('.project-card .project-card-main').trigger('click')
    expect(push).toHaveBeenCalledWith({
      name: 'transcriber-project-detail',
      params: { projectId: '1' },
    })
  })
})
