# GUI Status Display Bug - Comprehensive Task Breakdown

**Date Created:** 2025-10-11
**Issue:** Frontend shows conflicting status information
**Root Cause:** App.vue calls wrong endpoints and has duplicate hardcoded logic instead of using useSystemStatus composable
**Fix Approach:** Refactor App.vue to use existing useSystemStatus composable with correct endpoints

---

## Executive Summary

### Problem Statement
The GUI displays conflicting status information because:
1. App.vue has duplicate hardcoded status logic (lines 467-702)
2. App.vue calls wrong endpoints (`/api/health`, `/api/monitoring/status`)
3. Existing useSystemStatus composable with correct endpoints is not being used

### Solution Overview
- **Primary Fix:** Refactor App.vue to import and use useSystemStatus composable
- **Secondary Fix:** Remove duplicate hardcoded status logic from App.vue
- **Benefit:** Single source of truth, correct endpoints, maintainable code

### Files Affected
- **Primary:** `/home/kali/Desktop/AutoBot/autobot-user-frontend/src/App.vue` (lines 467-702)
- **Reference:** `/home/kali/Desktop/AutoBot/autobot-user-frontend/src/composables/useSystemStatus.js` (already correct)

### Correct Endpoints (from useSystemStatus)
- `/api/service-monitor/vms/status` - Infrastructure VM status
- `/api/service-monitor/services` - Service health status

---

## 1. PRE-IMPLEMENTATION TASKS

### Task 1.1: Verify Backend Endpoint Availability
**Agent:** `senior-backend-engineer`
**Complexity:** Simple
**Estimated Time:** 10 minutes
**Dependencies:** None
**Parallel Track:** A

**Description:**
Verify that backend endpoints exist and return expected data structures.

**Action Items:**
- [ ] Check `/api/service-monitor/vms/status` endpoint exists in backend routing
- [ ] Check `/api/service-monitor/services` endpoint exists in backend routing
- [ ] Verify response structure matches useSystemStatus expectations
- [ ] Test endpoints with curl or Postman to confirm they're accessible
- [ ] Document any discrepancies between expected and actual responses

**Success Criteria:**
- Both endpoints return 200 OK status
- Response structure matches composable expectations
- No authentication or CORS issues detected

**Commands:**
```bash
# Test VM status endpoint
curl -X GET https://172.16.168.20:8443/api/service-monitor/vms/status

# Test services endpoint
curl -X GET https://172.16.168.20:8443/api/service-monitor/services
```

---

### Task 1.2: Verify useSystemStatus Composable Functionality
**Agent:** `frontend-engineer`
**Complexity:** Simple
**Estimated Time:** 15 minutes
**Dependencies:** None
**Parallel Track:** A (can run parallel with Task 1.1)

**Description:**
Review and verify the useSystemStatus composable has all functionality needed by App.vue.

**Action Items:**
- [ ] Review useSystemStatus.js exports (state, methods, computed properties)
- [ ] Verify it provides: systemStatus, systemServices, showSystemStatus refs
- [ ] Verify it provides: refreshSystemStatus, updateSystemStatus, toggleSystemStatus methods
- [ ] Verify it provides: getSystemStatusTooltip, getSystemStatusText, getSystemStatusDescription
- [ ] Check for any missing functionality that App.vue currently implements
- [ ] Document API contract of composable

**Success Criteria:**
- All App.vue requirements can be satisfied by composable
- No missing functionality identified
- API contract documented

**Files to Review:**
- `/home/kali/Desktop/AutoBot/autobot-user-frontend/src/composables/useSystemStatus.js`

---

### Task 1.3: Identify Component Dependencies
**Agent:** `general-purpose`
**Complexity:** Medium
**Estimated Time:** 20 minutes
**Dependencies:** None
**Parallel Track:** B

**Description:**
Search codebase for any components that might depend on App.vue's status methods.

**Action Items:**
- [ ] Search for imports of App.vue status methods in other components
- [ ] Search for $parent or $root references to status data in child components
- [ ] Verify SystemStatusNotification component data expectations
- [ ] Check if any global event bus or store depends on App.vue status
- [ ] Document all dependencies found

**Success Criteria:**
- All dependencies identified and documented
- No hidden references to App.vue status logic found
- SystemStatusNotification compatibility confirmed

