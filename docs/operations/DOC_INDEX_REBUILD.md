# Doc Index Rebuild (one-time, #16934)

## When to run this

Before Issue #16934, the doc-sync git hook ran on every commit in every
worktree, with no branch or origin check, and indexed that worktree's own
(possibly unmerged) tree into the shared, live `autobot_docs` ChromaDB
collection. If this repository was worked on in worktrees before that fix
landed, the collection may still hold chunks from branches that never merged
to `main`.

Run this once, after #16934 has merged, to remove them. It is not part of
routine operation -- ordinary doc changes on `main` are indexed automatically
by the `post-merge-doc-sync` hook (see
[`autobot-infrastructure/shared/scripts/README.md`](../../autobot-infrastructure/shared/scripts/README.md)).

## Why an ordinary re-index does not fix this

`tools/index_documentation.py --force` re-embeds every file currently on
disk, but discovery only walks files that exist in the checkout it runs
from. A chunk indexed from a branch's doc file that was never merged has no
corresponding file on `main` to overwrite it, so it is never revisited and
survives indefinitely -- `--force` is a superset re-index, not a sync.

`DocIndexerService.rebuild_from_scratch()`
(`autobot-backend/services/knowledge/doc_indexer.py`) deletes the
`autobot_docs` collection first, then does a full re-index. What survives is
exactly what the checkout backing that call contains -- nothing more.

## The one command

Run from a **clean checkout of `origin/main`'s current tip** (not a
worktree with local changes, not a stale branch):

```bash
git fetch origin && git checkout origin/main
python3 tools/index_documentation.py --rebuild
```

`--rebuild` is intentionally a separate flag from `--force`: it is
destructive to the existing collection (a bad embedding model or a checkout
that is not actually `main`'s tip would leave the collection worse, not
better), so it does not share a flag with the routine re-index path.

## What it does

1. Deletes the `autobot_docs` ChromaDB collection.
2. Recreates it and indexes every documentation file discovered under the
   checkout's `docs/` tree, `CLAUDE.md`, plus the tiers `doc_indexer.py`
   already covers -- the same discovery `--force` uses, just starting from
   an empty collection.
3. Logs a summary: files indexed, failed, skipped, and the resulting vector
   count.

## Verification after running

```bash
python3 -c "
import asyncio
from services.knowledge.doc_indexer import get_doc_indexer_service

async def main():
    svc = get_doc_indexer_service()
    await svc.initialize()
    print('vectors:', svc._collection.count())

asyncio.run(main())
"
```

Compare the vector count to before the rebuild (logged by the run itself);
a large drop confirms branch-only chunks were removed, not that content was
lost -- cross-check a few `file_path` values in the result against
`git ls-files 'docs/*.md' CLAUDE.md` on `main` if in doubt.

## Owner runs this, not an agent

This writes to the live, production knowledge base that chat grounding
reads from. Per standing policy, no automated session runs this on your
behalf -- it is delivered here as a command for you to run.
