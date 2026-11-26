---
tags:
  - llc
  - module
  - github
  - integration
aliases:
  - Company OS PR Linking
  - GitHub PR Integration
status: current
---

# Company OS GitHub PR Integration

Links GitHub Pull Requests to Company OS work items (GH#9625), enabling:

- PR visibility on work item cards (🔗 badge on the Kanban board)
- Automatic review handoff to a named reviewer when a linked PR merges
- Webhook-driven auto-linking from branch names or PR bodies
- Manual linking via the work-items API

---

## Branch Naming Convention

To auto-link a PR to a Company OS work item, name the branch with one of:

| Pattern | Example |
|---------|---------|
| `llc/{work_item_id}` | `llc/550e8400-e29b-41d4-a716-446655440000` |
| `autobot-llc/{work_item_id}` | `autobot-llc/550e8400-e29b-41d4-a716-446655440000` |
| `llc-{work_item_id}` | `llc-550e8400-e29b-41d4-a716-446655440000` |

`{work_item_id}` is the work item's UUID.

### PR Body Pattern

Alternatively, include one of these in the PR description:

```markdown
Closes #llc-{work_item_id}
Fixes #llc-{work_item_id}
Resolves #llc-{work_item_id}
```

---

## Automatic Status Transitions

| PR event | Work item action |
|----------|------------------|
| PR opened | PR URL appended to `linked_pr_urls`, comment posted |
| PR merged | Item handed to a named reviewer through the review handoff (`in_review`), or left where it is with a comment saying why |
| PR closed without merge | Comment posted (no status change) |

A merged PR moves an item to `in_review` only when it is `in_progress`, held by an agent, and a reviewer
resolves: the item's reviewer, else its creator, who must be a current company member. The handoff assigns the
reviewer, releases the agent's checkout and notifies them. Otherwise the item keeps its status and a comment
on it says why. Work items already in `done` or `cancelled` are never touched.

---

## Manual PR Linking (agent SDK)

Adapters/agents link a PR after opening it:

```bash
POST /api/llc/work-items/{work_item_id}/link-pr
Content-Type: application/json

{
  "pr_url": "https://github.com/owner/repo/pull/123",
  "pr_number": 123,
  "repo": "owner/repo"
}
```

The URL is validated strictly (`https://github.com/{owner}/{repo}/pull/{n}`,
no query/fragment); when `repo` is supplied it must match the URL.

---

## GitHub Webhook Setup

1. **Webhook URL**: `https://your-autobot-domain/api/llc/webhooks/github`
2. **Content type**: `application/json`
3. **Secret**: set the same value in the `GITHUB_WEBHOOK_SECRET` environment
   variable on the backend — the endpoint is **fail-closed** (503 without it,
   401 on signature mismatch)
4. **Events**: "Pull requests"

The handler verifies the HMAC-SHA256 signature, extracts the work item ID from
the branch name or PR body, validates the PR URL against the webhook's
repository, links the PR, posts a comment, and transitions status on merge.

---

## Database Schema

`llc_work_items.linked_pr_urls` — `JSONB NOT NULL DEFAULT '[]'::jsonb`
(migration `20260612_056_llc_pr_linking.py`).

## Implementation Files

- `autobot-backend/llc/models/work_item.py` — `linked_pr_urls` field
- `autobot-backend/llc/api/work_items.py` — `POST /{id}/link-pr` endpoint
- `autobot-backend/llc/api/github_webhooks.py` — webhook handler
- `autobot-frontend/src/views/llc/KanbanBoardView.vue` — PR badge

## Example Workflow

1. Agent creates branch `llc/{work_item_id}`, commits, pushes, opens a PR
2. GitHub webhook fires → AutoBot links the PR to the work item
3. Work item card shows the 🔗 badge
4. PR merges → the agent's work item is handed to its reviewer (`in_review`)
5. Reviewer approves → work item marked `done`

## See Also

- Issue #9625 — GitHub PR ↔ work item linking
- [Company OS Module PRD](../planning/PRD_AutoBot_LLC_Module.md)