**Search Commands:**
```bash
# Search for references to App.vue status methods
grep -r "systemStatus\|systemServices\|refreshSystemStatus" autobot-user-frontend/src/components/

# Search for parent/root references
grep -r "\$parent\|\$root" autobot-user-frontend/src/components/ | grep -i status
```

---

### Task 1.4: Plan Code Review Strategy
**Agent:** `code-reviewer`
**Complexity:** Simple
**Estimated Time:** 10 minutes
**Dependencies:** Tasks 1.1, 1.2, 1.3
**Parallel Track:** C

**Description:**
Plan comprehensive code review approach for the refactoring.

**Action Items:**
- [ ] Define code review checklist based on research findings
- [ ] Identify critical review points (endpoint correctness, data flow, error handling)
- [ ] Plan testing scenarios for code review validation
- [ ] Schedule review to happen immediately after implementation
- [ ] Document review acceptance criteria

**Success Criteria:**
- Code review checklist created
- Review criteria clearly defined
- Review scheduled in workflow

---

## 2. IMPLEMENTATION TASKS

### Task 2.1: Refactor App.vue to Use Composable
**Agent:** `frontend-engineer`
**Complexity:** Medium
**Estimated Time:** 30 minutes
**Dependencies:** Tasks 1.1, 1.2, 1.3, 1.4
**Parallel Track:** D

**Description:**
Replace hardcoded status logic in App.vue with useSystemStatus composable.

**Action Items:**
- [ ] Import useSystemStatus at top of App.vue script section
- [ ] Remove hardcoded systemStatus ref (line 467-471)
- [ ] Remove hardcoded systemServices ref (line 473-481)
- [ ] Remove refreshSystemStatus method (line 563-690)
- [ ] Remove updateSystemStatus method (line 693-702)
- [ ] Remove getSystemStatusTooltip method (line 530-538)
- [ ] Remove getSystemStatusText method (line 540-548)
- [ ] Remove getSystemStatusDescription method (line 550-561)
- [ ] Destructure needed values/methods from useSystemStatus()
- [ ] Update setup() return statement to use composable values
- [ ] Verify template bindings still work with composable data

**Success Criteria:**
- All duplicate logic removed from App.vue
- useSystemStatus composable properly imported and used
- No compilation errors
- Template still renders correctly
- ~235 lines of code removed from App.vue

**Code Changes:**
```javascript
// ADD at top of script section (around line 434)
import { useSystemStatus } from '@/composables/useSystemStatus'

// MODIFY setup() function (around line 455)
setup() {
  // ... existing code ...

  // ADD: Use composable instead of local state
  const {
    systemStatus,
    systemServices,
    showSystemStatus,
    getSystemStatusTooltip,
    getSystemStatusText,
    getSystemStatusDescription,
    toggleSystemStatus,
    refreshSystemStatus,
    updateSystemStatus
  } = useSystemStatus()

  // REMOVE: Lines 467-702 (all hardcoded status logic)

  // ... rest of existing code ...
}
```

**Files Modified:**
- `/home/kali/Desktop/AutoBot/autobot-user-frontend/src/App.vue`

---

### Task 2.2: Update onMounted Lifecycle Hook
**Agent:** `frontend-engineer`
**Complexity:** Simple
**Estimated Time:** 10 minutes
**Dependencies:** Task 2.1
**Parallel Track:** D (sequential after 2.1)

**Description:**
Update the onMounted hook to use composable's refreshSystemStatus method.

**Action Items:**
- [ ] Locate onMounted hook (around line 810)
- [ ] Verify it's calling the composable's refreshSystemStatus (not local version)
- [ ] Ensure graceful error handling is maintained
- [ ] Verify updateSystemStatus is still called after refresh
- [ ] Test that initialization doesn't block Vue mounting

**Success Criteria:**
- onMounted uses composable methods correctly
- Error handling preserved
- No blocking calls during mount

**Code Changes:**
```javascript
// Around line 842 - should already use composable's method
try {
  await refreshSystemStatus()  // Now from composable
  updateSystemStatus()  // Now from composable
} catch (statusError) {
  console.warn('[App] System status initialization failed, but Vue app will continue:', statusError)
}
```

---

