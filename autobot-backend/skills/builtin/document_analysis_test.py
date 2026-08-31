# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""DocumentAnalysisSkill guards (#13897).

Every handler used to return ``{"success": True, "status": "queued"}`` against no
queue, no worker and no consumer. The skill is **registered and reachable** —
``discover_builtin_skills()`` finds it by module scan, so it is routable with no
textual reference anywhere to grep for — which made the fabricated success worse
than dead code: a live surface reporting work it never did.

The invariant these tests exist to hold is therefore not "the handlers call the
extractor" but the stricter one: **no handler reports success for work that did
not happen.**
"""

import io

import pytest

from skills.builtin.document_analysis import DocumentAnalysisSkill  # nosemgrep: skill-no-sibling-import


def _write_pdf(tmp_path, pages: list, name: str = "doc.pdf"):
    """Write a real PDF; ``None`` draws an image-only (scanned) page.

    Each text page is padded to comfortably clear ``DEFAULT_MIN_CHARS_PER_PAGE``
    (50). A page carrying three characters is, correctly, treated as a
    page-number stamp rather than content (#13884) — fixtures that ignore that
    would be testing against documents the extractor is designed to reject.
    """
    pytest.importorskip("reportlab", reason="reportlab needed to synthesize PDF fixtures")
    from reportlab.pdfgen import canvas

    filler = " Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor."

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    for entry in pages:
        if entry is None:
            from PIL import Image
            from reportlab.lib.utils import ImageReader

            pdf.drawImage(ImageReader(Image.new("RGB", (600, 800), "white")), 0, 0, width=400, height=500)
        else:
            pdf.drawString(72, 720, entry)
            pdf.drawString(72, 700, filler)
        pdf.showPage()
    pdf.save()

    path = tmp_path / name
    path.write_bytes(buffer.getvalue())
    return path


@pytest.fixture
def skill():
    return DocumentAnalysisSkill()


@pytest.fixture(autouse=True)
def _scope_allowed_roots_to_tmp_path(monkeypatch, tmp_path):
    """Fixtures below write real documents under ``tmp_path``, exercising the
    skill directly rather than through the real upload flow (which always
    writes under the project's file-manager root and is what production
    scopes ``allowed_roots`` to, #15238). Scope this test run's root to
    ``tmp_path`` instead of loosening the real default.
    """
    monkeypatch.setattr("skills.builtin.document_analysis.PROJECT_ALLOWED_ROOTS", (str(tmp_path),))


# ---------------------------------------------------------------------------
# The invariant
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["analyze_document", "extract_text", "summarize_document"])
async def test_no_handler_fabricates_a_queued_success(skill, tmp_path, action):
    """The exact regression: success:True with status:queued against no queue."""
    path = _write_pdf(tmp_path, ["real content"])
    result = await skill.execute(action, {"file_path": str(path)})

    assert result.get("status") != "queued", "no queue exists; claiming one is a fabricated success"
    if result.get("success"):
        assert "message" not in result or "queued" not in result["message"].lower()


@pytest.mark.asyncio
async def test_missing_file_reports_failure_not_success(skill, tmp_path):
    result = await skill.execute("extract_text", {"file_path": str(tmp_path / "absent.pdf")})
    assert result["success"] is False
    assert "Cannot read file" in result["error"]


@pytest.mark.asyncio
async def test_missing_file_path_is_rejected(skill):
    result = await skill.execute("analyze_document", {})
    assert result["success"] is False
    assert "file_path is required" in result["error"]


@pytest.mark.asyncio
async def test_unknown_action_is_rejected(skill):
    result = await skill.execute("not_a_tool", {"file_path": "/tmp/x.pdf"})
    assert result["success"] is False


# ---------------------------------------------------------------------------
# Real extraction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_text_returns_the_document_body(skill, tmp_path):
    path = _write_pdf(tmp_path, ["alpha content", "beta content"])
    result = await skill.execute("extract_text", {"file_path": str(path)})

    assert result["success"] is True
    assert "alpha content" in result["content"]
    assert "beta content" in result["content"]
    assert result["pages_read"] == 2


@pytest.mark.asyncio
async def test_analyze_reports_real_structure(skill, tmp_path):
    path = _write_pdf(tmp_path, ["one", "two", "three"])
    result = await skill.execute("analyze_document", {"file_path": str(path)})

    assert result["success"] is True
    assert result["format"] == "pdf"
    assert result["page_count"] == 3
    assert result["char_count"] > 0


# ---------------------------------------------------------------------------
# Config that previously changed nothing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_max_pages_actually_truncates(skill, tmp_path):
    path = _write_pdf(tmp_path, ["page one", "page two", "page three"])
    skill.apply_config({"max_pages": 2})
    result = await skill.execute("extract_text", {"file_path": str(path)})

    assert result["pages_read"] == 2
    assert result["truncated"] is True
    assert "page three" not in result["content"]


@pytest.mark.asyncio
async def test_max_pages_does_not_truncate_when_it_need_not(skill, tmp_path):
    path = _write_pdf(tmp_path, ["only page"])
    skill.apply_config({"max_pages": 100})
    result = await skill.execute("extract_text", {"file_path": str(path)})

    assert result["truncated"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "output_format,expect_markers",
    [("markdown", True), ("plain", False)],
)
async def test_output_format_changes_the_rendering(skill, tmp_path, output_format, expect_markers):
    path = _write_pdf(tmp_path, ["body text"])
    skill.apply_config({"output_format": output_format})
    result = await skill.execute("extract_text", {"file_path": str(path)})

    assert ("## Page" in result["content"]) is expect_markers
    assert "body text" in result["content"]


@pytest.mark.asyncio
async def test_json_output_format_returns_structured_pages(skill, tmp_path):
    path = _write_pdf(tmp_path, ["first", "second"])
    skill.apply_config({"output_format": "json"})
    result = await skill.execute("extract_text", {"file_path": str(path)})

    pages = result["content"]["pages"]
    assert [p["page"] for p in pages] == [1, 2]
    assert "first" in pages[0]["text"]


# ---------------------------------------------------------------------------
# Scanned documents and the OCR flag
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scanned_document_fails_rather_than_returning_empty_success(skill, tmp_path):
    pytest.importorskip("PIL", reason="Pillow needed for image-only pages")
    path = _write_pdf(tmp_path, [None])
    result = await skill.execute("extract_text", {"file_path": str(path)})

    assert result["success"] is False
    assert "scanned" in result["error"].lower() or "OCR" in result["error"]
    assert result["empty_pages"] == [1]


@pytest.mark.asyncio
async def test_ocr_enabled_changes_the_reported_reason(skill, tmp_path):
    """The flag defaulted True while no OCR existed; now it must mean something."""
    pytest.importorskip("PIL", reason="Pillow needed for image-only pages")
    path = _write_pdf(tmp_path, [None])

    skill.apply_config({"ocr_enabled": False})
    without = await skill.execute("extract_text", {"file_path": str(path)})

    skill.apply_config({"ocr_enabled": True})
    with_ocr = await skill.execute("extract_text", {"file_path": str(path)})

    assert without["error"] != with_ocr["error"]
    assert "not available" in with_ocr["error"]


def test_ocr_enabled_no_longer_defaults_to_true():
    """Advertising OCR-on while no OCR backend exists is the false claim."""
    manifest = DocumentAnalysisSkill.get_manifest()
    assert manifest.config["ocr_enabled"].default is False


# ---------------------------------------------------------------------------
# Path handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_path_outside_allowed_roots_is_rejected_before_any_read(skill):
    """Confinement, not a ".." denylist — see #14050 on why the denylist is wrong."""
    result = await skill.execute("extract_text", {"file_path": "../../etc/passwd"})
    assert result["success"] is False
    assert "Invalid file_path" in result["error"]


@pytest.mark.asyncio
async def test_absolute_path_outside_allowed_roots_is_rejected(skill):
    """A path with no ".." in it at all must still be confined."""
    result = await skill.execute("extract_text", {"file_path": "/etc/hosts.txt"})
    assert result["success"] is False
    assert "Invalid file_path" in result["error"]


@pytest.mark.asyncio
async def test_unsupported_extension_is_rejected(skill, tmp_path):
    path = tmp_path / "binary.exe"
    path.write_bytes(b"\x00\x01")
    result = await skill.execute("extract_text", {"file_path": str(path)})

    assert result["success"] is False
    assert "Unsupported format" in result["error"]


@pytest.mark.asyncio
async def test_plain_text_documents_are_supported(skill, tmp_path):
    path = tmp_path / "notes.md"
    path.write_text("# heading\n\nbody", encoding="utf-8")
    result = await skill.execute("extract_text", {"file_path": str(path)})

    assert result["success"] is True
    assert "body" in result["content"]
    assert result["pages_read"] is None, "unpaginated formats have no page count"


# ---------------------------------------------------------------------------
# Summarization: honest failure, not a fabricated success
# ---------------------------------------------------------------------------


def _stub_summarizer(monkeypatch, *, summary="a concise summary", raises=None, result=None):
    """Install a fake SummarizationAgent and capture what it was asked for."""
    import sys
    import types

    seen = {}

    class _Agent:
        async def handle_summarize(self, request):
            seen["payload"] = dict(request.payload)
            seen["action"] = request.action
            if raises:
                raise raises
            # #14541 review: the real `handle_summarize` always returns a
            # `status` discriminator. A stub that omits it agrees with the
            # reader and with nothing else, which is how both defects hid.
            return result if result is not None else {"status": "success", "summary": summary}

    base = types.ModuleType("agents.base_agent")

    class _AgentRequest:
        def __init__(self, request_id, agent_type, action, payload, **kw):
            self.request_id, self.agent_type = request_id, agent_type
            self.action, self.payload = action, payload

    base.AgentRequest = _AgentRequest

    agent_mod = types.ModuleType("agents.summarization_agent")
    agent_mod.get_summarization_agent = lambda: _Agent()

    pkg = sys.modules.get("agents") or types.ModuleType("agents")
    monkeypatch.setitem(sys.modules, "agents", pkg)
    monkeypatch.setitem(sys.modules, "agents.base_agent", base)
    monkeypatch.setitem(sys.modules, "agents.summarization_agent", agent_mod)
    return seen


@pytest.mark.asyncio
async def test_summarize_returns_a_real_summary(skill, tmp_path, monkeypatch):
    _stub_summarizer(monkeypatch, summary="the document in brief")
    path = _write_pdf(tmp_path, ["document body"])

    result = await skill.execute("summarize_document", {"file_path": str(path)})

    assert result["success"] is True
    assert result["summary"] == "the document in brief"


@pytest.mark.asyncio
async def test_summarize_sends_the_extracted_text_not_the_path(skill, tmp_path, monkeypatch):
    """The backend must receive document content, not a filename."""
    seen = _stub_summarizer(monkeypatch)
    path = _write_pdf(tmp_path, ["distinctive body text"])

    await skill.execute("summarize_document", {"file_path": str(path)})

    assert "distinctive body text" in seen["payload"]["text"]
    assert seen["action"] == "summarize"


@pytest.mark.asyncio
@pytest.mark.parametrize("max_length", ["short", "long"])
async def test_max_length_reaches_the_backend_and_the_result(skill, tmp_path, monkeypatch, max_length):
    """AC: max_length must change the output observably, not just be accepted."""
    seen = _stub_summarizer(monkeypatch)
    path = _write_pdf(tmp_path, ["body"])

    result = await skill.execute("summarize_document", {"file_path": str(path), "max_length": max_length})

    assert seen["payload"]["max_length"] == max_length
    assert result["max_length"] == max_length


@pytest.mark.asyncio
async def test_an_unavailable_backend_fails_rather_than_returning_the_text_as_a_summary(skill, tmp_path, monkeypatch):
    """The #13897 invariant: never success:True for work that did not happen."""
    import sys

    monkeypatch.setitem(sys.modules, "agents.summarization_agent", None)
    path = _write_pdf(tmp_path, ["document body"])

    result = await skill.execute("summarize_document", {"file_path": str(path)})

    assert result["success"] is False
    assert "summary" not in result, "returning raw text under a 'summary' key would be a lie"
    assert "document body" in result["extracted_text"]


@pytest.mark.asyncio
async def test_a_raising_backend_is_reported_not_swallowed(skill, tmp_path, monkeypatch):
    _stub_summarizer(monkeypatch, raises=RuntimeError("model timeout"))
    path = _write_pdf(tmp_path, ["body"])

    result = await skill.execute("summarize_document", {"file_path": str(path)})

    assert result["success"] is False
    assert "model timeout" in result["error"]


@pytest.mark.asyncio
async def test_an_empty_summary_is_a_failure_not_an_empty_success(skill, tmp_path, monkeypatch):
    """A backend that returns nothing has not summarized anything.

    The status says success and the text is blank — so this exercises the
    empty-text path specifically, rather than being rejected earlier by the
    discriminator. Without the status the result is unclassifiable and fails
    for a different reason, which would leave the empty-text branch untested.
    """
    _stub_summarizer(monkeypatch, result={"status": "success", "summary": "   "})
    path = _write_pdf(tmp_path, ["body"])

    result = await skill.execute("summarize_document", {"file_path": str(path)})

    assert result["success"] is False
    assert "no text" in result["error"].lower()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "shape",
    [
        {"status": "success", "response": "via response"},
        {"status": "success", "result": "via result"},
        {"status": "success", "text": "via text"},
    ],
)
async def test_summary_is_read_from_the_shapes_the_agent_may_return(skill, tmp_path, monkeypatch, shape):
    _stub_summarizer(monkeypatch, result=shape)
    path = _write_pdf(tmp_path, ["body"])

    result = await skill.execute("summarize_document", {"file_path": str(path)})

    assert result["success"] is True
    assert result["summary"]


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_skill_is_discoverable_by_the_registry():
    """Registration is by module scan — there is no reference to grep for."""
    from skills.registry import SkillRegistry

    registry = SkillRegistry()
    registry.discover_builtin_skills()
    assert "document-analysis" in registry._skills


# ---------------------------------------------------------------------------
# #14541 review: the status discriminator, and a test that meets the real agent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_agent_error_is_a_failure_not_a_summary(skill, tmp_path, monkeypatch):
    """The exact dict `BaseModalityAgent.process_query` returns on error.

    `process_query` does not re-raise — it returns `status: "error"` with the
    user-facing notice under `response`. That notice is a non-empty string, so
    a reader that walks the key-priority list without checking the status
    reports `success: True` with "Error generating summary. Please try again."
    presented as the document's summary. That is the #13897 failure mode.
    """
    notice = "Error generating summary. Please try again."
    _stub_summarizer(
        monkeypatch,
        result={
            "status": "error",
            "response": notice,
            "response_text": "connection refused",
            "agent_type": "summarization",
            "model_used": "a-model",
        },
    )
    path = _write_pdf(tmp_path, ["body"])

    result = await skill.execute("summarize_document", {"file_path": str(path)})

    assert result["success"] is False
    assert notice not in str(result.get("summary", "")), "the error notice must never be the summary"
    assert "summary" not in result, "a failed summarization must not report a summary at all"
    assert "connection refused" in result["error"], "the underlying cause belongs in the error"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("shape", "because"),
    [
        ({"summary": "no discriminator"}, "no status field"),
        ("a bare string", "unrecognised result type"),
        ({"status": "partial", "summary": "half done"}, "Summarization failed"),
    ],
)
async def test_a_result_that_cannot_be_classified_is_a_failure(skill, tmp_path, monkeypatch, shape, because):
    """An unrecognised shape is a failure, never a fall-through.

    A result this skill cannot classify is one it cannot vouch for. Accepting
    it because it happens to carry a plausible string is how the previous
    version turned an error into a summary.
    """
    _stub_summarizer(monkeypatch, result=shape)
    path = _write_pdf(tmp_path, ["body"])

    result = await skill.execute("summarize_document", {"file_path": str(path)})

    assert result["success"] is False
    assert because.lower() in result["error"].lower()


