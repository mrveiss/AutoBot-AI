# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Security Patch for Intelligent Agent - CVE-AUTOBOT-2025-002
Integrates prompt injection detection and secure command parsing into intelligent agent

This patch adds multi-layer security validation to the intelligent agent system:
- Layer 1: Input Sanitization - Clean user prompts before LLM processing
- Layer 2: Output Parsing - Secure command extraction with validation
- Layer 3: Command Validation - Enhanced security checks
- Layer 4: Execution Safeguards - Integration with SecureCommandExecutor
- Layer 5: Audit Logging - Comprehensive tracking

INSTALLATION:
1. Backup original intelligent_agent.py
2. Apply this patch to src/intelligence/intelligent_agent.py
3. Test with provided test cases
4. Deploy to production after validation
"""

import logging
from typing import Dict, List

from src.enhanced_security_layer import EnhancedSecurityLayer
from src.security.prompt_injection_detector import (
    get_prompt_injection_detector,
)
from src.security.secure_llm_command_parser import get_secure_llm_parser

logger = logging.getLogger(__name__)


class SecureIntelligentAgentMixin:
    """
    Security mixin for IntelligentAgent class
    Adds prompt injection protection and secure command parsing

    USAGE:
    Add this mixin to IntelligentAgent class:

    class IntelligentAgent(SecureIntelligentAgentMixin):
        def __init__(self, ...):
            super().__init__()
            self._init_security()
            ...
    """

    def _init_security(self):
        """Initialize security components"""
        # Initialize prompt injection detector
        self.injection_detector = get_prompt_injection_detector(strict_mode=True)

        # Initialize secure command parser
        self.secure_parser = get_secure_llm_parser(strict_mode=True)

        # Initialize enhanced security layer for command execution
        self.security_layer = EnhancedSecurityLayer()

        logger.info("✅ Security components initialized for IntelligentAgent")

    def _sanitize_user_goal(self, user_input: str) -> str:
        """
        Sanitize user input before processing (Layer 1: Input Sanitization)

        Args:
            user_input: Raw user input

        Returns:
            Sanitized user input
        """
        # Detect injection in user input
        result = self.injection_detector.detect_injection(
            user_input, context="user_input"
        )

        if result.blocked:
            logger.error("🚨 BLOCKED: User input contains injection patterns")
            logger.error("Patterns: %s", result.detected_patterns)
            raise ValueError(
                "User input blocked due to security policy violation: "
                f"{result.detected_patterns}"
            )

        # Return sanitized input
        return result.sanitized_text

    def _validate_conversation_context(self, conversation_context: List[Dict]) -> bool:
        """
        Validate conversation context for poisoning (Layer 1: Input Sanitization)

        Args:
            conversation_context: Conversation history to validate

        Returns:
            True if safe, raises ValueError if poisoned
        """
        # Convert conversation context to validation format
        history = []
        for entry in conversation_context:
            if entry.get("type") == "user_input":
                history.append({"user": entry.get("content", ""), "assistant": ""})
            elif entry.get("type") == "processed_goal":
                if history:
                    history[-1]["assistant"] = str(entry.get("content", ""))

        # Validate with injection detector
        is_safe = self.injection_detector.validate_conversation_context(history)

        if not is_safe:
            logger.error("🚨 BLOCKED: Conversation context poisoning detected")
            raise ValueError("Conversation context contains malicious patterns")

        return True

    def _secure_parse_llm_commands(
        self, llm_response: str, user_goal: str
    ) -> List[Dict[str, str]]:
        """
        Securely parse commands from LLM response (Layer 2: Output Parsing)

        REPLACES: _parse_llm_commands() method in IntelligentAgent

        Args:
            llm_response: LLM response text
            user_goal: Original user goal

        Returns:
            List of validated command dictionaries
        """
        # Use secure parser with validation
        validated_commands = self.secure_parser.parse_commands(llm_response, user_goal)

        # Convert ValidatedCommand objects to dict format
        command_dicts = []
        for validated in validated_commands:
            command_dicts.append(
                {
                    "command": validated.command,
                    "explanation": validated.explanation,
                    "next": validated.next_step,
                    "risk_level": validated.risk_level.value,
                    "validation_metadata": validated.validation_metadata,
                }
            )

        logger.info("✅ Securely parsed %s commands from LLM response", len(command_dicts))

        return command_dicts

    async def _secure_execute_command(
        self, command: str, user_goal: str, user_role: str = "agent"
    ) -> Dict:
        """
        Execute command with security validation (Layer 4: Execution Safeguards)

        Integrates with SecureCommandExecutor and EnhancedSecurityLayer

        Args:
            command: Command to execute
            user_goal: Original user goal for context
            user_role: Role of the user/agent executing the command

        Returns:
            Execution result with security metadata
        """
        logger.info("Executing command with security validation: %s", command)

        # Execute through enhanced security layer
        result = await self.security_layer.execute_command(
            command=command, user="intelligent_agent", user_role=user_role
        )

        # Add audit logging
        self.security_layer.audit_log(
            action="intelligent_agent_command_execution",
            user="intelligent_agent",
            outcome=result.get("status", "unknown"),
            details={
                "command": command,
                "user_goal": user_goal,
                "return_code": result.get("return_code"),
                "security": result.get("security", {}),
            },
        )

        return result


# PATCH INSTRUCTIONS for src/intelligence/intelligent_agent.py
PATCH_INSTRUCTIONS = """
=== SECURITY PATCH INSTALLATION INSTRUCTIONS ===

