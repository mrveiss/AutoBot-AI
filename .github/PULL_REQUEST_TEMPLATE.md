## Thinking Path
<!-- Required: Trace the reasoning from problem context to this change. What problem are we solving? Why this approach over alternatives? -->


## What Changed
<!-- Required: Bullet list of concrete changes made. Be specific — file names, function names, config keys. -->

-

## Verification
<!-- Required: How a reviewer can confirm this works. Include commands to run, endpoints to hit, or UI steps to follow. -->


## Risks
<!-- What could go wrong; edge cases not covered; rollback plan if needed. Write "None identified" if applicable. -->


## Model Used
<!-- Required: The AI model that produced or assisted with this change. Format: "Provider ModelID". Write "None — human-authored" if no AI was used. -->
<!-- Examples: "Claude Sonnet 4.6 (claude-sonnet-4-6)", "None — human-authored" -->


## Issue Link
<!-- Closes #N or related #N -->
Closes #

## Changelog fragment
<!-- Carried here from the duplicate template removed in #14156. The release
     workflow compiles changelog/unreleased/*.md into the per-version file
     (.github/workflows/release.yml, strategy B, #1296), so this is a live
     process and this was the only place a PR author was prompted about it.

     Copy changelog/unreleased/TEMPLATE.md, rename it to {issue}-{slug}.md,
     fill in the frontmatter and description, and commit it with this PR.

     Skip only for: docs-only changes, internal refactors, CI fixes, and
     dependency bumps with no behaviour change. -->
- [ ] Added `changelog/unreleased/{issue}-{slug}.md` — or N/A (internal change)

## Checklist
- [ ] Code follows AutoBot patterns from `CLAUDE.md`
- [ ] Tests added or updated (or N/A with reason)
- [ ] Documentation updated if behavior changed
- [ ] Pre-commit hooks pass (`git commit` runs them automatically)
- [ ] PR targets `Dev_new_gui` (not `main`)
- [ ] No secrets or credentials in the diff
