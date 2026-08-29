#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# Canonical hardcoded-value rule set (#14371).
#
# Three independent detectors used to implement "find hardcoded values", each
# with its own pattern list, its own exclude list, and — measured, not assumed —
# rules none of the others had:
#
#   1. pipeline-scripts/detect-hardcoded-values.sh   (CI, ssot-coverage.yml)
#      the only one scanning .sh/.yml/.yaml and autobot-infrastructure/, the
#      only one with the account-identity rules, and the only one whose VM-IP
#      pattern covered every octet.
#   2. autobot-infrastructure/shared/scripts/detect-hardcoded-values.sh (dormant)
#      the only one with per-value SSOT SUGGESTIONS, the generic model-name
#      regex, the hardcoded-URL rule, and six context skips nothing else had.
#   3. .../hooks/pre-commit-hardcoded-values                 (the enforcing hook)
#      the only one with magic numbers, roles, categories, DSNs, timeouts,
#      AutoBot paths, the `.get("field", default)` call-argument shape, and the
#      TypeScript union-type / JSDoc skips.
#
# This file is the UNION of all three. Every rule any of them had is here; none
# was traded away for another. The two entry points below are thin:
#
#   pipeline-scripts/detect-hardcoded-values.sh              tree scan, CI
#   autobot-infrastructure/shared/scripts/hooks/pre-commit-hardcoded-values
#                                                            staged files, local
#
# They differ only in WHERE the lines come from and what they do with the
# verdict. The rules themselves are here, once.
#
# Source this file -- do not execute it.
#
# WHY THIS LIBRARY DOES NOT SOURCE autobot-infrastructure/shared/scripts/lib/
# ssot-config.sh, although the retired detector 2 did (#14877 / #14172).
#
# That dependency deliberately does NOT travel with the logic, and the reason is
# not "we no longer need PROJECT_ROOT" -- it is that sourcing it would be unsafe
# here. ssot-config.sh `set -a`-loads the master .env and exports the whole of
# it, AUTOBOT_REDIS_PASSWORD included. This library is a scanner whose entire
# output is matched source lines, run in CI with its findings printed to a
# public log and posted to pull requests. Pulling a live secret into that
# process is a disclosure risk that the detector gains nothing from: its SSOT
# tables below are DETECTION PATTERNS (the literals it hunts for and the config
# key that replaces each), not runtime configuration it reads to do its job, and
# detector 2's tables were literal for the same reason. PROJECT_ROOT is resolved
# from each entry point's own location, which needs no .env and works on a
# deployed install that has no checkout.
#
# What DID travel is the capability #14877 added: a dependency that cannot be
# loaded must abort loudly rather than let the run continue on fallbacks. Every
# `source` in this library and in both entry points ends in an explicit failure
# block that exits non-zero, and hv_load_baseline treats an absent or empty
# baseline as fatal for the same reason -- an unread exemption set and an empty
# one are indistinguishable to every caller.
#
# Deriving the live fleet addresses from ssot-config.sh, so a renumbered fleet
# is still caught, is a real improvement and a separate, measurable change with
# its own secret-handling question to answer. It is filed rather than bundled
# into this consolidation.
#
# Output contract of hv_scan_line: zero or more records on stdout, one per line,
#   SEVERITY|CLASS|file|lineno|value|suggestion
# SEVERITY is VIOLATION or WARNING. CLASS is `ssot` for values that have a
# direct SSOT config equivalent (the ones ssot-coverage.yml fails the build on)
# or `other` for the rest — the same two buckets the CI entry point has always
# reported, so its JSON contract is unchanged.

if [ -n "${_AUTOBOT_HV_RULES_LOADED:-}" ]; then
    return 0
fi
_AUTOBOT_HV_RULES_LOADED=1

# ── SSOT mapping tables ──────────────────────────────────────────────────────
# From detector 2, which was the only one that could tell a developer WHICH
# config key replaces the literal it found. Losing that would have been a real
# capability loss, so the tables come across whole.
declare -A HV_SSOT_VM_IPS=(
    ["172.16.168.20"]="config.vm.main (AUTOBOT_BACKEND_HOST)"
    ["172.16.168.21"]="config.vm.frontend (AUTOBOT_FRONTEND_HOST)"
    ["172.16.168.22"]="config.vm.npu (AUTOBOT_NPU_WORKER_HOST)"
    ["172.16.168.23"]="config.vm.redis (AUTOBOT_REDIS_HOST)"
    ["172.16.168.24"]="config.vm.aistack (AUTOBOT_AI_STACK_HOST)"
    ["172.16.168.25"]="config.vm.browser (AUTOBOT_BROWSER_SERVICE_HOST)"
)

declare -A HV_SSOT_PORTS=(
    ["8001"]="config.port.backend (AUTOBOT_BACKEND_PORT)"
    ["5173"]="config.port.frontend (AUTOBOT_FRONTEND_PORT)"
    ["6379"]="config.port.redis (AUTOBOT_REDIS_PORT)"
    ["11434"]="config.port.ollama (AUTOBOT_OLLAMA_PORT)"
    ["6080"]="config.port.vnc (AUTOBOT_VNC_PORT)"
    ["8080"]="config.port.aistack (AUTOBOT_AI_STACK_PORT)"
    ["8081"]="config.port.npu (AUTOBOT_NPU_WORKER_PORT)"
    ["8082"]="config.port.npu (AUTOBOT_NPU_WORKER_PORT)"
    ["3000"]="config.port.* from ssot_config"
    # #14371: 8443, 5432 and 9090 come from detector 1's PORT_PATTERN, which was
    # DECLARED AND NEVER USED — the variable was assigned at the top of the
    # script and no scan function ever referenced it. A rule that existed only
    # as a string is still a rule the merge has to carry, so it is wired in here
    # rather than quietly dropped along with the dead variable.
    ["8443"]="config.port.* from ssot_config"
    ["5432"]="config.port.* from ssot_config"
    ["9090"]="config.port.* from ssot_config"
)

