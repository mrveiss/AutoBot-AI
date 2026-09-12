# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every get_prompt_injection_detector() construction site agrees on strict_mode (#16561 AC4).

``get_prompt_injection_detector`` is a ``lazy_singleton`` (#16529/#16530):
the first call constructs and caches the instance; every later call with
*different* args raises ``RuntimeError`` at runtime. Nothing currently
disagrees, but nothing previously checked that mechanically either -- a
future call site passing ``strict_mode=False`` would only be caught the
moment both call orders actually collide in one running process, which
depends on which endpoint happens to run first.

Parsed, not grepped: a regex can't tell a real keyword argument from this
file's own docstring, and can't distinguish a literal from a value forwarded
through another constructor's own default (the one indirect site here,
``SecureLLMCommandParser``).
"""

from __future__ import annotations

import ast
import subprocess  # nosec B404  # fixed argv, no shell, no caller input
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare

from autobot_shared.paths import scrubbed_git_env

REPO_ROOT = repo_root()
_SCOPED_DIR = "autobot-backend"

#: Call sites that pass strict_mode as a forwarded name, not a literal --
#: each entry names the reason that name is known to resolve to True today.
#: A new indirect site not listed here fails the test until classified.
_KNOWN_INDIRECT_SITES = {
    "autobot-backend/security/secure_llm_command_parser.py": (
        "SecureLLMCommandParser.__init__ forwards its own strict_mode "
        "parameter, which defaults to True and whose one production "
        "instantiation site (same file) passes strict_mode=True explicitly "
        "-- see test_secure_llm_command_parser_forwards_true below."
    ),
}


def _tracked_backend_python_files(root: Path = REPO_ROOT) -> list[Path]:
    """Tracked ``.py`` files under the scoped dir, tests excluded.

    Takes a root so the declaration below can be driven against an empty
    directory by ``reach_declarations_test`` (#15826).
    """
    result = subprocess.run(  # nosec B603 B607
        ["git", "ls-files", "--", f"{_SCOPED_DIR}/*.py"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        env=scrubbed_git_env(),
    )
    return [root / line for line in result.stdout.splitlines() if line and not line.endswith("_test.py")]


def _strict_mode_calls(source: str) -> list[ast.expr]:
    """The ``strict_mode`` argument expression of every get_prompt_injection_detector(...) call.

    Checks both shapes: PromptInjectionDetector.__init__(self, strict_mode)
    has exactly one parameter, so a positional call's sole argument IS
    strict_mode -- security/secure_llm_command_parser.py:66 calls it exactly
    this way (get_prompt_injection_detector(strict_mode), not
    strict_mode=strict_mode). An earlier version of this guard checked
    node.keywords only and never saw that site at all: its
    _KNOWN_INDIRECT_SITES entry was dead, and a future positional False
    would have passed silently (#16567 review).
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    found = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            continue
        if node.func.id != "get_prompt_injection_detector":
            continue
        for kw in node.keywords:
            if kw.arg == "strict_mode":
                found.append(kw.value)
        if node.args:
            found.append(node.args[0])
    return found


#: Ratcheted well below the live population (3133 non-test files under
#: autobot-backend/ as of #16561) so ordinary churn never trips it, while
#: still catching a narrowed glob or a broken git env (#15826).
REACH = declare(
    "prompt-injection-detector-strict-mode",
    discover=_tracked_backend_python_files,
    floor=2900,
    growth=300,
    what="tracked backend python files (tests excluded)",
)


class TestStrictModeCallsDetection:
    """Unit coverage of the helper itself (#16567 review): the whole-tree scan
    below is only as good as this detection, and it previously missed
    positional calls entirely -- these fixtures pin both shapes directly,
    independent of what the real tree currently contains.
    """

    def test_detects_keyword_true(self):
        (value,) = _strict_mode_calls("get_prompt_injection_detector(strict_mode=True)")
        assert isinstance(value, ast.Constant) and value.value is True

    def test_detects_keyword_false(self):
        (value,) = _strict_mode_calls("get_prompt_injection_detector(strict_mode=False)")
        assert isinstance(value, ast.Constant) and value.value is False

    def test_detects_positional_true(self):
        """secure_llm_command_parser.py's exact shape: get_prompt_injection_detector(strict_mode)."""
        (value,) = _strict_mode_calls("get_prompt_injection_detector(strict_mode)")
        assert isinstance(value, ast.Name) and value.id == "strict_mode"

    def test_detects_positional_literal_false(self):
        """The regression this fixture exists for: a bare positional False must
        be seen, not silently pass through an untouched node.args."""
        (value,) = _strict_mode_calls("get_prompt_injection_detector(False)")
        assert isinstance(value, ast.Constant) and value.value is False

    def test_unrelated_calls_are_ignored(self):
        assert _strict_mode_calls("some_other_function(strict_mode=False)") == []


def test_every_construction_site_passes_strict_mode_true_or_a_known_forward():
    files = _tracked_backend_python_files()
    assert files, "discovered zero backend python files -- a broken git env or moved directory, not a clean repo"

    disagreements: dict[str, str] = {}
    call_sites_found = 0
    for path in files:
        calls = _strict_mode_calls(path.read_text(encoding="utf-8"))
        if not calls:
            continue
        rel = str(path.relative_to(REPO_ROOT))
        for value in calls:
            call_sites_found += 1
            if isinstance(value, ast.Constant) and value.value is True:
                continue
            if rel in _KNOWN_INDIRECT_SITES:
                continue
            disagreements[rel] = ast.dump(value)

    assert (
        call_sites_found > 0
    ), "found zero get_prompt_injection_detector(strict_mode=...) call sites -- did the API change?"
    assert not disagreements, (
        f"{disagreements} call get_prompt_injection_detector with a strict_mode that is neither a literal "
        "True nor a known forwarded name (see _KNOWN_INDIRECT_SITES) -- the lazy_singleton raises RuntimeError "
        "the moment two disagreeing construction orders collide in one process; classify or fix this site (#16561)"
    )


def test_secure_llm_command_parser_forwards_true():
    """The one indirect site named in _KNOWN_INDIRECT_SITES: verified, not assumed."""
    import inspect

    from security.secure_llm_command_parser import SecureLLMCommandParser

    sig = inspect.signature(SecureLLMCommandParser.__init__)
    assert sig.parameters["strict_mode"].default is True, (
        "SecureLLMCommandParser.__init__'s strict_mode default changed from True -- "
        "_KNOWN_INDIRECT_SITES's justification for this file no longer holds"
    )

    source = Path(inspect.getfile(SecureLLMCommandParser)).read_text(encoding="utf-8")
    instantiations = [
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "SecureLLMCommandParser"
    ]
    assert len(instantiations) == 1, (
        f"expected exactly one SecureLLMCommandParser(...) instantiation site, found {len(instantiations)} -- "
        "_KNOWN_INDIRECT_SITES's claim of 'exactly one production instantiation site' needs re-verifying"
    )
    kwargs = {kw.arg: kw.value for kw in instantiations[0].keywords}
    assert (
        "strict_mode" in kwargs
        and isinstance(kwargs["strict_mode"], ast.Constant)
        and kwargs["strict_mode"].value is True
    ), "the one SecureLLMCommandParser(...) instantiation no longer passes strict_mode=True explicitly"