### Task 2.3: Verify Template Bindings
**Agent:** `frontend-engineer`
**Complexity:** Simple
**Estimated Time:** 15 minutes
**Dependencies:** Task 2.1
**Parallel Track:** D (sequential after 2.1)

**Description:**
Ensure all template bindings work correctly with composable data.

**Action Items:**
- [ ] Verify status indicator dot bindings (lines 17-25)
- [ ] Verify system status modal bindings (lines 314-336)
- [ ] Verify services list rendering (lines 342-369)
- [ ] Verify method calls in template (toggleSystemStatus, refreshSystemStatus)
- [ ] Check for any template syntax errors
- [ ] Test reactive updates with dev tools

**Success Criteria:**
- All template bindings compile without errors
- Data flows correctly from composable to template
- Reactive updates work as expected

**Template Sections to Verify:**
- Status indicator dot (lines 17-25)
- System status modal (lines 280-393)
- Service list (lines 342-369)

---

## 3. TESTING TASKS

### Task 3.1: Unit Test useSystemStatus Composable
**Agent:** `testing-engineer`
**Complexity:** Medium
**Estimated Time:** 45 minutes
**Dependencies:** Task 2.1
**Parallel Track:** E

**Description:**
Create comprehensive unit tests for the useSystemStatus composable.

**Action Items:**
- [ ] Create test file: `autobot-user-frontend/tests/unit/composables/useSystemStatus.spec.js`
- [ ] Test refreshSystemStatus with successful API responses
- [ ] Test refreshSystemStatus with API failures and fallbacks
- [ ] Test updateSystemStatus correctly calculates health status
- [ ] Test toggleSystemStatus toggles showSystemStatus ref
- [ ] Test getSystemStatusText returns correct text for each status
- [ ] Test getSystemStatusDescription returns correct descriptions
- [ ] Test getSystemStatusTooltip returns correct tooltips
- [ ] Mock apiEndpointMapper.fetchWithFallback calls
- [ ] Verify error handling and fallback behavior
- [ ] Achieve >90% code coverage on composable

**Success Criteria:**
- All composable functions have unit tests
- Tests pass locally
- Code coverage >90%
- Edge cases covered (network errors, empty responses, etc.)

**Test File Location:**
- `/home/kali/Desktop/AutoBot/autobot-user-frontend/tests/unit/composables/useSystemStatus.spec.js`

**Test Framework:**
- Vitest (already configured in project)
- @vue/test-utils for Vue 3 testing

---

### Task 3.2: Integration Test App.vue Status Display
**Agent:** `testing-engineer`
**Complexity:** Medium
**Estimated Time:** 40 minutes
**Dependencies:** Tasks 2.1, 2.2, 2.3
**Parallel Track:** E (can run parallel with 3.1)

**Description:**
Test App.vue integration with useSystemStatus composable.

**Action Items:**
- [ ] Create test file: `autobot-user-frontend/tests/integration/AppStatusIntegration.spec.js`
- [ ] Test App.vue mounts successfully with composable
- [ ] Test status indicator dot displays correct colors
- [ ] Test system status modal opens/closes correctly
- [ ] Test service list populates with mock data
- [ ] Test refresh button triggers refreshSystemStatus
- [ ] Test error handling when backend unavailable
- [ ] Mock backend API responses
- [ ] Verify template renders correctly with composable data

**Success Criteria:**
- App.vue renders correctly with composable
- All user interactions work as expected
- Error states handled gracefully
- Tests pass locally

**Test File Location:**
- `/home/kali/Desktop/AutoBot/autobot-user-frontend/tests/integration/AppStatusIntegration.spec.js`

---

### Task 3.3: Manual Testing Scenarios
**Agent:** `qa-tester` (or `frontend-engineer`)
**Complexity:** Medium
**Estimated Time:** 30 minutes
**Dependencies:** Tasks 2.1, 2.2, 2.3, deployment to VM1
**Parallel Track:** F (after deployment)

**Description:**
Execute manual testing scenarios in browser to verify functionality.

**Manual Test Cases:**

