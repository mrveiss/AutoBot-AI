# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Untranslated strings may shrink, never grow (#14209).

#14209 reports one key — `llc.orgChart.confirmTerminate` — sitting as
byte-identical English in all ten non-English locales. Measuring found it is
one instance of a systemic gap. When this guard was written, **26,991** values
across the ten locales were identical to their English source:

```
ar 3755 · fa 3819 · he 3819 · ur 3819   (~49% of 7,811 keys)
lv 2273 · pl 2239 · pt 2076 · fr 1878 · es 1681 · de 1632
```

Those figures are the measurement that motivated the guard, not the live state
— `BASELINE` below is the live number and is the only one that gates anything.

Sampling confirms these are real prose, not terms that legitimately match:

```
workflow.progress.cancelConfirm     "Are you sure you want to cancel this workflow?"
security.threatSettings.statusInactive  "No threat intelligence services configured"
ui.hostSelection.availableHosts     "Available Hosts"
```

Translating 27,000 strings is not a code change, so this guard does the part
that code can do: it pins the count per locale so the gap cannot widen while
the backlog is worked down. Every new user-facing string added without a
translation fails here.

**Fails in BOTH directions**, matching the other ratchets in `repo_tests/`.
Growth is a regression. An unrecorded *shrink* also fails, so translating a
batch means lowering the number in the same commit — which keeps each figure a
claim someone made deliberately rather than a drifting artefact.

A key counts as untranslated when its English source is longer than 12
characters, contains a letter, and the locale does not render it differently.
The length and letter filters are what keep `"OK"`, `"%"`, `"ID"` and bare
numerals out: short tokens and symbols are frequently identical across
languages for good reasons, and counting them would bury the real gap in noise.

