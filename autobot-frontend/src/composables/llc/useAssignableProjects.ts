// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// #18978: the projects a work item can go in, for the backlog's filter, form and sprint picker.
// A failed request is kept apart from an empty result, so a company is not told it has no project.
import { ref, type Ref } from 'vue'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useAssignableProjects')

export interface ProjectOpt {
  id: string
  name: string
  lifecycle_state: string
}

export function useAssignableProjects(companyId: Readonly<Ref<string>>) {
  const api = useApiClient()
  const projects = ref<ProjectOpt[]>([])
  const isLoadingProjects = ref(false)
  const projectsFailed = ref(false)

  async function loadProjects() {
    isLoadingProjects.value = true
    projectsFailed.value = false
    try {
      const result = await api.get<ProjectOpt[]>(`/api/llc/companies/${companyId.value}/projects`)
      projects.value = (result ?? []).filter(
        p => p.lifecycle_state !== 'archived' && p.lifecycle_state !== 'disposed',
      )
    } catch (err) {
      logger.error('Failed to load projects', err)
      projectsFailed.value = true
    } finally {
      isLoadingProjects.value = false
    }
  }

  return { projects, isLoadingProjects, projectsFailed, loadProjects }
}
