# Frontend API clients: when to use which (#11682, #12363)

The main app (`autobot-frontend`) talks to the backend through ONE transport,
`src/utils/ApiClient.ts`. Everything else is a thin layer over it or a recorded
exception. This documents the existing roles; it introduces no new abstraction.

| Need | Use | Why |
|---|---|---|
| Any authenticated backend call from a composable, store or repository | `apiClient` (default export of `utils/ApiClient.ts`) | Owns base URL, bearer token, `X-Organization-Id`, timeout, retry on `get`, 401 handling. `get/post/put/delete` return parsed JSON; `rawRequest` returns the `Response` (streaming, blobs). |
| A call that must stay a `fetch` (needs the `Response`, custom `credentials`, runs where the client singleton is awkward) | `fetchWithAuth` (`utils/fetchWithAuth.ts`) | Same token and org header as `ApiClient`, nothing else: no timeout, no retry, no 401 redirect. Prefer `rawRequest` for new code. |
| Fail-fast against a dependency that may be down | `apiClient.rawRequest/get/post(..., { circuitBreaker: '<dependency key>' })` | Opt-in circuit breaker (`utils/apiCircuitBreaker.ts`): 3 failures open the circuit for 30 s; 502/503/504 and thrown errors count, other responses do not. |
| Domain-specific endpoints | The domain client (`SecretsApiClient`, `FeatureFlagsApiClient`, `VisionMultimodalApiClient`, `AdvancedControlApiClient`) | Domain wrappers (being folded into the shared `apiClient`, #11682); add endpoints there, never a second transport. |
| `/api/*` calls through a service object | `ApiService` (`services/api.ts`) | A wrapper that holds the `apiClient` singleton and adds typed convenience methods (session presence, invitations, collaboration events). It is not a second client. |
| Several calls batched at chat start | `BatchApiService` (`services/BatchApiService.ts`) | Aggregates multiple `apiClient` calls with per-call error isolation; takes an injected client for tests. |
| Workflow builder REST calls | `WorkflowBuilderApiClient` (`composables/useWorkflowBuilder.ts`) | Private to the composable; wraps `httpClient` with a 60 s timeout and a `{ success, data, error }` envelope. |
| The SLM admin backend (separate origin, separate token) | `SlmClient` (`utils/slmClient.ts`) | Must not receive the main-app JWT. |

Raw `fetch(` that is none of the above must be recorded, with a reason, in
`_RAW_FETCH_EXCEPTIONS` in `repo_tests/frontend_api_contract_ratchet_test.py`; the
guard fails on an unrecorded one.
