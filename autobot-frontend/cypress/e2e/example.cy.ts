// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// https://on.cypress.io/api

describe('My First Test', () => {
  it('visits the app root url', () => {
    cy.visit('/')
    cy.contains('h1', 'You did it!')
  })
})
