// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { readFile } from "node:fs/promises";

import { makeDiagnostic } from "../diagnostic.mjs";

export const RULE_ID = "ds-font-size-literal";
export const ISSUE = "#19907";
//: `block`: every file holding a literal is recorded below with its count, so any hit is a new one.
export const SEVERITY = "block";
export const TARGETS = ["autobot-frontend/src", "autobot-slm-frontend/src", "libs/autobot-ui/src"];
export const EXTENSIONS = [".vue", ".css"];
export const DESCRIPTION =
  "a literal absolute font-size (rem, px, pt) -- type size is decided by the --text-* / --font-size-* / --aui-text-* scale, and a size written in place drifts from the scale around it";
export const FIX_HINT =
  "Use var(--text-*) or var(--font-size-*) in the apps, var(--aui-text-*) in the kit (design-tokens.css / libs/autobot-ui/src/tokens/contract.css). Use the token whose value equals the size; add a token to the scale once, never a number to a file. Relative sizes (em, %) are not covered";

//: Files not yet converted. Recorded by file with the count of literal
//: declarations, so the rule can land before the conversion finishes. Lower or
//: remove an entry in the PR that converts the file; a file with MORE literals
//: than recorded is reported again. A size with no token of equal value stays
//: here until the scale gains one.
const WAIVED_FILES = new Map([
  ["autobot-frontend/src/components/admin/HealthBar.vue", { count: 2, pr: "#19907" }],
  ["autobot-frontend/src/components/agents/AgentTaskDetail.vue", { count: 2, pr: "#19907" }],
  ["autobot-frontend/src/components/agents/HeartbeatPanel.vue", { count: 3, pr: "#19907" }],
  ["autobot-frontend/src/components/analytics/AdvancedAnalytics.vue", { count: 1, pr: "#19907" }],
  ["autobot-frontend/src/components/analytics/CodeEvolutionTimeline.vue", { count: 1, pr: "#19907" }],
  ["autobot-frontend/src/components/analytics/CodeGenerationDashboard.vue", { count: 5, pr: "#19907" }],
  ["autobot-frontend/src/components/analytics/CodeReviewDashboard.vue", { count: 8, pr: "#19907" }],
  ["autobot-frontend/src/components/analytics/ConversationFlowDashboard.vue", { count: 2, pr: "#19907" }],
  ["autobot-frontend/src/components/analytics/LLMPatternDashboard.vue", { count: 6, pr: "#19907" }],
  ["autobot-frontend/src/components/analytics/LogPatternDashboard.vue", { count: 10, pr: "#19907" }],
  ["autobot-frontend/src/components/analytics/PerformanceAnalysisDashboard.vue", { count: 13, pr: "#19907" }],
  ["autobot-frontend/src/components/analytics/PrecommitHookDashboard.vue", { count: 9, pr: "#19907" }],
  ["autobot-frontend/src/components/analytics/SourceManager.vue", { count: 1, pr: "#19907" }],
  ["autobot-frontend/src/components/analytics/TechnicalDebtDashboard.vue", { count: 2, pr: "#19907" }],
  ["autobot-frontend/src/components/analytics/panels/CodebaseApiEndpointsPanel.vue", { count: 5, pr: "#19907" }],
  ["autobot-frontend/src/components/analytics/panels/CodebaseChartsSection.vue", { count: 1, pr: "#19907" }],
  ["autobot-frontend/src/components/analytics/panels/CodebaseCrossLanguagePanel.vue", { count: 6, pr: "#19907" }],
  ["autobot-frontend/src/components/artifact-cells/ImageCell.vue", { count: 1, pr: "#19907" }],
  ["autobot-frontend/src/components/artifact-cells/VideoCell.vue", { count: 2, pr: "#19907" }],
  ["autobot-frontend/src/components/browser/InteractiveScreenshot.vue", { count: 3, pr: "#19907" }],
  ["autobot-frontend/src/components/charts/FunctionCallGraph.vue", { count: 2, pr: "#19907" }],
  ["autobot-frontend/src/components/charts/ImportTreeChart.vue", { count: 10, pr: "#19907" }],
  ["autobot-frontend/src/components/chat/ChatInput.vue", { count: 6, pr: "#19907" }],
  ["autobot-frontend/src/components/chat/DocumentationCategoryFilter.vue", { count: 6, pr: "#19907" }],
  ["autobot-frontend/src/components/chat/DocumentationResultCard.vue", { count: 2, pr: "#19907" }],
  ["autobot-frontend/src/components/chat/DocumentationSearchSidebar.vue", { count: 6, pr: "#19907" }],
  ["autobot-frontend/src/components/chat/DocumentationSuggestionChip.vue", { count: 2, pr: "#19907" }],
  ["autobot-frontend/src/components/chat/MultiModelChat.vue", { count: 6, pr: "#19907" }],
  ["autobot-frontend/src/components/chat/ReasoningTrace.vue", { count: 6, pr: "#19907" }],
  ["autobot-frontend/src/components/chat/VoiceConversationOverlay.vue", { count: 9, pr: "#19907" }],
  ["autobot-frontend/src/components/chat/VoiceConversationPanel.vue", { count: 5, pr: "#19907" }],
  ["autobot-frontend/src/components/documents/AIDocumentEditor.vue", { count: 5, pr: "#19907" }],
  ["autobot-frontend/src/components/feature-flags/AccessMetrics.vue", { count: 1, pr: "#19907" }],
  ["autobot-frontend/src/components/feature-flags/EndpointEnforcement.vue", { count: 1, pr: "#19907" }],
  ["autobot-frontend/src/components/feature-flags/EnforcementModeSelector.vue", { count: 1, pr: "#19907" }],
  ["autobot-frontend/src/components/file-browser/SandboxFileBrowser.vue", { count: 5, pr: "#19907" }],
  ["autobot-frontend/src/components/file-browser/SandboxTreeNode.vue", { count: 2, pr: "#19907" }],
  ["autobot-frontend/src/components/knowledge/BackupManager.vue", { count: 1, pr: "#19907" }],
  ["autobot-frontend/src/components/knowledge/BulkActionsToolbar.vue", { count: 1, pr: "#19907" }],
  ["autobot-frontend/src/components/knowledge/DocumentChangeFeed.vue", { count: 1, pr: "#19907" }],
  ["autobot-frontend/src/components/knowledge/KnowledgeBrowser.vue", { count: 2, pr: "#19907" }],
  ["autobot-frontend/src/components/knowledge/KnowledgeDocumentsBranch.vue", { count: 8, pr: "#19907" }],
  ["autobot-frontend/src/components/knowledge/KnowledgeGraph.vue", { count: 3, pr: "#19907" }],
  ["autobot-frontend/src/components/knowledge/KnowledgeHealth.vue", { count: 1, pr: "#19907" }],
  ["autobot-frontend/src/components/knowledge/KnowledgeResearchPanel.vue", { count: 1, pr: "#19907" }],
  ["autobot-frontend/src/components/knowledge/KnowledgeScopeSelector.vue", { count: 1, pr: "#19907" }],
  ["autobot-frontend/src/components/knowledge/KnowledgeUpload.vue", { count: 2, pr: "#19907" }],
  ["autobot-frontend/src/components/knowledge/KnowledgeVerificationQueue.vue", { count: 1, pr: "#19907" }],
  ["autobot-frontend/src/components/knowledge/VectorizationStatusBadge.vue", { count: 1, pr: "#19907" }],
  ["autobot-frontend/src/components/knowledge/WebResearchPanel.vue", { count: 12, pr: "#19907" }],
  ["autobot-frontend/src/components/knowledge/connectors/ConnectorStatusCard.vue", { count: 1, pr: "#19907" }],
  ["autobot-frontend/src/components/knowledge/modals/BulkEditModal.vue", { count: 1, pr: "#19907" }],
  ["autobot-frontend/src/components/knowledge/modals/CategoryEditModal.vue", { count: 1, pr: "#19907" }],
  ["autobot-frontend/src/components/knowledge/panels/SourcePreviewPanel.vue", { count: 2, pr: "#19907" }],
  ["autobot-frontend/src/components/knowledge/temporal/EventTimeline.vue", { count: 1, pr: "#19907" }],
  ["autobot-frontend/src/components/llc/HandoffModal.vue", { count: 2, pr: "#19907" }],
  ["autobot-frontend/src/components/llc/HireAgentModal.vue", { count: 2, pr: "#19907" }],
  ["autobot-frontend/src/components/llc/LlcSidebar.vue", { count: 2, pr: "#19907" }],
  ["autobot-frontend/src/components/llc/WorkItemBadge.vue", { count: 2, pr: "#19907" }],
  ["autobot-frontend/src/components/manpage/IntegrationStatusPanel.vue", { count: 1, pr: "#19907" }],
  ["autobot-frontend/src/components/operations/OperationProgress.vue", { count: 1, pr: "#19907" }],
  ["autobot-frontend/src/components/plugins/SchemaForm.vue", { count: 7, pr: "#19907" }],
  ["autobot-frontend/src/components/profile/DeviceManagementPanel.vue", { count: 3, pr: "#19907" }],
  ["autobot-frontend/src/components/schedulers/SchedulerToggles.vue", { count: 3, pr: "#19907" }],
  ["autobot-frontend/src/components/security/SecretsManager.vue", { count: 3, pr: "#19907" }],
  ["autobot-frontend/src/components/security/ThreatIntelligenceDashboard.vue", { count: 1, pr: "#19907" }],
  ["autobot-frontend/src/components/settings/ApiKeySetupWizard.vue", { count: 8, pr: "#19907" }],
  ["autobot-frontend/src/components/settings/MemoryPrivacyPanel.vue", { count: 3, pr: "#19907" }],
  ["autobot-frontend/src/components/settings/ProviderOAuthConnect.vue", { count: 10, pr: "#19907" }],
  ["autobot-frontend/src/components/terminal/AdvancedStepConfirmationModal.vue", { count: 5, pr: "#19907" }],
  ["autobot-frontend/src/components/vision/GUIAutomationControls.vue", { count: 1, pr: "#19907" }],
  ["autobot-frontend/src/components/vision/MediaGallery.vue", { count: 2, pr: "#19907" }],
  ["autobot-frontend/src/components/vision/ScreenCaptureViewer.vue", { count: 1, pr: "#19907" }],
  ["autobot-frontend/src/components/vision/VideoProcessor.vue", { count: 1, pr: "#19907" }],
  ["autobot-frontend/src/components/visualizations/AgentActivityVisualization.vue", { count: 2, pr: "#19907" }],
  ["autobot-frontend/src/components/workflow/AgentObservabilityPanel.vue", { count: 1, pr: "#19907" }],
  ["autobot-frontend/src/components/workflow/OrchestrationVisualizer.vue", { count: 1, pr: "#19907" }],
  ["autobot-frontend/src/components/workflow/WorkflowCanvas.vue", { count: 3, pr: "#19907" }],
  ["autobot-frontend/src/components/workflow/WorkflowHistory.vue", { count: 1, pr: "#19907" }],
  ["autobot-frontend/src/components/workflow/WorkflowLiveDashboard.vue", { count: 5, pr: "#19907" }],
  ["autobot-frontend/src/components/workflow/WorkflowNotificationConfig.vue", { count: 3, pr: "#19907" }],
  ["autobot-frontend/src/components/workflow/WorkflowRunner.vue", { count: 1, pr: "#19907" }],
  ["autobot-frontend/src/components/workflow/WorkflowTemplateGallery.vue", { count: 1, pr: "#19907" }],
  ["autobot-frontend/src/design-system/styles/dashboard-common.css", { count: 1, pr: "#19907" }],
  ["autobot-frontend/src/design-system/styles/dashboard-review-precommit.css", { count: 1, pr: "#19907" }],
  ["autobot-frontend/src/design-system/styles/panel-dependencies-charts-shared.css", { count: 9, pr: "#19907" }],
  ["autobot-frontend/src/views/AdminUsersView.vue", { count: 3, pr: "#19907" }],
  ["autobot-frontend/src/views/BudgetPolicies.vue", { count: 1, pr: "#19907" }],
  ["autobot-frontend/src/views/ComponentShowcaseView.vue", { count: 1, pr: "#19907" }],
  ["autobot-frontend/src/views/CustomDashboard.vue", { count: 3, pr: "#19907" }],
  ["autobot-frontend/src/views/ErrorMonitoringView.vue", { count: 20, pr: "#19907" }],
  ["autobot-frontend/src/views/KnowledgeView.vue", { count: 1, pr: "#19907" }],
  ["autobot-frontend/src/views/OnboardingWizard.vue", { count: 6, pr: "#19907" }],
  ["autobot-frontend/src/views/VisionAutomationView.vue", { count: 24, pr: "#19907" }],
  ["autobot-frontend/src/views/WorkflowBuilderView.vue", { count: 2, pr: "#19907" }],
  ["autobot-frontend/src/views/llc/ActivityFeedView.vue", { count: 3, pr: "#19907" }],
  ["autobot-frontend/src/views/llc/ApprovalsInbox.vue", { count: 3, pr: "#19907" }],
  ["autobot-frontend/src/views/llc/BacklogView.vue", { count: 5, pr: "#19907" }],
  ["autobot-frontend/src/views/llc/BoardsView.vue", { count: 4, pr: "#19907" }],
  ["autobot-frontend/src/views/llc/CompanyCreationWizard.vue", { count: 1, pr: "#19907" }],
  ["autobot-frontend/src/views/llc/CompanyPortabilityView.vue", { count: 1, pr: "#19907" }],
  ["autobot-frontend/src/views/llc/CompanySecretsView.vue", { count: 5, pr: "#19907" }],
  ["autobot-frontend/src/views/llc/CompanySelectorView.vue", { count: 3, pr: "#19907" }],
  ["autobot-frontend/src/views/llc/CostDashboard.vue", { count: 10, pr: "#19907" }],
  ["autobot-frontend/src/views/llc/GanttTimelineView.vue", { count: 7, pr: "#19907" }],
  ["autobot-frontend/src/views/llc/HeartbeatMonitor.vue", { count: 12, pr: "#19907" }],
  ["autobot-frontend/src/views/llc/KanbanBoardView.vue", { count: 6, pr: "#19907" }],
  ["autobot-frontend/src/views/llc/MembersView.vue", { count: 1, pr: "#19907" }],
  ["autobot-frontend/src/views/llc/PortfolioBrowserView.vue", { count: 2, pr: "#19907" }],
  ["autobot-frontend/src/views/llc/ProgramBrowserView.vue", { count: 2, pr: "#19907" }],
  ["autobot-frontend/src/views/llc/ProjectBrowserView.vue", { count: 7, pr: "#19907" }],
  ["autobot-frontend/src/views/llc/ReviewInboxView.vue", { count: 3, pr: "#19907" }],
  ["autobot-frontend/src/views/llc/RoutinesView.vue", { count: 4, pr: "#19907" }],
  ["autobot-frontend/src/views/llc/SprintBoardView.vue", { count: 8, pr: "#19907" }],
  ["autobot-frontend/src/views/llc/WorkItemDetail.vue", { count: 16, pr: "#19907" }],
  ["autobot-frontend/src/views/transcriber/ProjectDetailView.vue", { count: 3, pr: "#19907" }],
  ["autobot-frontend/src/views/transcriber/ProjectsView.vue", { count: 5, pr: "#19907" }],
  ["autobot-frontend/src/views/voice/VoiceBundleInfo.vue", { count: 1, pr: "#19907" }],
  ["autobot-slm-frontend/src/components/RoleManagementModal.vue", { count: 3, pr: "#19907" }],
  ["autobot-slm-frontend/src/components/agents/ConfigHistoryTab.vue", { count: 6, pr: "#19907" }],
  ["autobot-slm-frontend/src/components/agents/OrgChartTab.vue", { count: 10, pr: "#19907" }],
  ["autobot-slm-frontend/src/components/agents/OrgTreeNode.vue", { count: 2, pr: "#19907" }],
  ["autobot-slm-frontend/src/components/agents/ProcessMonitorTab.vue", { count: 3, pr: "#19907" }],
  ["autobot-slm-frontend/src/components/common/CodeSyncBadge.vue", { count: 1, pr: "#19907" }],
  ["autobot-slm-frontend/src/components/common/Sidebar.vue", { count: 1, pr: "#19907" }],
  ["autobot-slm-frontend/src/components/fleet/DecommissionModal.vue", { count: 4, pr: "#19907" }],
  ["autobot-slm-frontend/src/components/monitoring/GrafanaDashboard.vue", { count: 2, pr: "#19907" }],
  ["autobot-slm-frontend/src/views/AgentsView.vue", { count: 5, pr: "#19907" }],
  ["autobot-slm-frontend/src/views/SetupWizardView.vue", { count: 17, pr: "#19907" }],
  ["autobot-slm-frontend/src/views/UpdatesView.vue", { count: 1, pr: "#19907" }],
]);

