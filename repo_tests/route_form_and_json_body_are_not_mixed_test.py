# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No route mixes a ``Form`` field with a JSON body parameter (#15527).

One ``Form(...)`` default makes FastAPI read the **whole** request body as
``application/x-www-form-urlencoded``, and a form field always arrives as a
string. A parameter annotated ``dict`` or a Pydantic model in the same
signature therefore can never validate: the operation is published with a
body no client can construct, and every call answers 422 whatever it sends.

``POST /api/agent/execute_command`` shipped in that state --
``command_data: dict`` beside ``user_role: str = Form("user")`` -- and both
SDKs targeted it, so neither could be corrected client-side. This guard is
the class, not the instance: a form-only route is fine, a JSON-only route is
fine, the mixture is the defect.

Precision notes, all measured rather than assumed:

* a scalar parameter with no marker is a **query** parameter to FastAPI, not
  a body one, so only complex annotations count (``dict``, ``list``, their
  typing spellings, and model classes);
* a parameter whose name appears as ``{placeholder}`` in the decorator's path
  is a **path** parameter -- ``chat_id`` on ``/files/upload/{chat_id}``;
* markers reached through ``Annotated[T, Depends(...)]`` count as markers,
  which is how ``upload_package`` declares its session and current user.

Without those three, the sweep reports 4 hits on this tree instead of 0 --
``chat_knowledge.upload_file_to_chat``, ``conversation_files``
``.upload_conversation_file`` and ``code_source.upload_package`` are all
correct code.
"""

from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PACKAGES = ("autobot-backend", "autobot-slm-backend", "autobot_shared")

_VERBS = {"get", "post", "put", "patch", "delete", "head", "options"}
_MARKERS = {"Body", "Cookie", "Depends", "File", "Form", "Header", "Path", "Query", "Security"}
_NON_BODY = {"Request", "Response", "BackgroundTasks", "WebSocket", "UploadFile", "AsyncSession", "Session"}
_SCALARS = {"str", "int", "float", "bool", "bytes", "UUID", "Decimal", "datetime", "date", "time"}
_COMPLEX_BUILTINS = {"dict", "list", "Dict", "List", "Mapping", "Any"}

# Floors, measured on Dev_new_gui: 2791 route handlers, 24 of them carrying a
# ``Form`` field. Lower only when the tree genuinely holds fewer -- never to
# make a red run pass. The second floor is the load-bearing one: an extractor
# that stops recognising ``Form`` reports zero mixtures and reads clean.
_ROUTE_FLOOR = 2400
_FORM_ROUTE_FLOOR = 20


def _marker_of(default: ast.expr | None, annotation: ast.expr | None) -> str | None:
    """Name of the FastAPI marker on a parameter, from its default or ``Annotated``."""
    candidates: list[ast.expr] = [default] if default is not None else []
    if isinstance(annotation, ast.Subscript) and getattr(annotation.value, "id", "") == "Annotated":
        inner = annotation.slice
        candidates += list(inner.elts[1:]) if isinstance(inner, ast.Tuple) else []
    for candidate in candidates:
        if isinstance(candidate, ast.Call) and isinstance(candidate.func, ast.Name):
            if candidate.func.id in _MARKERS:
                return candidate.func.id
    return None


def _is_body_annotation(annotation: ast.expr | None) -> bool:
    """True when FastAPI would read this annotation out of the request body."""
    if annotation is None:
        return False
    if isinstance(annotation, ast.Subscript):
        head = getattr(annotation.value, "id", None)
        return head in _COMPLEX_BUILTINS
    if isinstance(annotation, ast.Name):
        name = annotation.id
        if name in _COMPLEX_BUILTINS:
            return True
        return name[:1].isupper() and name not in _NON_BODY and name not in _SCALARS
    return False


def _route_paths(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str] | None:
    """Path literals of the HTTP-verb decorators on *node*, or None if it is not a route."""
    paths: list[str] = []
    for decorator in node.decorator_list:
        call = decorator if isinstance(decorator, ast.Call) else None
        func = call.func if call is not None else decorator
        if not isinstance(func, ast.Attribute) or func.attr not in _VERBS:
            continue
        first = call.args[0] if call is not None and call.args else None
        paths.append(first.value if isinstance(first, ast.Constant) and isinstance(first.value, str) else "")
    return paths or None


def _classify(node: ast.FunctionDef | ast.AsyncFunctionDef, paths: list[str]) -> tuple[list[str], list[str]]:
    """Return the ``Form`` field names and the JSON body parameter names of one route."""
    placeholders = {segment.strip("{}") for path in paths for segment in path.split("/") if segment.startswith("{")}
    args = node.args.args + node.args.kwonlyargs
    defaults: list[ast.expr | None] = [None] * (len(node.args.args) - len(node.args.defaults))
    defaults += list(node.args.defaults) + list(node.args.kw_defaults)
    forms, bodies = [], []
    for arg, default in zip(args, defaults):
        marker = _marker_of(default, arg.annotation)
        if marker == "Form":
            forms.append(arg.arg)
        elif marker is None and arg.arg not in placeholders and _is_body_annotation(arg.annotation):
            bodies.append(arg.arg)
    return forms, bodies


def _scan_source(source: str, label: str) -> tuple[int, int, list[str]]:
    """Return (routes, form routes, mixed findings) for one module's source text."""
    routes = form_routes = 0
    findings: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        paths = _route_paths(node)
        if paths is None:
            continue
        routes += 1
        forms, bodies = _classify(node, paths)
        if forms:
            form_routes += 1
        if forms and bodies:
            findings.append(f"{label}:{node.lineno} {node.name} Form={sorted(forms)} body={sorted(bodies)}")
    return routes, form_routes, findings


