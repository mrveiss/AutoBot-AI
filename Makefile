# AutoBot Makefile — standard entry points for testing and coverage (#3285)
# Requires: pytest, pytest-cov, pytest-asyncio installed in the active venv
# Frontend targets require Node.js 20+ and npm ci run inside autobot-frontend/

.PHONY: test test-coverage test-backend test-frontend test-e2e format format-check help canonical-check canonical-check-py canonical-check-fe canonical-check-infra canonical-audit

# Default target: run all backend unit tests without coverage
test: test-backend

## Run backend unit tests with 70% coverage gate
test-coverage:
	pytest \
	    --cov=autobot-backend \
	    --cov=autobot-slm-backend \
	    --cov=autobot_shared \
	    --cov-report=term-missing \
	    --cov-report=html:reports/coverage-backend \
	    --cov-report=xml:reports/coverage-backend.xml \
	    --cov-fail-under=70 \
	    -m "not integration and not slow and not distributed and not performance"

## Run backend unit tests (no coverage)
test-backend:
	pytest \
	    -m "not integration and not slow and not distributed and not performance"

## Run frontend unit tests with 70% coverage gate
test-frontend:
	cd autobot-frontend && npm run test:coverage

## Run Playwright E2E tests (requires running backend+frontend)
test-e2e:
	cd autobot-frontend && npm run test:playwright

## Format Python with project-pinned Black + isort settings (#7249)
format:
	@bash scripts/format.sh

## Same as `make format` but exits non-zero if anything would change (CI mode)
format-check:
	@bash scripts/format.sh --check

## Show this help
help:
	@echo "AutoBot targets:"
	@echo "  make test            - backend unit tests (no coverage)"
	@echo "  make test-coverage   - backend tests + coverage gate (>=70%)"
	@echo "  make test-frontend   - frontend vitest coverage (>=70%)"
	@echo "  make test-e2e        - Playwright E2E tests"
	@echo "  make format          - format Python with project Black+isort settings"
	@echo "  make format-check    - check formatting without modifying files (CI)"

# ─── Canonical-style checks (#7458) ──────────────────────────────────────────

canonical-check: canonical-check-py canonical-check-fe canonical-check-infra
	@echo "canonical-check: all layers passed"

canonical-check-py:
	@python3 tools/lint/canonical_check.py --all --format pretty || \
		(echo "canonical-check-py: violations found"; exit 1)

canonical-check-fe:
	@cd autobot-frontend && find src -type f \( -name '*.ts' -o -name '*.vue' \) \
		-print0 2>/dev/null | xargs -0 --no-run-if-empty node scripts/canonical_check.mjs --files

canonical-check-infra:
	@find scripts -type f \( -name '*.sh' -o -name '*.yml' -o -name '*.yaml' \) \
		-print0 2>/dev/null | xargs -0 --no-run-if-empty python3 tools/lint/canonical_check_infra.py --files

canonical-audit:
	@mkdir -p .canonical-audit
	@python3 tools/lint/canonical_check.py --all --format markdown \
		--output .canonical-audit/canonical-audit-py-$$(date -u +%Y-%m-%d).md
	@python3 tools/lint/canonical_check_infra.py --all --format markdown \
		--output .canonical-audit/canonical-audit-infra-$$(date -u +%Y-%m-%d).md
	@echo "canonical-audit: report written to .canonical-audit/"
