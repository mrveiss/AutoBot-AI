# Task Manager Server - Development Tasks

This file tracks the implementation progress based on the defined milestones.

## Milestone 1: Core Setup & `createProject` Tool

- [x] **Create `tasks.md`:** Initial file creation.
- [x] **Define DB Schema:** Create `src/db/schema.sql` with tables and indexes.
- [x] **Implement DB Manager:** Create `src/db/DatabaseManager.ts` for connection, init, WAL.
- [x] **Update Config:** Ensure `src/config/ConfigurationManager.ts` handles DB path.
- [x] **Implement Project Repo:** Create `src/repositories/ProjectRepository.ts` with `create` method.
- [x] **Implement Project Service:** Create `src/services/ProjectService.ts` with `createProject` method.
- [x] **Implement `createProject` Params:** Create `src/tools/createProjectParams.ts`.
- [x] **Implement `createProject` Tool:** Create `src/tools/createProjectTool.ts`.
- [x] **Implement Utilities:** Create/update `src/utils/logger.ts`, `src/utils/errors.ts`, `src/utils/index.ts`.
- [x] **Update Server Setup:** Modify `src/server.ts`, `src/createServer.ts`, `src/tools/index.ts`, `src/services/index.ts`.
- [ ] **Write Tests:** Unit test `ProjectService`, Integration test `createProject` tool. *(Skipped/Deferred)*

## Milestone 2: Core Task Management Tools

- [x] Implement `addTask` tool (FR-002)
- [x] Implement `listTasks` tool (FR-003)
- [x] Implement `showTask` tool (FR-004)
- [x] Implement `setTaskStatus` tool (FR-005)

## Milestone 3: Advanced & I/O Tools

- [x] Implement `expandTask` tool (FR-006)
- [x] Implement `getNextTask` tool (FR-007)
- [x] Implement `exportProject` tool (FR-009)
- [x] Implement `importProject` tool (FR-010)
- [x] Implement structured logging (NFR-006).
- [x] Finalize documentation (README, tool descriptions).
