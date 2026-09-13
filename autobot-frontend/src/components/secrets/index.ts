// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Secrets Management Components
 *
 * Issue #874: Frontend Collaborative Session UI (#608 Phase 6)
 *
 * Components for managing secrets within collaborative sessions.
 *
 * #16429: SecretVault retired -- it duplicated SecretsManager.vue's CRUD
 * against the same /api/secrets/ backend; its one net-new capability
 * (virtual scrolling for 100+ items, #4037) was ported into SecretsManager
 * directly. ShareSecretDialog stays: unwired pending #16443 (the
 * real-time collaborative-session UI it depends on has never been wired
 * to any view). SecretAuditLog stays: wired into the Secrets page via
 * views/secrets/AuditLogView.vue.
 */

export { default as ShareSecretDialog } from './ShareSecretDialog.vue'
export { default as SecretAuditLog } from './SecretAuditLog.vue'
