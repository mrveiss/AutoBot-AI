# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Why each absolute reach floor is still absolute, and which ones are not done (#17914).

52 declarations bound their sweep with `floor=N` plus a `growth=M` allowance. The floor is a
constant, the tree grows, and the gap is consumed on a schedule -- `hooks-path-override` was
re-pinned seventeen times and every one of those numbers was correct when written.

**"52 carry an allowance" is not "52 pending conversions", and reading it that way is the
expensive mistake.** A relative floor needs a reference that measures the SAME population, so
that every change the rule should welcome moves numerator and denominator together
(`RATCHET_BASELINES.md` rule 7). Where the reference drifts on its own, a fraction walks
downward with nothing wrong and fires falsely -- the `docs/` case, where `archives/` only ever
grows, so a share of all docs sinks on its own. Many of these 52 are CORRECTLY absolute, and
"it has never tripped" is not the test for either verdict.

So each one carries a verdict and a measured reason. Two verdicts only:

``ABSOLUTE``
    No reference co-moves with this population. The floor stays a constant, and the mid-window
    rule in `_reach.verify_floor` (#17356) is what keeps it off the bottom of its window.
``CONVERTIBLE``
    A reference enumerating the same class exists and the conversion is real work still to do.
    `MAX_CONVERTIBLE` pins how many may remain and RATCHETS DOWN only, so this is a backlog
    that cannot grow quietly rather than a note somebody meant to come back to.

The reason codes, each a different argument -- conflating them produces the wrong fix:

``NOT_PATHS``
    The discovered items are parsed objects -- routers, workflow jobs, locale keys, symbols,
    source line sites. No file enumeration measures this population at all, so there is no
    reference to take a fraction of.
``SUBSET_DRIFTS``
    A proper subset of a larger file class, where the rest of the class grows at its own rate.
    A fraction of the class sinks as the other half grows: production Python against all
    tracked Python falls whenever tests are added, which is a change the rule welcomes.
``FIXED_INVENTORY``
    A small, deliberately enumerable set. A fraction of a large reference is meaningless at
    this size, and the band is already equality or close to it.
``COMPLETION_GAP``
    The guard completes materially fewer items than it lists. The relative mode applies ONE
    fraction to both `examined()` and `completed()`, so no single value can bound both.
``FRACTION_IS_COARSER``
    A reference exists and agrees, and the population is small enough that the coarsest safe
    fraction implies a floor BELOW the constant it would replace -- which #17914 AC2 refuses --
    while the only tighter fraction fires on a one-file skew.
``REFERENCE_EXISTS``
    The population is an independently enumerable file class. This is the `CONVERTIBLE` reason.

Measured 2026-10-04 against `origin/main` at `baec13de40`, by importing the registry and
running each declaration's own `discover` once. Counts are deliberately NOT written into the
reasons: a population written down here outlives the merge that changes it (#17384).
"""

from __future__ import annotations

ABSOLUTE = "ABSOLUTE"
CONVERTIBLE = "CONVERTIBLE"

#: The only legal verdicts and reason codes. Closed sets, because the table is read by a test
#: that compared membership and not spelling: `"ABSOLUTEE"` or an empty reason would have been
#: accepted as a recorded decision.
VERDICTS = frozenset({ABSOLUTE, CONVERTIBLE})
REASON_CODES = frozenset(
    {"NOT_PATHS", "SUBSET_DRIFTS", "FIXED_INVENTORY", "COMPLETION_GAP", "FRACTION_IS_COARSER", "REFERENCE_EXISTS"}
)

#: Declaration name -> (verdict, reason code, why).
#:
#: Every absolute declaration carrying a `growth` allowance must appear here, and
#: `reach_declarations_test` fails on a new one that does not -- so the pattern cannot be
#: re-added without someone writing down why (#17914 AC4).
ALLOWANCE_VERDICTS: dict[str, tuple[str, str, str]] = {
    "ansible-apt-repo-budget-override-sweep": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Ansible variable files are a subset of tracked YAML; workflow and compose YAML grow "
        "independently of the ansible tree, so a share of all YAML sinks with nothing wrong.",
    ),
    "ansible-inventory-shell-sweep": (
        ABSOLUTE,
        "FRACTION_IS_COARSER",
        "Measured, after an earlier verdict here said CONVERTIBLE with no blocker stated and a "
        "reviewer called that out: an independent suffix filter does count the same class and "
        "agrees with the sweep exactly. It still cannot convert, because at this population one "
        "step of a fraction is worth more files than the constant's own band -- 0.99 implies a "
        "floor BELOW the constant it would replace, which #17914 AC2 refuses, and 1.00 fires on "
        "a single index-versus-filesystem skew.",
    ),
    "audio-extension-allowlist": (
        ABSOLUTE,
        "COMPLETION_GAP",
        "It declares `skips` because it cannot read every file it lists, and the relative mode "
        "applies one fraction to both bounds -- a value that clears `examined()` fails "
        "`completed()` and the reverse.",
    ),
    "blanket-skip-test-module-sweep": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Test modules against all tracked Python: tests grow faster than production code, so "
        "this share rises and falls on unrelated work.",
    ),
    "chromadb-bind-host-override-candidates": (
        ABSOLUTE,
        "FIXED_INVENTORY",
        "A handful of inventory and role-default files.",
    ),
    "chromadb-bind-launch-sites": (
        ABSOLUTE,
        "FIXED_INVENTORY",
        "Single-digit launch sites; the band is already near equality.",
    ),
    "chromadb-compose-files": (
        ABSOLUTE,
        "FIXED_INVENTORY",
        "Single-digit compose files; a fraction of any reference is noise at this size.",
    ),
    "jekyll-processed-docs": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Markdown under `docs/` carrying front matter -- the only files Jekyll renders through "
        "Liquid. All `docs/**/*.md` is the obvious reference and it is the wrong one: it is the "
        "`archives/` case named in this module's own header. Archived pages are added without "
        "front matter and never removed, so the processed share sinks with nothing wrong, and a "
        "fraction of the whole would fire on that drift rather than on a guard going blind.",
    ),
    "chromadb-compose-port-sites": (ABSOLUTE, "NOT_PATHS", "Parsed `ports:` entries, not files."),
    "chromadb-compose-services": (ABSOLUTE, "NOT_PATHS", "Parsed compose services, not files."),
    "collectable-modules-inert-on-import": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Modules matching pytest's `python_files` patterns -- the same test-versus-production "
        "drift as `blanket-skip-test-module-sweep`.",
    ),
    "component-style-block-sweep": (
        ABSOLUTE,
        "NOT_PATHS",
        "`<style>` blocks within components, counted per block rather than per file.",
    ),
    "config-router-auth-coverage": (ABSOLUTE, "NOT_PATHS", "Routers listed in the config registries, not files."),
    "connector-redaction-sweep": (ABSOLUTE, "FIXED_INVENTORY", "A couple of dozen importable connector modules."),
    "detect-environment-env-files": (
        ABSOLUTE,
        "FIXED_INVENTORY",
        "The `.env*` files tracked at the repo root; a fixed, named set.",
    ),
    "direct-secrets-service-callers": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Production modules under two trees, against all tracked Python.",
    ),
    "docstring-restatement-scan": (
        ABSOLUTE,
        "NOT_PATHS",
        "Named public symbols, not files; nothing outside the sweep counts symbols.",
    ),
    "dpkg-ansible-registrations": (
        ABSOLUTE,
        "NOT_PATHS",
        "Ansible tasks registering a package-query result, not files.",
    ),
    "dpkg-list-call-sites": (ABSOLUTE, "NOT_PATHS", "Package-list invocations inside lines, not files."),
    "enum-hand-copy-census": (
        ABSOLUTE,
        "COMPLETION_GAP",
        "Its population is the tracked Python class, but it bounds `completed(parsed)` with the "
        "same declaration -- a file that will not parse is skipped, and one fraction cannot "
        "serve both bounds until that rate is measured and declared as `skips`.",
    ),
    "env-var-bare-cast": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "A filtered subset of tracked Python, against a Python class that grows elsewhere.",
    ),
    "excluded-tree-size-debt": (
        ABSOLUTE,
        "FIXED_INVENTORY",
        "Python inside the declared excluded trees -- a set the repository is trying to SHRINK, "
        "so a floor that rises with a reference would fight the work.",
    ),
    "fastapi-validation-handler": (ABSOLUTE, "SUBSET_DRIFTS", "Non-test Python, against all tracked Python."),
    "git-repo-root-call-site-files": (ABSOLUTE, "FIXED_INVENTORY", "Single-digit shell call sites."),
    "hardcoded-colour-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "One frontend tree's source, against all tracked `.vue`/`.ts`/`.js` including the other frontend.",
    ),
    "import-hermeticity": (
        ABSOLUTE,
        "NOT_PATHS",
        "Module records, not paths; the population is two declared trees minus tests.",
    ),
    "important-declaration-sweep": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "One frontend's components, against all tracked `.vue`.",
    ),
    "kb-admin-read-bypass": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Production Python under two trees, against all tracked Python.",
    ),
    "kb-content-redaction-chokepoint": (ABSOLUTE, "FIXED_INVENTORY", "Non-test files under one package."),
    "kb-read-visibility-production-sweep": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Production Python under three trees, against all tracked Python.",
    ),
    "model-revision-pinning-sweep": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Production Python under three trees, against all tracked Python.",
    ),
    "nginx-play-level-yml-sweep": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "`*.yml` under the ansible tree, against all tracked YAML.",
    ),
    "no-created-by-admin-literal": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Backend Python with tests excluded, against all tracked Python.",
    ),
    "npm-audit-workspace-coverage": (ABSOLUTE, "FIXED_INVENTORY", "Workspaces, not files; a named, single-digit set."),
    "one-claim-registry": (ABSOLUTE, "SUBSET_DRIFTS", "Python under five named trees, against all tracked Python."),
    "post-sync-branch-functions": (ABSOLUTE, "NOT_PATHS", "Functions inside one module, not files."),
    "prompt-injection-detector-strict-mode": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "A production Python subset, against all tracked Python.",
    ),
    "redaction-concept-census": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Tracked production Python, against all tracked Python including tests.",
    ),
    "response-model-secret-scan": (ABSOLUTE, "SUBSET_DRIFTS", "Backend Python modules, against all tracked Python."),
    "router-auth-coverage": (ABSOLUTE, "NOT_PATHS", "Routers registered in `core_routers.py`, not files."),
    "slm-frontend-components": (ABSOLUTE, "SUBSET_DRIFTS", "One frontend's components, against all tracked `.vue`."),
    "slm-frontend-locale-keys": (
        ABSOLUTE,
        "NOT_PATHS",
        "Message keys inside one JSON file; the only count of them is this sweep.",
    ),
    "slm-scripts-importing-services": (
        ABSOLUTE,
        "FIXED_INVENTORY",
        "A single-digit set the guard exists to keep at zero-or-few.",
    ),
    "sqlalchemy-requirements-files": (ABSOLUTE, "FIXED_INVENTORY", "Single-digit requirements files."),
    "store-fact-chokepoint": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "Production Python under two trees, against all tracked Python.",
    ),
    "tracked-key-material": (
        CONVERTIBLE,
        "REFERENCE_EXISTS",
        "Its population IS the tracked tree, the same shape `conflict-marker-scanned-files` "
        "already adopted. Held back on an OWNER question rather than a measurement: the file "
        "carries a recorded ruling that its floor is deliberately absolute and mid-window, and "
        "converting it would reverse that ruling from outside the file.",
    ),
    "undefined-css-var-scan": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "One frontend tree's source, against all tracked frontend source.",
    ),
    "vnc-password-not-in-frontend-source": (
        ABSOLUTE,
        "SUBSET_DRIFTS",
        "One frontend tree's source, against all tracked frontend source.",
    ),
    "websocket-subprotocol-echo": (
        ABSOLUTE,
        "FIXED_INVENTORY",
        "A couple of dozen backend modules that authenticate a WebSocket.",
    ),
    "workflow-job-parse-sweep": (ABSOLUTE, "NOT_PATHS", "Parsed workflow jobs, not files."),
    "workflow-rc-capture": (ABSOLUTE, "NOT_PATHS", "`run:` blocks under an errexit shell, not files."),
}

#: Declarations still waiting for a relative floor. Compared as a SET in both directions by
#: `reach_declarations_test`, not by a count: a `<=` ceiling never forces itself down, and one
#: declaration converting would silently free a slot for a new unconverted one
#: (RATCHET_BASELINES.md rule 4). SHRINKS ONLY -- an entry leaves when its declaration converts,
#: and nothing may add one.
CONVERTIBLE_BACKLOG = frozenset({"tracked-key-material"})

#: Declarations whose `what=` names no scope, because their discovery does not return paths a
#: prefix can describe, or because the population genuinely is the whole tree (`_reach_scope`'s
#: docstring states why `roots=` is opt-in). Compared as a SET in both directions, so a
#: declaration that gains `roots=` must be removed here and a new declaration has to make the
#: decision rather than inherit silence. SHRINKS ONLY.
#:
#: An earlier version of this was a `len(...) <= MAX_UNSCOPED` ceiling whose own comment claimed
#: a set comparison. A comment claiming a stronger check than the code performs is worse than no
#: comment, and a reviewer caught it; the names are frozen here instead.
UNSCOPED = frozenset(
    {
        "ansible-apt-repo-budget-override-sweep",
        "ansible-inventory-shell-sweep",
        "audio-extension-allowlist",
        "blanket-skip-test-module-sweep",
        "chromadb-bind-host-override-candidates",
        "chromadb-bind-launch-sites",
        "chromadb-compose-files",
        "chromadb-compose-port-sites",
        "chromadb-compose-services",
        "collectable-modules-inert-on-import",
        "component-style-block-sweep",
        "config-router-auth-coverage",
        "conflict-marker-scanned-files",
        "connector-redaction-sweep",
        "detect-environment-env-files",
        "docstring-restatement-scan",
        "dpkg-ansible-registrations",
        "dpkg-list-call-sites",
        "enum-hand-copy-census",
        "env-var-bare-cast",
        "excluded-tree-size-debt",
        "fastapi-validation-handler",
        "git-repo-root-call-site-files",
        "hardcoded-colour-scan",
        "hooks-path-override",
        "import-hermeticity",
        "important-declaration-sweep",
        "kb-content-redaction-chokepoint",
        "nginx-play-level-yml-sweep",
        "no-created-by-admin-literal",
        "npm-audit-workspace-coverage",
        "post-sync-branch-functions",
        "prompt-injection-detector-strict-mode",
        "redaction-concept-census",
        "redis-config-path-census",
        "reduced-motion-animate-call",
        "reduced-motion-animate-option",
        "reduced-motion-apex-animations",
        "reduced-motion-smooth-scroll",
        "response-model-secret-scan",
        "router-auth-coverage",
        "slm-frontend-components",
        "slm-frontend-locale-keys",
        "slm-scripts-importing-services",
        "sqlalchemy-requirements-files",
        "tracked-key-material",
        "tts-address-env-name-sweep",
        "undefined-css-var-scan",
        "vnc-password-not-in-frontend-source",
        "websocket-subprotocol-echo",
        "workflow-job-parse-sweep",
        "workflow-rc-capture",
    }
)
