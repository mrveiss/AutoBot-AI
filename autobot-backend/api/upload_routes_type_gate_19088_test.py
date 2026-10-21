# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Every UploadFile route refuses a disallowed name with a 4xx, and its real callers still pass (#19088).

Rejection tests call the route handler itself, so they fail if the gate is
removed from the route. Acceptance tests use the file names the in-repo
callers actually send, against the same allow-list constant the route imports.
"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import archive_safety
import plugin_install
from api import chat_knowledge, multimodal, voice
from autobot_shared.security import upload_filename_policy as policy
from llc.api import agent_api, work_items
from transcriber.routes import recordings


class FakeUpload:
    def __init__(self, filename, content_type="application/octet-stream", data=b"x"):
        self.filename = filename
        self.content_type = content_type
        self._data = data

    async def read(self, size=-1):
        data, self._data = self._data, b""
        return data


def _unwrap(fn):
    return getattr(fn, "__wrapped__", fn)


async def _refused(coro):
    with pytest.raises(HTTPException) as info:
        await coro
    assert 400 <= info.value.status_code < 500
    return info.value


BAD = ["payload.exe", "a/b.txt", "..\\x.txt", "noextension", "tool.msi", ""]
BAD_AUDIO = BAD + ["notes.txt", "evil.sh"]
BAD_IMAGE = BAD + ["x.wav", "page.html"]
BAD_ZIP = BAD + ["x.tar.gz", "x.txt"]


def _security_request():
    layer = SimpleNamespace(check_permission=lambda *a, **k: True, audit_log=lambda *a, **k: None)
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(security_layer=layer)))


@pytest.mark.asyncio
@pytest.mark.parametrize("name", BAD)
async def test_chat_knowledge_upload_refuses_a_bad_name(name):
    await _refused(_unwrap(chat_knowledge.upload_file_to_chat)("c1", SimpleNamespace(), FakeUpload(name), "upload"))


@pytest.mark.asyncio
@pytest.mark.parametrize("name", BAD_IMAGE)
async def test_multimodal_image_refuses_a_bad_name(name):
    await _refused(_unwrap(multimodal.process_image)(FakeUpload(name, "image/png"), "analysis", None, {"user_id": "u"}))


@pytest.mark.asyncio
@pytest.mark.parametrize("name", BAD_AUDIO)
async def test_multimodal_audio_refuses_a_bad_name(name):
    await _refused(_unwrap(multimodal.process_audio)(FakeUpload(name, "audio/wav"), "voice_command", {"user_id": "u"}))


