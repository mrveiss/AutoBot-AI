---
type: fix
scope: infra
issue: 16934
pr: 0
---
Doc-sync moved from `post-commit` to `post-merge` and gained an explicit gate on branch `main` at `origin/main`'s own tip, so a worktree's first commit can no longer re-index its own (possibly unmerged) doc tree into the shared, live `autobot_docs` ChromaDB collection. The hash cache moved to the checkout's shared `git-common-dir`, fixing the per-worktree cache miss that made every fresh worktree's first index treat every file as changed. `DocIndexerService.rebuild_from_scratch()` plus `tools/index_documentation.py --rebuild` deliver the one-time remedy for branch docs that already reached production before this landed — see `docs/operations/DOC_INDEX_REBUILD.md`; the owner runs it, not CI or an agent.
