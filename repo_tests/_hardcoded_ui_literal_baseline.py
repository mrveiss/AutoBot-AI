# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
r"""Hard-coded English UI text the frontends write instead of translating (#12732).

**The boundary.** An entry is a `.vue` file, mapped to how many hard-coded
English literals it contains, where:

* Files: `.vue` under `autobot-frontend/src` and `autobot-slm-frontend/src`,
  excluding `*.stories.*`, `__tests__/`, `*.spec.*`, `*.test.*`. Enumerated from
  the filesystem under the repo root.
* A literal is one of three kinds, detected by `repo_tests/_ui_literal_scan.py`
  (the same detector the SLM console's zero-baseline guard, #15665, uses):
  * template-text: a text node in the `<template>`, with tags and `{{ }}`
    interpolations removed, one line at a time, of at least 4 characters with two
    consecutive letters, that is not a URL, a path or a CamelCase/snake/kebab
    identifier. `<code>`, `<pre>`, `<svg>` and `<path>` content is opaque.
    A plain one-word label (`Running`, `Close`) is prose, for both guards;
  * attribute: a static (unbound) `placeholder`, `title`, `alt`, `aria-label`,
    `aria-description` or `label` whose value passes the same prose test;
  * script: in `<script>`, matching
    ``(?:\.value\s*=|message:|title:|confirm\(|alert\(|Error\()\s*[`'"]([A-Z][a-z][^`'"]{3,})[`'"]``.

**Not seen:** a literal in a custom component's own prop (`message`, `caption`,
`hint`), text built by concatenation, `v-bind` string literals, `.ts` files,
props defaults, and any language other than English.

**Pinned per file, not as a total**, so a literal removed in one file cannot
hide a new one in another. Counts are exact: a removed literal leaves its entry
stale until it is lowered in the commit that did the work, and a file that
reaches 0 leaves the dict.

**Shrink-only.** Replace a literal with `t('...')` and an English key in
`en.json`; do not delete text to get under the check. English-only i18n is the
current ruling, so this counts literals not yet moved to `t()`.

The SLM console's template text and attributes are held at zero by
`slm_frontend_bare_ui_literals_test.py` on the same detector and the same rule;
this ratchet adds the script kind there and pins the main GUI per file.

**Known false positives, counted on purpose** rather than special-cased: proper
nouns and product or language names (`Python`, `Vue`) and units (`KB/s`) are
not translatable prose in the strict sense but are not mechanically separable
from a one-word label. They stay in the counts; a migration that moves them to
`t()` is harmless and one that leaves them is recorded here.
"""

from __future__ import annotations

