# Task 6 Report — Findings API Endpoints (#11271)

## Files Created / Modified

- **Created:** `autobot-backend/llc/api/findings.py` (FastAPI APIRouter, 169 lines)
- **Created:** `autobot-backend/llc/tests/test_findings_api.py` (9 tests)
- **Modified:** `autobot-backend/llc/api/__init__.py` (added `findings_router` import + `include_router`)

## Mount / Prefix Confirmed

The LLC `__init__.py` defines `router = APIRouter(prefix="/llc", ...)` and the main FastAPI app mounts at `/api`. Routes serve at:
- `POST /api/llc/projects/{project_id}/findings/scan`
- `GET  /api/llc/projects/{project_id}/findings/proposals`
- `POST /api/llc/findings/proposals/{proposal_id}/promote`
- `POST /api/llc/findings/proposals/{proposal_id}/dismiss`

No double `/api` prefix — bare paths used inside the router (no `/api/llc` duplicated).

## Real Signatures Used

All imported at module level so tests can patch `llc.api.findings.*`:

- `from llc.services.finding_proposal_service import FindingsDisabledError, dismiss, promote, scan`
- `from llc.services.findings_policy import get_findings_policy`
- `from llc.models.finding_proposal import LLCFindingProposal` (all fields in `FindingProposalResponse`)
- `from llc.models.sprint import LLCProject` (for IDOR guard)
- `from llc.deps import get_session`
- `from api.user_management.dependencies import get_current_user, require_org_context`

### `scan(project, session) -> dict` — confirmed in `finding_proposal_service.py:170`
### `promote(proposal, session, actor_user_id: uuid.UUID) -> LLCWorkItem | dict` — line 217
### `dismiss(proposal, session, reason: str) -> None` — line 258
### `FindingsDisabledError` — line 34
### `get_findings_policy() -> FindingsPolicy` — confirmed in `findings_policy.py:46`

## Test Output

```
llc/tests/test_findings_api.py::test_scan_403_when_policy_disabled PASSED
llc/tests/test_findings_api.py::test_scan_409_when_no_code_source_id PASSED
llc/tests/test_findings_api.py::test_scan_success_returns_counts PASSED
llc/tests/test_findings_api.py::test_list_proposals_returns_proposals PASSED
llc/tests/test_findings_api.py::test_list_proposals_filter_by_status PASSED
llc/tests/test_findings_api.py::test_promote_calls_service PASSED
llc/tests/test_findings_api.py::test_dismiss_calls_service PASSED
llc/tests/test_findings_api.py::test_dismiss_requires_reason PASSED
llc/tests/test_findings_api.py::test_scan_idor_404_wrong_org PASSED
======================== 9 passed, 5 warnings in 3.62s
```

## Full LLC Suite

```
1118 passed, 1 skipped, 24 warnings in 39.38s
```

No regressions.

## Formatting

`black -l120` + `isort` clean on all three files.

## Commit SHA

(populated after commit)

## Concerns

None. The `_load_owned_proposal` IDOR guard requires `proposal.company_id == ctx.org_id`, mirroring `_load_owned_project`. The `_mk_client` helper in the test routes both project and proposal queries correctly via the SQLAlchemy statement string inspection pattern established by `test_project_lifecycle_api.py`.
