# Archived Obsolete Scripts (October 2025)

**Archive Date:** 2025-10-10
**Reason:** One-time debugging and validation scripts no longer needed

## Scripts Archived (7 files)

### Debug Scripts (4 files)

#### debug_sidebar_detailed.py
- **Purpose:** Playwright-based sidebar visibility debugging
- **Created:** 2025-09-28
- **Status:** ✅ Obsolete - Sidebar visibility now working correctly
- **Context:** Used to debug w-80 Tailwind class application

#### verify_chat_layout.py
- **Purpose:** Remote chat layout verification via Browser VM
- **Created:** 2025-09-28
- **Status:** ✅ Obsolete - Chat layout fixed
- **Context:** SSH + Playwright verification of layout fixes

#### verify_layout_remote.py
- **Purpose:** Simplified remote layout verification
- **Created:** 2025-09-28
- **Status:** ✅ Obsolete - Layout issues resolved
- **Context:** Cleaner implementation of layout verification

#### debug_kb_search.py
- **Purpose:** Knowledge Base search parameter debugging
- **Created:** 2025-09-29
- **Status:** ✅ Obsolete - KB search working correctly
- **Context:** Debugged top_k vs similarity_top_k parameter issues

### Validation Scripts (2 files)

#### validate_rag_integration.py
- **Purpose:** RAG integration validation
- **Created:** 2025-09-29
- **Status:** ✅ Obsolete - RAG integration complete and tested
- **Context:** Post-integration validation script

#### validate_network_config.sh
- **Purpose:** Docker network standardization validation
- **Created:** 2025-09-09
- **Status:** ✅ Obsolete - Network standardization complete
- **Context:** Validated 172.16.168.x subnet standardization

### Utility Scripts (1 file)

#### update_agents_ansible_references.sh
- **Purpose:** Add Ansible playbook references to agent configs
- **Created:** 2025-09-12
- **Status:** ✅ Obsolete - One-time update completed
- **Context:** Updated all .claude/agents/*.md files

## Why Archived?

All scripts were created for specific debugging sessions or one-time
validations during late September 2025 feature development. The features
now work correctly, making these scripts obsolete.

**Key Context:**
- Sidebar visibility issues resolved
- Chat layout working correctly
- Knowledge Base search functional
- RAG integration complete
- Network configuration standardized
- Agent configurations updated

## Retention Policy

These scripts are preserved for historical reference but should be reviewed
for deletion after 90 days if not referenced or reused.

---

**Archived by:** AutoBot cleanup script
**Archive Path:** `archive/scripts-obsolete-2025-10-10/`
**Original Location:** Root directory (`/home/kali/Desktop/AutoBot/`)
