# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Frontend files still holding a `var()` that names nothing (#17552).

**The boundary.** An entry counts one *site* where a `var(--name)` in
``autobot-frontend/src`` satisfies all of:

* the reference supplies **no fallback** -- ``var(--x, #fff)`` is fine, the
  fallback is what renders;
* ``--name`` is assigned nowhere in ``autobot-frontend/src`` in a ``.css``,
  ``.scss``, ``.vue``, ``.ts`` or ``.js`` file;
* ``--name`` is not one Tailwind v4 supplies itself.

Such a reference is not inert. It makes the declaration *invalid at
computed-value time*, so ``background`` renders ``transparent``, ``color``
silently **inherits**, and a ``border`` shorthand is dropped entirely. That is
what produced pale text on pale surfaces across the GUI.

**Shrink-only.** A number may fall or an entry vanish. Neither may grow, and no
new file may appear. Fix the reference -- do not add a fallback purely to get
under the check, because a fallback hard-codes a colour that then ignores the
theme, which is the same defect wearing a different hat.

Frozen at 134 sites in 46 files, after #17552 cleared the `--autobot-*`
namespace (46 sites) and the six `--color-`prefixed names (32 sites).
"""

from __future__ import annotations

#: ``path relative to the repo root -> sites still unresolved``.
UNDEFINED_CSS_VAR_SITES: dict[str, int] = {
    "autobot-frontend/src/assets/css/design-tokens.css": 1,
    "autobot-frontend/src/assets/css/themes/accents.css": 1,
    "autobot-frontend/src/assets/vue-notus.css": 1,
    "autobot-frontend/src/components/analytics/AnalyticsGrid.vue": 1,
    "autobot-frontend/src/components/analytics/CodebaseAnalytics.vue": 1,
    "autobot-frontend/src/components/analytics/CodebaseImpactPanel.vue": 1,
    "autobot-frontend/src/components/analytics/DuplicatesSection.vue": 1,
    "autobot-frontend/src/components/analytics/HardcodesSection.vue": 1,
    "autobot-frontend/src/components/analytics/ProblemsReportSection.vue": 1,
    "autobot-frontend/src/components/artifact-cells/ChartCell.vue": 3,
    "autobot-frontend/src/components/audit/AuditFilters.vue": 1,
    "autobot-frontend/src/components/audit/AuditLogTable.vue": 1,
    "autobot-frontend/src/components/audit/AuditStatistics.vue": 2,
    "autobot-frontend/src/components/base/ErrorBanner.vue": 4,
    "autobot-frontend/src/components/chat/ChatSidebar.vue": 2,
    "autobot-frontend/src/components/knowledge/ChromaDBExplorer.vue": 1,
    "autobot-frontend/src/components/knowledge/EntityExtractor.vue": 2,
    "autobot-frontend/src/components/knowledge/GraphConnectionPath.vue": 1,
    "autobot-frontend/src/components/knowledge/GraphRAGQuery.vue": 1,
    "autobot-frontend/src/components/knowledge/KnowledgeBrowser.vue": 4,
    "autobot-frontend/src/components/knowledge/KnowledgeBrowserHeader.vue": 1,
    "autobot-frontend/src/components/knowledge/KnowledgeGraph.vue": 1,
    "autobot-frontend/src/components/knowledge/KnowledgeUpload.vue": 7,
    "autobot-frontend/src/components/knowledge/SessionOrphanManager.vue": 5,
    "autobot-frontend/src/components/knowledge/VectorizationProgressModal.vue": 2,
    "autobot-frontend/src/components/knowledge/VectorizationStatusBadge.vue": 3,
    "autobot-frontend/src/components/knowledge/WatchFoldersPanel.vue": 1,
    "autobot-frontend/src/components/knowledge/WebResearchPanel.vue": 3,
    "autobot-frontend/src/components/knowledge/modals/BulkEditModal.vue": 1,
    "autobot-frontend/src/components/llc/RoleAttachmentPanel.vue": 3,
    "autobot-frontend/src/components/modals/TelemetryConsentModal.vue": 3,
    "autobot-frontend/src/components/plugins/CapabilityApprovalDialog.vue": 4,
    "autobot-frontend/src/components/plugins/CapabilityAuditLog.vue": 4,
    "autobot-frontend/src/components/profile/DeviceManagementPanel.vue": 2,
    "autobot-frontend/src/components/settings/TelemetrySettingsPanel.vue": 1,
    "autobot-frontend/src/components/terminal/TerminalHeader.vue": 5,
    "autobot-frontend/src/components/terminal/TerminalInput.vue": 15,
    "autobot-frontend/src/components/terminal/TerminalModals.vue": 9,
    "autobot-frontend/src/components/terminal/TerminalOutput.vue": 15,
    "autobot-frontend/src/components/ui/BaseAlert.vue": 3,
    "autobot-frontend/src/components/ui/CommandPermissionDialog.vue": 4,
    "autobot-frontend/src/components/ui/DataTable.vue": 1,
    "autobot-frontend/src/components/ui/HostSelectionDialog.vue": 2,
    "autobot-frontend/src/components/visualizations/WorkflowVisualization.vue": 1,
    "autobot-frontend/src/views/BudgetPolicies.vue": 3,
    "autobot-frontend/src/views/llc/RolesView.vue": 4,
}

#: Frozen total, asserted separately so a per-file edit cannot drift it unseen.
TOTAL_SITES = 134