@pytest.mark.asyncio
async def test_multimodal_combine_refuses_a_bad_image_and_a_bad_audio_name():
    for kwargs in ({"image_file": FakeUpload("x.exe", "image/png")}, {"audio_file": FakeUpload("x.txt", "audio/wav")}):
        await _refused(
            multimodal._collect_modal_inputs(None, kwargs.get("image_file"), kwargs.get("audio_file"), "x", "u")
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("name", BAD_AUDIO)
async def test_voice_routes_refuse_a_bad_name(name):
    req = _security_request()
    await _refused(_unwrap(voice.voice_clone_api)(req, "hello", FakeUpload(name), "user"))
    await _refused(_unwrap(voice.voice_create_api)("v", FakeUpload(name)))
    await _refused(_unwrap(voice.voice_transcribe_api)(req, FakeUpload(name), ""))


@pytest.mark.asyncio
@pytest.mark.parametrize("name", BAD)
async def test_agent_attachment_refuses_a_bad_name(name, monkeypatch):
    monkeypatch.setattr(agent_api, "agent_context", lambda request: ("agent", "company"))
    await _refused(agent_api.agent_upload_attachment("w1", FakeUpload(name), SimpleNamespace()))


@pytest.mark.asyncio
@pytest.mark.parametrize("name", BAD)
async def test_work_item_attachment_refuses_a_bad_name(name, monkeypatch):
    async def get(session, work_item_id):
        return SimpleNamespace(company_id="org")

    monkeypatch.setattr(work_items, "_service", lambda: SimpleNamespace(get=get))
    ctx = SimpleNamespace(org_id="org")
    await _refused(
        work_items.upload_attachment("w1", "org", FakeUpload(name), None, None, session=None, _current_user={}, ctx=ctx)
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("name", BAD_AUDIO)
async def test_transcriber_recording_refuses_a_bad_name(name, monkeypatch):
    async def get_project(project_id):
        return {"id": project_id}

    monkeypatch.setattr(recordings, "caller_can_access", lambda project, request: True)
    await _refused(
        recordings.upload_recording(1, SimpleNamespace(), FakeUpload(name), SimpleNamespace(get_project=get_project))
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("name", BAD_ZIP)
async def test_archive_stream_refuses_a_bad_name(name, tmp_path):
    await _refused(archive_safety.stream_upload_to(FakeUpload(name), tmp_path / "u.zip"))
    assert not (tmp_path / "u.zip").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("name", BAD_ZIP)
async def test_plugin_install_refuses_a_bad_name(name):
    await _refused(plugin_install.install_from_zip(FakeUpload(name)))


@pytest.mark.asyncio
@pytest.mark.parametrize("name", BAD_ZIP)
async def test_theme_install_refuses_a_bad_name(name):
    import theme_install

    await _refused(theme_install.install_theme_from_zip(FakeUpload(name)))


# Real callers: (caller, allow-list the route uses, names that caller actually sends).
LEGITIMATE = [
    # autobot-frontend/src/composables/useVoiceConversation.ts:648 -- blob named speech.wav (voice/transcribe)
    ("voice transcribe", policy.AUDIO_EXTENSIONS, ["speech.wav"]),
    # autobot-frontend/src/composables/useVoiceProfiles.ts:123 via VoiceSettingsPanel.vue:221 -- recording.webm or a picked audio/* file
    ("voice create", policy.AUDIO_EXTENSIONS, ["recording.webm", "ref.wav", "me.mp3", "me.m4a", "me.ogg", "me.flac"]),
    # autobot-frontend/src/components/transcriber/UploadModal.vue:20 ACCEPT list
    (
        "transcriber recordings",
        policy.AUDIO_EXTENSIONS,
        [f"talk{e}" for e in (".wav", ".mp3", ".mp4", ".m4a", ".ogg", ".flac", ".webm")],
    ),
    # autobot-frontend/src/components/chat/VisionAnalysisModal.vue:186 accept list; vision/VideoProcessor.vue:339 frame_N.jpg
    ("multimodal image", policy.IMAGE_EXTENSIONS, ["a.png", "a.jpg", "a.jpeg", "a.webp", "a.gif", "frame_0.jpg"]),
    # autobot-frontend/src/composables/usePlugins.ts:216 / views/slm/ThemeManagerView.vue:73 (accept=".zip")
    ("plugin and theme zip", policy.ZIP_EXTENSIONS, ["my-plugin.zip", "theme.ZIP"]),
    # autobot-slm-backend/api/code_source.py:upload_package -- ".tar.gz or .tgz" role packages
    ("slm role package", policy.TARBALL_EXTENSIONS, ["autobot-slm-backend-abc123.tar.gz", "role.tgz"]),
    # work item attachments (default document list)
    ("llc attachments", policy.ALLOWED_EXTENSIONS, ["spec.pdf", "log.txt", "shot.png", "data.csv"]),
]


@pytest.mark.parametrize("caller,allowed,names", LEGITIMATE, ids=[c[0] for c in LEGITIMATE])
def test_the_real_files_each_caller_sends_pass_its_allow_list(caller, allowed, names):
    for name in names:
        assert policy.is_safe_file(name, allowed) is True, (caller, name)
        assert policy.require_safe_upload(name, allowed) == name


@pytest.mark.asyncio
async def test_a_real_wav_clears_the_voice_gate_and_reaches_the_audio_read(monkeypatch):
    class Reached(Exception):
        pass

    async def stop(upload):
        raise Reached

    import media.audio.upload_limits as limits

    monkeypatch.setattr(limits, "read_capped_audio", stop)
    with pytest.raises(Reached):
        await _unwrap(voice.voice_transcribe_api)(_security_request(), FakeUpload("speech.wav"), "")


# What the frontend producers really name their audio (#19088 follow-up):
#   useVoiceConversation.ts:648/668   -> "speech.wav" (also for the webm/opus fallback recorder's blob)
#   VoiceSettingsPanel.vue:221        -> "recording.webm" (MediaRecorder blob, every browser), or the picked file's own name
#   UploadModal.vue:20 ACCEPT         -> wav mp3 mp4 m4a ogg flac webm
_FRONTEND_AUDIO_NAMES = [
    "speech.wav",
    "recording.webm",
    "SPEECH.WAV",
    "Voice Memo 12.m4a",
    "talk.ogg",
    "talk.mp4",
    "talk.mp3",
    "talk.flac",
]


@pytest.mark.parametrize("name", _FRONTEND_AUDIO_NAMES)
def test_every_audio_name_the_frontend_produces_passes(name):
    assert policy.require_safe_upload(name, policy.AUDIO_EXTENSIONS) == name


@pytest.mark.parametrize("name", ["blob", "audio", "speech", "recording", ""])
def test_a_name_with_no_extension_is_refused_and_the_frontend_never_sends_one(name):
    # Every producer above sets an explicit name with an extension; a nameless Blob would 400, by design.
    assert policy.is_safe_file(name, policy.AUDIO_EXTENSIONS) is False


def test_aac_and_opus_were_never_accepted_by_voice_create_so_no_regression():
    from media.audio.reference_wav import ALLOWED_EXTENSIONS as reference_allowed

    # reference_wav.py (#18477) already answers 415 for any suffix outside the one SSOT set; the gate shares it.
    assert reference_allowed == policy.AUDIO_EXTENSIONS
    assert not {".aac", ".opus"} & policy.AUDIO_EXTENSIONS


# --- request.form() routes (knowledge /upload and /audio/upload), the combine content type, files.py ----------


class BodyForbidden:
    """An upload whose body must never be read: a bad name has to be refused first."""

    def __init__(self, filename, content_type="application/octet-stream"):
        self.filename = filename
        self.content_type = content_type

    async def read(self, size=-1):
        raise AssertionError("the body was read before the name/type gate")


def _form_request(upload):
    async def form():
        return {"file": upload}

    return SimpleNamespace(form=form, app=SimpleNamespace(), client=None)


@pytest.fixture
def kb_present(monkeypatch):
    from api import knowledge

    async def fake_kb(app, force_refresh=False):
        return object()

    monkeypatch.setattr(knowledge, "get_or_create_knowledge_base", fake_kb)
    return knowledge


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name",
    ["payload.exe", "a/b.txt", "..\\x.txt", "noextension", "notes.txt‮gpj.exe", "x∕y.txt", ".env", "", None],
)
async def test_knowledge_upload_refuses_a_bad_name_before_reading_the_body(name, kb_present):
    err = await _refused(_unwrap(kb_present.upload_file_to_knowledge)(True, _form_request(BodyForbidden(name))))
    assert getattr(err, "detail_code", "").startswith("upload.")


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["payload.exe", "a/b.mp3", "notes.txt", "x.mp3‮exe", "song", "", None])
async def test_knowledge_audio_upload_refuses_a_bad_name_before_reading_the_body(name, kb_present):
    await _refused(_unwrap(kb_present.upload_audio_file)(True, _form_request(BodyForbidden(name))))


def test_the_kb_name_gate_keeps_its_stable_codes_and_serves_the_folder_watcher_too():
    from api.knowledge import _validate_file_upload, require_safe_kb_name

    with pytest.raises(HTTPException) as unsupported:
        _validate_file_upload("a.exe", 1)  # the kb_folder_watcher caller
    assert unsupported.value.detail_code == "upload.unsupported_type"
    with pytest.raises(HTTPException) as invalid:
        require_safe_kb_name("a/b.txt")
    assert invalid.value.detail_code == "upload.invalid_filename"
    require_safe_kb_name("report.pdf")


@pytest.mark.asyncio
async def test_combine_refuses_a_non_image_content_type_like_process_image():
    upload = BodyForbidden("shot.png", "text/html")
    await _refused(multimodal._collect_modal_inputs(None, upload, None, "x", "u"))
    await _refused(_unwrap(multimodal.process_image)(upload, "analysis", None, {"user_id": "u"}))


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["payload.exe", "a/b.txt", "noextension", ""])
async def test_general_file_upload_refuses_a_bad_name_before_reading_the_body(name, monkeypatch):
    from api import files

    auth = SimpleNamespace(check_file_permissions=lambda request, action: (True, {"user_id": "u"}))
    monkeypatch.setattr(files, "get_auth_middleware", lambda: auth)
    request = SimpleNamespace(state=SimpleNamespace())
    await _refused(_unwrap(files.upload_file)(request, BodyForbidden(name), "", False))