#### Test Case 1: Status Indicator Display
- [ ] Load application in browser (http://172.16.168.21:5173)
- [ ] Verify status indicator dot appears in top-left
- [ ] Verify dot color matches system health (green/yellow/red)
- [ ] Verify dot animates (pulse) when issues detected

**Expected Results:**
- Dot visible and colored correctly
- Animation works for error states

---

#### Test Case 2: System Status Modal
- [ ] Click status indicator (AB logo with dot)
- [ ] Verify modal opens with system status
- [ ] Verify "System Overview" section shows correct status
- [ ] Verify "Services" section lists all services
- [ ] Verify each service shows correct status (healthy/warning/error)
- [ ] Verify service status text is accurate

**Expected Results:**
- Modal opens smoothly
- All sections populated correctly
- Service statuses match backend reality

---

#### Test Case 3: Refresh Functionality
- [ ] Open system status modal
- [ ] Click "Refresh" button
- [ ] Verify loading state (if implemented)
- [ ] Verify services update with latest status
- [ ] Verify timestamp updates

**Expected Results:**
- Refresh triggers backend call
- UI updates with new data
- No errors in console

---

#### Test Case 4: Error Handling
- [ ] Stop backend API (simulate network failure)
- [ ] Open system status modal
- [ ] Verify graceful error handling
- [ ] Verify fallback status displayed
- [ ] Verify error logged to console (not crash)
- [ ] Restart backend API
- [ ] Click refresh
- [ ] Verify recovery to normal status

**Expected Results:**
- No application crash
- Fallback UI displayed
- Recovery works after backend restored

---

#### Test Case 5: Responsive Design
- [ ] Test status modal on desktop (1920x1080)
- [ ] Test status modal on tablet (768x1024)
- [ ] Test status modal on mobile (375x667)
- [ ] Verify all elements visible and accessible
- [ ] Verify click targets large enough on mobile

**Expected Results:**
- Modal responsive on all screen sizes
- No layout issues
- Touch targets adequate on mobile

---

### Task 3.4: Edge Case Validation
**Agent:** `testing-engineer`
**Complexity:** Medium
**Estimated Time:** 30 minutes
**Dependencies:** Tasks 3.1, 3.2, 3.3
**Parallel Track:** E

**Description:**
Test edge cases and unusual scenarios.

**Edge Cases to Test:**

#### Edge Case 1: Empty Service List
- [ ] Mock backend returning empty services array
- [ ] Verify UI handles gracefully (shows "No services found" or similar)
- [ ] No JavaScript errors

#### Edge Case 2: Partial Service Failure
- [ ] Mock VM endpoint success, services endpoint failure
- [ ] Verify partial data displayed
- [ ] Warning shown for failed endpoint

#### Edge Case 3: Malformed Backend Response
- [ ] Mock backend returning invalid JSON
- [ ] Verify error handling catches and logs error
- [ ] Fallback state displayed

#### Edge Case 4: Slow Backend Response
- [ ] Mock backend with 10-second delay
- [ ] Verify timeout handling (should have 5-second timeout)
- [ ] Fallback data used after timeout

#### Edge Case 5: Rapid Refresh Clicks
- [ ] Click refresh button 5 times rapidly
- [ ] Verify no race conditions
- [ ] Only latest request's data displayed
- [ ] No duplicate network requests

**Success Criteria:**
- All edge cases handled gracefully
- No crashes or unhandled errors
- User experience remains smooth

---

## 4. DOCUMENTATION TASKS

### Task 4.1: Update Code Comments
**Agent:** `documentation-engineer`
**Complexity:** Simple
**Estimated Time:** 20 minutes
**Dependencies:** Tasks 2.1, 2.2, 2.3
**Parallel Track:** G (can run parallel with testing)

**Description:**
Add/update code comments in modified files.

**Action Items:**
- [ ] Add JSDoc comments to App.vue script section explaining composable usage
- [ ] Document why useSystemStatus is used instead of local state
- [ ] Add comments explaining the correct endpoints being called
- [ ] Update any existing comments that reference old implementation
- [ ] Ensure comments follow project standards

**Success Criteria:**
- All new code has clear comments
- JSDoc format used for functions
- Comments explain "why" not just "what"

**Files to Update:**
- `/home/kali/Desktop/AutoBot/autobot-user-frontend/src/App.vue`
- `/home/kali/Desktop/AutoBot/autobot-user-frontend/src/composables/useSystemStatus.js` (if needed)

---

### Task 4.2: Update API Documentation
**Agent:** `documentation-engineer`
**Complexity:** Simple
**Estimated Time:** 15 minutes
**Dependencies:** Task 1.1
**Parallel Track:** G (can run parallel with 4.1)

**Description:**
Document the correct API endpoints used for system status.

**Action Items:**
- [ ] Create or update API documentation for `/api/service-monitor/vms/status`
- [ ] Create or update API documentation for `/api/service-monitor/services`
- [ ] Document request/response structure for each endpoint
- [ ] Add examples of successful responses
- [ ] Add examples of error responses
- [ ] Document authentication requirements (if any)

**Success Criteria:**
- Complete API documentation for both endpoints
- Request/response examples provided
- Error cases documented

**Documentation Location:**
- `/home/kali/Desktop/AutoBot/docs/api/service-monitor-endpoints.md` (create if needed)

---

### Task 4.3: Update User Guide (if applicable)
**Agent:** `documentation-engineer`
**Complexity:** Simple
**Estimated Time:** 10 minutes
**Dependencies:** Task 3.3
**Parallel Track:** G

**Description:**
Update user-facing documentation if system status display behavior changes.

**Action Items:**
- [ ] Check if user guide exists for system status feature
- [ ] Update screenshots if UI changed
- [ ] Document how to interpret status indicator colors
- [ ] Document what each service status means
- [ ] Add troubleshooting section if needed

**Success Criteria:**
- User guide reflects current implementation
- Screenshots current and accurate
- Clear explanations for end users

**Documentation Location:**
- `/home/kali/Desktop/AutoBot/docs/user-guides/system-status-monitoring.md` (if exists)

---

## 5. DEPLOYMENT TASKS

### Task 5.1: Sync Changes to Frontend VM (VM1)
**Agent:** `devops-engineer`
**Complexity:** Simple
**Estimated Time:** 5 minutes
**Dependencies:** All implementation and testing tasks complete
**Parallel Track:** H

**Description:**
Sync modified frontend files to VM1 (172.16.168.21).

**Action Items:**
- [ ] Verify all tests passing locally before sync
- [ ] Use sync-frontend.sh or sync-to-vm.sh script
- [ ] Sync App.vue to VM1
- [ ] Sync useSystemStatus.js to VM1 (verify no changes needed)
- [ ] Verify file permissions after sync
- [ ] Check sync completed without errors

**Success Criteria:**
- All files synced successfully to VM1
- No permission errors
- Files match local versions exactly

**Sync Commands:**
```bash
# Sync App.vue to VM1
./scripts/utilities/sync-to-vm.sh frontend autobot-user-frontend/src/App.vue /home/autobot/autobot-user-frontend/src/App.vue

# Sync composable (if modified)
./scripts/utilities/sync-to-vm.sh frontend autobot-user-frontend/src/composables/useSystemStatus.js /home/autobot/autobot-user-frontend/src/composables/useSystemStatus.js

# Or sync entire src directory
./scripts/utilities/sync-to-vm.sh frontend autobot-user-frontend/src/ /home/autobot/autobot-user-frontend/src/
```

---

### Task 5.2: Restart Frontend Service on VM1
**Agent:** `devops-engineer`
**Complexity:** Simple
**Estimated Time:** 3 minutes
**Dependencies:** Task 5.1
**Parallel Track:** H (sequential after 5.1)

**Description:**
Restart the frontend development server on VM1 to load new code.

**Action Items:**
- [ ] SSH to VM1 (172.16.168.21)
- [ ] Navigate to frontend directory
- [ ] Restart development server (or rebuild if production mode)
- [ ] Verify service starts without errors
- [ ] Check logs for any startup issues

**Success Criteria:**
- Frontend service restarted successfully
- No errors in startup logs
- Service accessible at http://172.16.168.21:5173

**Commands:**
```bash
# SSH to VM1
ssh -i ~/.ssh/autobot_key autobot@172.16.168.21

# If dev mode
cd /home/autobot/autobot-vue
npm run dev

# If production mode (rebuild)
cd /home/autobot/autobot-vue
npm run build
# Restart production server (depends on setup)
```

**Note:** Check current VM1 setup to determine if dev or production mode is running.

---

### Task 5.3: Post-Deployment Verification
**Agent:** `qa-tester` (or `devops-engineer`)
**Complexity:** Medium
**Estimated Time:** 20 minutes
**Dependencies:** Task 5.2
**Parallel Track:** H (sequential after 5.2)

**Description:**
Verify deployment successful and functionality works on VM1.

**Verification Steps:**

#### Step 1: Basic Connectivity
- [ ] Access frontend at http://172.16.168.21:5173
- [ ] Verify application loads without errors
- [ ] Check browser console for JavaScript errors
- [ ] Check Network tab for failed API requests

#### Step 2: Status Display Functionality
- [ ] Verify status indicator dot appears in header
- [ ] Click status indicator to open modal
- [ ] Verify services list populated correctly
- [ ] Verify status colors correct (green/yellow/red)
- [ ] Click refresh button
- [ ] Verify status updates

#### Step 3: Backend Connectivity
- [ ] Open browser DevTools Network tab
- [ ] Click refresh in status modal
- [ ] Verify correct endpoints called:
  - `/api/service-monitor/vms/status`
  - `/api/service-monitor/services`
- [ ] Verify responses return 200 OK
- [ ] Verify response data structure correct

#### Step 4: Error Handling
- [ ] Temporarily stop backend API
- [ ] Click refresh in status modal
- [ ] Verify graceful error handling (no crash)
- [ ] Verify fallback status displayed
- [ ] Restart backend API
- [ ] Verify recovery

**Success Criteria:**
- All verification steps pass
- No errors in browser console
- Correct endpoints being called
- Status display matches backend reality

---

### Task 5.4: Rollback Plan Documentation
**Agent:** `devops-engineer`
**Complexity:** Simple
**Estimated Time:** 10 minutes
**Dependencies:** None (can be done anytime)
**Parallel Track:** I (parallel with everything)

**Description:**
Document rollback procedure in case deployment fails.

**Action Items:**
- [ ] Document current App.vue version (git commit hash)
- [ ] Create backup of App.vue on VM1 before deployment
- [ ] Document rollback commands to restore previous version
- [ ] Test rollback procedure in staging (if available)
- [ ] Document who to contact if rollback needed

**Success Criteria:**
- Rollback procedure documented
- Backup created before deployment
- Rollback tested and verified

**Rollback Procedure:**
```bash
# On local machine - revert to previous commit
git checkout <previous-commit-hash> autobot-user-frontend/src/App.vue

# Sync reverted file to VM1
./scripts/utilities/sync-to-vm.sh frontend autobot-user-frontend/src/App.vue /home/autobot/autobot-user-frontend/src/App.vue

# On VM1 - restart service
ssh -i ~/.ssh/autobot_key autobot@172.16.168.21
cd /home/autobot/autobot-vue
npm run dev  # or rebuild if production
```

---

## 6. TASK DEPENDENCIES & PARALLEL EXECUTION TRACKS

### Dependency Graph

```
Phase 1: Pre-Implementation (All can run in parallel)
├── Track A: Tasks 1.1, 1.2 (parallel)
├── Track B: Task 1.3
└── Track C: Task 1.4 (depends on 1.1, 1.2, 1.3)

Phase 2: Implementation (Sequential)
└── Track D: Task 2.1 → Task 2.2 → Task 2.3

Phase 3: Testing (Parallel after implementation)
├── Track E: Tasks 3.1, 3.2, 3.4 (parallel)
└── Track F: Task 3.3 (after deployment)

Phase 4: Documentation (Parallel with testing)
└── Track G: Tasks 4.1, 4.2, 4.3 (parallel)

Phase 5: Deployment (Sequential)
├── Track H: Task 5.1 → Task 5.2 → Task 5.3
└── Track I: Task 5.4 (parallel, can be done anytime)
```

### Parallel Execution Opportunities

**Maximum Parallelization:**
1. **Pre-Implementation Phase:** Run Tasks 1.1, 1.2, 1.3 simultaneously (3 agents)
2. **Testing + Documentation Phase:** Run Tasks 3.1, 3.2, 3.4, 4.1, 4.2, 4.3 simultaneously (6 agents)

**Estimated Total Time with Parallelization:**
- Pre-Implementation: ~20 minutes (parallel)
- Implementation: ~55 minutes (sequential)
- Testing + Documentation: ~45 minutes (parallel)
- Deployment: ~28 minutes (sequential)
- **Total: ~2.5 hours** (vs ~5 hours sequential)

---

## 7. AGENT ASSIGNMENTS SUMMARY

| Agent Type | Tasks Assigned | Total Time | Priority |
|------------|----------------|------------|----------|
| `senior-backend-engineer` | Task 1.1 | 10 min | High |
| `frontend-engineer` | Tasks 1.2, 2.1, 2.2, 2.3 | 90 min | Critical |
| `general-purpose` | Task 1.3 | 20 min | High |
| `code-reviewer` | Task 1.4, Review all code changes | 40 min | Critical |
| `testing-engineer` | Tasks 3.1, 3.2, 3.4 | 115 min | High |
| `qa-tester` | Tasks 3.3, 5.3 | 50 min | High |
| `documentation-engineer` | Tasks 4.1, 4.2, 4.3 | 45 min | Medium |
| `devops-engineer` | Tasks 5.1, 5.2, 5.3, 5.4 | 38 min | High |

**Critical Path Agents:**
- `frontend-engineer` - Implementation tasks (90 min)
- `code-reviewer` - Mandatory review before deployment
- `devops-engineer` - Deployment tasks

---

## 8. RISK ASSESSMENT & MITIGATION

### High-Risk Areas

#### Risk 1: Breaking Changes to App.vue
**Probability:** Medium
**Impact:** High
**Mitigation:**
- Comprehensive unit and integration tests before deployment
- Code review by senior frontend engineer
- Rollback plan documented and tested
- Deploy to staging first (if available)

#### Risk 2: Backend Endpoints Not Available
**Probability:** Low
**Impact:** High
**Mitigation:**
- Task 1.1 verifies endpoint availability before implementation
- Graceful fallback handling already in composable
- Manual testing includes backend failure scenarios

#### Risk 3: Template Binding Issues
**Probability:** Low
**Impact:** Medium
**Mitigation:**
- Task 2.3 specifically verifies template bindings
- Integration tests cover template rendering
- Manual testing validates UI rendering

#### Risk 4: Performance Regression
**Probability:** Low
**Impact:** Medium
**Mitigation:**
- Composable uses same API patterns as before
- No additional network requests introduced
- Manual testing includes performance observation

---

## 9. SUCCESS CRITERIA CHECKLIST

### Pre-Deployment Checklist
- [ ] All unit tests passing (Task 3.1)
- [ ] All integration tests passing (Task 3.2)
- [ ] Edge cases validated (Task 3.4)
- [ ] Code review approved by code-reviewer agent
- [ ] Manual testing completed successfully (Task 3.3)
- [ ] Documentation updated (Tasks 4.1, 4.2, 4.3)
- [ ] Rollback plan documented (Task 5.4)

### Post-Deployment Checklist
- [ ] Files synced to VM1 successfully (Task 5.1)
- [ ] Frontend service restarted without errors (Task 5.2)
- [ ] Post-deployment verification passed (Task 5.3)
- [ ] Status indicator displays correctly
- [ ] Correct API endpoints being called
- [ ] System status modal functions correctly
- [ ] Service list populated accurately
- [ ] Refresh functionality works
- [ ] Error handling works gracefully
- [ ] No JavaScript errors in browser console
- [ ] No backend errors in API logs

### Final Acceptance Criteria
- [ ] GUI displays correct service statuses (no more conflicting information)
- [ ] Code duplication eliminated (App.vue uses composable)
- [ ] Correct endpoints called (`/api/service-monitor/*` instead of `/api/monitoring/status`)
- [ ] All tests passing
- [ ] Documentation complete
- [ ] No regressions in functionality
- [ ] Performance maintained or improved

---

## 10. ESTIMATED EFFORT SUMMARY

### By Complexity

| Complexity | Task Count | Total Time |
|------------|------------|------------|
| Simple | 11 tasks | ~105 minutes |
| Medium | 8 tasks | ~215 minutes |
| Complex | 0 tasks | 0 minutes |
| **Total** | **19 tasks** | **~320 minutes (~5.3 hours)** |

### By Phase

| Phase | Task Count | Sequential Time | Parallel Time |
|-------|------------|----------------|---------------|
| Pre-Implementation | 4 tasks | 55 min | 20 min |
| Implementation | 3 tasks | 55 min | 55 min |
| Testing | 4 tasks | 145 min | 45 min |
| Documentation | 3 tasks | 45 min | 20 min |
| Deployment | 4 tasks | 38 min | 28 min |
| **Total** | **18 tasks** | **338 min (5.6 hrs)** | **168 min (2.8 hrs)** |

**With Optimal Parallelization: ~2.8 hours total**

---

## 11. NEXT STEPS

### Immediate Actions (Before Starting Implementation)

1. **Get Approval:** Review this task breakdown with team/user for approval
2. **Resource Allocation:** Ensure required agents available for parallel execution
3. **Environment Check:** Verify VM1 accessible and backend running
4. **Backup Current State:** Create git branch and VM1 backup before changes

### Execution Order

**Phase 1: Pre-Implementation (Parallel)**
```bash
# Launch 3 agents simultaneously
Task(subagent_type="senior-backend-engineer", description="Verify backend endpoints", ...)
Task(subagent_type="frontend-engineer", description="Verify useSystemStatus composable", ...)
Task(subagent_type="general-purpose", description="Identify component dependencies", ...)
```

**Phase 2: Implementation (Sequential)**
```bash
# Launch frontend-engineer for refactoring
Task(subagent_type="frontend-engineer", description="Refactor App.vue to use composable", ...)
# Followed by code-reviewer
Task(subagent_type="code-reviewer", description="Review all code changes", ...)
```

**Phase 3: Testing + Documentation (Parallel)**
```bash
# Launch 6 agents simultaneously
Task(subagent_type="testing-engineer", description="Unit test composable", ...)
Task(subagent_type="testing-engineer", description="Integration test App.vue", ...)
Task(subagent_type="testing-engineer", description="Edge case validation", ...)
Task(subagent_type="documentation-engineer", description="Update code comments", ...)
Task(subagent_type="documentation-engineer", description="Update API docs", ...)
Task(subagent_type="documentation-engineer", description="Update user guide", ...)
```

**Phase 4: Deployment (Sequential)**
```bash
# Launch devops-engineer for deployment
Task(subagent_type="devops-engineer", description="Sync files and restart service", ...)
# Followed by qa-tester
Task(subagent_type="qa-tester", description="Post-deployment verification", ...)
```

---

## 12. APPENDIX

### A. Correct Endpoint Details

#### Endpoint 1: VM Status
```
GET /api/service-monitor/vms/status
Response: {
  "vms": [
    {
      "name": "Backend API",
      "status": "online|warning|error",
      "message": "Status description"
    },
    ...
  ]
}
```

#### Endpoint 2: Service Health
```
GET /api/service-monitor/services
Response: {
  "services": {
    "backend": {
      "status": "online|warning|error",
      "health": "Health description"
    },
    "redis": { ... },
    "ollama": { ... },
    ...
  }
}
```

### B. Wrong Endpoints (Being Replaced)

#### Wrong Endpoint 1: Basic Health
```
GET /api/health
Response: { "status": "ok" }
Purpose: Basic health check, NOT detailed service status
```

#### Wrong Endpoint 2: Monitoring System Status
```
GET /api/monitoring/status
Response: {
  "active": true,
  "uptime_seconds": 12345,
  ...
}
Purpose: Monitoring system status, NOT service health
```

### C. File Line Numbers Reference

**App.vue - Lines to Remove:**
- 467-471: hardcoded systemStatus ref
- 473-481: hardcoded systemServices ref
- 530-538: getSystemStatusTooltip method
- 540-548: getSystemStatusText method
- 550-561: getSystemStatusDescription method
- 563-690: refreshSystemStatus method
- 693-702: updateSystemStatus method

**Total Lines Removed: ~235 lines**

### D. Testing Commands Reference

```bash
# Run unit tests
cd /home/kali/Desktop/AutoBot/autobot-vue
npm run test:unit

# Run integration tests
npm run test:integration

# Run all tests
npm run test

# Check test coverage
npm run test:coverage

# Lint code
npm run lint

# Type check
npm run type-check
```

---

**End of Task Breakdown Document**

**Document Version:** 1.0
**Created:** 2025-10-11
**Status:** Ready for Review and Approval