1. BACKUP ORIGINAL FILE:
   cp src/intelligence/intelligent_agent.py src/intelligence/intelligent_agent.py.backup

2. ADD SECURITY IMPORTS (at top of file, after existing imports):

   from src.security.prompt_injection_detector import get_prompt_injection_detector, InjectionRisk
   from src.security.secure_llm_command_parser import get_secure_llm_parser
   from src.enhanced_security_layer import EnhancedSecurityLayer

3. INITIALIZE SECURITY IN __init__ (add to IntelligentAgent.__init__):

   # Security components (CVE-AUTOBOT-2025-002 fix)
   self.injection_detector = get_prompt_injection_detector(strict_mode=True)
   self.secure_parser = get_secure_llm_parser(strict_mode=True)
   self.security_layer = EnhancedSecurityLayer()
   logger.info("✅ Security components initialized")

4. SANITIZE USER INPUT (in process_natural_language_goal method, line ~194):

   # BEFORE:
   logger.info("Processing natural language goal: %s", user_input)

   # AFTER:
   # Layer 1: Sanitize user input for injection attempts
   try:
       result = self.injection_detector.detect_injection(user_input, context="user_input")
       if result.blocked:
           yield StreamChunk(
               timestamp=self._get_timestamp(),
               chunk_type=ChunkType.ERROR,
               content=f"🚨 Security Policy Violation: {result.detected_patterns}",
               metadata={"security_blocked": True, "patterns": result.detected_patterns}
           )
           return
       user_input = result.sanitized_text
   except Exception as e:
       logger.error("Security validation error: %s", e)
       yield StreamChunk(
           timestamp=self._get_timestamp(),
           chunk_type=ChunkType.ERROR,
           content=f"❌ Security validation failed: {str(e)}",
           metadata={"security_error": True}
       )
       return

   logger.info("Processing sanitized goal: %s", user_input)

5. VALIDATE CONVERSATION CONTEXT (in process_natural_language_goal, before adding to context):

   # BEFORE: (line ~197)
   self.state.conversation_context.append({...})

   # AFTER:
   # Validate conversation context for poisoning
   try:
       history = [{"user": msg.get("content", ""), "assistant": ""}
                  for msg in self.state.conversation_context
                  if msg.get("type") == "user_input"]
       is_safe = self.injection_detector.validate_conversation_context(history)
       if not is_safe:
           yield StreamChunk(
               timestamp=self._get_timestamp(),
               chunk_type=ChunkType.ERROR,
               content="🚨 Conversation context poisoning detected",
               metadata={"context_poisoning": True}
           )
           return
   except Exception as e:
       logger.warning("Context validation warning: %s", e)

   self.state.conversation_context.append({...})

6. REPLACE _parse_llm_commands METHOD (entire method replacement, lines ~608-636):

   def _parse_llm_commands(self, llm_response: str, user_goal: str = "") -> List[Dict[str, str]]:
       '''
       Securely parse commands from LLM response with injection protection

       SECURITY FIX: Now uses SecureLLMCommandParser for validation
       '''
       # Use secure parser instead of naive string parsing
       validated_commands = self.secure_parser.parse_commands(llm_response, user_goal)

       # Convert ValidatedCommand objects to dict format
       command_dicts = []
       for validated in validated_commands:
           command_dicts.append({
               "command": validated.command,
               "explanation": validated.explanation,
               "next": validated.next_step,
               "risk_level": validated.risk_level.value,
               "validation_metadata": validated.validation_metadata
           })

       logger.info("✅ Securely parsed %s commands", len(command_dicts))
       return command_dicts

7. UPDATE _handle_complex_goal (line ~446 - add user_goal parameter):

   # BEFORE:
   commands = self._parse_llm_commands(llm_response)

   # AFTER:
   commands = self._parse_llm_commands(llm_response, user_goal=user_input)

8. ADD SECURITY AUDIT LOGGING (in _handle_complex_goal, after command execution):

   # After command execution loop (around line ~472)
   # Log security event for audit
   self.security_layer.audit_log(
       action="intelligent_agent_complex_goal",
       user="intelligent_agent",
       outcome="completed",
       details={
           "user_goal": user_input,
           "commands_extracted": len(commands),
           "commands_executed": executed_count
       }
   )

9. TEST THE PATCH:

   python tests/test_prompt_injection_protection.py

10. VERIFY SECURITY:

    - Test with injection attack scenarios
    - Verify all attacks are blocked
    - Check audit logs for security events
    - Validate command approval workflow

=== END OF PATCH INSTRUCTIONS ===
"""


def generate_patch_file():
    """Generate a diff-style patch file for the intelligent agent"""
    logger.debug("%s", PATCH_INSTRUCTIONS)


if __name__ == "__main__":
    """Generate patch instructions"""
    generate_patch_file()
