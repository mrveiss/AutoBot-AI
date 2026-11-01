# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Slice 2 of #18557: sibling helpers that were near-copies share ONE core (parent #17312).

Each row names the module that now owns the core and the callers that must delegate to it. A
detector reads the callers' syntax tree (or shell function headers) and reports a definition the
core already provides -- the signature of the old copy coming back. Every detector has a contrast
test: an inline old-copy string that MUST be detected and a delegating caller that must NOT be.

Rows kept separate on purpose (recorded on #18557, one reason each):
    * worker ``main.py`` entries: ``autobot-browser-worker`` and ``autobot-tts-worker`` are synced
      to their nodes as their own directory and never import ``autobot_shared``, so a shared
      ``autobot_shared/worker_entry.py`` would be unimportable there; guarded below.
    * ``ingest_man_pages`` vs ``command_manual_manager``: an ingest worklist vs risk/category tables
      whose membership differs, not a copy.
"""

from __future__ import annotations

import ast
import re

from repo_tests._paths import repo_root

ROOT = repo_root()
AUTO_TOOLS = "autobot-backend/code_analysis/auto-tools/"
MIGRATIONS = "autobot-infrastructure/autobot-backend/scripts/migrations/"
AGENTS = "autobot-backend/agents/"
ANSIBLE = "autobot-slm-backend/ansible/"


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def defined_functions(source: str) -> set[str]:
    """Names of every function/method defined anywhere in *source*."""
    return {n.name for n in ast.walk(ast.parse(source)) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def class_defines_init(source: str) -> bool:
    """True when a class in *source* defines ``__init__`` itself."""
    return "__init__" in defined_functions(source)


def referenced_names(source: str) -> set[str]:
    """Every bare name loaded in *source* (a private copy of a constant reads it)."""
    return {n.id for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Name)}


def shell_functions(source: str) -> set[str]:
    """Names declared as ``name() {`` at column 0 in a shell script."""
    return set(re.findall(r"^(\w+)\(\)\s*\{", source, re.MULTILINE))


# --- Row 1: security_sanitizer / security_deep_sanitizer -------------------------------------
SANITIZER_CORE = {
    "validate_html_structure",
    "analyze_context_safety",
    "is_minified_library_code",
    "scan_directory",
    "inject_security_headers",
    "inject_dom_sanitization",
}
SANITIZERS = [AUTO_TOOLS + "security_sanitizer.py", AUTO_TOOLS + "security_deep_sanitizer.py"]

OLD_SANITIZER_COPY = """
class SecurityFixAgent(SecurityFixToolBase):
    def scan_directory(self, directory):
        return []
"""
DELEGATING_SANITIZER = """
class SecurityFixAgent(SecurityFixToolBase):
    def _csp_header(self):
        return "<meta>"
"""


def test_sanitizer_detector_flags_an_old_copy_and_passes_a_delegate():
    assert defined_functions(OLD_SANITIZER_COPY) & SANITIZER_CORE == {"scan_directory"}
    assert not defined_functions(DELEGATING_SANITIZER) & SANITIZER_CORE


def test_sanitizer_pair_defines_none_of_the_shared_core():
    for rel in SANITIZERS:
        assert not defined_functions(_read(rel)) & SANITIZER_CORE, rel


def test_tool_base_owns_the_sanitizer_core():
    assert SANITIZER_CORE <= defined_functions(_read(AUTO_TOOLS + "tool_base.py"))


# --- Row 2: logging_standardizer / performance_optimizer -------------------------------------
CONSOLE_TOOLS = [AUTO_TOOLS + "logging_standardizer.py", AUTO_TOOLS + "performance_optimizer.py"]

OLD_CONSOLE_COPY = "class T(ConsoleLogToolBase):\n    def should_process_file(self, p):\n        return True\n"
DELEGATING_CONSOLE = "class T(ConsoleLogToolBase):\n    BACKUP_DIR_NAME = '.x'\n"


def test_console_detector_flags_an_old_copy_and_passes_a_delegate():
    assert "should_process_file" in defined_functions(OLD_CONSOLE_COPY)
    assert "should_process_file" not in defined_functions(DELEGATING_CONSOLE)


def test_console_tools_do_not_redefine_should_process_file():
    for rel in CONSOLE_TOOLS:
        assert "should_process_file" not in defined_functions(_read(rel)), rel
    assert "should_process_file" in defined_functions(_read(AUTO_TOOLS + "tool_base.py"))


def test_logging_standardizer_has_no_private_init():
    assert not class_defines_init(_read(AUTO_TOOLS + "logging_standardizer.py"))


# --- Row 4: session migration scripts --------------------------------------------------------
SESSION_CORE = {"connect_redis", "get_all_sessions", "get_session_data"}
SESSION_SCRIPTS = [
    MIGRATIONS + "migrate_sessions_user_attribution.py",
    MIGRATIONS + "cleanup_orphaned_sessions.py",
    MIGRATIONS + "backfill_activity_user_ids.py",
    MIGRATIONS + "validate_migration.py",
]
OLD_SESSION_COPY = (
    "class M:\n    async def get_all_sessions(self):\n        return await self.r.keys('chat:session:*')\n"
)
DELEGATING_SESSION = "class M(SessionDataMixin):\n    async def run(self):\n        await self.connect_redis()\n"


def test_session_detector_flags_an_old_copy_and_passes_a_delegate():
    assert defined_functions(OLD_SESSION_COPY) & SESSION_CORE == {"get_all_sessions"}
    assert not defined_functions(DELEGATING_SESSION) & SESSION_CORE


def test_session_scripts_define_none_of_the_shared_core():
    for rel in SESSION_SCRIPTS:
        assert not defined_functions(_read(rel)) & SESSION_CORE, rel


def test_session_core_lives_in_the_sibling_module():
    assert SESSION_CORE <= defined_functions(_read(MIGRATIONS + "_session_redis.py"))


# --- Row 6: modality agents --------------------------------------------------------------------
MODALITY_AGENTS = [
    AGENTS + f"{name}_agent.py"
    for name in (
        "audio_processing",
        "image_analysis",
        "code_generation",
        "data_analysis",
        "sentiment_analysis",
        "translation",
        "summarization",
    )
]
OLD_AGENT_COPY = "class A(BaseModalityAgent):\n    def __init__(self):\n        super().__init__('a')\n"
DELEGATING_AGENT = "class A(BaseModalityAgent):\n    AGENT_ID = 'a'\n    CAPABILITIES = ('x',)\n"


def test_agent_detector_flags_an_old_copy_and_passes_a_delegate():
    assert class_defines_init(OLD_AGENT_COPY)
    assert not class_defines_init(DELEGATING_AGENT)


def test_modality_agents_have_no_private_init():
    for rel in MODALITY_AGENTS:
        assert not class_defines_init(_read(rel)), rel


def test_base_modality_agent_owns_init_and_there_is_no_second_standard_agent():
    assert "__init__" in defined_functions(_read(AGENTS + "base_modality_agent.py"))
    assert not (ROOT / AGENTS / "_standard_agent.py").exists()


# --- Row 7: terminal_handlers risk assessment --------------------------------------------------
RISK_TABLES = {"RISKY_COMMAND_PATTERNS", "MODERATE_RISK_PATTERNS"}
OLD_RISK_COPY = "for p in RISKY_COMMAND_PATTERNS:\n    pass\n"
DELEGATING_RISK = "def f(c):\n    return command_assessor.assess_command_risk(c)\n"


def test_risk_detector_flags_an_old_copy_and_passes_a_delegate():
    assert referenced_names(OLD_RISK_COPY) & RISK_TABLES
    assert not referenced_names(DELEGATING_RISK) & RISK_TABLES


def test_terminal_handlers_delegates_risk_assessment():
    source = _read("autobot-backend/api/terminal_handlers.py")
    assert not referenced_names(source) & RISK_TABLES
    assert "command_assessor" in referenced_names(source)


# --- Row 7: terminal_handlers chat and audit ----------------------------------------------------
OLD_TERMINAL_COPY = (
    "async def f(self, text):\n"
    "    await self.chat_history_manager.add_message(text=text)\n"
    "    async with aiofiles.open(path, 'a') as f:\n"
    "        await f.write(text)\n"
    "    self.audit_log.append(text)\n"
)
DELEGATING_TERMINAL = (
    "async def f(self, text):\n"
    "    await self._chat.save_command_to_chat(text)\n"
    "    await self._chat.write_to_transcript(text)\n"
    "    self._audit.log_activity('x', {})\n"
)


def private_terminal_work(source: str) -> set[str]:
    """Chat, transcript and audit writes done directly rather than through the two delegates."""
    found = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Attribute) and node.attr == "add_message":
            found.add("chat save")
        if isinstance(node, ast.Attribute) and node.attr == "open":
            if isinstance(node.value, ast.Name) and node.value.id == "aiofiles":
                found.add("transcript write")
        if isinstance(node, ast.Attribute) and node.attr == "audit_log":
            found.add("audit log")
    return found


def test_terminal_work_detector_flags_an_old_copy_and_passes_a_delegate():
    assert private_terminal_work(OLD_TERMINAL_COPY) == {"chat save", "transcript write", "audit log"}
    assert private_terminal_work(DELEGATING_TERMINAL) == set()


def test_terminal_handlers_delegates_chat_transcript_and_audit():
    source = _read("autobot-backend/api/terminal_handlers.py")
    assert private_terminal_work(source) == set()
    assert {"TerminalAuditLogger", "TerminalChatIntegrator"} <= referenced_names(source)


# --- Row 9: deploy wrappers --------------------------------------------------------------------
DEPLOY_CORE = {"log", "error_exit", "success", "check_prerequisites", "test_connectivity"}
DEPLOY_SCRIPTS = [ANSIBLE + "deploy-hybrid.sh", ANSIBLE + "deploy-native.sh"]
OLD_DEPLOY_COPY = "log() {\n    echo hi\n}\n"
DELEGATING_DEPLOY = 'source "$(dirname "${BASH_SOURCE[0]}")/../../scripts/lib/deploy-common.sh"\n'


def test_deploy_detector_flags_an_old_copy_and_passes_a_delegate():
    assert shell_functions(OLD_DEPLOY_COPY) & DEPLOY_CORE == {"log"}
    assert not shell_functions(DELEGATING_DEPLOY) & DEPLOY_CORE


def test_deploy_wrappers_source_the_lib_and_define_none_of_it():
    for rel in DEPLOY_SCRIPTS:
        source = _read(rel)
        assert not shell_functions(source) & DEPLOY_CORE, rel
        assert "scripts/lib/deploy-common.sh" in source, rel
    assert DEPLOY_CORE <= shell_functions(_read("scripts/lib/deploy-common.sh"))


# --- Row 5: the reason the worker entries stay separate ----------------------------------------
def imports_autobot_shared(source: str) -> bool:
    """True when *source* imports ``autobot_shared``; a comment or string naming it does not count."""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import) and any(a.name.split(".")[0] == "autobot_shared" for a in node.names):
            return True
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "autobot_shared":
            return True
    return False


def test_worker_import_detector_flags_an_import_and_passes_a_mention():
    assert imports_autobot_shared("from autobot_shared.worker_entry import run\n")
    assert imports_autobot_shared("import autobot_shared.logging_manager\n")
    assert not imports_autobot_shared("# cannot use autobot_shared here\nX = 'autobot_shared'\n")


def test_isolated_workers_cannot_import_autobot_shared():
    for rel in ("autobot-browser-worker/main.py", "autobot-tts-worker/main.py"):
        assert not imports_autobot_shared(_read(rel)), rel
    assert not (ROOT / "autobot_shared" / "worker_entry.py").exists()
