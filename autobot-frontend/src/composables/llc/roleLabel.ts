// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The one translation of a company membership role code (#20816): MembersView and TeamsView both show
 * it. A code with no `llcMembers.role.<code>` key is shown as the code itself, never as the key path.
 */
import { useI18n } from 'vue-i18n'

type Translate = (key: string) => string

/** `owner` -> the translated label; an unknown code comes back unchanged. */
export function roleLabelFor(t: Translate, role: string): string {
  const key = `llcMembers.role.${role}`
  const label = t(key)
  return label === key ? role : label
}

/** The translator bound to the current locale, for a component's `roleLabel(role)`. */
export function useRoleLabel(): (role: string) => string {
  const { t } = useI18n()
  return (role: string) => roleLabelFor(t, role)
}
