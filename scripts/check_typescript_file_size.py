#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Pre-commit hook: reject oversized `.ts`/`.vue` files (#17885).

Named for the LANGUAGE, not for `autobot-frontend/`, because that is what it measures: the
glob is every tracked `.ts`/`.vue` file, and 3 of the 184 recorded are TypeScript outside both
frontends -- a VS Code extension and two MCP tools under `autobot-infrastructure/`. The first
draft called this the "frontend" gate and would have shipped a name narrower than its own
scope, which is the mismatch its siblings avoid by being called python- and shell-file-size.

The third configuration of `tools/lint/file_size_engine.py`, after the Python (#5060) and
shell (#17353) gates. Nothing measured `.ts`/`.vue` length before this: the only two size
hooks in `.pre-commit-config.yaml` were those two, `function-length-check` is
``types: [python]``, and no ESLint `max-lines` rule exists in either frontend. A frontend
file did not pass a size rule -- nothing asked.

The ceilings below came from this gate's own first run over the tree, not from a number
chosen in advance. Generated output is excluded by prefix rather than by entry, because
`types/generated/api.ts` is 178,894 lines and recording that as a ceiling would make the
record look like a decision.
"""

from __future__ import annotations

import argparse
import logging
import pathlib
import sys

logger = logging.getLogger(__name__)

# scripts/ is not a package; put the repo root on the path so the engine is importable when
# this runs as a bare hook.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from tools.lint import file_size_engine as engine  # noqa: E402
from tools.lint.file_size_engine import GateConfig  # noqa: E402

MAX_LINES = 600

#: Repo-relative path of this hook, quoted in every message that asks for an edit.
SELF_REL = "scripts/check_typescript_file_size.py"

#: The data module holding RATCHET_BASELINE, the second copy of these numbers. Two
#: hand-kept records on purpose: neither derives from the other, so no ceiling can be raised
#: by editing one file alone (#17872).
RATCHET_REL = "repo_tests/typescript_file_size_ratchet_baseline.py"

#: Out of scope, mirroring this hook's ``exclude:`` in ``.pre-commit-config.yaml``.
#: ``types/generated/`` is emitted by the OpenAPI generator -- 178,894 lines in one frontend
#: and 26,572 in the other -- and a generated file cannot be split by its author.
EXCLUDED_PREFIXES = (
    ".worktrees/",
    "autobot-frontend/src/types/generated/",
    "autobot-slm-frontend/src/types/generated/",
)

#: Floor for the tree walk: below this it stopped covering the frontends (#14547).
MIN_TRACKED_TS_FILES = 1200

#: Grandfathered files: over MAX_LINES when this gate landed, mapped to the line count
#: recorded for each. THIS MAPPING ONLY SHRINKS -- entries leave when a file reaches
#: MAX_LINES, and a ceiling may be lowered but never raised. Never add an entry to make a new
#: file pass; split the file instead.
#:
#: All 184 came from this gate's own first run over the tree (#17885), not from a number chosen
#: RE-TAKE these before landing: see the baseline module's note on first
#: measurement versus ratchet step -- a record generated from one tree and landed against
#: another is stale by construction (#17885).
#: in advance: 1,779 tracked `.ts`/`.vue` files in scope, 184 of them over 600 lines, the
#: largest at 2,947. Mirrored in ``repo_tests/typescript_file_size_ratchet_baseline.py`` -- lower
#: an entry here and lower it there in the same commit, or the lines just cut stay spendable in
#: the gap between the two (#17872).
KNOWN_LARGE: dict[str, int] = {
    "autobot-frontend/src/App.vue": 1168,
    "autobot-frontend/src/components/__tests__/ChatInterface.test.ts": 760,
    "autobot-frontend/src/components/__tests__/TerminalWindow.test.ts": 627,
    "autobot-frontend/src/components/agents/HeartbeatPanel.vue": 723,
    "autobot-frontend/src/components/analytics/AdvancedAnalytics.vue": 903,
    "autobot-frontend/src/components/analytics/CodeEvolutionTimeline.vue": 775,
    "autobot-frontend/src/components/analytics/CodeGenerationDashboard.vue": 1108,
    "autobot-frontend/src/components/analytics/CodeQualityDashboard.vue": 1903,
    "autobot-frontend/src/components/analytics/CodeReviewDashboard.vue": 1221,
    "autobot-frontend/src/components/analytics/CodebaseAnalytics.vue": 1295,
    "autobot-frontend/src/components/analytics/CodebaseAnalyticsLanding.vue": 763,
    "autobot-frontend/src/components/analytics/ConversationFlowDashboard.vue": 909,
    "autobot-frontend/src/components/analytics/LLMPatternDashboard.vue": 1080,
    "autobot-frontend/src/components/analytics/LogPatternDashboard.vue": 952,
    "autobot-frontend/src/components/analytics/PatternAnalysis.vue": 982,
    "autobot-frontend/src/components/analytics/PerformanceAnalysisDashboard.vue": 1075,
    "autobot-frontend/src/components/analytics/PrecommitHookDashboard.vue": 1097,
    "autobot-frontend/src/components/analytics/SourceManager.vue": 867,
    "autobot-frontend/src/components/analytics/TechnicalDebtDashboard.vue": 1819,
    "autobot-frontend/src/components/analytics/panels/CodebaseBugPredictionPanel.vue": 802,
    "autobot-frontend/src/components/analytics/panels/CodebaseCrossLanguagePanel.vue": 656,
    "autobot-frontend/src/components/analytics/panels/CodebaseIntelligenceScoresPanel.vue": 1421,
    "autobot-frontend/src/components/analytics/panels/CodebaseOwnershipPanel.vue": 1035,
    "autobot-frontend/src/components/audit/AuditLogTable.vue": 758,
    "autobot-frontend/src/components/browser/BrowserSessionManager.vue": 654,
    "autobot-frontend/src/components/charts/BaseChart.vue": 602,
    "autobot-frontend/src/components/charts/FunctionCallGraph.vue": 2165,
    "autobot-frontend/src/components/charts/ImportTreeChart.vue": 1365,
    "autobot-frontend/src/components/chat/ChatInput.vue": 1716,
    "autobot-frontend/src/components/chat/ChatInterface.vue": 1519,
    "autobot-frontend/src/components/chat/ChatMessages.vue": 2122,
    "autobot-frontend/src/components/chat/ChatSidebar.vue": 808,
    "autobot-frontend/src/components/chat/DocumentationSearchSidebar.vue": 766,
    "autobot-frontend/src/components/chat/VisionAnalysisModal.vue": 786,
    "autobot-frontend/src/components/chat/VisualBrowserPanel.vue": 632,
    "autobot-frontend/src/components/chat/VoiceConversationOverlay.vue": 916,
    "autobot-frontend/src/components/chat/VoiceConversationPanel.vue": 649,
    "autobot-frontend/src/components/desktop/DesktopInterface.vue": 894,
    "autobot-frontend/src/components/desktop/PopoutChromiumBrowser.vue": 1229,
    "autobot-frontend/src/components/examples/ThemingPatternExample.vue": 603,
    "autobot-frontend/src/components/feature-flags/AccessMetrics.vue": 729,
    "autobot-frontend/src/components/feature-flags/EndpointEnforcement.vue": 701,
    "autobot-frontend/src/components/file-browser/FileBrowser.vue": 736,
    "autobot-frontend/src/components/knowledge/ChromaDBExplorer.vue": 1158,
    "autobot-frontend/src/components/knowledge/DocumentChangeFeed.vue": 601,
    "autobot-frontend/src/components/knowledge/EntityExtractor.vue": 781,
    "autobot-frontend/src/components/knowledge/EntityGraphManager.vue": 692,
    "autobot-frontend/src/components/knowledge/GraphConnectionPath.vue": 701,
    "autobot-frontend/src/components/knowledge/GraphRAGQuery.vue": 713,
    "autobot-frontend/src/components/knowledge/KBSearchResultPanel.vue": 630,
    "autobot-frontend/src/components/knowledge/KnowledgeBrowser.vue": 1785,
    "autobot-frontend/src/components/knowledge/KnowledgeEntries.vue": 1360,
    "autobot-frontend/src/components/knowledge/KnowledgeGraph.vue": 2073,
    "autobot-frontend/src/components/knowledge/KnowledgeHealth.vue": 925,
    "autobot-frontend/src/components/knowledge/KnowledgePersistenceDialog.vue": 892,
    "autobot-frontend/src/components/knowledge/KnowledgeResearchPanel.vue": 1200,
    "autobot-frontend/src/components/knowledge/KnowledgeSystemDocs.vue": 863,
    "autobot-frontend/src/components/knowledge/KnowledgeUpload.vue": 1634,
    "autobot-frontend/src/components/knowledge/KnowledgeVerificationQueue.vue": 799,
    "autobot-frontend/src/components/knowledge/SystemKnowledgeManager.vue": 1035,
    "autobot-frontend/src/components/knowledge/WebResearchPanel.vue": 779,
    "autobot-frontend/src/components/knowledge/WebResearchSettings.vue": 1028,
    "autobot-frontend/src/components/knowledge/connectors/ConnectorConfigModal.vue": 1627,
    "autobot-frontend/src/components/knowledge/modals/BulkEditModal.vue": 616,
    "autobot-frontend/src/components/knowledge/modals/CategoryEditModal.vue": 727,
    "autobot-frontend/src/components/llc/TemplateBrowser.vue": 806,
    "autobot-frontend/src/components/manpage/ManPageManager.vue": 1214,
    "autobot-frontend/src/components/security/SecretsManager.vue": 2947,
    "autobot-frontend/src/components/security/ThreatIntelligenceDashboard.vue": 838,
    "autobot-frontend/src/components/security/ThreatIntelligenceSettings.vue": 652,
    "autobot-frontend/src/components/settings/ApiKeySetupWizard.vue": 614,
    "autobot-frontend/src/components/settings/SettingsPanel.vue": 943,
    "autobot-frontend/src/components/settings/ThemePresetPicker.vue": 621,
    "autobot-frontend/src/components/terminal/AdvancedStepConfirmationModal.vue": 616,
    "autobot-frontend/src/components/terminal/BaseXTerminal.vue": 825,
    "autobot-frontend/src/components/terminal/TerminalModals.vue": 743,
    "autobot-frontend/src/components/terminal/TerminalWindow.vue": 1787,
    "autobot-frontend/src/components/ui/HostSelectionDialog.vue": 965,
    "autobot-frontend/src/components/vision/GUIAutomationControls.vue": 793,
    "autobot-frontend/src/components/vision/MediaGallery.vue": 843,
    "autobot-frontend/src/components/vision/ScreenCaptureViewer.vue": 836,
    "autobot-frontend/src/components/vision/VideoProcessor.vue": 897,
    "autobot-frontend/src/components/visualizations/AgentActivityVisualization.vue": 959,
    "autobot-frontend/src/components/visualizations/SystemArchitectureDiagram.vue": 1881,
    "autobot-frontend/src/components/visualizations/WorkflowVisualization.vue": 1020,
    "autobot-frontend/src/components/workflow/PhaseProgressionIndicator.vue": 634,
    "autobot-frontend/src/components/workflow/WorkflowCanvas.vue": 2884,
    "autobot-frontend/src/components/workflow/WorkflowLiveDashboard.vue": 782,
    "autobot-frontend/src/composables/__tests__/useClipboard.test.ts": 696,
    "autobot-frontend/src/composables/__tests__/useConnectionTester.test.ts": 944,
    "autobot-frontend/src/composables/__tests__/useErrorHandler.test.ts": 1901,
    "autobot-frontend/src/composables/__tests__/useFormValidation.test.ts": 1009,
    "autobot-frontend/src/composables/__tests__/useKeyboard.test.ts": 1123,
    "autobot-frontend/src/composables/__tests__/useKnowledgeVectorization.test.ts": 656,
    "autobot-frontend/src/composables/__tests__/useLocalStorage.test.ts": 1007,
    "autobot-frontend/src/composables/__tests__/useModal.test.ts": 761,
    "autobot-frontend/src/composables/__tests__/usePagination.test.ts": 808,
    "autobot-frontend/src/composables/__tests__/useTimeout.test.ts": 1211,
    "autobot-frontend/src/composables/analytics/useAnalyticsDataFetchers.ts": 707,
    "autobot-frontend/src/composables/useKeyboard.ts": 650,
    "autobot-frontend/src/composables/useKnowledgeVectorization.ts": 679,
    "autobot-frontend/src/composables/usePatternAnalysis.ts": 900,
    "autobot-frontend/src/composables/usePrometheusMetrics.ts": 643,
    "autobot-frontend/src/composables/useSystemStatus.ts": 622,
    "autobot-frontend/src/composables/useTheme.ts": 610,
    "autobot-frontend/src/composables/useTimeout.ts": 749,
    "autobot-frontend/src/composables/useVoiceConversation.ts": 980,
    "autobot-frontend/src/composables/useVoiceOutput.ts": 995,
    "autobot-frontend/src/composables/useWorkflowBuilder.ts": 1305,
    "autobot-frontend/src/config/__tests__/ssot-config.spec.ts": 678,
    "autobot-frontend/src/config/ssot-config.ts": 860,
    "autobot-frontend/src/models/controllers/ChatController.ts": 1158,
    "autobot-frontend/src/models/controllers/KnowledgeController.ts": 645,
    "autobot-frontend/src/models/repositories/ChatRepository.ts": 675,
    "autobot-frontend/src/models/repositories/KnowledgeRepository.ts": 897,
    "autobot-frontend/src/router/index.ts": 1633,
    "autobot-frontend/src/services/GlobalWebSocketService.ts": 909,
    "autobot-frontend/src/services/TerminalService.ts": 1137,
    "autobot-frontend/src/stores/useChatStore.ts": 1174,
    "autobot-frontend/src/stores/useKnowledgeStore.ts": 809,
    "autobot-frontend/src/utils/ApiClient.ts": 842,
    "autobot-frontend/src/utils/RumAgent.ts": 869,
    "autobot-frontend/src/utils/VisionMultimodalApiClient.ts": 663,
    "autobot-frontend/src/utils/debugUtils.ts": 620,
    "autobot-frontend/src/views/AdminUsersView.vue": 833,
    "autobot-frontend/src/views/AdvancedControlView.vue": 1103,
    "autobot-frontend/src/views/BudgetPolicies.vue": 940,
    "autobot-frontend/src/views/BusinessIntelligenceView.vue": 988,
    "autobot-frontend/src/views/CustomDashboard.vue": 1106,
    "autobot-frontend/src/views/DevSpeedupView.vue": 672,
    "autobot-frontend/src/views/ErrorMonitoringView.vue": 872,
    "autobot-frontend/src/views/EvolutionView.vue": 781,
    "autobot-frontend/src/views/FailureAnalysisDashboard.vue": 799,
    "autobot-frontend/src/views/MarketplaceView.vue": 711,
    "autobot-frontend/src/views/OnboardingWizard.vue": 884,
    "autobot-frontend/src/views/PluginsView.vue": 1094,
    "autobot-frontend/src/views/SettingsView.vue": 784,
    "autobot-frontend/src/views/VisionAutomationView.vue": 873,
    "autobot-frontend/src/views/WorkflowBuilderView.vue": 2300,
    "autobot-frontend/src/views/llc/BacklogView.vue": 842,
    "autobot-frontend/src/views/llc/CompanyCreationWizard.vue": 909,
    "autobot-frontend/src/views/llc/CompanyPortabilityView.vue": 867,
    "autobot-frontend/src/views/llc/CostDashboard.vue": 1017,
    "autobot-frontend/src/views/llc/GanttTimelineView.vue": 817,
    "autobot-frontend/src/views/llc/HeartbeatMonitor.vue": 807,
    "autobot-frontend/src/views/llc/OrgChart.vue": 1527,
    "autobot-frontend/src/views/llc/ProjectBrowserView.vue": 1379,
    "autobot-frontend/src/views/llc/RolesView.vue": 1030,
    "autobot-frontend/src/views/llc/RoutinesView.vue": 691,
    "autobot-frontend/src/views/llc/SprintBoardView.vue": 681,
    "autobot-frontend/src/views/llc/WorkItemDetail.vue": 1069,
    "autobot-infrastructure/shared/ide-extensions/vscode-autobot/src/extension.ts": 741,
    "autobot-infrastructure/shared/mcp/tools/mcp-autobot-tracker/src/background-monitor.ts": 713,
    "autobot-infrastructure/shared/mcp/tools/mcp-autobot-tracker/src/index.ts": 957,
    "autobot-slm-frontend/src/components/AddNodeModal.vue": 1188,
    "autobot-slm-frontend/src/components/RoleManagementModal.vue": 614,
    "autobot-slm-frontend/src/components/fleet/DecommissionModal.vue": 699,
    "autobot-slm-frontend/src/components/fleet/NodeLifecyclePanel.vue": 984,
    "autobot-slm-frontend/src/composables/useAutobotApi.ts": 2092,
    "autobot-slm-frontend/src/composables/useCodeSync.ts": 1078,
    "autobot-slm-frontend/src/composables/useOrchestrationManagement.ts": 693,
    "autobot-slm-frontend/src/composables/usePrometheusMetrics.ts": 622,
    "autobot-slm-frontend/src/composables/useSlmApi.ts": 1457,
    "autobot-slm-frontend/src/stores/fleet.ts": 994,
    "autobot-slm-frontend/src/types/slm.ts": 838,
    "autobot-slm-frontend/src/views/AgentsView.vue": 737,
    "autobot-slm-frontend/src/views/CodeSyncView.vue": 2080,
    "autobot-slm-frontend/src/views/DeploymentsView.vue": 1703,
    "autobot-slm-frontend/src/views/FleetOverview.vue": 837,
    "autobot-slm-frontend/src/views/MaintenanceView.vue": 818,
    "autobot-slm-frontend/src/views/OrchestrationView.vue": 2193,
    "autobot-slm-frontend/src/views/ReplicationView.vue": 731,
    "autobot-slm-frontend/src/views/SecurityView.vue": 1409,
    "autobot-slm-frontend/src/views/SetupWizardView.vue": 1834,
    "autobot-slm-frontend/src/views/SkillsView.vue": 645,
    "autobot-slm-frontend/src/views/SystemUpdatesTab.vue": 638,
    "autobot-slm-frontend/src/views/monitoring/ErrorMonitor.vue": 640,
    "autobot-slm-frontend/src/views/monitoring/LogViewer.vue": 602,
    "autobot-slm-frontend/src/views/settings/SecuritySettings.vue": 807,
    "autobot-slm-frontend/src/views/settings/admin/DataHygieneView.vue": 669,
    "autobot-slm-frontend/src/views/settings/admin/LogForwardingSettings.vue": 725,
    "autobot-slm-frontend/src/views/settings/admin/NPUWorkersSettings.vue": 726,
    "autobot-slm-frontend/src/views/settings/admin/SSOSettings.vue": 869,
    "autobot-slm-frontend/src/views/settings/admin/UserManagementSettings.vue": 1235,
}


def repo_root() -> pathlib.Path:
    """Repo root derived from this file, never from the caller's cwd."""
    return pathlib.Path(__file__).resolve().parents[1]


def _config() -> GateConfig:
    """This gate's configuration, read from the module globals at call time (#17377 AC2)."""
    return GateConfig(
        label="typescript-file-size",
        max_lines=MAX_LINES,
        self_rel=SELF_REL,
        ratchet_rel=RATCHET_REL,
        excluded_prefixes=EXCLUDED_PREFIXES,
        min_tracked_files=MIN_TRACKED_TS_FILES,
        known_large=KNOWN_LARGE,
        globs=("*.ts", "*.vue"),
    )


def normalise(path: str) -> str:
    return engine.normalise(path)


def count_lines(path: pathlib.Path) -> int | None:
    return engine.count_lines(path)


def tracked_typescript_files(root: pathlib.Path) -> list[str]:
    return engine.tracked_files(_config(), root)


def verdict(rel: str, line_count: int) -> str | None:
    return engine.verdict(_config(), rel, line_count)


def unmeasured(rel: str) -> str:
    return engine.unmeasured(rel)


def _vanished_entry_problem(rel: str, root: pathlib.Path) -> str:
    return engine.vanished_entry_problem(_config(), rel, root)


def _reach_breach_problem(reached: int) -> str:
    return engine.reach_breach_problem(_config(), reached)


def _report_unmeasured(rel: str, seen: set[str], problems: list[str]) -> None:
    engine.report_unmeasured(rel, seen, problems)


def _scan_tracked_files(root: pathlib.Path, tracked: list[str]) -> tuple[int, set[str], list[str]]:
    return engine.scan_tracked_files(_config(), root, tracked)


def audit_ceilings() -> tuple[int, list[str]]:
    return engine.audit_ceilings(
        _config(), repo_root(), enumerate_files=tracked_typescript_files, scan=_scan_tracked_files
    )


def configure_logging() -> None:
    engine.configure_logging(logger)


def run_audit() -> int:
    return engine.run_audit(_config(), repo_root(), logger, audit=audit_ceilings)


def check_paths(paths: list[str]) -> int:
    return engine.check_paths(_config(), repo_root(), paths, logger)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reject oversized frontend files (#17885).")
    parser.add_argument("paths", nargs="*", help="staged files, as pre-commit passes them")
    parser.add_argument("--audit-ceilings", action="store_true", help="rule on the whole tree")
    args = parser.parse_args(argv)
    configure_logging()
    return run_audit() if args.audit_ceilings else check_paths(args.paths)


if __name__ == "__main__":
    sys.exit(main())