declare -A HV_SSOT_MODELS=(
    ["qwen3.5:9b"]="config.llm.default_model (AUTOBOT_DEFAULT_LLM_MODEL)"
    ["nomic-embed-text:latest"]="config.llm.embedding_model (AUTOBOT_EMBEDDING_MODEL)"
    ["llama3.2:latest"]="ROUTING_MODEL/DEFAULT_LLM_MODEL from autobot_shared.ssot_config"
    ["llama3.2:1b"]="ROUTING_MODEL/DEFAULT_LLM_MODEL from autobot_shared.ssot_config"
    ["gemma2:2b"]="ROUTING_MODEL/DEFAULT_LLM_MODEL from autobot_shared.ssot_config"
    ["phi3:mini"]="ROUTING_MODEL/DEFAULT_LLM_MODEL from autobot_shared.ssot_config"
    ["mistral:7b-instruct"]="ROUTING_MODEL/DEFAULT_LLM_MODEL from autobot_shared.ssot_config"
    ["dolphin-llama3:8b"]="ROUTING_MODEL/DEFAULT_LLM_MODEL from autobot_shared.ssot_config"
)

# ── rule patterns ────────────────────────────────────────────────────────────
# Detector 1's VM-IP pattern covered EVERY fourth octet; detector 3's covered
# only 19-25. The union keeps the wide one, so a new fleet address is caught the
# day it is typed rather than the day someone remembers to widen a regex.
# PARSED BY tools/lint/check_docs_no_fleet_addressing.py (#15208), which truncates
# this pattern at its final '\.' to derive the bare subnet prefix for docs/. Keep
# the assignment un-indented, single-quoted and without an 'export' prefix: that
# reader fails closed, so a reformat here breaks the docs guard rather than
# silently narrowing it.
HV_VM_IP='172\.16\.168\.[0-9]+'
HV_PORTS='8001|5173|6379|11434|6080|8080|8081|8082|3000|8443|5432|9090'
HV_AUTOBOT_PATHS='/opt/autobot|/tmp/autobot|/var/lib/autobot'
HV_MODEL_NAMES='llama3\.2:latest|llama3\.2:1b|qwen3\.5:9b|nomic-embed-text:latest|gemma2:2b|phi3:mini|mistral:7b-instruct|dolphin-llama3:8b'
# Detector 2's generic catch-all, kept alongside the explicit list above: it
# catches a model tag nobody has added to the table yet.
HV_MODEL_GENERIC='(llama3|dolphin|openchat|gemma|phi|deepseek|qwen)[a-z0-9._-]*:[0-9]+(b|B)'
HV_DB_DSN='(sqlite:///|postgresql://[^{]|mysql://[^{]|mongodb://[^{])'
HV_TIMEOUT_VALUES='30|60|120|300|3600'
HV_URL='https?://[a-zA-Z0-9]'
# Account identity, from detector 1 (#14316). ACCOUNT_PATH is the original rule;
# ACCOUNT_POSITION is the broadened half — the same two account names appearing
# bare, in the positions that carry an account identity in shell/systemd/sudoers
# text. A path match alone misses exactly that shape.
HV_ACCOUNT_PATH='/home/kali|/home/autobot'
HV_ACCOUNT_POSITION='(User=|Group=)(kali|autobot)\b|chown[^=]*\b(kali|autobot):(kali|autobot)\b|^[[:space:]]*(kali|autobot)[[:space:]]+ALL='

# One ERE that matches a line if ANY rule above could fire on it.
#
# A tree scan cannot afford to run every rule over every line of a 5000-file
# repository in bash: this is the cheap first pass that `grep -rE` applies, and
# only the surviving lines reach hv_scan_line. It must therefore be a SUPERSET
# of every rule's trigger — a rule missing from here is a rule that never fires
# on a tree scan, silently. hardcoded_value_rules_test.py asserts exactly that,
# by feeding each rule's own positive fixture through the prefilter.
# The `.get("field", default)` shape needs its OWN alternative here. The
# keyword-style alternatives below anchor on an `=`/`:` right after the field
# name, and in a `.get()` call there is none — `doc.get("category", "general")`
# has a quote and a comma where the operator would be. Caught by
# hardcoded_value_rules_test.py, which feeds every rule's own positive fixture
# through this pattern: without it the role and category call-argument rules
# fired under hv_scan_line and were UNREACHABLE on a tree scan. Full surface,
# no sink — the rule existed, was registered, was tested, and nothing on the
# tree-scan path could ever reach it.
_HV_PREFILTER_GET_FIELDS='role|category|search_mode|mode|timeout|timeout_seconds|connect_timeout|read_timeout|limit|top_k|max_results|page_size|batch|offset|rag'
hv_prefilter_pattern() {
    # Assembled in two parts: the `.get()` alternative carries both quote
    # characters, and inlining it would close this string's own quoting.
    local get_shape="\\.get\\([[:space:]]*[\"']("
    get_shape+="${_HV_PREFILTER_GET_FIELDS})[\"']"
    printf '%s' "${HV_VM_IP}|:(${HV_PORTS})[^0-9]|${HV_AUTOBOT_PATHS}|${HV_MODEL_NAMES}|${HV_MODEL_GENERIC}|${HV_DB_DSN}|${HV_URL}|${HV_ACCOUNT_PATH}|${HV_ACCOUNT_POSITION}|(limit|top_k|max_results|page_size|batch|offset|rag)|(role|category|search_mode|mode)[^a-z_]*[=:]|(timeout|timeout_seconds|connect_timeout|read_timeout)|${get_shape}"
}

