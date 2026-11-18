// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
export interface AuthorityException {
  path: string
  reason: string
}
export interface AuthorityEntry {
  status: 'canonical' | 'undecided'
  owner: string | null
  issue: string
  note?: string
  exceptions?: readonly AuthorityException[]
}
export const AUTHORITY: Readonly<Record<string, AuthorityEntry>>
export function designSystemOwner(concept: string): string
export function authorityProblems(table?: Record<string, AuthorityEntry>): string[]
