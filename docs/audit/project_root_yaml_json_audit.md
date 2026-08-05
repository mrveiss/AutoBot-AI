# #13149 Task 5 — `${AUTOBOT_PROJECT_ROOT:-…}` in YAML/JSON, audited per consumer

The issue asks for these to be "confirmed per consumer rather than bulk-edited",
on the theory that some consumers legitimately expand environment variables.
That theory holds for exactly one group. The rest are the same defect as Class A.

## Verdicts

| File | Consumer | Expands? | Verdict |
|---|---|---|---|
| `ansible/playbooks/sync-user-backend.yml` | `ansible.builtin.shell` | **yes** | works; dangerous default (Class B) |
| `ansible/playbooks/deploy-hybrid-docker.yml` (×2) | `synchronize` `src:` | **no** | needs live confirmation |
| `ansible/playbooks/deploy-native-services.yml` (×3) | `synchronize` `src:` | **no** | needs live confirmation |
| `ansible/playbooks/fix-slm-agent-node-id.yml` | `synchronize` `src:` | **no** | needs live confirmation |
| `ansible/playbooks/enroll-node.yml` (×2) | Jinja `default('${…}')` | **no** | literal default |
| `config/security/compliance.yaml` | `compliance_manager.py` | **no** | **confirmed broken** |
| `config/security/threat_detection.yaml` | **nothing** | n/a | dead config key |
| `config/logging.yml` | `log_aggregator.py` **writes** it | n/a | stale generated artefact |
| `config/logging/promtail/promtail-config.yml` | Promtail (Grafana) | conditional | only with `-config.expand-env=true` |
| `code_analysis/auto-tools/results/vue_*.json` (×2) | none — generated output | n/a | stale artefact |
| `.mcp/config.json`, `mcp-autobot-tracker/*.json` (×3) | MCP clients | **no** | literal |
| `THIRD-PARTY-NOTICES` | none | n/a | prose |

## The one that genuinely expands

`sync-user-backend.yml:12` assigns the literal to a var, then uses it inside an
`ansible.builtin.shell` block. Jinja emits the raw string and **the shell expands
it**, so the path is correct. `${VAR:-default}` is POSIX, so this survives the
dash-vs-bash trap that bites `set -o pipefail`.

It is still Class B: with the variable unset, its sync (archive plus delete,
correctly carrying `--exclude=.env` among others) targets the **deployed
install** rather than the checkout. Functional, and precisely the #13092 hazard.

## Confirmed broken — `compliance.yaml`

```python
# autobot-backend/security/enterprise/compliance_manager.py:94
self.audit_base_path = Path(
    self.config.get("audit_storage", {}).get("base_path", str(PATH.get_log_path("audit")))
)
self.audit_base_path.mkdir(parents=True, exist_ok=True)
```

`yaml.safe_load` performs no expansion, and **`expandvars` appears nowhere in this
repository's Python**. Reproduced:

```
yaml value  : ${AUTOBOT_PROJECT_ROOT:-/opt/autobot/code_source}/logs/audit
is_absolute : False
created     : ['${AUTOBOT_PROJECT_ROOT:-']

./${AUTOBOT_PROJECT_ROOT:-/opt/autobot/code_source}/logs/audit
```

A junk tree **relative to the working directory**. Written under it:
`.audit_key` (line 187) and PII access logs (line 536). So the compliance audit
trail lands somewhere nobody reads, in a cwd-dependent location, and two
processes with different working directories keep separate trails.

The `.get(key, default)` shape hides it: the fallback is a correct
`PATH.get_log_path("audit")`, but it never fires, because the key **is** present
— it is just wrong.

## Needs a live check, not a guess

`ansible.builtin.synchronize` builds an rsync invocation rather than running a
shell line. If its `src:` is passed without a shell, `${…}` stays literal and the
sync silently targets a nonexistent directory. Confirming this means running the
playbook, which is a deploy path — it must be exercised through the builtin
updater, not ad hoc. Marked for confirmation rather than assumed.

`enroll-node.yml` is not ambiguous: the literal sits inside a Jinja
`default('…')`, so when `slm_code_repository` is undefined the value is the raw
`${…}` string.

## Recommendation

1. `compliance.yaml`, `threat_detection.yaml`, `logging.yml` — drop the
   placeholder and let the consumer's own `PATH.get_*` default apply, or resolve
   through `autobot_shared.paths.project_root()`. These are ordinary bugs.
2. `synchronize` playbooks — confirm on a live run before editing.
3. `sync-user-backend.yml` — keep the expansion, replace the live-install default.
4. `vue_*.json` — regenerate; editing generated output is pointless.
5. Promtail — leave unless `-config.expand-env=true` is absent from the unit.
