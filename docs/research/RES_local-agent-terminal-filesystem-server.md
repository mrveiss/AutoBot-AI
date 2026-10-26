# Research: local agent terminal + filesystem tool server

## Phase 1 — Source Analysis: an open-source local tool server giving chat assistants terminal and filesystem access

### What It Is
A TypeScript MCP server (MIT, actively maintained, very large install base by its own
figures) that exposes a local machine's terminal, processes and filesystem to any MCP
client. A commercial hosted tier relays web/mobile AI clients to a local "remote device"
process over an authenticated channel; the free local server is the open-source core.

### Architecture & Key Patterns
- Single-process stdio MCP server; tools grouped as config / terminal+process / filesystem /
  search / edit, each with a zod schema and a handler module.
- Terminal manager keeps long-lived child processes keyed by PID; output buffered and read
  incrementally with `offset/length` paging (0 = since last read, positive = absolute,
  negative = tail).
- Remote mode: OAuth device-authorization flow, device session persisted to a `0600` file,
  then relay `AI client → hosted MCP → local device → local server`.
- Optional file-preview UI resources (markdown editor, directory tree) returned as MCP UI.
- Local tool-call history (JSONL, 1000 entries, 4 KB output cap per entry, 5 MB file cap).

### Notable Implementation Details
- **Search/replace edit with fuzzy fallback:** exact match first; on miss, fuzzy-locate the
  closest span, report similarity %, a character-level diff and code-point stats, and refuse
  to apply below a 0.7 threshold. `expected_replacements` forces the caller to state the
  occurrence count, failing loudly on a mismatch. Line endings detected and preserved.
  Every fuzzy miss is logged for later analysis of how models mis-quote code.
- **Prompt/state detection for interactive processes:** classifies output tails as waiting at
  a REPL prompt (Python, Node, R, PowerShell, psql, cmd, POSIX shells), continuation prompt,
  or still running — lets an agent drive SSH/DB/REPL sessions without fixed sleeps, and
  strips prompt echoes from returned output.
- **Command blocklist parser** extracts every command name from chains, pipes, `$()` and
  backticks — a hardening of a previously bypassable naive split.
- **Write/read line limits** (default read 1000, write 50 lines per call) push the model
  toward chunked edits.
- Telemetry with path redaction / property sanitization; opt-out config key.

### Strengths
- Very pragmatic agent ergonomics: output paging, tail reads, prompt detection, edit
  feedback that tells the model *why* it missed.
- Honest security doc: states plainly that allowed-directories and the blocklist are
  guardrails, not a boundary, and that only OS-level isolation contains a hostile client.

### Weaknesses / Limitations
- No security boundary by design: terminal access bypasses directory restrictions; the
  trusted-client assumption explicitly excludes prompt injection.
- No approval gate per command — execution is immediate; review is left to the client UI.
- Blocklist is a denylist over a parsed command line — inherently incomplete.
- Large single files (filesystem ~1.2k lines, remote channel ~80 KB) and ~300 open issues.
- Telemetry on by default (opt-out).

### Visible vs Hidden Metrics
- **Visible (self-reported):** ~10k stars, ~325k weekly downloads, 60+ prompt library,
  multi-client support. Stars verified via the repo API; download figure not verified.
- **Hidden:** adopting the server itself means a second Node runtime and tool surface beside
  ours, a denylist security model weaker than an approval gate, telemetry to disable, and a
  hosted relay that is a vendor lock-in and an extra trust party.
- **Weighing:** the *server* is not worth adopting for a platform with its own executor and
  approval gates; individual *techniques* (fuzzy-edit feedback, prompt-state detection,
  paged process output, occurrence-count assertion) are cheap and portable.

## Phase 2 — AutoBot Comparison

Audit scope: `autobot-backend/` (read only, nothing executed). Existing-issue search found no duplicates;
the nearest are #13591 (post-edit diagnostics) and #16840 / #15755 (approval wiring).

### What We Can Adopt

