// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The org canvas's workflow attach / detach (#14549, #21242): the form's two values, the one
 * in-flight flag both mutations share, and the error either leaves.
 *
 * The writes go through the company workflows service. No optimistic update: the canvas is the
 * confirmation, so the process nodes are reloaded after a write and left alone when it fails. The
 * view is not remounted when the company changes, so the company is captured before each await and
 * nothing is written into state that now belongs to another company.
 */
import { computed, ref, type Ref } from 'vue'
import type { ProcessNodeSource } from '@/composables/llc/orgCanvasGraph'
import type { CompanyWorkflowsService } from '@/composables/llc/useCompanyWorkflows'

export interface OrgProcessAttachmentDeps {
  companyId: () => string
  workflows: Pick<CompanyWorkflowsService, 'attach' | 'detach'>
  processNodes: Ref<ProcessNodeSource[]>
  /** Re-run the process-node fetch (the lazy guard cleared first). */
  reload: () => Promise<void>
  /** The server's reason, or the translated fallback for `key`. */
  describe: (err: unknown, key: string) => string
}

export function useOrgProcessAttachment(deps: OrgProcessAttachmentDeps) {
  const roleId = ref('')
  const workflowId = ref('')
  const inFlight = ref(false)
  const error = ref<string | null>(null)

  /** Workflow ids already on the chosen role: the select lists them, disabled. */
  const attachedIds = computed(() =>
    deps.processNodes.value.filter((n) => n.role_id === roleId.value).map((n) => n.workflow_id),
  )

  async function run(write: () => Promise<unknown>, failKey: string, onDone?: () => void): Promise<void> {
    const cid = deps.companyId()
    inFlight.value = true
    error.value = null
    try {
      await write()
      if (cid !== deps.companyId()) return
      onDone?.()
      await deps.reload()
    } catch (err: unknown) {
      if (cid === deps.companyId()) error.value = deps.describe(err, failKey)
    } finally {
      inFlight.value = false
    }
  }

  async function attach(): Promise<void> {
    const role = roleId.value
    const workflow = workflowId.value
    if (!deps.companyId() || !role || !workflow || inFlight.value) return
    await run(() => deps.workflows.attach(role, workflow), 'llc.orgChart.attachError', () => {
      workflowId.value = ''
    })
  }

  async function detach(role: string, workflow: string): Promise<void> {
    if (!deps.companyId() || inFlight.value) return
    await run(() => deps.workflows.detach(role, workflow), 'llc.orgChart.detachError')
  }

  return { roleId, workflowId, inFlight, error, attachedIds, attach, detach }
}
