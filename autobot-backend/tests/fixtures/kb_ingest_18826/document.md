**Companion:** [`dedup-defork-report.md`](dedup-defork-report.md) (clusters **F1–F23**; the brief said F1–F21, but the delivered report has 23 clusters, and all are linked here).

## 0. Data collection and exact counts

The **first-choice MCP connector was tried first** and returned `scm_not_connected`. Collection then fell back to the **unauthenticated public REST API**, paged **per label** (`/repos/mrveiss/AutoBot-AI/issues?labels=<label>&state=open&per_page=100&page=N`) until a short page. No label needed more than 6 pages, so the list endpoint's ~1,000-item cap was never reached. Pull requests (`pull_request` key) were excluded; there were 0.

```text
GET /repos/mrveiss/AutoBot-AI/issues?labels=<label>&state=open&per_page=100&page=N
```

All 200 repo labels were listed (`raw/bugs/labels_p1..3.json`). These matched the bug/tech-debt family:

| Label | Open issues |
|---|---:|
| `bug` | 578 |
| `tech-debt` | 292 |
| `technical-debt` | 81 |
| `refactor` | 14 |
| `refactoring` | 10 |
| `code-quality` | 4 |
| `dead-code` | 2 |
| `cleanup` | 1 |
| `hardcoding-violation` | 1 |
| `hardcoding` | 1 |
| **Union (distinct issues analysed)** | **937** |

Note: `bug` ∩ `tech-debt` = 22. The labels `code-smell`, `maintainability` and `type:refactor` exist but have **0** open issues. No open issue carries `fixed` or `wontfix`; one (#17409) carries `duplicate`. The issues were created between 2025-12-07 and 2026-10-13.

## 1. Executive summary

- **937 open issues** were classified. **20 root-cause codes** were assigned by hand from each title, with the body consulted where the title was ambiguous. Subsystem and symptom were assigned by keyword rules (see §8, Limitations).
- The backlog is dominated by **structural causes, not isolated feature bugs**. Four causes account for **434 of 937 issues (46%)**:
    - **[B] guards and CI gates that pass without checking** (132)
    - **[A] forked/duplicated implementations** (111)
    - **[C] unwired/dead/half-migrated code** (100)
    - **[Q] process/backlog hygiene** (91)
- Isolated "real" domain bugs with no shared mechanism ([S]) are only **47**.
- B, C, D and G share one meta-pattern: **the system claims something it never executes**. Examples: a gate reports clean over an empty scan, a feature is built but never called, an error becomes a 200, a caller invokes a method that does not exist. Each fix below converts such a claim into an executed check.
- **Stale or already-fixed:** 5 in-scope issues verified fixed in code (plus #18088 from task 1, which is open but labelled only `backend`/`security`, so outside this label set) and 3 partly superseded (§6). A further **95** open issues are named in the subject of at least one merged PR since they were opened, and **9** are named by a `fixes/closes #N` keyword in a merged commit. These are triage candidates.
- **Duplicates/overlaps:** 30 groups (§5). 54 issue pairs have TF-IDF title+body cosine ≥ 0.38 (`raw/bugs/similar_pairs.tsv`).
### 1.1 Top 10 root causes, ranked by issues likely closed ÷ effort

Effort points: S=1, M=2, L=4. "Likely closes" is the subset the named single fix addresses directly (§4). "Total" counts every issue coded to that cause.

| Rank | Root cause | Total issues | Likely closes | Effort | Score | Single fix |
|---:|---|---:|---:|:-:|---:|---|
| 1 | [B] Vacuous/blind guards & CI gates | 132 | 82 | M | 41.0 | Guard contract: declare()+floor, fail-on-empty, no path-filter skip, planted test |
| 2 | [C] Unwired/dead/half-migrated code | 100 | 73 | L | 18.2 | Wire-or-retire reachability gate + retirement sweep |