#: ``repo-relative .vue path -> hard-coded English literals not yet moved to t()``.
HARDCODED_UI_LITERALS: dict[str, int] = {
    "autobot-frontend/src/components/admin/NpuWorkerPairConfirmDialog.vue": 9,
    "autobot-frontend/src/components/agents/AgentTaskDetail.vue": 15,
    "autobot-frontend/src/components/agents/HeartbeatPanel.vue": 31,
    "autobot-frontend/src/components/analytics/AddSourceModal.vue": 2,
    "autobot-frontend/src/components/analytics/AgentCostPanel.vue": 1,
    "autobot-frontend/src/components/analytics/AnalyticsGrid.vue": 1,
    "autobot-frontend/src/components/analytics/CodeEvolutionTimeline.vue": 2,
    "autobot-frontend/src/components/analytics/CodeGenerationDashboard.vue": 3,
    "autobot-frontend/src/components/analytics/CodeQualityDashboard.vue": 1,
    "autobot-frontend/src/components/analytics/CodebaseAnalytics.vue": 1,
    "autobot-frontend/src/components/analytics/CodebaseDependenciesPanel.vue": 2,
    "autobot-frontend/src/components/analytics/CodebaseOverviewPanel.vue": 1,
    "autobot-frontend/src/components/analytics/CodebaseSecurityPanel.vue": 1,
    "autobot-frontend/src/components/analytics/LLMPatternDashboard.vue": 6,
    "autobot-frontend/src/components/analytics/LogPatternDashboard.vue": 1,
    "autobot-frontend/src/components/analytics/PatternAnalysis.vue": 2,
    "autobot-frontend/src/components/analytics/PrecommitHookDashboard.vue": 4,
    "autobot-frontend/src/components/analytics/ShareSourceModal.vue": 2,
    "autobot-frontend/src/components/analytics/SourceManager.vue": 1,
    "autobot-frontend/src/components/analytics/UnwiredTrackerTile.vue": 2,
    "autobot-frontend/src/components/analytics/panels/CodebaseApiEndpointsPanel.vue": 5,
    "autobot-frontend/src/components/analytics/panels/CodebaseBugPredictionPanel.vue": 10,
    "autobot-frontend/src/components/analytics/panels/CodebaseConfigDuplicatesPanel.vue": 4,
    "autobot-frontend/src/components/analytics/panels/CodebaseCrossLanguagePanel.vue": 9,
    "autobot-frontend/src/components/analytics/panels/CodebaseEnvironmentPanel.vue": 8,
    "autobot-frontend/src/components/analytics/panels/CodebaseIntelligenceScoresPanel.vue": 21,
    "autobot-frontend/src/components/analytics/panels/CodebaseOwnershipPanel.vue": 12,
    "autobot-frontend/src/components/artifact-cells/ChartCell.vue": 4,
    "autobot-frontend/src/components/artifact-cells/CodeCell.vue": 2,
    "autobot-frontend/src/components/async/AsyncComponentWrapper.vue": 1,
    "autobot-frontend/src/components/async/AsyncErrorFallback.vue": 7,
    "autobot-frontend/src/components/autoresearch/ApprovalCard.vue": 6,
    "autobot-frontend/src/components/autoresearch/ExperimentTimeline.vue": 3,
    "autobot-frontend/src/components/autoresearch/InsightsPanel.vue": 6,
    "autobot-frontend/src/components/autoresearch/PromptOptimizerPanel.vue": 12,
    "autobot-frontend/src/components/browser/InteractiveScreenshot.vue": 3,
    "autobot-frontend/src/components/canvas/CanvasCell.vue": 19,
    "autobot-frontend/src/components/canvas/CanvasCellToolbar.vue": 5,
    "autobot-frontend/src/components/canvas/CanvasConflictBanner.vue": 6,
    "autobot-frontend/src/components/canvas/CanvasEdgeStates.vue": 14,
    "autobot-frontend/src/components/canvas/CanvasExportSheet.vue": 8,
    "autobot-frontend/src/components/canvas/CanvasPanel.vue": 1,
    "autobot-frontend/src/components/canvas/CanvasSplitLayout.vue": 1,
    "autobot-frontend/src/components/canvas/CanvasToolPalette.vue": 9,
    "autobot-frontend/src/components/canvas/CanvasView.vue": 1,
    "autobot-frontend/src/components/canvas/CodeCell.vue": 5,
    "autobot-frontend/src/components/charts/FunctionCallGraph.vue": 5,
    "autobot-frontend/src/components/charts/ImportTreeChart.vue": 2,
    "autobot-frontend/src/components/chat/ChatBrowser.vue": 1,
    "autobot-frontend/src/components/chat/ChatFilePanel.vue": 1,
    "autobot-frontend/src/components/chat/ChatInput.vue": 7,
    "autobot-frontend/src/components/chat/ChatInterface.vue": 3,
    "autobot-frontend/src/components/chat/ChatMessages.vue": 1,
    "autobot-frontend/src/components/chat/DeleteConversationDialog.vue": 2,
    "autobot-frontend/src/components/chat/MCPPromptTemplatePicker.vue": 5,
    "autobot-frontend/src/components/chat/McpPromptPicker.vue": 15,
    "autobot-frontend/src/components/chat/MessageItem.vue": 2,
    "autobot-frontend/src/components/chat/OverseerStepMessage.vue": 2,
    "autobot-frontend/src/components/chat/SlashCommandDropdown.vue": 1,
    "autobot-frontend/src/components/desktop/DesktopContextPanel.vue": 1,
    "autobot-frontend/src/components/desktop/DesktopInterface.vue": 13,
    "autobot-frontend/src/components/desktop/PopoutChromiumBrowser.vue": 4,
    "autobot-frontend/src/components/documents/AIDocumentEditor.vue": 11,
    "autobot-frontend/src/components/examples/ThemingPatternExample.vue": 46,
    "autobot-frontend/src/components/file-browser/SandboxFileBrowser.vue": 12,
    "autobot-frontend/src/components/knowledge/ChromaDBExplorer.vue": 24,
    "autobot-frontend/src/components/knowledge/DeduplicationManager.vue": 7,
    "autobot-frontend/src/components/knowledge/GraphRAGQuery.vue": 1,
    "autobot-frontend/src/components/knowledge/KBSearchResultPanel.vue": 15,
    "autobot-frontend/src/components/knowledge/KnowledgeGraph.vue": 1,
    "autobot-frontend/src/components/knowledge/KnowledgeHealth.vue": 2,
    "autobot-frontend/src/components/knowledge/KnowledgeSystemDocs.vue": 1,
    "autobot-frontend/src/components/knowledge/KnowledgeUpload.vue": 4,
    "autobot-frontend/src/components/knowledge/McpResourceBrowser.vue": 10,
    "autobot-frontend/src/components/knowledge/MemoryOrphanManager.vue": 1,
    "autobot-frontend/src/components/knowledge/SessionOrphanManager.vue": 1,
    "autobot-frontend/src/components/knowledge/SystemKnowledgeManager.vue": 19,
    "autobot-frontend/src/components/knowledge/WebResearchSettings.vue": 46,
    "autobot-frontend/src/components/knowledge/connectors/ConnectorConfigModal.vue": 11,
    "autobot-frontend/src/components/knowledge/connectors/ConnectorHistoryPanel.vue": 6,
    "autobot-frontend/src/components/knowledge/web-research/CrawlTab.vue": 1,
    "autobot-frontend/src/components/knowledge/web-research/ExtractTab.vue": 1,
    "autobot-frontend/src/components/knowledge/web-research/ScrapeTab.vue": 2,
    "autobot-frontend/src/components/knowledge/web-research/SiteMapTab.vue": 1,
    "autobot-frontend/src/components/llc/LlcBreadcrumb.vue": 1,
    "autobot-frontend/src/components/llc/TemplateBrowser.vue": 9,
    "autobot-frontend/src/components/manpage/ManPageManager.vue": 3,
    "autobot-frontend/src/components/plugins/CapabilityApprovalDialog.vue": 3,
    "autobot-frontend/src/components/plugins/PluginInstallModal.vue": 1,
    "autobot-frontend/src/components/security/SecretsManager.vue": 2,
    "autobot-frontend/src/components/security/ThreatIntelligenceDashboard.vue": 2,
    "autobot-frontend/src/components/settings/PushNotificationSettingsPanel.vue": 11,
    "autobot-frontend/src/components/settings/SettingsPanel.vue": 2,
    "autobot-frontend/src/components/settings/TelegramSettingsPanel.vue": 13,
    "autobot-frontend/src/components/settings/ThemePresetPicker.vue": 5,
    "autobot-frontend/src/components/terminal/CompletionSuggestions.vue": 1,
    "autobot-frontend/src/components/terminal/SSHTerminal.vue": 3,
    "autobot-frontend/src/components/terminal/TerminalHeader.vue": 2,
    "autobot-frontend/src/components/terminal/TerminalModals.vue": 1,
    "autobot-frontend/src/components/terminal/TerminalOutput.vue": 1,
    "autobot-frontend/src/components/terminal/TerminalStatusBar.vue": 1,
    "autobot-frontend/src/components/terminal/TerminalWindow.vue": 2,
    "autobot-frontend/src/components/theme/EmberThemeToggle.vue": 4,
    "autobot-frontend/src/components/transcriber/AiAnalysisPanel.vue": 6,
    "autobot-frontend/src/components/transcriber/AsrProviderSelector.vue": 14,
    "autobot-frontend/src/components/transcriber/UploadModal.vue": 2,
    "autobot-frontend/src/components/ui/ConfirmDialog.vue": 2,
    "autobot-frontend/src/components/ui/PreferencesPanel.vue": 1,
    "autobot-frontend/src/components/visualizations/ServiceMessageTimeline.vue": 2,
    "autobot-frontend/src/components/workflow/NotificationConfigModal.vue": 2,
    "autobot-frontend/src/components/workflow/PhaseProgressionIndicator.vue": 1,
    "autobot-frontend/src/components/workflow/WorkflowTemplateGallery.vue": 1,
    "autobot-frontend/src/views/AdminMcpServersView.vue": 1,
    "autobot-frontend/src/views/AdminSandboxView.vue": 2,
    "autobot-frontend/src/views/AgentActivity.vue": 9,
    "autobot-frontend/src/views/BusinessIntelligenceView.vue": 2,
    "autobot-frontend/src/views/CanvasView.vue": 1,
    "autobot-frontend/src/views/ComponentShowcaseView.vue": 9,
    "autobot-frontend/src/views/CustomDashboard.vue": 6,
    "autobot-frontend/src/views/DevSpeedupView.vue": 1,
    "autobot-frontend/src/views/ExperimentDashboard.vue": 7,
    "autobot-frontend/src/views/OnboardingWizard.vue": 28,
    "autobot-frontend/src/views/SettingsView.vue": 8,
    "autobot-frontend/src/views/UsageView.vue": 60,
    "autobot-frontend/src/views/secrets/LlmApiKeysView.vue": 1,
    "autobot-frontend/src/views/slm/ThemeManagerView.vue": 3,
    "autobot-frontend/src/views/transcriber/ProjectDetailView.vue": 10,
    "autobot-frontend/src/views/transcriber/ProjectsView.vue": 16,
    "autobot-frontend/src/views/transcriber/TranscriptView.vue": 5,
    "autobot-frontend/src/views/voice/VoiceBundleInfo.vue": 5,
    "autobot-slm-frontend/src/components/DeploymentLogViewer.vue": 4,
    "autobot-slm-frontend/src/components/RoleManagementModal.vue": 1,
    "autobot-slm-frontend/src/components/agents/ProcessMonitorTab.vue": 1,
    "autobot-slm-frontend/src/components/fleet/AssignNPURoleModal.vue": 1,
    "autobot-slm-frontend/src/components/fleet/DecommissionModal.vue": 1,
    "autobot-slm-frontend/src/components/fleet/NPUDetailsPanel.vue": 2,
    "autobot-slm-frontend/src/components/fleet/NodeServicesPanel.vue": 1,
    "autobot-slm-frontend/src/components/monitoring/GrafanaDashboard.vue": 2,
    "autobot-slm-frontend/src/components/orchestration/RestartConfirmDialog.vue": 1,
    "autobot-slm-frontend/src/views/CodeSyncView.vue": 5,
    "autobot-slm-frontend/src/views/DeploymentsView.vue": 21,
    "autobot-slm-frontend/src/views/ExternalAgentsView.vue": 1,
    "autobot-slm-frontend/src/views/MaintenanceView.vue": 9,
    "autobot-slm-frontend/src/views/OrchestrationView.vue": 2,
    "autobot-slm-frontend/src/views/ReplicationView.vue": 2,
    "autobot-slm-frontend/src/views/SecurityView.vue": 21,
    "autobot-slm-frontend/src/views/SetupWizardView.vue": 3,
    "autobot-slm-frontend/src/views/SystemUpdatesTab.vue": 5,
    "autobot-slm-frontend/src/views/monitoring/AlertsMonitor.vue": 1,
    "autobot-slm-frontend/src/views/monitoring/ErrorMonitor.vue": 1,
    "autobot-slm-frontend/src/views/settings/APISettings.vue": 1,
    "autobot-slm-frontend/src/views/settings/BackendSettings.vue": 2,
    "autobot-slm-frontend/src/views/settings/DisposalPolicySettings.vue": 1,
    "autobot-slm-frontend/src/views/settings/GeneralSettings.vue": 3,
    "autobot-slm-frontend/src/views/settings/MonitoringSettings.vue": 1,
    "autobot-slm-frontend/src/views/settings/NotificationsSettings.vue": 2,
    "autobot-slm-frontend/src/views/settings/SecuritySettings.vue": 6,
    "autobot-slm-frontend/src/views/settings/admin/CacheSettings.vue": 5,
    "autobot-slm-frontend/src/views/settings/admin/ConfigDefaultsSettings.vue": 4,
    "autobot-slm-frontend/src/views/settings/admin/DataHygieneView.vue": 1,
    "autobot-slm-frontend/src/views/settings/admin/LLMSettings.vue": 2,
    "autobot-slm-frontend/src/views/settings/admin/LogForwardingSettings.vue": 4,
    "autobot-slm-frontend/src/views/settings/admin/NPUWorkersSettings.vue": 4,
    "autobot-slm-frontend/src/views/settings/admin/PromptsSettings.vue": 4,
    "autobot-slm-frontend/src/views/settings/admin/SSOSettings.vue": 2,
    "autobot-slm-frontend/src/views/settings/admin/UserManagementSettings.vue": 6,
    "autobot-slm-frontend/src/views/tools/admin/BatchTool.vue": 3,
    "autobot-slm-frontend/src/views/tools/admin/MCPTool.vue": 1,
    "autobot-slm-frontend/src/views/tools/admin/NoVNCTool.vue": 1,
    "autobot-slm-frontend/src/views/tools/admin/VisionTool.vue": 1,
    "autobot-slm-frontend/src/views/tools/admin/VoiceTool.vue": 4,
}