@pytest.mark.asyncio
async def test_the_real_agent_error_branch_produces_the_shape_this_skill_reads():
    """Drive the REAL `process_query`, mocking only the LLM boundary.

    Every other test here talks to a hand-written stub, so they can only prove
    the reader agrees with the stub. This one imports the real
    `SummarizationAgent` and runs the real `BaseModalityAgent.process_query`
    error path, then feeds its actual output through the skill's own
    classifier. If the agent's error contract ever changes shape, this fails
    here rather than silently downgrading a failure into a summary in
    production.

    `__new__` skips `__init__` deliberately: constructing the agent for real
    would pull in provider/endpoint/model config this test has no business
    depending on. The method under test is inherited and untouched by that.
    """
    # Imported directly, NOT via importorskip: this is the one test that meets
    # the real agent, so an environment where it cannot run must fail loudly
    # rather than skip back into the all-stubs state the review found.
    import agents.summarization_agent as agents_pkg  # nosemgrep: extension-no-core-internals

    agent = agents_pkg.SummarizationAgent.__new__(agents_pkg.SummarizationAgent)
    agent.model_name = "a-model"

    class _Boom:
        async def chat_optimized(self, *a, **kw):
            raise RuntimeError("connection refused")

    agent.llm_interface = _Boom()

    result = await agent.process_query("some document text")

    # The real contract, asserted rather than assumed.
    assert result["status"] == "error"
    assert result["response"] == agents_pkg.SummarizationAgent.QUERY_ERROR_MESSAGE
    assert result["response"].strip(), "the notice is non-empty, which is why status must be read first"

    # And the skill classifies that real output as a failure.
    failure = DocumentAnalysisSkill._agent_failure(result)
    assert failure, "the real agent's error result must be classified as a failure"
    assert "connection refused" in failure
