// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ProjectsView from '@/views/transcriber/ProjectsView.vue'

// --- API mock ---------------------------------------------------------------
const listProjects = vi.fn()
const createProject = vi.fn()
const deleteProject = vi.fn()

// mockReset:true wipes factories — re-apply implementations in beforeEach.
vi.mock('@/composables/transcriber/useTranscriberApi', () => ({
  useTranscriberApi: () => ({ listProjects, createProject, deleteProject }),
}))

// Capture router.push to assert navigation.
const push = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
}))

function project(id: number, name = `Project ${id}`) {
  return {
    id,
    name,
    description: `Desc ${id}`,
    created_at: '2026-06-18T00:00:00Z',
    user_id: 'u1',
  }
}

function mountView() {
  return mount(ProjectsView)
}

describe('ProjectsView.vue', () => {
  beforeEach(() => {
    listProjects.mockResolvedValue([project(1), project(2)])
    createProject.mockResolvedValue(project(3, 'New One'))
    deleteProject.mockResolvedValue(undefined)
    push.mockClear()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
  })

  it('lists projects on mount', async () => {
    const wrapper = mountView()
    await flushPromises()
    expect(listProjects).toHaveBeenCalled()
    const cards = wrapper.findAll('.project-card')
    expect(cards).toHaveLength(2)
    expect(wrapper.text()).toContain('Project 1')
  })

  it('shows the empty state when there are no projects', async () => {
    listProjects.mockResolvedValue([])
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.find('.projects-list').exists()).toBe(false)
    expect(wrapper.text()).toContain('No projects yet')
  })

  it('shows an error state when loading fails', async () => {
    listProjects.mockRejectedValue(new Error('boom'))
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.find('.projects-error').exists()).toBe(true)
  })

  it('creates a project and prepends it to the list', async () => {
    const wrapper = mountView()
    await flushPromises()

    await wrapper.find('.btn-primary').trigger('click')
    await wrapper.findAll('.create-input')[0].setValue('New One')
    await wrapper.find('.create-form').trigger('submit')
    await flushPromises()

    expect(createProject).toHaveBeenCalledWith('New One', '')
    expect(wrapper.findAll('.project-card')).toHaveLength(3)
    expect(wrapper.findAll('.project-name')[0].text()).toBe('New One')
  })

  it('does not create a project with an empty name', async () => {
    const wrapper = mountView()
    await flushPromises()
    await wrapper.find('.btn-primary').trigger('click')
    await wrapper.find('.create-form').trigger('submit')
    await flushPromises()
    expect(createProject).not.toHaveBeenCalled()
  })

  it('deletes a project after confirmation and refreshes the list', async () => {
    const wrapper = mountView()
    await flushPromises()
    await wrapper.findAll('.btn-danger')[0].trigger('click')
    await flushPromises()
    expect(deleteProject).toHaveBeenCalledWith(1)
    expect(wrapper.findAll('.project-card')).toHaveLength(1)
  })

  it('navigates to the project detail view when a project is opened', async () => {
    const wrapper = mountView()
    await flushPromises()
    await wrapper.findAll('.project-open')[0].trigger('click')
    expect(push).toHaveBeenCalledWith({
      name: 'transcriber-project-detail',
      params: { projectId: 1 },
    })
  })
})
