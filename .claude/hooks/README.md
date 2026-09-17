# Hook declarations: `matcher` vs `if`

Hooks are declared in [`.claude/settings.json`](../settings.json). JSON carries no
comments, so the semantics live here — next to the scripts the declarations point at
(#15997).

`repo_tests/hook_declarations_are_reachable_test.py` enforces what is enforceable.

## A hook that never fires looks exactly like one that passes

Both produce silence. A matcher naming a tool that does not exist, or a command
pointing at a script that has moved, protects nothing while reading as healthy.
That is why the guard exists, and why it checks reach rather than behaviour:
whether the harness *invoked* a hook is runtime evidence no repository test can
produce.

## `matcher` selects a tool. It does not inspect arguments.

`matcher` is a pattern over **tool names**:

| Matcher | Selects |
|---|---|
| `Bash` | every Bash call |
| `Edit\|Write` | every Edit and every Write |
| `Edit` | Edit only |

Two consequences worth stating, because both have caused confusion here:

**Per-occurrence events carry no tool name.** `Stop`, `SubagentStop`,
`Notification`, `SessionStart`, `SessionEnd`, `UserPromptSubmit` and `PreCompact`
fire once per occurrence, not per tool call. A `matcher` on one of these selects
nothing and filters nothing — it is a silent no-op that reads as a filter. Leave
it empty. The guard reports a non-empty one.

**A matcher cannot narrow by argument.** To act on a *particular* Bash command,
the settings match the tool and then test the arguments inside the hook:

```jsonc
// .claude/settings.json — PreToolUse[0].hooks[1]
"matcher": "Bash",
"command": "if [[ \"$TOOL_ARGS\" == *\"git commit\"* ]]; then ... fi"
```

The hook process therefore starts on **every** Bash call and exits immediately
for the ones it does not care about. That is the cost of this form, and it is
the form the working configuration uses.

### An unresolved divergence

[`docs/developer/INSIGHTS_IMPROVEMENTS.md`](../../docs/developer/INSIGHTS_IMPROVEMENTS.md)
shows a different form, narrowing inside the matcher itself:

```json
"matcher": "Bash(git commit*)"
```

**I have not verified that this form fires**, and nothing in this repository
demonstrates it working — every live entry in `settings.json` uses a bare tool
name. It is recorded here as a divergence rather than presented as an
alternative, because a reader who copies it from the doc would get a hook that
either filters earlier (good) or never fires at all (silent, and the exact
failure this page is about).

The guard accommodates both readings: a matcher shaped exactly like `Name(...)`
also has its `Name` tried as a tool name. Strictly that shape — not "the text
before any `(`". The looser rule silently repaired a malformed `Bash|Nonexistent(`
into a reachable `Bash`, which is a checker quietly correcting its input instead
of reporting it. A malformed pattern is now reported with its own reason.

If the specifier form turns out to be unsupported, the right fix is to correct
the doc, not to loosen the guard.

## Adding a hook

1. Add the entry to `.claude/settings.json`.
2. If it runs a script, put the script in this directory and reference it as
   `$CLAUDE_PROJECT_DIR/.claude/hooks/<name>.sh` — the guard resolves that form
   and fails if the file is absent.
3. If the entry names a tool the guard does not know, add the tool to
   `TOOL_NAMES` in the guard **in the same change**. That list is the contract;
   a list that silently grew to match whatever the settings said would answer
   every question with "yes".
4. Shell hook suites are run in CI by `repo_tests/shell_lib_test.py` via its
   `SHELL_SUITES` list. A suite that is not in that list is collected by nothing
   (#14884).
