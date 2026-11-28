// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('chatSessionCompany')

/** The company fields a chat carries; the server owns them (#16905, #21997). */
interface CompanyFields {
  id: string
  companyId?: string
  unassigned?: boolean
}

/**
 * An import of a chat already held is skipped, except that its company is refreshed: the server owns it,
 * so a reload keeps it current. An import that omits a field (the public importChatSession) must not
 * blank what is held (#16905).
 */
export function refreshExistingCompany(existing: CompanyFields, incoming: CompanyFields): void {
  logger.debug(`Session ${incoming.id} already exists, skipping import`)
  if (incoming.companyId !== undefined) existing.companyId = incoming.companyId
  if (incoming.unassigned !== undefined) existing.unassigned = incoming.unassigned
  else if (incoming.companyId) existing.unassigned = false // assigned to a company means not unassigned
}