# ── matching primitives ──────────────────────────────────────────────────────
#
# PERFORMANCE IS A CORRECTNESS PROPERTY HERE. The first version of this library
# expressed every predicate as `printf '%s' "$line" | grep -qE …`, which forks
# two processes per rule per line. Measured against the six scan directories it
# had not finished after ten minutes — and a tree scan that times out is a scan
# that reports nothing, which is the same fail-open shape the rules exist to
# catch, one level up. bash's own `[[ =~ ]]` runs the same ERE in-process, and
# `${line,,}` gives the case-insensitive rules a lowercase copy without the
# global `shopt -s nocasematch` state.
#
# So: no subprocess in the per-line path. The extracted match comes from
# BASH_REMATCH, never from a second `grep -o` pass.

# 0 when $1 matches ERE $2. Sets HV_MATCH to the matched text.
_hv_match() {
    [[ $1 =~ $2 ]] || return 1
    HV_MATCH="${BASH_REMATCH[0]}"
    return 0
}

# ── file scope ───────────────────────────────────────────────────────────────
# The union of all three exclude lists. Where they disagreed the WIDER exclusion
# wins for SSOT-definition files (a file that IS the config is not a violation
# of using it) and the NARROWER one wins for everything else, so no detector's
# coverage shrinks.
HV_SCAN_EXTENSIONS='py|ts|vue|js|sh|yml|yaml'

# Files that are themselves the source of truth, or are generated, or are tests
# asserting known config values.
_HV_EXCLUDE_RE='(/__pycache__/|/node_modules/|/\.venv/|/venv/|/archive/|/dist/|/tmp/|/\.tmp/|^tmp/|^archive/)'
_HV_EXCLUDE_RE+='|(^|/)(_generated|generated)/'
_HV_EXCLUDE_RE+='|(test_[^/]*\.(py|ts)$|[^/]*_test\.(py|ts)$|[^/]*\.(test|spec)\.(ts|js)$|/__tests__/)'
# #15273: test-SUPPORT modules living under repo_tests/ -- helper functions
# and fixture data imported only by *_test.py files, collected as a test by
# none of them -- get the same exemption the filename rule above already
# grants its siblings, for the reason that rule states at its own top: a
# module whose only reachable caller is test code carries the same
# 'fixtures legitimately use literal IPs' rationale (HARDCODING_PREVENTION.md)
# no matter what its filename happens to be. Scoped to the DIRECTORY, not to
# a widened filename pattern, so it cannot reach into production code that
# happens to share a name -- repo_tests/ carries nothing else (#15187/#15195).
_HV_EXCLUDE_RE+='|(^|/)repo_tests/'
_HV_EXCLUDE_RE+='|(ssot_config\.py|ssot-config\.ts|ssot_mappings\.py|registry_defaults\.py|threshold_constants\.py)'
_HV_EXCLUDE_RE+='|(path_constants\.py|network_constants\.py|security_constants\.py|constants/network\.ts)'
_HV_EXCLUDE_RE+='|(/constants/|config\.py$|config\.yaml$|\.env|\.example$|\.lock$)'
# The detectors themselves: their bodies are literal tables of every SSOT IP,
# port and model. They are SSOT-definition files exactly like ssot_mappings.py,
# not violations of the rule they implement (#14316).
_HV_EXCLUDE_RE+='|(detect-hardcoded-values\.sh$|hardcoded-value-rules\.sh$|pre-commit-hardcoded-values$)'
_HV_EXT_RE="\.(${HV_SCAN_EXTENSIONS})$"

# 0 when *$1* should be scanned.
hv_file_in_scope() {
    local path="${1:-}"
    [ -n "$path" ] || return 1
    [[ $path =~ $_HV_EXT_RE ]] || return 1
    [[ $path =~ $_HV_EXCLUDE_RE ]] && return 1
    return 0
}

# ── shared line predicates ───────────────────────────────────────────────────
_HV_COMMENT_RE='^[[:space:]]*(#|//|\*)'
# A line already going through config / an env var. Detector 1 also honoured an
# explicit `noqa` marker; both are union members.
_HV_CONFIG_RE='(config\.|CONFIG\[|getenv|os\.environ|ssot_config|AUTOBOT_[A-Z_]+|NetworkConstants)'
_HV_NOQA_RE='(#[[:space:]]*noqa|//[[:space:]]*noqa)'
# A TypeScript/Flow string-literal union type, e.g.
# `role?: 'user' | 'assistant' | 'system'` — a type annotation enumerating the
# accepted values, not a hardcoded default (detector 3, #14048).
_HV_UNION_TYPE_RE="[\"'][[:space:]]*\|[[:space:]]*[\"']"

# The call-argument shape `obj.get("field", value)` (detector 3, #14005/#14048).
#
# Every keyword-style regex below binds a field name to a literal with `=`/`:`.
# In a `.get()` call the field name is a STRING-LITERAL positional argument, so
# there is no operator to anchor on and the keyword-style pattern is blind to
# it. Anchored to `.get(` so it matches an actual dict-style lookup and not any
# comma-joined pair of literals (a tuple, an assertion).
#
#   $1 line (already lowercased by the caller for the case-insensitive rules)
#   $2 field alternation   $3 value regex, already quoted or bare
_hv_get_call_argument() {
    local re="\\.get\\([[:space:]]*[\"'](${2})[\"'][[:space:]]*,[[:space:]]*${3}"
    [[ $1 =~ $re ]]
}