**"Does not render it differently" covers two states, deliberately (#16063).**
The key may be present with the English string copied in, or absent entirely —
in which case `fallbackLocale: 'en'` renders the English string anyway, so the
reader sees exactly the same thing. This guard used to count only the first,
which was safe only because `locale-parity.test.ts` forbade the second
outright. Now that a locale is allowed to lag `en.json`, counting only the
present-and-identical case would mean an English-only key added today is
invisible here — and since an unrecorded shrink also fails, a locale falling
further behind would register as **progress**. A state the instrument cannot
see must not read as the good state.
"""

from __future__ import annotations

import pytest

from scripts.list_untranslated import LOCALES, MIN_MEANINGFUL_LENGTH, is_meaningful, load, untranslated_keys

_LOCALES = LOCALES

# Lower these as translations land. Never raise one to admit a new untranslated
# string: translate it, or leave the key out until it can be translated.
BASELINE = {
    "ar": 3830,  # #19217: the retired main-app web research editors (-12) on main's 3842; #15907: +7 English-only keys llc.orgChart.heartbeat.{label,on,off,saveFailed} and hireAgent.{runOnHeartbeat,runOnHeartbeatHint,failed} (failed replaces the hard-coded 'Failed to hire agent.' in HireAgentModal.vue); #18252/#18255 theme presets: +31 English-only keys moved from literals (ui.themePresets.* names/descriptions/header/advanced, ui.themeToggle.accent*Description; 38 added, 7 strings of <=12 chars uncounted); #19307: +1 English-only key knowledge.chroma.quarantined; #12741: +24, ~45 hard-coded Codebase Analytics strings (counts, units, filter tabs, labels) moved into en.json as English-only keys, minus the 10 retired showingOf keys; #17514: +5 English-only keys (visualizations.agentActivity.{notReported,statusNotReported,...}) replacing the hard-coded ' Agent' suffix, 'N/A' and the s/m/h/'ago' units in AgentActivityVisualization.vue; #16253: +4 English-only keys nav.backendHealth.* (the backend notice), replacing the hard-coded 'Connected'/'Degraded'/'Disconnected'/'Checking...' backend status texts and the 'System errors detected'/'System warnings' indicator texts removed from useAppStore/App.vue/ClearNotifications.js; #19241 provider sign-in UI: +24 English-only keys (en-only per the 2026-10-18 owner rule); #19270: +1 English-only key visualizations.resourceHeatmap.loadFailed; #17829: +1 English-only key chat.input.stopFailed; #14780: +1 English-only key audit.logTable.paginationAria; #19016 Telegram ingest mode: +14 English-only settings.telegramPanel.* keys (20 added; 6 short labels uncounted); #18242 Company OS: +1 English-only key llc.dashboard.noApprovals; #18242 train-42 review: +2 English-only keys views.customDashboard.dashboardLimit/widgetLimit; #18242: +17 English-only dashboard keys (+15 grid/Home, +2 review); #14778: -7, the orphaned ui.dataTable.* keys left with the retired DataTable; #14776: the retired BasePanel's untranslated base.panel keys removed (-1); #17561/#17565: skip-link labels and palette strings translated; #18354: unused theme/darkMode/switchLanguage keys removed (-4); train-85h merge: main's 3834 + this train's +7; #19334: +1 English-only key workflow.notifications.eventServiceFailed (channelTelegram is <=12 chars, uncounted)
    "de": 1734,  # #19217: the retired main-app web research editors (-12) on main's 1746; #15907: +7 English-only keys llc.orgChart.heartbeat.{label,on,off,saveFailed} and hireAgent.{runOnHeartbeat,runOnHeartbeatHint,failed} (failed replaces the hard-coded 'Failed to hire agent.' in HireAgentModal.vue); #18252/#18255 theme presets: +31 English-only keys moved from literals (ui.themePresets.* names/descriptions/header/advanced, ui.themeToggle.accent*Description; 38 added, 7 strings of <=12 chars uncounted); #19307: +1 English-only key knowledge.chroma.quarantined; #12741: +33, ~45 hard-coded Codebase Analytics strings (counts, units, filter tabs, labels) moved into en.json as English-only keys, minus the 10 retired showingOf keys; #17514: +5 English-only keys (visualizations.agentActivity.{notReported,statusNotReported,...}) replacing the hard-coded ' Agent' suffix, 'N/A' and the s/m/h/'ago' units in AgentActivityVisualization.vue; #16253: +4 English-only keys nav.backendHealth.* (the backend notice), replacing the hard-coded 'Connected'/'Degraded'/'Disconnected'/'Checking...' backend status texts and the 'System errors detected'/'System warnings' indicator texts removed from useAppStore/App.vue/ClearNotifications.js; #19241 provider sign-in UI: +24 English-only keys (en-only per the 2026-10-18 owner rule); #19270: +1 English-only key visualizations.resourceHeatmap.loadFailed; #17829: +1 English-only key chat.input.stopFailed; #14780: +1 English-only key audit.logTable.paginationAria; #19016 Telegram ingest mode: +14 English-only settings.telegramPanel.* keys (20 added; 6 short labels uncounted); #18242 Company OS: +1 English-only key llc.dashboard.noApprovals; #18242 train-42 review: +2 English-only keys views.customDashboard.dashboardLimit/widgetLimit; #18242: +17 English-only dashboard keys (+15 grid/Home, +2 review); #14778: -7, the orphaned ui.dataTable.* keys left with the retired DataTable; #17561/#17565: skip-link labels and palette strings translated; #18354: unused theme/darkMode/switchLanguage keys removed (-4); train-85h merge: main's 1738 + this train's +7; #19334: +1 English-only key workflow.notifications.eventServiceFailed (channelTelegram is <=12 chars, uncounted)
    "es": 1782,  # #19217: the retired main-app web research editors (-12) on main's 1794; #15907: +7 English-only keys llc.orgChart.heartbeat.{label,on,off,saveFailed} and hireAgent.{runOnHeartbeat,runOnHeartbeatHint,failed} (failed replaces the hard-coded 'Failed to hire agent.' in HireAgentModal.vue); #18252/#18255 theme presets: +31 English-only keys moved from literals (ui.themePresets.* names/descriptions/header/advanced, ui.themeToggle.accent*Description; 38 added, 7 strings of <=12 chars uncounted); #19307: +1 English-only key knowledge.chroma.quarantined; #12741: +33, ~45 hard-coded Codebase Analytics strings (counts, units, filter tabs, labels) moved into en.json as English-only keys, minus the 10 retired showingOf keys; #17514: +5 English-only keys (visualizations.agentActivity.{notReported,statusNotReported,...}) replacing the hard-coded ' Agent' suffix, 'N/A' and the s/m/h/'ago' units in AgentActivityVisualization.vue; #16253: +4 English-only keys nav.backendHealth.* (the backend notice), replacing the hard-coded 'Connected'/'Degraded'/'Disconnected'/'Checking...' backend status texts and the 'System errors detected'/'System warnings' indicator texts removed from useAppStore/App.vue/ClearNotifications.js; #19241 provider sign-in UI: +24 English-only keys (en-only per the 2026-10-18 owner rule); #19270: +1 English-only key visualizations.resourceHeatmap.loadFailed; #17829: +1 English-only key chat.input.stopFailed; #14780: +1 English-only key audit.logTable.paginationAria; #19016 Telegram ingest mode: +14 English-only settings.telegramPanel.* keys (20 added; 6 short labels uncounted); #18242 Company OS: +1 English-only key llc.dashboard.noApprovals; #18242 train-42 review: +2 English-only keys views.customDashboard.dashboardLimit/widgetLimit; #18242: +17 English-only dashboard keys (+15 grid/Home, +2 review); #14778: -7, the orphaned ui.dataTable.* keys left with the retired DataTable; #17561/#17565: skip-link labels and palette strings translated; #18354: unused theme/darkMode/switchLanguage keys removed (-4); train-85h merge: main's 1786 + this train's +7; #19334: +1 English-only key workflow.notifications.eventServiceFailed (channelTelegram is <=12 chars, uncounted)
    "fa": 3893,  # #19217: the retired main-app web research editors (-12) on main's 3905; #15907: +7 English-only keys llc.orgChart.heartbeat.{label,on,off,saveFailed} and hireAgent.{runOnHeartbeat,runOnHeartbeatHint,failed} (failed replaces the hard-coded 'Failed to hire agent.' in HireAgentModal.vue); #18252/#18255 theme presets: +31 English-only keys moved from literals (ui.themePresets.* names/descriptions/header/advanced, ui.themeToggle.accent*Description; 38 added, 7 strings of <=12 chars uncounted); #19307: +1 English-only key knowledge.chroma.quarantined; #12741: +24, ~45 hard-coded Codebase Analytics strings (counts, units, filter tabs, labels) moved into en.json as English-only keys, minus the 10 retired showingOf keys; #17514: +5 English-only keys (visualizations.agentActivity.{notReported,statusNotReported,...}) replacing the hard-coded ' Agent' suffix, 'N/A' and the s/m/h/'ago' units in AgentActivityVisualization.vue; #16253: +4 English-only keys nav.backendHealth.* (the backend notice), replacing the hard-coded 'Connected'/'Degraded'/'Disconnected'/'Checking...' backend status texts and the 'System errors detected'/'System warnings' indicator texts removed from useAppStore/App.vue/ClearNotifications.js; #19241 provider sign-in UI: +24 English-only keys (en-only per the 2026-10-18 owner rule); #19270: +1 English-only key visualizations.resourceHeatmap.loadFailed; #17829: +1 English-only key chat.input.stopFailed; #14780: +1 English-only key audit.logTable.paginationAria; #19016 Telegram ingest mode: +14 English-only settings.telegramPanel.* keys (20 added; 6 short labels uncounted); #18242 Company OS: +1 English-only key llc.dashboard.noApprovals; #18242 train-42 review: +2 English-only keys views.customDashboard.dashboardLimit/widgetLimit; #18242: +17 English-only dashboard keys (+15 grid/Home, +2 review); #14778: -7, the orphaned ui.dataTable.* keys left with the retired DataTable; #14776: the retired BasePanel's untranslated base.panel keys removed (-1); #17561/#17565: skip-link labels and palette strings translated; #18354: unused theme/darkMode/switchLanguage keys removed (-4); train-85h merge: main's 3897 + this train's +7; #19334: +1 English-only key workflow.notifications.eventServiceFailed (channelTelegram is <=12 chars, uncounted)
    "fr": 1978,  # #19217: the retired main-app web research editors (-12) on main's 1990; #15907: +7 English-only keys llc.orgChart.heartbeat.{label,on,off,saveFailed} and hireAgent.{runOnHeartbeat,runOnHeartbeatHint,failed} (failed replaces the hard-coded 'Failed to hire agent.' in HireAgentModal.vue); #18252/#18255 theme presets: +31 English-only keys moved from literals (ui.themePresets.* names/descriptions/header/advanced, ui.themeToggle.accent*Description; 38 added, 7 strings of <=12 chars uncounted); #19307: +1 English-only key knowledge.chroma.quarantined; #12741: +32, ~45 hard-coded Codebase Analytics strings (counts, units, filter tabs, labels) moved into en.json as English-only keys, minus the 10 retired showingOf keys; #17514: +5 English-only keys (visualizations.agentActivity.{notReported,statusNotReported,...}) replacing the hard-coded ' Agent' suffix, 'N/A' and the s/m/h/'ago' units in AgentActivityVisualization.vue; #16253: +4 English-only keys nav.backendHealth.* (the backend notice), replacing the hard-coded 'Connected'/'Degraded'/'Disconnected'/'Checking...' backend status texts and the 'System errors detected'/'System warnings' indicator texts removed from useAppStore/App.vue/ClearNotifications.js; #19241 provider sign-in UI: +24 English-only keys (en-only per the 2026-10-18 owner rule); #19270: +1 English-only key visualizations.resourceHeatmap.loadFailed; #17829: +1 English-only key chat.input.stopFailed; #14780: +1 English-only key audit.logTable.paginationAria; #19016 Telegram ingest mode: +14 English-only settings.telegramPanel.* keys (20 added; 6 short labels uncounted); #18242 Company OS: +1 English-only key llc.dashboard.noApprovals; #18242 train-42 review: +2 English-only keys views.customDashboard.dashboardLimit/widgetLimit; #18242: +17 English-only dashboard keys (+15 grid/Home, +2 review); #14778: -7, the orphaned ui.dataTable.* keys left with the retired DataTable; #17561/#17565: skip-link labels and palette strings translated; #18354: unused theme/darkMode/switchLanguage keys removed (-4); train-85h merge: main's 1982 + this train's +7; #19334: +1 English-only key workflow.notifications.eventServiceFailed (channelTelegram is <=12 chars, uncounted)
    "he": 3893,  # #19217: the retired main-app web research editors (-12) on main's 3905; #15907: +7 English-only keys llc.orgChart.heartbeat.{label,on,off,saveFailed} and hireAgent.{runOnHeartbeat,runOnHeartbeatHint,failed} (failed replaces the hard-coded 'Failed to hire agent.' in HireAgentModal.vue); #18252/#18255 theme presets: +31 English-only keys moved from literals (ui.themePresets.* names/descriptions/header/advanced, ui.themeToggle.accent*Description; 38 added, 7 strings of <=12 chars uncounted); #19307: +1 English-only key knowledge.chroma.quarantined; #12741: +24, ~45 hard-coded Codebase Analytics strings (counts, units, filter tabs, labels) moved into en.json as English-only keys, minus the 10 retired showingOf keys; #17514: +5 English-only keys (visualizations.agentActivity.{notReported,statusNotReported,...}) replacing the hard-coded ' Agent' suffix, 'N/A' and the s/m/h/'ago' units in AgentActivityVisualization.vue; #16253: +4 English-only keys nav.backendHealth.* (the backend notice), replacing the hard-coded 'Connected'/'Degraded'/'Disconnected'/'Checking...' backend status texts and the 'System errors detected'/'System warnings' indicator texts removed from useAppStore/App.vue/ClearNotifications.js; #19241 provider sign-in UI: +24 English-only keys (en-only per the 2026-10-18 owner rule); #19270: +1 English-only key visualizations.resourceHeatmap.loadFailed; #17829: +1 English-only key chat.input.stopFailed; #14780: +1 English-only key audit.logTable.paginationAria; #19016 Telegram ingest mode: +14 English-only settings.telegramPanel.* keys (20 added; 6 short labels uncounted); #18242 Company OS: +1 English-only key llc.dashboard.noApprovals; #18242 train-42 review: +2 English-only keys views.customDashboard.dashboardLimit/widgetLimit; #18242: +17 English-only dashboard keys (+15 grid/Home, +2 review); #14778: -7, the orphaned ui.dataTable.* keys left with the retired DataTable; #14776: the retired BasePanel's untranslated base.panel keys removed (-1); #17561/#17565: skip-link labels and palette strings translated; #18354: unused theme/darkMode/switchLanguage keys removed (-4); train-85h merge: main's 3897 + this train's +7; #19334: +1 English-only key workflow.notifications.eventServiceFailed (channelTelegram is <=12 chars, uncounted)
    "lv": 2365,  # #19217: the retired main-app web research editors (-12) on main's 2377; #15907: +7 English-only keys llc.orgChart.heartbeat.{label,on,off,saveFailed} and hireAgent.{runOnHeartbeat,runOnHeartbeatHint,failed} (failed replaces the hard-coded 'Failed to hire agent.' in HireAgentModal.vue); #18252/#18255 theme presets: +31 English-only keys moved from literals (ui.themePresets.* names/descriptions/header/advanced, ui.themeToggle.accent*Description; 38 added, 7 strings of <=12 chars uncounted); #19307: +1 English-only key knowledge.chroma.quarantined; #12741: +24, ~45 hard-coded Codebase Analytics strings (counts, units, filter tabs, labels) moved into en.json as English-only keys, minus the 10 retired showingOf keys; #17514: +5 English-only keys (visualizations.agentActivity.{notReported,statusNotReported,...}) replacing the hard-coded ' Agent' suffix, 'N/A' and the s/m/h/'ago' units in AgentActivityVisualization.vue; #16253: +4 English-only keys nav.backendHealth.* (the backend notice), replacing the hard-coded 'Connected'/'Degraded'/'Disconnected'/'Checking...' backend status texts and the 'System errors detected'/'System warnings' indicator texts removed from useAppStore/App.vue/ClearNotifications.js; #19241 provider sign-in UI: +24 English-only keys (en-only per the 2026-10-18 owner rule); #19270: +1 English-only key visualizations.resourceHeatmap.loadFailed; #17829: +1 English-only key chat.input.stopFailed; #14780: +1 English-only key audit.logTable.paginationAria; #19016 Telegram ingest mode: +14 English-only settings.telegramPanel.* keys (20 added; 6 short labels uncounted); #18242 Company OS: +1 English-only key llc.dashboard.noApprovals; #18242 train-42 review: +2 English-only keys views.customDashboard.dashboardLimit/widgetLimit; #18242: +17 English-only dashboard keys (+15 grid/Home, +2 review); #14778: -7, the orphaned ui.dataTable.* keys left with the retired DataTable; #17561/#17565: skip-link labels and palette strings translated; #18354: unused theme/darkMode/switchLanguage keys removed (-4); train-85h merge: main's 2369 + this train's +7; #19334: +1 English-only key workflow.notifications.eventServiceFailed (channelTelegram is <=12 chars, uncounted)
    "pl": 2331,  # #19217: the retired main-app web research editors (-12) on main's 2343; #15907: +7 English-only keys llc.orgChart.heartbeat.{label,on,off,saveFailed} and hireAgent.{runOnHeartbeat,runOnHeartbeatHint,failed} (failed replaces the hard-coded 'Failed to hire agent.' in HireAgentModal.vue); #18252/#18255 theme presets: +31 English-only keys moved from literals (ui.themePresets.* names/descriptions/header/advanced, ui.themeToggle.accent*Description; 38 added, 7 strings of <=12 chars uncounted); #19307: +1 English-only key knowledge.chroma.quarantined; #12741: +24, ~45 hard-coded Codebase Analytics strings (counts, units, filter tabs, labels) moved into en.json as English-only keys, minus the 10 retired showingOf keys; #17514: +5 English-only keys (visualizations.agentActivity.{notReported,statusNotReported,...}) replacing the hard-coded ' Agent' suffix, 'N/A' and the s/m/h/'ago' units in AgentActivityVisualization.vue; #16253: +4 English-only keys nav.backendHealth.* (the backend notice), replacing the hard-coded 'Connected'/'Degraded'/'Disconnected'/'Checking...' backend status texts and the 'System errors detected'/'System warnings' indicator texts removed from useAppStore/App.vue/ClearNotifications.js; #19241 provider sign-in UI: +24 English-only keys (en-only per the 2026-10-18 owner rule); #19270: +1 English-only key visualizations.resourceHeatmap.loadFailed; #17829: +1 English-only key chat.input.stopFailed; #14780: +1 English-only key audit.logTable.paginationAria; #19016 Telegram ingest mode: +14 English-only settings.telegramPanel.* keys (20 added; 6 short labels uncounted); #18242 Company OS: +1 English-only key llc.dashboard.noApprovals; #18242 train-42 review: +2 English-only keys views.customDashboard.dashboardLimit/widgetLimit; #18242: +17 English-only dashboard keys (+15 grid/Home, +2 review); #14778: -7, the orphaned ui.dataTable.* keys left with the retired DataTable; #17561/#17565: skip-link labels and palette strings translated; #18354: unused theme/darkMode/switchLanguage keys removed (-4); train-85h merge: main's 2335 + this train's +7; #19334: +1 English-only key workflow.notifications.eventServiceFailed (channelTelegram is <=12 chars, uncounted)
    "pt": 2168,  # #19217: the retired main-app web research editors (-12) on main's 2180; #15907: +7 English-only keys llc.orgChart.heartbeat.{label,on,off,saveFailed} and hireAgent.{runOnHeartbeat,runOnHeartbeatHint,failed} (failed replaces the hard-coded 'Failed to hire agent.' in HireAgentModal.vue); #18252/#18255 theme presets: +31 English-only keys moved from literals (ui.themePresets.* names/descriptions/header/advanced, ui.themeToggle.accent*Description; 38 added, 7 strings of <=12 chars uncounted); #19307: +1 English-only key knowledge.chroma.quarantined; #12741: +24, ~45 hard-coded Codebase Analytics strings (counts, units, filter tabs, labels) moved into en.json as English-only keys, minus the 10 retired showingOf keys; #17514: +5 English-only keys (visualizations.agentActivity.{notReported,statusNotReported,...}) replacing the hard-coded ' Agent' suffix, 'N/A' and the s/m/h/'ago' units in AgentActivityVisualization.vue; #16253: +4 English-only keys nav.backendHealth.* (the backend notice), replacing the hard-coded 'Connected'/'Degraded'/'Disconnected'/'Checking...' backend status texts and the 'System errors detected'/'System warnings' indicator texts removed from useAppStore/App.vue/ClearNotifications.js; #19241 provider sign-in UI: +24 English-only keys (en-only per the 2026-10-18 owner rule); #19270: +1 English-only key visualizations.resourceHeatmap.loadFailed; #17829: +1 English-only key chat.input.stopFailed; #14780: +1 English-only key audit.logTable.paginationAria; #19016 Telegram ingest mode: +14 English-only settings.telegramPanel.* keys (20 added; 6 short labels uncounted); #18242 Company OS: +1 English-only key llc.dashboard.noApprovals; #18242 train-42 review: +2 English-only keys views.customDashboard.dashboardLimit/widgetLimit; #18242: +17 English-only dashboard keys (+15 grid/Home, +2 review); #14778: -7, the orphaned ui.dataTable.* keys left with the retired DataTable; #17561/#17565: skip-link labels and palette strings translated; #18354: unused theme/darkMode/switchLanguage keys removed (-4); train-85h merge: main's 2172 + this train's +7; #19334: +1 English-only key workflow.notifications.eventServiceFailed (channelTelegram is <=12 chars, uncounted)
    "ur": 3893,  # #19217: the retired main-app web research editors (-12) on main's 3905; #15907: +7 English-only keys llc.orgChart.heartbeat.{label,on,off,saveFailed} and hireAgent.{runOnHeartbeat,runOnHeartbeatHint,failed} (failed replaces the hard-coded 'Failed to hire agent.' in HireAgentModal.vue); #18252/#18255 theme presets: +31 English-only keys moved from literals (ui.themePresets.* names/descriptions/header/advanced, ui.themeToggle.accent*Description; 38 added, 7 strings of <=12 chars uncounted); #19307: +1 English-only key knowledge.chroma.quarantined; #12741: +24, ~45 hard-coded Codebase Analytics strings (counts, units, filter tabs, labels) moved into en.json as English-only keys, minus the 10 retired showingOf keys; #17514: +5 English-only keys (visualizations.agentActivity.{notReported,statusNotReported,...}) replacing the hard-coded ' Agent' suffix, 'N/A' and the s/m/h/'ago' units in AgentActivityVisualization.vue; #16253: +4 English-only keys nav.backendHealth.* (the backend notice), replacing the hard-coded 'Connected'/'Degraded'/'Disconnected'/'Checking...' backend status texts and the 'System errors detected'/'System warnings' indicator texts removed from useAppStore/App.vue/ClearNotifications.js; #19241 provider sign-in UI: +24 English-only keys (en-only per the 2026-10-18 owner rule); #19270: +1 English-only key visualizations.resourceHeatmap.loadFailed; #17829: +1 English-only key chat.input.stopFailed; #14780: +1 English-only key audit.logTable.paginationAria; #19016 Telegram ingest mode: +14 English-only settings.telegramPanel.* keys (20 added; 6 short labels uncounted); #18242 Company OS: +1 English-only key llc.dashboard.noApprovals; #18242 train-42 review: +2 English-only keys views.customDashboard.dashboardLimit/widgetLimit; #18242: +17 English-only dashboard keys (+15 grid/Home, +2 review); #14778: -7, the orphaned ui.dataTable.* keys left with the retired DataTable; #14776: the retired BasePanel's untranslated base.panel keys removed (-1); #17561/#17565: skip-link labels and palette strings translated; #18354: unused theme/darkMode/switchLanguage keys removed (-4); train-85h merge: main's 3897 + this train's +7; #19334: +1 English-only key workflow.notifications.eventServiceFailed (channelTelegram is <=12 chars, uncounted)
}

# The ONE definition of "untranslated" lives in scripts/list_untranslated.py, which
# translators run to find work (#18768); this guard counts with the same code.
_MIN_MEANINGFUL_LENGTH = MIN_MEANINGFUL_LENGTH
_untranslated_keys = untranslated_keys
_is_meaningful = is_meaningful


def _load(code: str) -> dict[str, str]:
    return load(code, _LOCALES)


def _untranslated(code: str) -> list[str]:
    return _untranslated_keys(_load("en"), _load(code))


def test_the_locale_files_this_guard_reads_are_present() -> None:
    """A renamed locale directory would make every count zero, and zero passes."""
    assert _LOCALES.is_dir(), f"{_LOCALES} is missing — this guard is pinned to the wrong path"

    english = _load("en")
    assert len(english) > 5000, (
        f"only {len(english)} English keys found — the flatten has stopped reaching the catalogue, "
        "which would make every count below meaningless"
    )


def test_a_key_a_locale_does_not_carry_is_counted_as_untranslated() -> None:
    """The known positive for the missing-key half (#16063).

    Deleting a key from a locale must not shrink the count. It is the one way
    this ratchet could be gamed into reporting progress for a regression, and
    it is unreachable through the locale files themselves while any of them is
    complete — so it is asserted against dictionaries rather than fixtures.
    """
    key = "a.key.with.a.sentence"
    english = {key: "A sentence long enough to count"}

    assert _untranslated_keys(english, dict(english)) == [key], "present and identical must count"
    assert _untranslated_keys(english, {}) == [key], "absent must count — the runtime renders English either way"
    assert _untranslated_keys(english, {key: "Une phrase assez longue pour compter"}) == []
    assert _untranslated_keys({key: "OK"}, {}) == [], "the length filter still applies to a missing key"


@pytest.mark.parametrize("code", sorted(BASELINE))
def test_untranslated_strings_only_shrink(code: str) -> None:
    """Growth is a regression; an unrecorded shrink is a stale baseline."""
    actual = len(_untranslated(code))
    baseline = BASELINE[code]

    assert actual <= baseline, (
        f"{code}: {actual} strings are still English, ratchet allows {baseline} (#14209). "
        "English is the only required language for now (owner, 2026-10-18; #12732): a new key goes into en.json "
        "alone, and a PR that moves hard-coded literals into en.json raises this baseline by exactly the keys it "
        "moved, citing them. Never copy English text into another locale's file."
    )
    assert actual == baseline, (
        f"{code}: down to {actual} untranslated but the baseline still says {baseline} — "
        "lower it in the commit that did the translating, so the number stays a deliberate claim"
    )


def test_a_destructive_confirmation_is_never_left_in_english() -> None:
    """The specific key #14209 was filed for.

    A confirmation for an irreversible action is the worst place for a language
    the reader may not speak: they are being asked to approve something with no
    recovery path.
    """
    english = _load("en")["llc.orgChart.confirmTerminate"]

    for code in sorted(BASELINE):
        value = _load(code).get("llc.orgChart.confirmTerminate")
        assert value is not None, f"{code}: llc.orgChart.confirmTerminate is missing"
        assert value != english, f"{code}: llc.orgChart.confirmTerminate is still the English string (#14209)"
        assert "{name}" in value, f"{code}: translation dropped the {{name}} placeholder"
