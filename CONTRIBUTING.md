# Contributing to AutoBot

Thanks for wanting to contribute — small fixes and thoughtful larger changes are both very welcome.

AutoBot is a self-hosted AI platform. Contributions that make it faster, more reliable, or easier to deploy and extend are the highest priority.

---

## Two Paths to Get Your Pull Request Accepted

### Path 1: Small, Focused Changes *(fastest way to get merged)*

- Pick **one** clear thing to fix or improve
- Touch the **smallest possible number of files**
- All tests pass and CI is green
- Fill out the [PR template](.github/PULL_REQUEST_TEMPLATE.md) fully

These get reviewed quickly when they are clean and targeted.

Good candidates: bug fixes, documentation corrections, test coverage gaps, Docker/deployment improvements, small UI polish.

### Path 2: Bigger or Impactful Changes

1. **Open an issue first** — describe what you are trying to solve and your proposed approach
2. Wait for feedback before writing code
3. In your PR include:
   - Before / after screenshots or a short video for any UI or behavior change
   - Clear description of what changed and why
   - Proof it works (manual testing notes, curl output, or test run)
   - All tests passing and CI green
   - [PR template](.github/PULL_REQUEST_TEMPLATE.md) fully filled out

PRs that follow this path are **much** more likely to be accepted, even when they are large.

---

## PR Requirements (all PRs)

### Branch Target

All PRs must target **`Dev_new_gui`**, not `main`. Direct commits to `main` are blocked by a pre-commit hook.

### Commit Format

```text
<type>(scope): <description> (#issue-number)
```

Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`

Example: `fix(chat): prevent duplicate messages on reconnect (#1234)`

### Use the PR Template

Every pull request must follow [`.github/PULL_REQUEST_TEMPLATE.md`](.github/PULL_REQUEST_TEMPLATE.md). Required sections: Thinking Path, What Changed, Verification, Risks, and Checklist.

### Tests Must Pass

Run tests locally before pushing. CI must be green before a PR can be merged.

```bash
# Backend
cd autobot-backend && python -m pytest

# Frontend
cd autobot-frontend && npm run type-check && npm run lint
```

### No `--no-verify`

Never bypass the pre-commit hook with `--no-verify`. If the hook blocks your commit, fix the underlying issue.

---

## Writing a Good PR Description

Every PR description must include a **Thinking Path** — a short chain of reasoning from the top of the project down to exactly what you changed. This replaces vague summaries with traceable logic.

### Thinking Path Example

> - AutoBot lets users chat with their own documents using any LLM
> - The chat session cache uses a hard-coded 24-hour Redis TTL
> - Hard-coded TTLs cannot be tuned without redeploying, which breaks operator setups with custom retention policies
> - So this PR replaces the hard-coded value with a module-level constant resolved from the `AUTOBOT_CHAT_SESSION_CACHE_TTL` env var, with a logged-fallback default of 24h
> - That way operators can tune retention without touching source code

After the Thinking Path, include: what you changed, why it matters, how to verify it, and any risks or known limitations. Screenshots if there is a visible change.

---

## Feature Contributions

AutoBot's core feature roadmap is actively managed. Uncoordinated feature PRs may be closed even when the implementation is high quality — that is about roadmap coherence and long-term maintenance, not a judgement of your effort.

If you want to contribute a feature:

- Check [open issues](https://github.com/mrveiss/AutoBot-AI/issues) and [GitHub Discussions](https://github.com/mrveiss/AutoBot-AI/discussions) first
- Open an issue to discuss the idea before writing code
- If the feature fits as a plugin, prefer building it that way

Bugs, documentation improvements, and small targeted fixes are the easiest path to getting merged — and genuinely appreciated.

---

## General Rules

- One PR = one logical change
- Keep commits focused and descriptive
- No commented-out code, no TODO comments — file a GitHub issue instead
- No `print()` or `console.log()` — use the project logger (`logging.getLogger(__name__)` / `createLogger('Name')`)
- If you find a bug while working on something else, open a new issue rather than fixing it inline
- Be kind in discussions

---

## Setting Up Locally

```bash
git clone https://github.com/mrveiss/AutoBot-AI.git
cd AutoBot-AI
cp .env.example .env
docker compose up -d
```

Visit **[http://localhost](http://localhost)** — AutoBot is running.

For backend development without Docker:

```bash
cd autobot-backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8001
```

For frontend development:

```bash
cd autobot-frontend
npm install
npm run dev
```

---

## Good First Issues

New to the codebase? Start with issues tagged [`good-first-issue`](https://github.com/mrveiss/AutoBot-AI/issues?q=is%3Aopen+label%3Agood-first-issue).

---

Questions? Open an issue or start a [Discussion](https://github.com/mrveiss/AutoBot-AI/discussions). Happy hacking.