export const waivedFilesForTest = () => new Map(WAIVED_FILES);

const DECLARATION = /(?<![\w-])font-size\s*:\s*([^;}]*)/g;
const LINE_WAIVER = /canonical:\s*ignore\s+ds-font-size-literal\b/;
const COMMENT_LINE = /^\s*(?:\*|\/\/|\/\*|<!--)/;
//: A reference to a custom property with no fallback -- the only way a size may be spelled.
const TOKEN_REF = /var\(\s*--[\w-]+\s*\)/g;
//: An absolute length. em and % are relative to the parent and have no token, so they are not literals here.
const ABSOLUTE_LENGTH = /\d(?:\.\d+)?(?:rem|px|pt)\b/;

/** A value is a literal when, token references removed, an absolute length is left (a token fallback counts). */
export function isLiteral(value) {
  return ABSOLUTE_LENGTH.test(value.replace(TOKEN_REF, ""));
}

export async function check(filePath) {
  let text;
  try {
    text = await readFile(filePath, "utf-8");
  } catch {
    return [];
  }
  const norm = filePath.split("\\").join("/");
  const waiver = [...WAIVED_FILES].find(([f]) => norm.endsWith(f))?.[1];
  const hits = [];
  text.split(/\r?\n/).forEach((line, idx) => {
    if (COMMENT_LINE.test(line) || LINE_WAIVER.test(line)) return;
    for (const m of line.matchAll(DECLARATION)) {
      if (isLiteral(m[1])) hits.push({ idx, col: m.index, line });
    }
  });
  return hits.slice(waiver ? waiver.count : 0).map(({ idx, col, line }) =>
    makeDiagnostic({
      ruleId: RULE_ID,
      issue: ISSUE,
      severity: SEVERITY,
      file: filePath,
      line: idx + 1,
      col,
      message: "literal font-size -- use a --text-* / --font-size-* / --aui-text-* token",
      snippet: line.trim().slice(0, 120),
      fixHint: FIX_HINT,
    }),
  );
}