@lru_cache(maxsize=None)
def _sweep() -> tuple[int, int, tuple[str, ...]]:
    """Every route handler in the two backends and the shared package."""
    routes = form_routes = 0
    findings: list[str] = []
    for package in _PACKAGES:
        for module in sorted((_REPO_ROOT / package).rglob("*.py")):
            try:
                source = module.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            try:
                counted, formed, found = _scan_source(source, module.relative_to(_REPO_ROOT).as_posix())
            except SyntaxError:
                continue
            routes += counted
            form_routes += formed
            findings += found
    return routes, form_routes, tuple(sorted(findings))


def _assert_population_floor() -> tuple[int, int, tuple[str, ...]]:
    """Guard the sweep itself: a collapsed population must fail by name."""
    routes, form_routes, findings = _sweep()
    assert routes >= _ROUTE_FLOOR, (
        f"FIX THE SWEEP: found only {routes} route handlers, floor is {_ROUTE_FLOOR}. "
        "The decorator matcher stopped matching, so a clean result here means nothing."
    )
    assert form_routes >= _FORM_ROUTE_FLOOR, (
        f"FIX THE SWEEP: found only {form_routes} routes declaring a Form field, floor is "
        f"{_FORM_ROUTE_FLOOR}. Nothing is being compared, so a clean result here means nothing."
    )
    return routes, form_routes, findings


def test_the_sweep_still_resolves_a_population_worth_asserting_on() -> None:
    """The floors fire on their own, so a collapsed sweep is named rather than green."""
    routes, form_routes, _ = _assert_population_floor()
    assert routes >= _ROUTE_FLOOR and form_routes >= _FORM_ROUTE_FLOOR


def test_the_extractor_sees_form_in_the_source_it_reads() -> None:
    """The token matched is one the subject actually emits.

    ``pause_agent_api`` and ``resume_agent_api`` in ``autobot-backend/api/agent.py``
    declare ``user_role: str = Form("user")`` and nothing else form-like, so a
    matcher that has drifted off the real spelling loses them by name here
    rather than silently reporting zero mixtures everywhere.
    """
    source = (_REPO_ROOT / "autobot-backend" / "api" / "agent.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    seen = {
        node.name: _classify(node, _route_paths(node) or [])[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _route_paths(node) is not None
    }
    assert seen.get("pause_agent_api") == ["user_role"], seen.get("pause_agent_api")
    assert seen.get("resume_agent_api") == ["user_role"], seen.get("resume_agent_api")


def test_no_route_mixes_a_form_field_with_a_json_body_parameter() -> None:
    """The substantive assertion -- evaluated only after the floors hold."""
    _, _, findings = _assert_population_floor()
    assert not findings, (
        "These routes declare a Form field beside a JSON body parameter, which FastAPI "
        "publishes as a form-encoded operation whose body no client can satisfy:\n"
        + "\n".join(f"  {finding}" for finding in findings)
        + "\n\nPut the fields in one request model, or make every field a Form field."
    )


_MIXED = """
@router.post("/execute_command")
async def execute_command(request: Request, command_data: dict, user_role: str = Form("user")):
    return {}
"""

_FIXED = """
@router.post("/execute_command")
async def execute_command(request: Request, payload: CommandExecutePayload):
    return {}
"""

_FORM_ONLY_UPLOAD = """
@router.post("/files/upload/{chat_id}")
async def upload_file_to_chat(chat_id: str, request: Request, file: UploadFile = File(...),
                              association_type: str = Form(default="upload")):
    return {}
"""

_ANNOTATED_DEPENDS = """
@router.post("/upload-package")
async def upload_package(db: Annotated[AsyncSession, Depends(get_db)],
                         _: Annotated[dict, Depends(get_current_user)], role_name: str = Form(...)):
    return {}
"""


def test_the_guard_flags_a_route_that_mixes_form_and_a_body_parameter() -> None:
    """The contrast mutation, run on source text so no real file is edited."""
    _, form_routes, findings = _scan_source(_MIXED, "probe.py")
    assert form_routes == 1
    assert len(findings) == 1 and "command_data" in findings[0], findings


def test_the_guard_passes_the_shape_that_replaced_it() -> None:
    """The same route with one request model is clean -- the fix is what silences it."""
    assert _scan_source(_FIXED, "probe.py")[2] == []


def test_a_path_parameter_beside_a_form_field_is_not_a_finding() -> None:
    """``chat_id`` is a path parameter, not a body one; flagging it is a false positive."""
    routes, form_routes, findings = _scan_source(_FORM_ONLY_UPLOAD, "probe.py")
    assert (routes, form_routes) == (1, 1)
    assert findings == []


def test_an_annotated_depends_parameter_is_not_a_body_parameter() -> None:
    """A marker reached through ``Annotated`` is still a marker."""
    assert _scan_source(_ANNOTATED_DEPENDS, "probe.py")[2] == []