# Strip the userinfo out of a URL-shaped value before it is reported.
#
# Both rules that emit one of these echo the literal they matched, and that
# literal reaches a tracked baseline file and a public CI log that is posted
# onto pull requests. `postgresql://user:pass@host/db` therefore travels
# verbatim into both -- demonstrated, not hypothetical: two such values were
# already sitting in the generated baseline. Those two happen to be
# placeholders, which is luck about the sample, not a property of the
# mechanism: a real credential in a real DSN lands there identically.
#
# Shared by _hv_rule_dsn and _hv_rule_url rather than written twice -- they had
# the same defect for the same reason, and two redactors would be two things to
# drift. The scheme and host survive so the finding is still actionable; only
# the credential is dropped.
#
# `[^/@[:space:]]*` before the `@` is what keeps this from eating a path: in
# `https://example.com/a@b` the `@` follows a `/`, so nothing is redacted.
_hv_redact_userinfo() {
    if [[ $1 =~ ^(.*[a-zA-Z0-9+.-]+://)[^/@[:space:]]*@(.*)$ ]]; then
        printf '%s<redacted>@%s' "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}"
        return 0
    fi
    printf '%s' "$1"
}

_hv_emit() {
    printf '%s|%s|%s|%s|%s|%s\n' "$1" "$2" "$3" "$4" "$5" "$6"
}

# ── the rules ────────────────────────────────────────────────────────────────
# One function per rule class, each taking (file, lineno, line, lowercased line)
# and emitting zero or more records. Every skip that any of the three detectors
# applied to its own version of the rule is applied here.

_HV_SVG_RE='(<path|fill-rule|clip-rule|d="[Mm])'
_HV_PORT_CONTEXT_RE=":(${HV_PORTS})[^0-9]"
_HV_PORT_SKIP_RE='(\[[0-9]*:[0-9]*\]|"[0-9]+:[0-9]+"|A[0-9]{2}:[0-9]{4})'
_HV_SCHEMA_EXAMPLE_RE='(json_schema_extra|"example"|placeholder=|e\.g\.,|"url":[[:space:]]*"http)'
_HV_MODEL_CONST_RE='(ROUTING_MODEL|CLASSIFICATION_MODEL|LIGHT_PROCESSING_MODEL|INSTRUCTION_MODEL|SYSTEM_MODEL|QUALITY_MODEL|DEFAULT_LLM_MODEL|DEFAULT_EMBEDDING_MODEL)'
_HV_MODEL_TABLE_RE='(cost_per|compute_cost|"models":[[:space:]]*\[|embedding_models[[:space:]]*=|complex requests to)'
_HV_MODEL_LIST_ITEM_RE="^[[:space:]]+[\"'][a-z0-9_.-]+:[a-z0-9]+[\"'],?$"
_HV_MODEL_QUOTED_RE="[\"'](${HV_MODEL_NAMES})[\"']"
_HV_PATH_QUOTED_RE="[\"'](${HV_AUTOBOT_PATHS})[^\"']*"
_HV_PATH_SKIP_RE='(AUTOBOT_BASE_DIR|PathConfig|PathConstants|Field\(|default=[^,]*opt/autobot|\$\{[A-Z_]+:-/opt/autobot)'
_HV_DSN_QUOTED_RE='"(sqlite:///|postgresql://|mysql://|mongodb://)[^"]*"'
_HV_DSN_SKIP_RE='(SettingsConfigDict|env_prefix|default=|Field\()'
_HV_URL_FULL_RE="${HV_URL}[^\"'\`[:space:],)]*"
_HV_URL_SKIP_RE='(example\.(com|org|net)|autobot\.local|localhost|127\.0\.0\.1|w3\.org|xmlns=|placeholder=|schemas\.|json-schema\.org|\.github\.com|opensource\.org|apache\.org)'
_HV_ACCOUNT_RE="(${HV_ACCOUNT_PATH}|${HV_ACCOUNT_POSITION})"
_HV_ROLE_SKIP_RE='(CategoryDefaults\.|ROLE_|^[[:space:]]*(ROLE_|DEFAULT_)[A-Z_]*=)'
_HV_ROLE_KEYWORD_RE="role[^a-z_]*[=:][^=]*[\"'](user|assistant|system)[\"']"
_HV_ROLE_VALUE_RE="[\"'](user|assistant|system)[\"']"
_HV_CATEGORY_SKIP_RE='(CategoryDefaults\.|GENERAL|UNKNOWN|SEARCH_MODE)'
_HV_CATEGORY_KEYWORD_RE="(category|search_mode|mode)[^a-z_]*[=:][^=]*[\"'](general|hybrid|unknown)[\"']"
_HV_CATEGORY_VALUE_RE="[\"'](general|hybrid|unknown)[\"']"
_HV_TIMEOUT_SKIP_RE='(TimeoutConfig|AUTOBOT_TIMEOUT|^[[:space:]]*[A-Z_]*TIMEOUT[A-Z_]*[[:space:]]*=)'
_HV_TIMEOUT_KEYWORD_RE="(timeout|timeout_seconds|connect_timeout|read_timeout)[^a-z_]*[=:][^=]*\b(${HV_TIMEOUT_VALUES})\b"
_HV_TIMEOUT_VALUE_RE="\b(${HV_TIMEOUT_VALUES})\b"
_HV_MAGIC_SKIP_RE='(^from |^import |QueryDefaults\.|DEFAULT_|_LIMIT|_SIZE|-> int$|-> int:|List\[|Optional\[)'
_HV_OFFSET_RE='offset[^a-z_]*[=:][^=]*\b0\b'

# VM IPs. Wide octet range (detector 1); per-IP suggestion (detector 2).
_hv_rule_ip() {
    _hv_match "$3" "$HV_VM_IP" || return 0
    local ip="$HV_MATCH"
    # SVG/path data: `d="M172.16…"` is coordinate data, not an address.
    [[ $3 =~ $_HV_SVG_RE ]] && return 0
    _hv_emit VIOLATION ssot "$1" "$2" "$ip" "${HV_SSOT_VM_IPS[$ip]:-config.vm.* from ssot_config}"
}

# Infrastructure ports in URL context (`:8001/`, `:8001"`).
_hv_rule_port() {
    _hv_match "$3" "$_HV_PORT_CONTEXT_RE" || return 0
    # HV_MATCH is ":<port><one trailing non-digit>"; strip both ends.
    local port="${HV_MATCH#:}"; port="${port%[^0-9]}"
    # Array slicing `[0:10]`, docker user mapping `"1000:1000"`, OWASP ids.
    [[ $3 =~ $_HV_PORT_SKIP_RE ]] && return 0
    # JSON-schema examples, placeholders, prose URLs (detector 2, #2687).
    [[ $3 =~ $_HV_SCHEMA_EXAMPLE_RE ]] && return 0
    _hv_emit VIOLATION ssot "$1" "$2" ":$port" "${HV_SSOT_PORTS[$port]:-config.port.* from ssot_config}"
}

# Model-name literals: the explicit table AND detector 2's generic tag regex.
_hv_rule_model() {
    case "$1" in *config*|*failsafe*|*llm_interface*) return 0 ;; esac
    [[ $3 =~ $_HV_MODEL_CONST_RE ]] && return 0
    # Cost tables, discovery lists and bare string list items (detector 2).
    [[ $3 =~ $_HV_MODEL_TABLE_RE ]] && return 0
    [[ $3 =~ $_HV_MODEL_LIST_ITEM_RE ]] && return 0
    if _hv_match "$3" "$_HV_MODEL_QUOTED_RE"; then
        local bare="${HV_MATCH//\"/}"; bare="${bare//\'/}"
        _hv_emit VIOLATION ssot "$1" "$2" "$bare" "${HV_SSOT_MODELS[$bare]:-config.llm.default_model (AUTOBOT_DEFAULT_LLM_MODEL)}"
        return 0
    fi
    _hv_match "$3" "$HV_MODEL_GENERIC" || return 0
    _hv_emit VIOLATION ssot "$1" "$2" "$HV_MATCH" "config.llm.default_model (AUTOBOT_DEFAULT_LLM_MODEL)"
}

# AutoBot filesystem paths used as bare literals (detector 3, #3397).
_hv_rule_path() {
    _hv_match "$3" "$_HV_PATH_QUOTED_RE" || return 0
    local value="$HV_MATCH"
    [[ $3 =~ $_HV_PATH_SKIP_RE ]] && return 0
    _hv_emit VIOLATION other "$1" "$2" "$value" "config.path.base_dir, or os.environ.get('AUTOBOT_BASE_DIR', '/opt/autobot')"
}

# Database DSN literals (detector 3, #3397).
_hv_rule_dsn() {
    _hv_match "$3" "$_HV_DSN_QUOTED_RE" || return 0
    local dsn="$HV_MATCH"
    [[ $3 =~ $_HV_DSN_SKIP_RE ]] && return 0
    _hv_emit VIOLATION other "$1" "$2" "$(_hv_redact_userinfo "$dsn")" "config.database.* from ssot_config, or the AUTOBOT_DB_URL env var"
}

# Hardcoded URLs (detector 2 only — the single rule that fork alone carried).
_hv_rule_url() {
    _hv_match "$3" "$_HV_URL_FULL_RE" || return 0
    local url="$HV_MATCH"
    case "$1" in
        *enterprise*|*sso_integration*|*injection_detector*|*domain_security*|*secure_llm*|*secure_web*) return 0 ;;
    esac
    # Example domains, W3C/SVG namespaces, licence URLs and placeholders.
    [[ $3 =~ $_HV_URL_SKIP_RE ]] && return 0
    # A URL containing a known SSOT IP is reported by _hv_rule_ip instead, with
    # the config key that replaces it — a strictly more useful message.
    [[ $3 =~ $HV_VM_IP ]] && return 0
    _hv_emit VIOLATION other "$1" "$2" "$(_hv_redact_userinfo "$url")" "SSOT config URLs (config.backend_url, config.redis_url, …)"
}

# Account identities in the positions that actually carry one (detector 1,
# #14316): a /home/<user> path, a systemd User=/Group=, a chown owner:group, or
# a sudoers rule. The path rule alone missed `User=kali`, `chown kali:kali` and
# bare sudoers lines in three infrastructure scripts.
_hv_rule_account() {
    _hv_match "$3" "$_HV_ACCOUNT_RE" || return 0
    _hv_emit VIOLATION other "$1" "$2" "$HV_MATCH" "AUTOBOT_BASE_DIR / an account variable, not a literal account name"
}

# Role strings (detector 3).
#
# #14024: THREE unrelated vocabularies use the word "role" and share literals —
# platform RBAC (auth.permissions.Role), company membership
# (llc.models.enums.MembershipRole) and chat message roles
# (CategoryDefaults.ROLE_*). This rule detects the chat vocabulary's values, but
# "user" is in the RBAC one as well, so naming a chat constant for it is a coin
# flip that a reader then applies mechanically.
#
# That is not hypothetical. `tools/tool_registry` had `"user_role": "user"`, an
# RBAC input read by `worker_node._validate_user_role`. This rule suggested
# `CategoryDefaults.ROLE_USER`. Applying it would have tied an authorization
# decision to a presentation constant, gone green, and been invisible in review
# (#13934); a later re-tuning of the chat vocabulary would then have silently
# changed an authz value.
#
# So for an ambiguous value the guard now REPORTS the ambiguity instead of
# picking a side. "assistant" and "system" belong to the chat vocabulary alone
# and keep the concrete suggestion. The detection set is unchanged — only the
# advice — so this adds no findings and needs no baseline change.
_HV_ROLE_AMBIGUOUS_VALUES_RE='(user)'
_HV_ROLE_CHAT_SUGGESTION="CategoryDefaults.ROLE_ASSISTANT/ROLE_SYSTEM (chat message vocabulary)"
_HV_ROLE_AMBIGUOUS_SUGGESTION="AMBIGUOUS (#14024): this value is in more than one role vocabulary \
- chat (CategoryDefaults.ROLE_USER) and platform RBAC (auth.permissions.Role.USER). \
Trace the consumer before replacing it; do not apply a suggestion blind."
_hv_rule_role() {
    [[ $3 =~ $_HV_ROLE_SKIP_RE ]] && return 0
    [[ $3 =~ $_HV_UNION_TYPE_RE ]] && return 0
    [[ $3 =~ $_HV_ROLE_KEYWORD_RE ]] || _hv_get_call_argument "$3" 'role' "$_HV_ROLE_VALUE_RE" || return 0
    _hv_match "$3" "$_HV_ROLE_VALUE_RE" || return 0
    local _hv_role_suggestion="$_HV_ROLE_CHAT_SUGGESTION"
    [[ $HV_MATCH =~ $_HV_ROLE_AMBIGUOUS_VALUES_RE ]] && _hv_role_suggestion="$_HV_ROLE_AMBIGUOUS_SUGGESTION"
    _hv_emit VIOLATION other "$1" "$2" "$HV_MATCH" "$_hv_role_suggestion"
}

# Category / search-mode strings (detector 3, #14005).
_hv_rule_category() {
    [[ $3 =~ $_HV_CATEGORY_SKIP_RE ]] && return 0
    [[ $3 =~ $_HV_UNION_TYPE_RE ]] && return 0
    [[ $3 =~ $_HV_CATEGORY_KEYWORD_RE ]] || _hv_get_call_argument "$3" 'category|search_mode|mode' "$_HV_CATEGORY_VALUE_RE" || return 0
    _hv_match "$3" "$_HV_CATEGORY_VALUE_RE" || return 0
    _hv_emit VIOLATION other "$1" "$2" "$HV_MATCH" "CategoryDefaults.GENERAL/SEARCH_MODE_HYBRID/UNKNOWN"
}

# Timeout literals (detector 3, #3397).
_hv_rule_timeout() {
    [[ $3 =~ $_HV_TIMEOUT_SKIP_RE ]] && return 0
    [[ $3 =~ $_HV_TIMEOUT_KEYWORD_RE ]] || _hv_get_call_argument "$3" 'timeout|timeout_seconds|connect_timeout|read_timeout' "$_HV_TIMEOUT_VALUE_RE" || return 0
    _hv_match "$3" "$_HV_TIMEOUT_VALUE_RE" || return 0
    _hv_emit VIOLATION other "$1" "$2" "$HV_MATCH" "config.timeout.* from ssot_config (TimeoutConfig)"
}

# One magic-number pattern: the keyword-style shape OR the call-argument shape.
# $4 is the LOWERCASED line — detector 3 matched these case-insensitively.
_hv_magic_pattern() {
    local file="$1" n="$2" lower="$3" fields="$4" value="$5" fix="$6"
    local re="(${fields})[^a-z_].*=[[:space:]]*${value}\b"
    [[ $lower =~ $re ]] || _hv_get_call_argument "$lower" "$fields" "${value}\\b" || return 1
    _hv_emit VIOLATION other "$file" "$n" "$value" "$fix"
}

# Query/pagination magic numbers (detector 3). Five patterns, one of which is a
# WARNING rather than a VIOLATION — `offset=0` is common enough that detector 3
# deliberately did not block on it, and that severity distinction is itself a
# rule the merge has to carry.
_hv_rule_magic_number() {
    local file="$1" n="$2" lower="$4"
    [[ $3 =~ $_HV_MAGIC_SKIP_RE ]] && return 0
    _hv_magic_pattern "$file" "$n" "$lower" 'limit|top_k|max_results|page_size' '10' \
        "QueryDefaults.DEFAULT_SEARCH_LIMIT" && return 0
    _hv_magic_pattern "$file" "$n" "$lower" 'limit|page_size' '50' \
        "QueryDefaults.DEFAULT_PAGE_SIZE" && return 0
    _hv_magic_pattern "$file" "$n" "$lower" 'limit|batch' '100' \
        "QueryDefaults.KNOWLEDGE_DEFAULT_LIMIT or BatchConfig.LARGE_BATCH" && return 0
    if [[ $lower =~ $_HV_OFFSET_RE ]] || _hv_get_call_argument "$lower" 'offset' '0\b'; then
        _hv_emit WARNING other "$file" "$n" "offset=0" "QueryDefaults.DEFAULT_OFFSET, for consistency"
        return 0
    fi
    _hv_magic_pattern "$file" "$n" "$lower" 'max_results|rag' '5' \
        "QueryDefaults.RAG_DEFAULT_RESULTS" && return 0
    return 0
}

# ── the rule registry, and the scan entry points ────────────────────────────
#
# Every rule class the three detectors had, in one list. Adding a rule means
# adding a function and a name here; hardcoded_value_rules_test.py asserts that
# each name in this list has a fixture that trips it AND that the fixture
# survives hv_prefilter_pattern, so a rule cannot be registered and then be
# unreachable on a tree scan.
HV_RULES=(
    ip
    port
    model
    path
    dsn
    url
    account
    role
    category
    timeout
    magic_number
)

# Apply every rule to one line. Emits zero or more records; always returns 0.
hv_scan_line() {
    local file="$1" n="$2" line="$3" rule lower
    [[ $line =~ $_HV_COMMENT_RE ]] && return 0
    [[ $line =~ $_HV_NOQA_RE ]] && return 0
    [[ $line =~ $_HV_CONFIG_RE ]] && return 0
    lower="${line,,}"
    for rule in "${HV_RULES[@]}"; do
        "_hv_rule_${rule}" "$file" "$n" "$line" "$lower"
    done
    return 0
}

# Apply every rule to every line of one file, exact line numbers preserved.
#
# The prefilter is applied per line here as well as on the tree-scan path, for
# two reasons and not only the obvious one.
#
# Speed: `pre-commit run --all-files` hands this entry point every tracked file,
# and `verify-precommit-config` is a REQUIRED check. Measured without the
# prefilter, 200 files took 78s — about 50 minutes over the 7639 tracked
# in-scope files, which is not a slow check, it is a check that never reports.
#
# Symmetry, which matters more: the two entry points must agree about what is in
# scope. If a tree scan filtered lines and a staged scan did not, the same file
# would be judged differently depending on which one looked at it — the exact
# shape of the get_staged_files defect (#14034) that reported a Vue file as a
# Redis connection. Both paths now apply the same superset filter, and
# hardcoded_value_rules_test.py asserts per rule that the filter really is a
# superset, so this costs no coverage on either.
#
# Line numbers stay exact because the counter increments before the filter.
hv_scan_file() {
    local file="${1:?file required}" n=0 line
    [ -f "$file" ] || return 0
    # Computed once per process, not once per file: the command substitution is
    # a fork, and pre-commit hands this entry point every tracked file in one
    # invocation.
    [ -n "${_HV_PREFILTER_CACHE:-}" ] || _HV_PREFILTER_CACHE="$(hv_prefilter_pattern)"
    local prefilter="$_HV_PREFILTER_CACHE"
    while IFS= read -r line || [ -n "$line" ]; do
        n=$((n + 1))
        [[ $line =~ $prefilter ]] || continue
        hv_scan_line "$file" "$n" "$line"
    done < "$file"
    return 0
}

# Apply every rule to a tree, using hv_prefilter_pattern as the cheap first pass.
#
# The prefilter is a SUPERSET of every rule's trigger, so it changes the cost of
# a whole-tree scan and not its result — the property the test suite pins per
# rule, by feeding each rule's own positive fixture through it.
hv_scan_tree() {
    local root="${1:?root required}" ext raw file n line
    local -a includes=() args=()
    IFS='|' read -r -a includes <<< "$HV_SCAN_EXTENSIONS"
    for ext in "${includes[@]}"; do args+=("--include=*.${ext}"); done
    [ -d "$root" ] || return 0
    while IFS= read -r raw; do
        [ -n "$raw" ] || continue
        file="${raw%%:*}"; raw="${raw#*:}"
        n="${raw%%:*}";   line="${raw#*:}"
        hv_file_in_scope "$file" || continue
        hv_scan_line "$file" "$n" "$line"
    done < <(grep -rnE "${args[@]}" -e "$(hv_prefilter_pattern)" "$root" 2>/dev/null || true)
    return 0
}

# ── the measured baseline ────────────────────────────────────────────────────
#
# pipeline-scripts/hardcoded_values_baseline.txt records what the merged rule
# set already finds in the tree, keyed `<count>|<class>|<file>|<value>`. The
# COUNT is part of the key on purpose: without it, a second occurrence of an
# already-known value in an already-known file would be waved through, and the
# baseline would grow silently while appearing to hold.
#
# Suppressed findings are never discarded — hv_partition returns them so both
# entry points can print how many there were and which issue owns them.
HV_BASELINE_ISSUE="#14371"
declare -A HV_BASELINE=()
declare -A HV_BASELINE_SEEN=()
# Declared at load so `set -u` cannot turn "partition was never called" into an
# unbound-variable crash that looks like a scan failure.
HV_SUPPRESSED=0

# Parse a baseline file into the associative array named by $2.
#
# One parser, two callers: hv_load_baseline below and the no-growth guard, which
# has to read TWO baselines (this branch's and the base ref's) in one process.
# Writing the guard its own parser would be a second thing to drift from the
# format -- the exact fork this whole change exists to stop.
#
# Fail-closed at every step. A named-but-absent file, a file that parses to
# nothing, a line whose count is not a number, and a line with an empty key are
# all FATAL: an unread exemption set and an empty one are indistinguishable to
# every caller, and the unread one silently turns 1977 known findings into 1977
# build failures -- or, in the guard's direction, waves through every addition.
hv_parse_baseline_into() {
    local _hv_bp_file="${1:?baseline path required}" _hv_bp_line _hv_bp_count _hv_bp_key
    local -n _hv_bp_out="${2:?target array name required}"
    _hv_bp_out=()
    [ -f "$_hv_bp_file" ] || { printf 'FATAL: baseline %s does not exist\n' "$_hv_bp_file" >&2; return 1; }
    while IFS= read -r _hv_bp_line; do
        [[ $_hv_bp_line =~ ^[[:space:]]*(#|$) ]] && continue
        _hv_bp_count="${_hv_bp_line%%|*}"
        _hv_bp_key="${_hv_bp_line#*|}"
        [[ $_hv_bp_count =~ ^[0-9]+$ ]] || {
            printf 'FATAL: %s: count is not a number: %s\n' "$_hv_bp_file" "$_hv_bp_line" >&2
            return 1
        }
        [ -n "$_hv_bp_key" ] && [ "$_hv_bp_key" != "$_hv_bp_line" ] || {
            printf 'FATAL: %s: line has no <count>|<key> separator: %s\n' "$_hv_bp_file" "$_hv_bp_line" >&2
            return 1
        }
        _hv_bp_out["$_hv_bp_key"]="$_hv_bp_count"
    done < "$_hv_bp_file"
    [ "${#_hv_bp_out[@]}" -gt 0 ] || {
        printf 'FATAL: baseline %s parsed to zero entries\n' "$_hv_bp_file" >&2
        return 1
    }
    return 0
}

# Load the baseline into HV_BASELINE for suppression.
hv_load_baseline() {
    HV_BASELINE=(); HV_BASELINE_SEEN=()
    hv_parse_baseline_into "${1:?baseline path required}" HV_BASELINE
}

# Report every way the baseline at $2 is LARGER than the one at $1.
#
# THE INVARIANT THIS ASSERTS, which until now lived only in a comment three
# functions up: the baseline only ever shrinks. `--audit-baseline` checks the
# opposite direction -- that no entry has been stranded -- so between them the
# file cannot reference what no longer exists NOR quietly acquire what does.
#
# Without this, the bypass is one line: hardcode a value, append its key here in
# the same change, and hv_partition suppresses it as already-known while
# ssot-coverage reports zero violations over a finding the detector made
# correctly. The count-in-key design already stopped a bump on an EXISTING key
# from being free; a brand-new key was the more direct route and was undefended.
#
# Shrinking is not growth and must stay silent: removals and decreases are how a
# fixed violation leaves, and a guard that blocked those would make the file
# unmaintainable. Returns 0 when the new baseline is a subset-or-equal.
hv_baseline_growth() {
    local old_file="${1:?old baseline required}" new_file="${2:?new baseline required}" key found=0
    declare -A _hv_old=() _hv_new=()
    hv_parse_baseline_into "$old_file" _hv_old || return 2
    hv_parse_baseline_into "$new_file" _hv_new || return 2
    for key in "${!_hv_new[@]}"; do
        if [ -z "${_hv_old[$key]+set}" ]; then
            printf 'NEW-KEY  (+%s)  %s\n' "${_hv_new[$key]}" "$key"
            found=1
        elif [ "${_hv_new[$key]}" -gt "${_hv_old[$key]}" ]; then
            printf 'COUNT-UP (%s->%s)  %s\n' "${_hv_old[$key]}" "${_hv_new[$key]}" "$key"
            found=1
        fi
    done
    [ "$found" -eq 0 ]
}

# Split records on stdin into new (stdout) and baselined (counted in
# HV_SUPPRESSED). Records arrive as SEVERITY|CLASS|file|line|value|suggestion.
#
# CALL THIS WITH REDIRECTION, NEVER THROUGH A PIPE. `… | hv_partition` puts it
# in a subshell, so HV_SUPPRESSED and HV_BASELINE_SEEN are set in a process that
# then exits — the caller reads back zero suppressed findings and an empty
# seen-map, which reads exactly like "the baseline matched nothing" and makes
# the stale-entry audit report every entry as stale. Found by running it that
# way. Both entry points use `hv_partition < in > out`.
hv_partition() {
    local rec sev class file lineno value key allowed
    HV_SUPPRESSED=0
    while IFS='|' read -r sev class file lineno value _; do
        [ -n "$sev" ] || continue
        key="${class}|${file}|${value}"
        allowed="${HV_BASELINE[$key]:-0}"
        HV_BASELINE_SEEN["$key"]=$(( ${HV_BASELINE_SEEN[$key]:-0} + 1 ))
        if [ "${HV_BASELINE_SEEN[$key]}" -le "$allowed" ]; then
            HV_SUPPRESSED=$((HV_SUPPRESSED + 1))
            continue
        fi
        printf '%s|%s|%s|%s|%s\n' "$sev" "$class" "$file" "$lineno" "$value"
    done
    return 0
}

# Baseline keys that matched fewer findings than they claim.
#
# An allowlist entry naming a moved file exempts nothing, and does it silently.
# These are reported so a fixed violation cannot leave a stranded exemption that
# quietly re-permits the same value when the file comes back.
hv_stale_baseline_entries() {
    local key
    for key in "${!HV_BASELINE[@]}"; do
        [ "${HV_BASELINE_SEEN[$key]:-0}" -lt "${HV_BASELINE[$key]}" ] && printf '%s\n' "$key"
    done
    return 0
}

# The baseline rewritten to what the last scan actually found -- REMOVAL ONLY.
#
# WHY THIS IS SAFE, structurally rather than by inspection. Two properties, and
# both come from the shape of the loop rather than from a check that could be
# forgotten:
#
#   * it iterates "${!HV_BASELINE[@]}" -- keys ALREADY in the baseline -- so it
#     cannot introduce one. Findings are never iterated here.
#   * it emits min(baseline_count, seen_count), so it cannot raise one.
#
# That matters because a prune that could add or increment would BE the bypass
# check_baseline_no_growth.sh exists to prevent: fix nothing, run prune, and
# every new finding becomes "known". The two guards are complementary only
# while this direction is closed by construction.
#
# hv_partition increments HV_BASELINE_SEEN BEFORE testing it against the
# allowance, so `seen` is the true number of findings for that key, including
# any beyond what the baseline permits. That is what makes min() correct: a key
# baselined at 2 and now found 3 times prunes to 2, not 3.
#
# Requires a completed hv_partition over a FULL tree scan. Pruning against a
# partial scan drops every key the scan did not reach.
#
# The live risk is a scan DIRECTORY that has moved or been renamed, because
# hv_scan_tree treats a missing root as a silent no-op: the other directories
# still produce hundreds of findings, so the total stays non-zero and an
# empty-scan check cannot see it. Reproduced during review -- one absent
# directory silently removed every baseline key beneath it, exit 0.
#
# An earlier version of this comment also cited "a rules file that failed to
# load". That path was never reachable: detect-hardcoded-values.sh fails fatally
# on an unsourceable library before any scanning begins. Naming a risk the code
# already forecloses makes the remaining, real one look handled -- so the
# caller now asserts every SCAN_DIRS entry exists before it scans.
hv_pruned_baseline() {
    local key kept seen
    for key in "${!HV_BASELINE[@]}"; do
        kept="${HV_BASELINE[$key]}"
        seen="${HV_BASELINE_SEEN[$key]:-0}"
        [ "$seen" -lt "$kept" ] && kept="$seen"
        [ "$kept" -gt 0 ] && printf '%s|%s\n' "$kept" "$key"
    done
    return 0
}
