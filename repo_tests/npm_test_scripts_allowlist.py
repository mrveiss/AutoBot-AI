# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The RECORD of ungated npm test runners, kept apart from the check (#15667).

``npm_test_scripts_run_in_ci_test.py`` asks a fixed question: is every declared
runner invoked by some workflow? This module holds the answers that are
currently allowed -- which runners are knowingly ungated and why, and the
down-only ceiling on wholly ungated packages.

They are separate files because they grow at different rates. The check is
finished; the record gains an entry every time a runner is triaged, and it was
the record that pushed the pair through the 600-line ceiling (#15698). Keeping
them together would mean re-deciding the split every few entries.

Editing rules, unchanged by the move:

* every reason must name the issue that EXPIRES the entry -- "nothing runs it"
  describes the defect, it does not decide anything about it
* ``MAX_WHOLLY_UNGATED_PACKAGES`` only ever goes DOWN. Raising it to let a new
  app through is how this guard becomes the thing it replaced
"""

#: `<package dir>::<script>` -> the DECISION taken, and the issue that expires
#: the entry. Every reason must name an issue number: "nothing runs it" is a
#: description of the defect, not a decision about it.
UNINVOKED_TEST_SCRIPTS = {
    "autobot-frontend::test:unit": (
        "#10365 -- COVERED ELSEWHERE. frontend-test.yml runs `test:coverage`, which "
        "is `vitest run --coverage` over the same default config, so a separate "
        "`test:unit` step would run every unit test twice. The suite IS gated; only "
        "this spelling of it is not"
    ),
    "autobot-frontend::test:e2e": (
        "#15679 -- SUPERSEDED, RETIREMENT NOT YET TAKEN. Measured: the whole cypress "
        "suite is ONE scaffold spec, cypress/e2e/example.cy.ts, asserting "
        "`cy.contains('h1', 'You did it!')` -- create-vue starter text that appears "
        "nowhere in src/, so gating it would red the check on a template remnant while "
        "tests/e2e carries 11 playwright specs against the real app. Ten workflows "
        "already set CYPRESS_INSTALL_BINARY=0 on #13410's finding that no CI job runs "
        "cypress. Retiring the spec is the remaining decision, not a wiring fix"
    ),
    "autobot-frontend::test:playwright": (
        "#15679 -- WIRE IN, BUT NOT AT THIS COST. Measured: 103 tests over 11 spec "
        "files in tests/e2e, times SEVEN browser projects including the branded msedge "
        "and chrome channels, behind `webServer: npm run dev` and against a running "
        "backend the specs address directly -- the whole stack, on every frontend pull "
        "request. visual-regression.yml is NOT the precedent this entry once claimed: "
        "it is workflow_dispatch-ONLY (#9825, #10316) and runs a different config over "
        "storybook with two chromium projects and no backend (#15693)"
    ),
    "libs/autobot-sdk-ts::test:live": (
        "#15698, #15694 -- DELIBERATELY NOT GATED: IT NEEDS A BACKEND CI DOES NOT "
        "HAVE. The two tests behind this script dial a real HTTP endpoint; the four "
        "that do not stayed in `test`, which IS gated by npm-package-tests.yml "
        "(#15676). They were "
        "split rather than left behind a skip-if-unreachable branch, because that "
        "branch ended in `return` -- jest reports that as PASSED, so a backend-less run "
        "showed 6 passed with two of them asserting nothing. Standing this up in CI "
        "means running FastAPI + Redis + Chroma in the workflow, which is its own "
        "change, not a wiring fix"
    ),
    "autobot-infrastructure/shared/ide-extensions/vscode-autobot::test": (
        "#15678 -- NOT GATEABLE: THERE IS NO HARNESS TO GATE. Measured, not assumed: "
        "the package's only source file is src/extension.ts. There is no src/test/, so "
        "`tsc -p ./` cannot produce the out/test/runTest.js the script names, and there "
        "is no package-lock.json for `npm ci` either. A gate on it today could only ever "
        "be red. Write the extension test harness, or retire the script"
    ),
}

#: DOWN-ONLY ceiling on packages whose EVERY runner is allowlisted -- a whole
#: app gated by nothing, which is exactly the #15667 shape. Was 5 on the first
#: measurement (.mcp, autobot-browser-worker, vscode-autobot,
#: mcp-structured-thinking, libs/autobot-sdk-ts); npm-package-tests.yml gates
#: .mcp (#15674), autobot-browser-worker (#15675), libs/autobot-sdk-ts (#15676)
#: and mcp-structured-thinking (#15677), leaving vscode-autobot alone. NEVER
#: raise this to make a new app pass; wire the app in, or this guard has become
#: the thing it replaced.
MAX_WHOLLY_UNGATED_PACKAGES = 1