| # | Technique | AutoBot today (audited) | Visible benefit | Hidden cost | Verdict | Effort |
|---|---|---|---|---|---|---|
| A1 | Edit miss returns an error with closest match, similarity and diff | `api/filesystem_mcp.py:1077-1100` `_apply_edits_to_content` **silently skips** an `old_text` that is not found; the response only counts `edits_applied` | The model learns why it missed instead of believing the edit landed | ~80 lines; difflib is stdlib | adopt (the silent skip is a defect, not just a gap) | moderate |
| A2 | Expected-occurrence assertion | Same helper calls `str.replace` → replaces **every** occurrence, no count check | Prevents unintended multi-site rewrites | A new optional schema field | adopt | trivial |
| A3 | Line-ending preservation | Text-mode `aiofiles.open` with no `newline=` → CRLF files are rewritten as LF | No whole-file diffs on Windows-origin files | None | adopt | trivial |
| A4 | Fuzzy fallback that *applies* above a threshold | Absent (grep `difflib\|SequenceMatcher\|rapidfuzz` only hits unrelated modules) | Fewer retries | Applying a fuzzy match is a silent wrong-site edit risk | rejected-by-hidden-metrics: report the near-miss (A1), never auto-apply | — |
| A5 | Edit-miss telemetry for later analysis | Absent (no log, metric or record on a miss) | Data on how models mis-quote code | A small structured log; must route through the redaction boundary | adopt-with-conditions (redacted, counts + similarity only) | trivial |
| A6 | Prompt-state detection for interactive sessions (REPL/shell/psql prompts) | `agents/interactive_terminal_agent.py:295-317` matches sudo and y/N prompts only; the agent command path `services/pty_command.py` waits for an end marker, so ssh/psql/REPL runs to the timeout (rc 124) | Agent drives REPL/ssh/DB sessions without timeouts | Prompt regexes are heuristic and need a test corpus | adopt | moderate |
| A7 | Tail (negative-offset) window over spilled/process output | `agent_loop/tool_output_spill.py:339` clamps `offset` to `max(0, …)`; there is no paging over a still-running process | Logs and tests fail at the end, and the tail is what matters | Small | adopt | trivial |
| A8 | Per-call read/write line limits | Absent (10 MB byte cap only, `api/filesystem_mcp.py:213`) | Context protection | Overlaps the spill mechanism, which already caps windows at 8000 chars | rejected-by-hidden-metrics: duplicates spill (twice-defined) | — |

### What We Already Do Better
- **Human approval per command:** `services/agent_terminal/service.py:661-701` resolves the AI line, applies auto-approve rules, then queues; the reference work executes immediately with only a denylist.
- **Command substitution:** `security/command_patterns.py:173-180` forbids `$()`/backticks outright, where the reference work parses inside them to apply a denylist.
- **Large-output handling:** a spill-and-page design (`tools/tool_registry.py:132-155`) instead of fixed per-call line caps.

### Gaps & Opportunities (by impact)
1. **Security — auto-approve rules match on the first word only.** `services/command_approval_manager.py:393-430` `_extract_command_pattern` reduces any command to `"<first word> *"`, and `check_auto_approve_rules` (:303-345) matches that pattern plus a risk level. Risk is judged from the first command (`secure_command_executor.py:379-391`), and the splitting only handles `;` (:200-225). So a stored `cat *` rule at a safe risk level can match `cat x && <other command>` if the pattern table does not escalate the tail. The reference work's parser (it extracts every command from chains, pipes and substitutions) is the relevant technique. The fix: parse every segment and require every segment to match a rule.
2. A1–A3: the edit tool silently drops misses, over-replaces, and rewrites line endings.
3. A6: interactive sessions time out instead of detecting prompts.
4. A7 and A5.

### Specific Code/Files Affected
- `autobot-backend/services/command_approval_manager.py` — segment-aware pattern extraction; all segments must match.
- `autobot-backend/secure_command_executor.py` — split on `&&`, `||`, `|`, newline; assess the risk of every segment and take the max.
- `autobot-backend/api/filesystem_mcp.py` — `_apply_edits_to_content`: error on a miss with a closest-match diff, an `expected_replacements` field, `newline=""` on open; edit-miss structured log.
- `autobot-backend/services/pty_command.py` and `agents/interactive_terminal_agent.py` — prompt-state classifier shared by both.
- `autobot-backend/agent_loop/tool_output_spill.py` — negative offset = tail window.

## Linked issues

- #19465 Umbrella: agent tool ergonomics and terminal safety (research follow-ups)
- #19462 security(terminal): learned auto-approve rules match a chained command on its first word
- #19463 fix(tools): edit_file silently skips a missed edit, replaces every occurrence, and rewrites CRLF to LF
- #19464 feat(terminal): detect when an interactive process waits at a prompt instead of running to the timeout
- #16620 feat(agent): spilled outputs can be sliced but not searched (tail-read delta posted there)
