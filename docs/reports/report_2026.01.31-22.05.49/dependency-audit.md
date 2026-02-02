# Dependency Audit
**Generated**: 2026.01.31-23:10:00
**Report ID**: report_2026.01.31-22.05.49
**Analysis Scope**: requirements.txt and package.json
**Priority Level**: Medium

## Executive Summary
The project utilizes a wide range of specialized AI and infrastructure libraries. While most are up-to-date, there are critical version constraints for `protobuf` and security updates for `pypdf` that must be maintained.

## Impact Assessment
- **Timeline Impact**: Regular maintenance required to avoid "dependency hell".
- **Resource Requirements**: Low.
- **Business Value**: Medium - Ensures security and performance.
- **Risk Level**: Low

## Critical Dependency Findings

### 1. Protobuf Version Constraint
- **Version**: `protobuf>=4.23.0,<5.0.0`
- **Reason**: Protobuf 5.x/6.x causes `AttributeError` in TensorFlow.
- **Action**: DO NOT update beyond 4.x until TF compatibility is resolved.

### 2. PyPDF Security Update
- **Version**: `pypdf>=6.4.0`
- **Impact**: Fixes 4 critical CVEs.
- **Action**: Verified as complete in `requirements.txt`.

### 3. FAISS GPU Support
- **Package**: `faiss-gpu>=1.7.4`
- **Requirement**: CUDA toolkit installation on VM4.
- **Action**: Ensure deployment scripts verify CUDA presence.

## Frontend Dependencies (autobot-vue)
- **Framework**: Vue 3.5.17
- **Key Libraries**: Pinia (State), Vite (Build), XTerm (Terminal).
- **Audit**: frontend dependencies are modern and well-managed.

## Outdated Dependencies
- **Action Required**: Conduct a full `pip list --outdated` on all 5 VMs to identify minor version updates for non-constrained packages.
