# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Data module for ``scripts/check_frontend_file_size.py``'s ``KNOWN_LARGE``.

Split out from the hook for the same reason the Python gate's is (#14547): 184
entries inline would put the hook over its own MAX_LINES, and a guard cannot
ask everything else to split without doing the same to its own data.

**No number here was chosen.** Every value is what a full walk of the tracked,
in-scope ``*.ts``/``*.vue`` tree measured on the day this gate landed (#17885).
The gate's job was to ask the question for the first time; this file is the
answer it got, not a ceiling anybody picked.

The table follows the rule stated once in ``scripts/python_file_size_known_large.py``
(#19544): it only shrinks, it is the only record of these ceilings, and an entry is
lowered here when its file shrinks.
"""

from __future__ import annotations

KNOWN_LARGE: dict[str, int] = {
    "autobot-frontend/src/components/__tests__/ChatInterface.test.ts": 760,
    "autobot-frontend/src/components/__tests__/TerminalWindow.test.ts": 627,
    "autobot-frontend/src/components/agents/HeartbeatPanel.vue": 721,
    "autobot-frontend/src/components/analytics/AdvancedAnalytics.vue": 902,  # #18849: 903 -> 902
    "autobot-frontend/src/components/analytics/CodeEvolutionTimeline.vue": 772,
    "autobot-frontend/src/components/analytics/CodeGenerationDashboard.vue": 1108,
    "autobot-frontend/src/components/analytics/CodeQualityDashboard.vue": 1791,
    "autobot-frontend/src/components/analytics/CodeReviewDashboard.vue": 1220,
    "autobot-frontend/src/components/analytics/CodebaseAnalytics.vue": 1267,
    "autobot-frontend/src/components/analytics/CodebaseAnalyticsLanding.vue": 758,
    "autobot-frontend/src/components/analytics/ConversationFlowDashboard.vue": 909,
    "autobot-frontend/src/components/analytics/LLMPatternDashboard.vue": 1080,
    "autobot-frontend/src/components/analytics/LogPatternDashboard.vue": 941,
    "autobot-frontend/src/components/analytics/PatternAnalysis.vue": 944,
    "autobot-frontend/src/components/analytics/PerformanceAnalysisDashboard.vue": 1075,
    "autobot-frontend/src/components/analytics/PrecommitHookDashboard.vue": 1097,
    "autobot-frontend/src/components/analytics/SourceManager.vue": 838,
    "autobot-frontend/src/components/analytics/TechnicalDebtDashboard.vue": 1712,
    "autobot-frontend/src/components/analytics/panels/CodebaseBugPredictionPanel.vue": 779,
    "autobot-frontend/src/components/analytics/panels/CodebaseCrossLanguagePanel.vue": 640,
    "autobot-frontend/src/components/analytics/panels/CodebaseIntelligenceScoresPanel.vue": 1325,
    "autobot-frontend/src/components/analytics/panels/CodebaseOwnershipPanel.vue": 1035,
    "autobot-frontend/src/components/audit/AuditLogTable.vue": 737,  # #14780 BasePagination: 758 -> 741
    "autobot-frontend/src/components/browser/BrowserSessionManager.vue": 647,  # #18849: 654 -> 653
    "autobot-frontend/src/components/charts/BaseChart.vue": 602,
    "autobot-frontend/src/components/charts/FunctionCallGraph.vue": 2153,  # #19906: 2165 -> 2153
    "autobot-frontend/src/components/charts/ImportTreeChart.vue": 1353,  # #19906: 1365 -> 1353
    "autobot-frontend/src/components/chat/ChatInput.vue": 1631,  # #20133: 1672 -> 1631
    "autobot-frontend/src/components/chat/ChatInterface.vue": 1521,
    "autobot-frontend/src/components/chat/ChatMessages.vue": 2118,  # #18849: 2119 -> 2118
    "autobot-frontend/src/components/chat/ChatSidebar.vue": 807,  # #18849: 808 -> 807
    "autobot-frontend/src/components/chat/DocumentationSearchSidebar.vue": 766,
    "autobot-frontend/src/components/chat/VisionAnalysisModal.vue": 702,
    "autobot-frontend/src/components/chat/VisualBrowserPanel.vue": 632,
    "autobot-frontend/src/components/chat/VoiceConversationOverlay.vue": 916,
    "autobot-frontend/src/components/chat/VoiceConversationPanel.vue": 649,
    "autobot-frontend/src/components/desktop/DesktopInterface.vue": 894,
    "autobot-frontend/src/components/desktop/PopoutChromiumBrowser.vue": 1229,
    "autobot-frontend/src/components/examples/ThemingPatternExample.vue": 603,
    "autobot-frontend/src/components/feature-flags/AccessMetrics.vue": 722,
    "autobot-frontend/src/components/feature-flags/EndpointEnforcement.vue": 639,
    "autobot-frontend/src/components/file-browser/FileBrowser.vue": 736,
    "autobot-frontend/src/components/knowledge/ChromaDBExplorer.vue": 1155,
    "autobot-frontend/src/components/knowledge/DocumentChangeFeed.vue": 601,
    "autobot-frontend/src/components/knowledge/EntityExtractor.vue": 776,
    "autobot-frontend/src/components/knowledge/EntityGraphManager.vue": 692,
    "autobot-frontend/src/components/knowledge/GraphConnectionPath.vue": 701,
    "autobot-frontend/src/components/knowledge/GraphRAGQuery.vue": 713,
    "autobot-frontend/src/components/knowledge/KBSearchResultPanel.vue": 625,
    "autobot-frontend/src/components/knowledge/KnowledgeBrowser.vue": 1772,  # #17563: 1785 -> 1772 (kit Breadcrumb)
    "autobot-frontend/src/components/knowledge/KnowledgeEntries.vue": 1358,  # #19118: 1359 -> 1358
    "autobot-frontend/src/components/knowledge/KnowledgeGraph.vue": 2068,
    "autobot-frontend/src/components/knowledge/KnowledgeHealth.vue": 925,
    "autobot-frontend/src/components/knowledge/KnowledgePersistenceDialog.vue": 891,  # #18819+#18849 one import (-1)
    "autobot-frontend/src/components/knowledge/KnowledgeResearchPanel.vue": 1189,
    "autobot-frontend/src/components/knowledge/KnowledgeSystemDocs.vue": 863,
    "autobot-frontend/src/components/knowledge/KnowledgeUpload.vue": 1634,
    "autobot-frontend/src/components/knowledge/KnowledgeVerificationQueue.vue": 797,
    "autobot-frontend/src/components/knowledge/SystemKnowledgeManager.vue": 1018,  # #19906: 1034 -> 1018
    "autobot-frontend/src/components/knowledge/WebResearchPanel.vue": 779,
    "autobot-frontend/src/components/knowledge/connectors/ConnectorConfigModal.vue": 1626,  # #18849: 1627 -> 1626
    "autobot-frontend/src/components/knowledge/modals/BulkEditModal.vue": 615,  # #18849: 616 -> 615
    "autobot-frontend/src/components/knowledge/modals/CategoryEditModal.vue": 726,  # #18849: 727 -> 726
    "autobot-frontend/src/components/llc/TemplateBrowser.vue": 806,
    "autobot-frontend/src/components/manpage/ManPageManager.vue": 1213,  # #18849: 1214 -> 1213
    "autobot-frontend/src/components/security/SecretsManager.vue": 2775,
    "autobot-frontend/src/components/security/ThreatIntelligenceDashboard.vue": 776,
    "autobot-frontend/src/components/terminal/AdvancedStepConfirmationModal.vue": 615,  # #18849: 616 -> 615
    "autobot-frontend/src/components/terminal/BaseXTerminal.vue": 825,
    "autobot-frontend/src/components/terminal/TerminalModals.vue": 742,  # #18849: 743 -> 742
    "autobot-frontend/src/components/terminal/TerminalWindow.vue": 1612,
    "autobot-frontend/src/components/ui/HostSelectionDialog.vue": 924,
    "autobot-frontend/src/components/vision/GUIAutomationControls.vue": 708,
    "autobot-frontend/src/components/vision/MediaGallery.vue": 723,
    "autobot-frontend/src/components/vision/ScreenCaptureViewer.vue": 835,
    "autobot-frontend/src/components/vision/VideoProcessor.vue": 897,
    "autobot-frontend/src/components/visualizations/AgentActivityVisualization.vue": 936,
    "autobot-frontend/src/components/visualizations/SystemArchitectureDiagram.vue": 1881,
    "autobot-frontend/src/components/visualizations/WorkflowVisualization.vue": 1017,  # #16744: 1020 -> 1019
    "autobot-frontend/src/components/workflow/PhaseProgressionIndicator.vue": 634,
    "autobot-frontend/src/components/workflow/WorkflowCanvas.vue": 2887,
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
    "autobot-frontend/src/composables/analytics/useAnalyticsDataFetchers.ts": 701,
    "autobot-frontend/src/composables/useKeyboard.ts": 650,
    "autobot-frontend/src/composables/useKnowledgeVectorization.ts": 679,
    "autobot-frontend/src/composables/usePatternAnalysis.ts": 865,
    "autobot-frontend/src/composables/useTimeout.ts": 749,
    "autobot-frontend/src/composables/useVoiceConversation.ts": 986,
    "autobot-frontend/src/composables/useVoiceOutput.ts": 1089,
    "autobot-frontend/src/composables/useWorkflowBuilder.ts": 1293,
    "autobot-frontend/src/config/__tests__/ssot-config.spec.ts": 626,
    "autobot-frontend/src/config/ssot-config.ts": 819,
    "autobot-frontend/src/models/controllers/ChatController.ts": 1156,
    "autobot-frontend/src/models/controllers/KnowledgeController.ts": 645,
    "autobot-frontend/src/models/repositories/ChatRepository.ts": 674,
    "autobot-frontend/src/models/repositories/KnowledgeRepository.ts": 897,
    "autobot-frontend/src/router/index.ts": 1385,
    "autobot-frontend/src/services/GlobalWebSocketService.ts": 905,
    "autobot-frontend/src/services/TerminalService.ts": 1137,
    "autobot-frontend/src/stores/useChatStore.ts": 1176,
    "autobot-frontend/src/stores/useKnowledgeStore.ts": 809,
    "autobot-frontend/src/utils/RumAgent.ts": 857,
    "autobot-frontend/src/utils/VisionMultimodalApiClient.ts": 663,
    "autobot-frontend/src/utils/debugUtils.ts": 620,
    "autobot-frontend/src/views/AdminUsersView.vue": 796,
    "autobot-frontend/src/views/AdvancedControlView.vue": 1056,
    "autobot-frontend/src/views/BudgetPolicies.vue": 879,
    "autobot-frontend/src/views/BusinessIntelligenceView.vue": 987,  # #20004: 988 -> 987
    "autobot-frontend/src/views/CustomDashboard.vue": 878,  # #18242: 1106 -> 884; train-42 review: -5, then -1
    "autobot-frontend/src/views/DevSpeedupView.vue": 644,
    "autobot-frontend/src/views/ErrorMonitoringView.vue": 839,
    "autobot-frontend/src/views/EvolutionView.vue": 771,
    "autobot-frontend/src/views/FailureAnalysisDashboard.vue": 768,  # #13422: 799 -> 782; #19906: -> 768
    "autobot-frontend/src/views/MarketplaceView.vue": 680,
    "autobot-frontend/src/views/OnboardingWizard.vue": 836,
    "autobot-frontend/src/views/PluginsView.vue": 1058,
    "autobot-frontend/src/views/SettingsView.vue": 739,
    "autobot-frontend/src/views/VisionAutomationView.vue": 848,
    "autobot-frontend/src/views/WorkflowBuilderView.vue": 2201,  # #13422: 2300 -> 2267 (kit RiskBadge)
    "autobot-frontend/src/views/llc/BacklogView.vue": 823,
    "autobot-frontend/src/views/llc/CompanyCreationWizard.vue": 909,
    "autobot-frontend/src/views/llc/CompanyPortabilityView.vue": 761,
    "autobot-frontend/src/views/llc/CostDashboard.vue": 1012,  # #20123: 1015 -> 1012 (mixed bucket lists each currency)
    "autobot-frontend/src/views/llc/GanttTimelineView.vue": 817,
    "autobot-frontend/src/views/llc/HeartbeatMonitor.vue": 805,
    "autobot-frontend/src/views/llc/OrgChart.vue": 1517,  # #14780: 1527 -> 1522 (kit BaseDrawer)
    "autobot-frontend/src/views/llc/ProjectBrowserView.vue": 1370,  # #18819 1379->1374; #18849 -1; #14778 BaseInput -1
    "autobot-frontend/src/views/llc/RolesView.vue": 1026,  # #18819 1029->1027; #18849 one kit import on the merge (-1)
    "autobot-frontend/src/views/llc/RoutinesView.vue": 688,
    "autobot-frontend/src/views/llc/SprintBoardView.vue": 664,
    # #14780: 1046 -> 1013 (kit BaseDrawer); #18750: 994 (comments tab returns)
    "autobot-frontend/src/views/llc/WorkItemDetail.vue": 948,  # #20068: 994 -> 949
    "autobot-infrastructure/shared/ide-extensions/vscode-autobot/src/extension.ts": 741,
    "autobot-infrastructure/shared/mcp/tools/mcp-autobot-tracker/src/background-monitor.ts": 713,
    "autobot-infrastructure/shared/mcp/tools/mcp-autobot-tracker/src/index.ts": 957,
    "autobot-slm-frontend/src/components/AddNodeModal.vue": 1067,  # #14777 batch 2: 1111 -> 1067
    "autobot-slm-frontend/src/components/fleet/NodeLifecyclePanel.vue": 934,
    "autobot-slm-frontend/src/composables/useAutobotApi.ts": 1973,  # #19217 factory in; #12363 formatter out
    "autobot-slm-frontend/src/composables/useCodeSync.ts": 1078,
    "autobot-slm-frontend/src/composables/useOrchestrationManagement.ts": 693,
    "autobot-slm-frontend/src/composables/useSlmApi.ts": 1457,
    "autobot-slm-frontend/src/stores/fleet.ts": 994,
    "autobot-slm-frontend/src/types/slm.ts": 838,
    "autobot-slm-frontend/src/views/AgentsView.vue": 712,
    "autobot-slm-frontend/src/views/CodeSyncView.vue": 2035,  # #18819: 2080 -> 2069
    "autobot-slm-frontend/src/views/DeploymentsView.vue": 1614,  # #18819 + #14777: 1703 -> 1623; #20003: -> 1614
    "autobot-slm-frontend/src/views/FleetOverview.vue": 708,  # #14780: 786 -> 708
    "autobot-slm-frontend/src/views/MaintenanceView.vue": 790,  # #14777 batch 2: 817 -> 794; #20003: -> 790
    "autobot-slm-frontend/src/views/OrchestrationView.vue": 2189,
    "autobot-slm-frontend/src/views/ReplicationView.vue": 699,  # #18819 + #14777: 731 -> 706
    "autobot-slm-frontend/src/views/SecurityView.vue": 1368,  # #14780 BasePagination: 1386 -> 1374
    "autobot-slm-frontend/src/views/SetupWizardView.vue": 1790,
    "autobot-slm-frontend/src/views/SkillsView.vue": 631,  # #18819 + #14777: 645 -> 633; #19482: -> 631
    "autobot-slm-frontend/src/views/SystemUpdatesTab.vue": 621,  # #18819: 638 -> 635; #19482: -> 632; #18863: -> 626
    "autobot-slm-frontend/src/views/monitoring/ErrorMonitor.vue": 602,  # #14780: 617 -> 609; #19482: 608; #20004: 602
    "autobot-slm-frontend/src/views/settings/SecuritySettings.vue": 706,  # #18819 + #14777: 807 -> 773
    "autobot-slm-frontend/src/views/settings/admin/DataHygieneView.vue": 656,  # #18819 + #14777: 669 -> 662
    "autobot-slm-frontend/src/views/settings/admin/LogForwardingSettings.vue": 650,  # #14780: 664 -> 655 (BaseSwitch)
    "autobot-slm-frontend/src/views/settings/admin/NPUWorkersSettings.vue": 716,  # #18819 + #14777: 733 -> 721
    "autobot-slm-frontend/src/views/settings/admin/SSOSettings.vue": 822,  # #18819 + #14777: 869 -> 824; #19816: -> 822
    "autobot-slm-frontend/src/views/settings/admin/UserManagementSettings.vue": 1057,  # #18819 + #14777: 1099 -> 1088
}
