# Frontend API clients: when to use which (#11682, #12363)

The main app (`autobot-frontend`) talks to the backend through ONE transport,
`src/utils/ApiClient.ts`. Everything else is a thin layer over it or a recorded
exception. This documents the existing roles; it introduces no new abstraction.

The transport itself is the kit's `ApiClientBase` (`libs/autobot-ui/src/utils/ApiClientBase.ts`): timeout and
abort, GET retry with `Retry-After`, `HttpError`, FormData/Blob bodies and the own-origin guard live there once.
Each app's client subclasses it and binds that app's generated `paths` contract (`ApiClientBase<Options, paths>`).

## The typed call comes first (#12363)

```ts
// path params, query and body are typed from the operation; the result is its JSON 200 (or 201) body
const item = await apiClient.call('get', '/api/items/{item_id}', { path: { item_id: id } })
const list = await apiClient.call('get', '/api/items', { query: { limit: 20 } })
const made = await apiClient.call('post', '/api/items', { body: { name } })
// SSE, blobs, downloads: the Response itself, non-2xx not thrown
const res = await apiClient.callRaw('post', '/api/chat/stream', { body })
```

- The path is the literal key of `paths` (the `{param}` form); a path, method, body or missing path param that
  the backend contract does not document fails `vue-tsc`. No hand-written `<Shape>` generic: that is an
  assertion the compiler cannot check, and `apiClient.call<` counts in the `inline_generics` ratchet.
- `call` sends a GET through `get()` (retry) and every other method once. Use `rawRequest`/`callRaw` for streams
  and blobs. An endpoint the contract lacks is a backend gap: add the route and `response_model`, regenerate
  the types, then call it; do not fall back to a string path.
- The domain clients below are being dissolved into this call (#12363 slices 1-3); do not add endpoints to them.

## Roles

| Need | Use | Why |
|---|---|---|
| Any authenticated backend call from a composable, store or repository | `apiClient.call(method, path, init)` (default export of `utils/ApiClient.ts`) | Owns base URL, bearer token, `X-Organization-Id`, timeout, retry on GET, 401 handling. `call` is typed from the generated contract and returns parsed JSON; `callRaw`/`rawRequest` return the `Response` (streaming, blobs). `get/post/put/delete` with a string path remain for code not yet moved. |
| A call that must stay a `fetch` (needs the `Response`, custom `credentials`, runs where the client singleton is awkward) | `fetchWithAuth` (`utils/fetchWithAuth.ts`) | Same token and org header as `ApiClient`, nothing else: no timeout, no retry, no 401 redirect. Prefer `rawRequest` for new code. |
| Fail-fast against a dependency that may be down | `apiClient.rawRequest/get/post(..., { circuitBreaker: '<dependency key>' })` | Opt-in circuit breaker (`utils/apiCircuitBreaker.ts`): 3 failures open the circuit for 30 s; 502/503/504 and thrown errors count, other responses do not. |
| Domain-specific endpoints | The domain client (`SecretsApiClient`, `FeatureFlagsApiClient`, `VisionMultimodalApiClient`, `AdvancedControlApiClient`) | Domain wrappers (being folded into the shared `apiClient`, #11682); add endpoints there, never a second transport. |
| `/api/*` calls through a service object | `ApiService` (`services/api.ts`) | A wrapper that holds the `apiClient` singleton and adds typed convenience methods (session presence, invitations, collaboration events). It is not a second client. |
| Several calls batched at chat start | `BatchApiService` (`services/BatchApiService.ts`) | Aggregates multiple `apiClient` calls with per-call error isolation; takes an injected client for tests. |
| Workflow builder REST calls | `WorkflowBuilderApiClient` (`composables/useWorkflowBuilder.ts`) | Private to the composable; wraps `httpClient` with a 60 s timeout and a `{ success, data, error }` envelope. |
| The SLM admin backend (separate origin, separate token) | `SlmClient` (`utils/slmClient.ts`) | Must not receive the main-app JWT. |

Raw `fetch(` that is none of the above is banned by eslint (`no-restricted-syntax`, the same selectors the SLM
app uses). A legitimate one (bootstrap before any client exists, another origin, a worker, telemetry that must
never throw) carries, directly above the call, a comment giving the reason and
`// eslint-disable-next-line no-restricted-syntax -- <reason>`; `repo_tests/frontend_single_api_client_12363_test.py`
counts every other transport and only lets its pin fall. `fetchWithAuth` is a bridge retired in slice 3; the
`fetch_with_auth_importers` and `hand_built_urls` ratchets in `repo_tests/frontend_api_contract_ratchet_test.py`
only go down.
