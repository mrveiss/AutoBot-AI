// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// Contract-typed GET helpers (#16292). Each frontend generates `paths` from its own
// backend's OpenAPI schema (src/types/generated/api.ts). These types read a GET
// endpoint's 200 response straight from that contract, so a caller does not need
// `api.get<Shape>()`, a shape assertion TypeScript cannot check
// (repo_tests/frontend_api_contract_ratchet_test.py). They are generic over
// `Paths`, so each app supplies its own contract and neither client forks them.

/** The keys of *Paths* that declare a GET operation. openapi-typescript marks an
 *  absent method `get?: never`, which does not satisfy the required `get` here. */
export type GetPath<Paths> = {
  [P in keyof Paths]: Paths[P] extends { get: unknown } ? P : never
}[keyof Paths] &
  string

/** The JSON body of an operation's 200 response. */
export type JsonOf<Op> = Op extends { responses: { 200: { content: { 'application/json': infer Body } } } }
  ? Body
  : never

/** The JSON body a GET on *P* returns, per the contract. */
export type GetResponse<Paths, P extends GetPath<Paths>> = Paths[P] extends { get: infer Op } ? JsonOf<Op> : never
