# Documentation Changelog

All notable changes to AutoBot documentation are tracked in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.4.1] - 2026-06-13

### Added

- **Release & Changelog Workflow** ([docs/developer/RELEASE_WORKFLOW.md](../developer/RELEASE_WORKFLOW.md))
  - Documents how root `CHANGELOG.md` is generated (git-cliff via `release.yml`), where fragments live, and the #9870 root cause that left it stale for ~3 months.

### Fixed

- Root `CHANGELOG.md` `[Unreleased]` staleness ([1.4.0] known gap) audited and resolved (#9870): `release.yml` read an always-empty action output for `--bumped-version`, silently skipping every release; workflow fixed, stale block replaced with an honest note pending next regeneration.

---

## [1.4.0] - 2026-05-10

### Added

- **System State Refresh** ([docs/system-state.md](../system-state.md))
  - Q2 2026 update covering canonical type consolidation, schema domain split, security work, plugin SDK changes, and frontend probe-backed health composables.
- **Plugin SDK `required_env` Reference** ([docs/developer/PLUGIN_SDK.md](../developer/PLUGIN_SDK.md))
  - Documents declarative `required_env` field on `PluginManifest` (#6971, PR #7256).
- **Archive of issue-#870 status file** ([docs/archives/IMPLEMENTATION_STATUS_issue_870.md](../archives/IMPLEMENTATION_STATUS_issue_870.md))
  - Moved root-level `IMPLEMENTATION_STATUS.md` to archives; original file scoped to issue #870 only, no longer reflects platform state.

### Changed

- **Index navigation** ([docs/INDEX.md](../INDEX.md))
  - Renamed "Roadmap 2025" link label to "Roadmap (2025–2026)" to reflect current scope.
- **Unified Memory Manager docs** ([docs/developer/UNIFIED_MEMORY_MANAGER_IMPLEMENTATION.md](../developer/UNIFIED_MEMORY_MANAGER_IMPLEMENTATION.md))
  - Migrated `TaskStatus` import examples to canonical `autobot_shared.status_enums.TaskStatus` (post-#6973).

### Known Gaps (filed as discovery issues)

- `useProbeBackedHealth` composable lacks dedicated doc page (PR #7277).
- `make_async_redis()` / `patch_async_redis()` test fixtures undocumented (PR #7267).
- `DateRangeParams` `Depends()` helper undocumented (PR #7110).
- Codegen MANIFEST canonical-enum coverage undocumented (PR #7269).
- Root `CHANGELOG.md` `[Unreleased]` section stale (git-cliff has not run for current issue range) — needs release workflow audit.

---

## [1.3.0] - 2025-12-21

### Added
- **Scaling Strategy Documentation** ([docs/operations/scaling-strategy.md](operations/scaling-strategy.md))
  - Vertical and horizontal scaling playbooks for all 5 VM types
  - Scaling triggers and thresholds
  - Monitoring recommendations
  - Load balancer configurations

- **Documentation Improvement Roadmap** ([docs/DOCUMENTATION_IMPROVEMENT_ROADMAP.md](DOCUMENTATION_IMPROVEMENT_ROADMAP.md))
  - Tracks all documentation gaps and resolutions
  - Success metrics for documentation quality
  - Future enhancement considerations

- **Documentation Versioning System** (this file)
  - CHANGELOG.md for tracking documentation updates
  - Follows Keep a Changelog format

---

## [1.2.0] - 2025-12-13

### Added
- **Architecture Decision Records (ADRs)** ([docs/adr/](adr/))
  - [ADR-001](adr/001-distributed-vm-architecture.md): Distributed 6-VM Architecture
  - [ADR-002](adr/002-redis-database-separation.md): Redis Database Separation Strategy
  - [ADR-003](adr/003-npu-integration-strategy.md): NPU Hardware Acceleration Integration
  - [ADR-004](adr/004-chat-workflow-architecture.md): Chat Workflow and Message Processing
  - [ADR-005](adr/005-single-frontend-mandate.md): Single Frontend Server Mandate
  - [Template](adr/template.md): ADR template for future decisions

- **Data Flow Diagrams** ([docs/architecture/data-flows.md](architecture/data-flows.md))
  - Overall System Data Flow
  - Chat Message Flow (sequence diagram)
  - Knowledge Base Ingestion Flow
  - Workflow Execution Flow
  - Authentication Flow
  - Browser Automation Flow
  - VNC Desktop Stream Flow
  - Redis Database Layout

- **Disaster Recovery Documentation** ([docs/operations/disaster-recovery.md](operations/disaster-recovery.md))
  - Recovery objectives (RTO/RPO)
  - 7 failure scenarios with recovery procedures
  - Backup procedures (daily and weekly)
  - Health monitoring scripts
  - Post-incident review process

- **Redis Schema Documentation** ([docs/architecture/redis-schema.md](architecture/redis-schema.md))
  - Database 0 (main): Sessions, cache, queues
  - Database 1 (knowledge): Vectors, documents, facts
  - Database 2 (prompts): System prompts, templates
  - Database 3 (analytics): Metrics, usage, errors
  - Access patterns and maintenance operations

---

## [1.1.0] - 2025-11-15

### Added
- **Developer Documentation**
  - [DEVELOPER_SETUP.md](developer/DEVELOPER_SETUP.md): Complete setup guide
  - [HARDCODING_PREVENTION.md](developer/HARDCODING_PREVENTION.md): No hardcoded values policy
  - [REDIS_CLIENT_USAGE.md](developer/REDIS_CLIENT_USAGE.md): Redis client patterns
  - [UTF8_ENFORCEMENT.md](developer/UTF8_ENFORCEMENT.md): UTF-8 encoding requirements
  - [INFRASTRUCTURE_DEPLOYMENT.md](developer/INFRASTRUCTURE_DEPLOYMENT.md): VM infrastructure guide
  - [LOGGING_STANDARDS.md](developer/LOGGING_STANDARDS.md): Structured logging requirements
  - [CODE_QUALITY_ENFORCEMENT.md](developer/CODE_QUALITY_ENFORCEMENT.md): Pre-commit hooks

### Changed
- Updated CLAUDE.md with comprehensive workflow requirements
- Reorganized docs/ directory structure

---

## [1.0.0] - 2025-10-01

### Added
- Initial documentation structure
- [docs/INDEX.md](INDEX.md): Documentation index
- [docs/api/COMPREHENSIVE_API_DOCUMENTATION.md](api/COMPREHENSIVE_API_DOCUMENTATION.md): API reference
- [docs/architecture/README.md](architecture/README.md): Architecture overview
- [docs/system-state.md](system-state.md): System status tracking

---

## Version Guidelines

### When to Update This Changelog

- **Major version (X.0.0)**: Significant documentation restructure or new major sections
- **Minor version (0.X.0)**: New documentation files or significant updates
- **Patch version (0.0.X)**: Small fixes, corrections, or clarifications

### Entry Format

```markdown
## [VERSION] - YYYY-MM-DD

### Added
- New documentation or features

### Changed
- Updates to existing documentation

### Deprecated
- Documentation marked for removal

### Removed
- Documentation that was removed

### Fixed
- Corrections to existing documentation
```

---

## Related Documentation

- [Documentation Improvement Roadmap](DOCUMENTATION_IMPROVEMENT_ROADMAP.md)
- [System State](system-state.md)
- [CLAUDE.md](../CLAUDE.md): Project instructions

---

**Author**: mrveiss
**Copyright**: © 2025 mrveiss
