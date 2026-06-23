# Pluggable Theme Packages via /slm — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let admins install themes by uploading a zip via /slm; deliver them to the running user frontend at runtime and make them user-selectable — no rebuild.

**Architecture:** Themes are a backend-owned package type modeled on `plugin_install.py`. Shared zip-safety primitives are extracted to `archive_safety.py` (used by both plugins and themes). A strict CSS validator enforces `[data-theme-variant="<id>"]` scoping and blocks external fetches. The backend stores/serves themes; the frontend fetches a registry, extends `availableVariants`, and applies a selected theme via `fetch` + `adoptedStyleSheets` (CSP-safe).

**Tech Stack:** Python/FastAPI (autobot-backend), pytest; Vue 3 + TypeScript (autobot-frontend), vitest, vue-tsc.

## Global Constraints

- Worktree: `.worktrees/issue-10472`, branch `issue-10472`. Base/PR target: `Dev_new_gui`.
- Python line length 120; functions ≤30 lines; `encoding="utf-8"` explicit; logging via `get_logger(__name__)` (no `print`).
- Frontend: no `console.*` (use `createLogger`); strict CSP (`style-src 'self'`, no `unsafe-inline`) — runtime CSS must use `adoptedStyleSheets`, never inline `<style>` or cross-origin `<link>`.
- Admin gate = `from auth_middleware import check_admin_permission` (`Depends(check_admin_permission)`), as used by `plugin_manager.py`.
- Route error wrapper = `from error_handler import with_error_handling` (decorator BELOW `@router.*`).
- Copyright header `# Copyright 2025-2026 mrveiss` + `# SPDX-License-Identifier: Apache-2.0` on new Python files; `// Copyright …` on new TS/Vue files.
- Commit format: `<type>(scope): <desc> (#10472)`.

---

### Task 1: Extract shared archive-safety primitives

Generalize the plugin zip-hardening into a reusable module so themes reuse the exact same security code (DRY — one place to fix zip-slip/symlink/bomb guards).

**Files:**
- Create: `autobot-backend/archive_safety.py`
- Modify: `autobot-backend/plugin_install.py` (re-point to the shared module)
- Test: `autobot-backend/archive_safety_test.py`

**Interfaces:**
- Produces:
  - `MAX_ZIP_UNCOMPRESSED_BYTES`, `MAX_ZIP_ENTRIES`, `MAX_UPLOAD_BYTES`, `MAX_COMPRESSION_RATIO` (ints)
  - `is_zip_symlink(info: zipfile.ZipInfo) -> bool`
  - `validate_zip_metadata(zf: zipfile.ZipFile, extract_root: Path) -> None`
  - `safe_extract(zf: zipfile.ZipFile, extract_root: Path) -> None`
  - `find_package_root(extract_dir: Path, manifest_filename: str) -> Path`
  - `move_into_target(source: Path, target: Path) -> None`
  - `async stream_upload_to(upload: UploadFile, dest: Path) -> None`
  - all raise `fastapi.HTTPException` on violation.

- [ ] **Step 1: Write the failing test**

```python
# autobot-backend/archive_safety_test.py
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
import io
import zipfile
from pathlib import Path

import pytest
from fastapi import HTTPException

from archive_safety import find_package_root, safe_extract, validate_zip_metadata


def _zip_bytes(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_safe_extract_writes_files(tmp_path: Path):
    zf = zipfile.ZipFile(io.BytesIO(_zip_bytes({"theme.json": b"{}"})))
    safe_extract(zf, tmp_path)
    assert (tmp_path / "theme.json").read_bytes() == b"{}"


def test_validate_rejects_zip_slip(tmp_path: Path):
    zf = zipfile.ZipFile(io.BytesIO(_zip_bytes({"../evil.txt": b"x"})))
    with pytest.raises(HTTPException) as exc:
        validate_zip_metadata(zf, tmp_path)
    assert exc.value.status_code == 400


def test_find_package_root_in_single_subdir(tmp_path: Path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "theme.json").write_text("{}", encoding="utf-8")
    assert find_package_root(tmp_path, "theme.json") == tmp_path / "pkg"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd autobot-backend && python -m pytest archive_safety_test.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'archive_safety'`.

- [ ] **Step 3: Create `archive_safety.py`**

Move the bodies of `_is_zip_symlink`, `_validate_zip_metadata`, `_safe_extract`, `_move_into_target`, `_stream_upload_to`, and a generalized `find_package_root` (the old `_find_plugin_root` but taking `manifest_filename`) from `plugin_install.py` into `archive_safety.py` as public functions. Copy the constants `_MAX_*` as public `MAX_*`. Keep the logic byte-for-byte; only rename (drop leading `_`) and parameterize the manifest filename.

```python
# autobot-backend/archive_safety.py
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Shared, hardened zip-archive handling for package installers (plugins, themes).

Extracted from plugin_install.py (#10472) so every installer reuses the same
zip-slip / symlink / zip-bomb / upload-size guards — one place to audit and fix.
"""
from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

MAX_ZIP_UNCOMPRESSED_BYTES = 256 * 1024 * 1024
MAX_ZIP_ENTRIES = 5000
MAX_UPLOAD_BYTES = 512 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100


def is_zip_symlink(info: zipfile.ZipInfo) -> bool:
    return ((info.external_attr >> 16) & 0xF000) == 0xA000


def validate_zip_metadata(zf: zipfile.ZipFile, extract_root: Path) -> None:
    names = zf.namelist()
    if len(names) > MAX_ZIP_ENTRIES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Archive has too many entries (>{MAX_ZIP_ENTRIES})")
    extract_root_resolved = extract_root.resolve()
    for info in zf.infolist():
        if info.is_dir():
            continue
        target = (extract_root / info.filename).resolve()
        try:
            target.relative_to(extract_root_resolved)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Archive entry escapes root: {info.filename}") from exc
        if is_zip_symlink(info):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Archive contains symlink: {info.filename}")
        if info.compress_size > 0 and info.file_size // info.compress_size > MAX_COMPRESSION_RATIO:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Archive entry has suspicious compression ratio: {info.filename}")


def safe_extract(zf: zipfile.ZipFile, extract_root: Path) -> None:
    extract_root_resolved = extract_root.resolve()
    bytes_written = 0
    for info in zf.infolist():
        if info.is_dir():
            continue
        if "__MACOSX/" in info.filename or Path(info.filename).name.startswith("._"):
            continue
        target = (extract_root / info.filename).resolve()
        target.relative_to(extract_root_resolved)
        if is_zip_symlink(info):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Archive contains symlink: {info.filename}")
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info) as src, target.open("wb") as out:
            while chunk := src.read(1024 * 1024):
                bytes_written += len(chunk)
                if bytes_written > MAX_ZIP_UNCOMPRESSED_BYTES:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archive uncompressed size exceeds 256MB")
                out.write(chunk)


def find_package_root(extract_dir: Path, manifest_filename: str) -> Path:
    if (extract_dir / manifest_filename).is_file():
        return extract_dir
    children = [c for c in extract_dir.iterdir() if c.is_dir() and c.name != "__MACOSX" and not c.name.startswith(".")]
    if len(children) == 1 and (children[0] / manifest_filename).is_file():
        return children[0]
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{manifest_filename} not found at archive root or single top-level folder")


def move_into_target(source: Path, target: Path) -> None:
    for child in source.iterdir():
        shutil.move(str(child), str(target / child.name))
    source.rmdir()


async def stream_upload_to(upload: UploadFile, dest: Path) -> None:
    bytes_written = 0
    with dest.open("wb") as out:
        while chunk := await upload.read(1024 * 1024):
            bytes_written += len(chunk)
            if bytes_written > MAX_UPLOAD_BYTES:
                raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=f"Upload exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)}MB")
            out.write(chunk)
```

- [ ] **Step 4: Re-point `plugin_install.py` to the shared module**

In `plugin_install.py`, delete the moved private functions + `_MAX_*` constants, and add `import archive_safety as _arch`. Replace internal calls: `_validate_zip_metadata(...)`→`_arch.validate_zip_metadata(...)`, `_safe_extract`→`_arch.safe_extract`, `_find_plugin_root(d)`→`_arch.find_package_root(d, "plugin.json")`, `_move_into_target`→`_arch.move_into_target`, `_stream_upload_to`→`_arch.stream_upload_to`. Keep `_MAX_UPLOAD_BYTES` references pointing at `_arch.MAX_UPLOAD_BYTES`.

- [ ] **Step 5: Run tests (new + plugin regression)**

Run: `cd autobot-backend && python -m pytest archive_safety_test.py plugin_install_test.py -q` (if `plugin_install_test.py` is absent, run `python -m pytest -k plugin_install -q`).
Expected: PASS — new archive-safety tests pass AND existing plugin install tests still pass (behavior preserved).

- [ ] **Step 6: Commit**

```bash
git add autobot-backend/archive_safety.py autobot-backend/archive_safety_test.py autobot-backend/plugin_install.py
git commit -m "refactor(backend): extract shared archive-safety zip hardening from plugin_install (#10472)"
```

---

### Task 2: Strict theme CSS validator

The security keystone: a pure function that accepts theme CSS only if every rule is scoped to the theme's variant and contains no external fetches.

**Files:**
- Create: `autobot-backend/theme_css_validator.py`
- Test: `autobot-backend/theme_css_validator_test.py`

**Interfaces:**
- Produces: `validate_theme_css(css: str, variant_id: str) -> None` — raises `HTTPException(400, detail=...)` on the first violation; returns `None` if valid.
- Consumes: nothing.

- [ ] **Step 1: Write the failing test**

```python
# autobot-backend/theme_css_validator_test.py
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi import HTTPException

from theme_css_validator import validate_theme_css

OK = '[data-theme-variant="x"] { --bg-primary: #fff; }'


def test_accepts_scoped_rule():
    validate_theme_css(OK, "x")  # no raise


def test_rejects_unscoped_rule():
    with pytest.raises(HTTPException):
        validate_theme_css("body { color: red; }", "x")


def test_rejects_wrong_variant_id():
    with pytest.raises(HTTPException):
        validate_theme_css('[data-theme-variant="other"] { --x: 1; }', "x")


def test_rejects_at_import():
    with pytest.raises(HTTPException):
        validate_theme_css('@import url("http://evil/x.css");', "x")


def test_rejects_external_url():
    with pytest.raises(HTTPException):
        validate_theme_css('[data-theme-variant="x"] { background: url(http://evil/p.png); }', "x")


def test_accepts_data_uri_and_relative_url():
    validate_theme_css('[data-theme-variant="x"] { src: url(data:font/woff2;base64,AA); }', "x")
    validate_theme_css('[data-theme-variant="x"] { src: url(./fonts/a.woff2); }', "x")


def test_rejects_expression_and_oversize():
    with pytest.raises(HTTPException):
        validate_theme_css('[data-theme-variant="x"] { width: expression(alert(1)); }', "x")
    with pytest.raises(HTTPException):
        validate_theme_css("[data-theme-variant=\"x\"] { /* a */ }" + "a" * (512 * 1024), "x")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd autobot-backend && python -m pytest theme_css_validator_test.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'theme_css_validator'`.

- [ ] **Step 3: Write the validator**

Approach: strip comments; enforce size cap; reject forbidden tokens anywhere (`@import`, `expression(`, `behavior:`, `javascript:`); reject any `url(...)` whose target is not `data:` or a relative path (no `http:`/`https:`/`//`/`\\`); then split into top-level rule blocks and require each block's selector list to start every selector with `[data-theme-variant="<variant_id>"]`.

```python
# autobot-backend/theme_css_validator.py
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Strict validator for uploaded theme CSS (#10472).

Untrusted CSS may only style its own variant and must not fetch anything
external. Rejects on the first violation with an HTTPException(400).
"""
from __future__ import annotations

import re

from fastapi import HTTPException, status

MAX_CSS_BYTES = 512 * 1024
_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_FORBIDDEN = ("@import", "expression(", "behavior:", "javascript:", "@charset")
_URL = re.compile(r"url\(\s*['\"]?([^'\")]+)['\"]?\s*\)", re.IGNORECASE)
_BLOCK = re.compile(r"([^{}]+)\{[^{}]*\}", re.DOTALL)


def _reject(detail: str) -> None:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Theme CSS rejected: {detail}")


def validate_theme_css(css: str, variant_id: str) -> None:
    if len(css.encode("utf-8")) > MAX_CSS_BYTES:
        _reject(f"exceeds {MAX_CSS_BYTES // 1024}KB")
    stripped = _COMMENT.sub(" ", css)
    lowered = stripped.lower()
    for tok in _FORBIDDEN:
        if tok in lowered:
            _reject(f"forbidden token {tok!r}")
    for ref in _URL.findall(stripped):
        target = ref.strip()
        if target.startswith("data:"):
            continue
        if re.match(r"^(https?:)?//", target, re.IGNORECASE) or "\\" in target or ":" in target.split("/")[0]:
            _reject(f"external url() not allowed: {target}")
    scope = f'[data-theme-variant="{variant_id}"]'
    blocks = _BLOCK.findall(stripped)
    if not blocks:
        _reject("no style rules found")
    for selector_list in blocks:
        for selector in selector_list.split(","):
            sel = selector.strip()
            if not sel or sel.startswith("@"):  # @font-face/@media handled below
                continue
            if not sel.startswith(scope):
                _reject(f"selector not scoped to {scope}: {sel[:60]}")
```

Note: `@font-face`/`@media` wrappers — for MVP, reject at-rules other than the allowed set by treating any selector beginning with `@` as needing review; keep it simple: the test suite above does not require `@media`, and `@import`/`@charset` are already forbidden. If a later theme needs `@font-face`, that is a follow-up (documented in spec "out of scope"). Keep this MVP behavior: at-rule selectors are skipped only if they are `@font-face` with `src: url(data:|relative)` — already covered by the url() check.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd autobot-backend && python -m pytest theme_css_validator_test.py -q`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add autobot-backend/theme_css_validator.py autobot-backend/theme_css_validator_test.py
git commit -m "feat(backend): strict theme CSS validator — scope + sanitise uploads (#10472)"
```

---

### Task 3: Theme install service

Install/list/uninstall theme packages on disk using the shared archive-safety guards and the CSS validator.

**Files:**
- Create: `autobot-backend/theme_install.py`
- Test: `autobot-backend/theme_install_test.py`

**Interfaces:**
- Consumes: `archive_safety` (Task 1), `validate_theme_css` (Task 2).
- Produces:
  - `class ThemeManifest(BaseModel)`: `id: str`, `name: str`, `author: str`, `version: str`, `supports: list[str] = ["light","dark"]`.
  - `class ThemeDescriptor(BaseModel)`: same fields (registry shape).
  - `themes_dir() -> Path` → `config.path.data_path / "themes"` (created).
  - `async install_theme_from_zip(upload: UploadFile) -> ThemeDescriptor`
  - `list_installed_themes() -> list[ThemeDescriptor]`
  - `uninstall_theme(theme_id: str) -> None` (404 if absent)
  - `theme_css_path(theme_id: str) -> Path` (404 if absent), `theme_asset_path(theme_id, rel: str) -> Path` (path-traversal guarded; 404 if absent)

- [ ] **Step 1: Write the failing test**

```python
# autobot-backend/theme_install_test.py
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
import io
import json
import zipfile

import pytest
from fastapi import HTTPException, UploadFile

import theme_install


def _theme_zip(theme_id="aqua", css=None) -> UploadFile:
    css = css or f'[data-theme-variant="{theme_id}"] {{ --bg-primary: #eef; }}'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("theme.json", json.dumps({"id": theme_id, "name": "Aqua", "author": "me", "version": "1.0.0"}))
        zf.writestr("theme.css", css)
    buf.seek(0)
    return UploadFile(filename=f"{theme_id}.zip", file=buf)


@pytest.fixture(autouse=True)
def _tmp_themes(tmp_path, monkeypatch):
    monkeypatch.setattr(theme_install, "themes_dir", lambda: tmp_path)


@pytest.mark.asyncio
async def test_install_then_list_then_uninstall():
    desc = await theme_install.install_theme_from_zip(_theme_zip("aqua"))
    assert desc.id == "aqua"
    assert [t.id for t in theme_install.list_installed_themes()] == ["aqua"]
    assert theme_install.theme_css_path("aqua").is_file()
    theme_install.uninstall_theme("aqua")
    assert theme_install.list_installed_themes() == []


@pytest.mark.asyncio
async def test_install_rejects_unscoped_css():
    with pytest.raises(HTTPException):
        await theme_install.install_theme_from_zip(_theme_zip("bad", css="body { color: red }"))


@pytest.mark.asyncio
async def test_duplicate_install_conflicts():
    await theme_install.install_theme_from_zip(_theme_zip("dup"))
    with pytest.raises(HTTPException) as exc:
        await theme_install.install_theme_from_zip(_theme_zip("dup"))
    assert exc.value.status_code == 409
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd autobot-backend && python -m pytest theme_install_test.py -q`
Expected: FAIL — `AttributeError`/`ImportError` (module/functions absent).

- [ ] **Step 3: Write `theme_install.py`**

```python
# autobot-backend/theme_install.py
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Install/list/uninstall uploaded theme packages (#10472)."""
from __future__ import annotations

import json
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from pydantic import BaseModel

import archive_safety as _arch
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config
from theme_css_validator import validate_theme_css

logger = get_logger(__name__)
_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")


class ThemeManifest(BaseModel):
    id: str
    name: str
    author: str
    version: str
    supports: list[str] = ["light", "dark"]


class ThemeDescriptor(BaseModel):
    id: str
    name: str
    author: str
    version: str
    supports: list[str]


def themes_dir() -> Path:
    target = config.path.data_path / "themes"
    target.mkdir(parents=True, exist_ok=True)
    return target


def _read_manifest(root: Path) -> ThemeManifest:
    mf = root / "theme.json"
    if not mf.is_file():
        raise HTTPException(status_code=400, detail="theme.json not found at theme root")
    try:
        return ThemeManifest(**json.loads(mf.read_text(encoding="utf-8")))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid theme.json: {exc}") from exc


async def install_theme_from_zip(upload: UploadFile) -> ThemeDescriptor:
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = Path(tmp) / "u.zip"
        await _arch.stream_upload_to(upload, zip_path)
        extract = Path(tmp) / "x"
        extract.mkdir()
        try:
            with zipfile.ZipFile(zip_path) as zf:
                _arch.validate_zip_metadata(zf, extract)
                _arch.safe_extract(zf, extract)
        except zipfile.BadZipFile as exc:
            raise HTTPException(status_code=400, detail="Not a valid ZIP archive") from exc
        root = _arch.find_package_root(extract, "theme.json")
        manifest = _read_manifest(root)
        if not _ID.match(manifest.id):
            raise HTTPException(status_code=400, detail="Invalid theme id (lowercase alphanumeric/-/_, ≤63)")
        css_file = root / "theme.css"
        if not css_file.is_file():
            raise HTTPException(status_code=400, detail="theme.css not found")
        validate_theme_css(css_file.read_text(encoding="utf-8"), manifest.id)
        target = themes_dir() / manifest.id
        try:
            target.mkdir(parents=False, exist_ok=False)
        except FileExistsError as exc:
            raise HTTPException(status_code=409, detail=f"Theme '{manifest.id}' already installed") from exc
        _arch.move_into_target(root, target)
        logger.info("Installed theme '%s' v%s", manifest.id, manifest.version)
        return ThemeDescriptor(**manifest.model_dump())


def list_installed_themes() -> list[ThemeDescriptor]:
    out: list[ThemeDescriptor] = []
    base = themes_dir()
    for d in sorted(base.iterdir()):
        mf = d / "theme.json"
        if d.is_dir() and mf.is_file():
            try:
                out.append(ThemeDescriptor(**ThemeManifest(**json.loads(mf.read_text(encoding="utf-8"))).model_dump()))
            except Exception:
                logger.warning("Skipping malformed theme dir: %s", d.name)
    return out


def _theme_dir(theme_id: str) -> Path:
    if not _ID.match(theme_id):
        raise HTTPException(status_code=400, detail="Invalid theme id")
    d = themes_dir() / theme_id
    if not d.is_dir():
        raise HTTPException(status_code=404, detail=f"Theme '{theme_id}' not found")
    return d


def uninstall_theme(theme_id: str) -> None:
    shutil.rmtree(_theme_dir(theme_id))


def theme_css_path(theme_id: str) -> Path:
    p = _theme_dir(theme_id) / "theme.css"
    if not p.is_file():
        raise HTTPException(status_code=404, detail="theme.css missing")
    return p


def theme_asset_path(theme_id: str, rel: str) -> Path:
    base = _theme_dir(theme_id).resolve()
    target = (base / rel).resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid asset path") from exc
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Asset not found")
    return target
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd autobot-backend && python -m pytest theme_install_test.py -q`
Expected: PASS (3 tests). (If `pytest-asyncio` mode requires it, the repo already uses async tests — mirror `plugin_install_test.py`'s markers.)

- [ ] **Step 5: Commit**

```bash
git add autobot-backend/theme_install.py autobot-backend/theme_install_test.py
git commit -m "feat(backend): theme package install/list/uninstall service (#10472)"
```

---

### Task 4: Theme API router

Expose admin install/uninstall + public registry/CSS/asset serving, and register the router.

**Files:**
- Create: `autobot-backend/api/themes.py`
- Modify: `autobot-backend/initialization/router_registry/core_routers.py` (register router)
- Test: `autobot-backend/api/themes_test.py`

**Interfaces:**
- Consumes: `theme_install` (Task 3), `check_admin_permission`, `with_error_handling`.
- Produces routes: `POST /api/themes`, `DELETE /api/themes/{theme_id}`, `GET /api/themes`, `GET /api/themes/{theme_id}/theme.css`, `GET /api/themes/{theme_id}/assets/{rel:path}`.

- [ ] **Step 1: Write the failing test**

```python
# autobot-backend/api/themes_test.py
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
import io
import json
import zipfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import theme_install
from api import themes as themes_api
from auth_middleware import check_admin_permission


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(theme_install, "themes_dir", lambda: tmp_path)
    app = FastAPI()
    app.include_router(themes_api.router)
    app.dependency_overrides[check_admin_permission] = lambda: True
    return TestClient(app)


def _zip(theme_id="aqua"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("theme.json", json.dumps({"id": theme_id, "name": "Aqua", "author": "me", "version": "1.0.0"}))
        zf.writestr("theme.css", f'[data-theme-variant="{theme_id}"] {{ --bg-primary:#eef; }}')
    return buf.getvalue()


def test_upload_list_serve_delete(client):
    r = client.post("/api/themes", files={"file": ("aqua.zip", _zip(), "application/zip")})
    assert r.status_code == 200, r.text
    assert client.get("/api/themes").json()[0]["id"] == "aqua"
    css = client.get("/api/themes/aqua/theme.css")
    assert css.status_code == 200 and "data-theme-variant" in css.text
    assert client.delete("/api/themes/aqua").status_code == 200
    assert client.get("/api/themes").json() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd autobot-backend && python -m pytest api/themes_test.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'api.themes'`.

- [ ] **Step 3: Write `api/themes.py`**

```python
# autobot-backend/api/themes.py
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Theme package API — admin install/uninstall + public registry/serve (#10472)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse

import theme_install
from auth_middleware import check_admin_permission
from error_handler import with_error_handling

router = APIRouter(prefix="/api/themes", tags=["themes"])


@router.post("")
@with_error_handling(error_code_prefix="THEME_INSTALL")
async def install_theme(file: UploadFile = File(...), admin_check: bool = Depends(check_admin_permission)):
    desc = await theme_install.install_theme_from_zip(file)
    return JSONResponse(desc.model_dump())


@router.delete("/{theme_id}")
@with_error_handling(error_code_prefix="THEME_UNINSTALL")
async def uninstall_theme(theme_id: str, admin_check: bool = Depends(check_admin_permission)):
    theme_install.uninstall_theme(theme_id)
    return {"status": "deleted", "id": theme_id}


@router.get("")
@with_error_handling(error_code_prefix="THEME_LIST")
async def list_themes():
    return [d.model_dump() for d in theme_install.list_installed_themes()]


@router.get("/{theme_id}/theme.css")
@with_error_handling(error_code_prefix="THEME_CSS")
async def serve_theme_css(theme_id: str):
    return FileResponse(theme_install.theme_css_path(theme_id), media_type="text/css")


@router.get("/{theme_id}/assets/{rel:path}")
@with_error_handling(error_code_prefix="THEME_ASSET")
async def serve_theme_asset(theme_id: str, rel: str):
    return FileResponse(theme_install.theme_asset_path(theme_id, rel))
```

- [ ] **Step 4: Register the router**

In `autobot-backend/initialization/router_registry/core_routers.py`: near the existing `from plugin_manager import router as plugin_manager_router` (line ~109) add `from api.themes import router as themes_router`. In the registration tuple list (near line ~503 where `(plugin_manager_router, "", ["plugins"], "plugin_manager")` is) add `(themes_router, "", ["themes"], "themes")` (the router already carries its `/api/themes` prefix, so mount prefix is `""`).

- [ ] **Step 5: Run tests**

Run: `cd autobot-backend && python -m pytest api/themes_test.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add autobot-backend/api/themes.py autobot-backend/api/themes_test.py autobot-backend/initialization/router_registry/core_routers.py
git commit -m "feat(backend): theme API — install/uninstall/registry/serve, admin-gated (#10472)"
```

---

### Task 5: Frontend theme registry composable

Fetch the installed-theme registry from the backend.

**Files:**
- Create: `autobot-frontend/src/composables/useThemeRegistry.ts`
- Test: `autobot-frontend/src/composables/__tests__/useThemeRegistry.test.ts`

**Interfaces:**
- Consumes: `apiClient.get` (`@/utils/ApiClient`).
- Produces: `interface InstalledTheme { id: string; name: string; author: string; version: string; supports: string[] }`; `async function fetchInstalledThemes(): Promise<InstalledTheme[]>` (returns `[]` on error — graceful).

- [ ] **Step 1: Write the failing test**

```ts
// autobot-frontend/src/composables/__tests__/useThemeRegistry.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/utils/ApiClient', () => ({ apiClient: { get: vi.fn() } }))
import { apiClient } from '@/utils/ApiClient'
import { fetchInstalledThemes } from '../useThemeRegistry'

describe('fetchInstalledThemes', () => {
  beforeEach(() => vi.clearAllMocks())

  it('returns installed themes from the registry', async () => {
    ;(apiClient.get as any).mockResolvedValue([{ id: 'aqua', name: 'Aqua', author: 'me', version: '1.0.0', supports: ['light'] }])
    const themes = await fetchInstalledThemes()
    expect(themes.map((t) => t.id)).toEqual(['aqua'])
  })

  it('returns [] when the registry call fails (graceful)', async () => {
    ;(apiClient.get as any).mockRejectedValue(new Error('network'))
    expect(await fetchInstalledThemes()).toEqual([])
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd autobot-frontend && npx vitest run src/composables/__tests__/useThemeRegistry.test.ts`
Expected: FAIL — cannot resolve `../useThemeRegistry`.

- [ ] **Step 3: Write the composable**

```ts
// autobot-frontend/src/composables/useThemeRegistry.ts
// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { apiClient } from '@/utils/ApiClient'
import { createLogger } from '@/utils/logger'

const log = createLogger('ThemeRegistry')

export interface InstalledTheme {
  id: string
  name: string
  author: string
  version: string
  supports: string[]
}

/** Fetch installed theme descriptors. Returns [] on any error (graceful degrade). */
export async function fetchInstalledThemes(): Promise<InstalledTheme[]> {
  try {
    const themes = await apiClient.get<InstalledTheme[]>('/api/themes')
    return Array.isArray(themes) ? themes : []
  } catch (err) {
    log.warn('Failed to fetch installed themes; using built-ins only', err)
    return []
  }
}
```

(Confirm the logger import path: `grep -rn "createLogger" src/utils/logger.ts`. If it differs, match the existing export.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd autobot-frontend && npx vitest run src/composables/__tests__/useThemeRegistry.test.ts`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add autobot-frontend/src/composables/useThemeRegistry.ts autobot-frontend/src/composables/__tests__/useThemeRegistry.test.ts
git commit -m "feat(frontend): theme registry composable — fetch installed themes (#10472)"
```

---

### Task 6: Runtime theme delivery in useThemeVariant

Extend the variant system so installed themes are selectable and applied via `adoptedStyleSheets`.

**Files:**
- Modify: `autobot-frontend/src/composables/useThemeVariant.ts`
- Test: `autobot-frontend/src/composables/__tests__/useThemeVariantRuntime.test.ts`

**Interfaces:**
- Consumes: `fetchInstalledThemes`, `InstalledTheme` (Task 5); `apiClient` for CSS text.
- Produces (additions to the composable's return): `installedThemes: Ref<InstalledTheme[]>`, `loadInstalledThemes(): Promise<void>` (merges ids into `availableVariants`, labels, descriptions); `applyThemeVariant` extended to adopt a fetched stylesheet for installed ids.

- [ ] **Step 1: Write the failing test**

```ts
// autobot-frontend/src/composables/__tests__/useThemeVariantRuntime.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('../useThemeRegistry', () => ({
  fetchInstalledThemes: vi.fn().mockResolvedValue([{ id: 'aqua', name: 'Aqua', author: 'me', version: '1.0.0', supports: ['light'] }]),
}))
vi.mock('@/utils/ApiClient', () => ({ apiClient: { get: vi.fn().mockResolvedValue('[data-theme-variant="aqua"]{--bg-primary:#eef}') } }))

beforeEach(() => {
  localStorage.clear()
  document.documentElement.removeAttribute('data-theme-variant')
  ;(document as any).adoptedStyleSheets = []
  vi.resetModules()
})

describe('useThemeVariant runtime themes', () => {
  it('merges installed theme ids into availableVariants after loadInstalledThemes', async () => {
    const { useThemeVariant } = await import('../useThemeVariant')
    const { availableVariants, loadInstalledThemes } = useThemeVariant()
    await loadInstalledThemes()
    expect(availableVariants.value ?? availableVariants).toContain('aqua')
  })
})
```

(If `availableVariants` is a plain array today, this task converts it to a `ref` so it can grow at runtime — update the return type accordingly and adjust `EmberThemeToggle.vue` to read `.value` or keep it reactive via `computed`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd autobot-frontend && npx vitest run src/composables/__tests__/useThemeVariantRuntime.test.ts`
Expected: FAIL — `loadInstalledThemes` is not a function.

- [ ] **Step 3: Implement runtime delivery**

In `useThemeVariant.ts`: add module state `const installedThemes = ref<InstalledTheme[]>([])` and `const runtimeVariantIds = ref<string[]>([])`; make `availableVariants` a `computed(() => [...VALID_VARIANTS, ...runtimeVariantIds.value])`. Add:

```ts
import { fetchInstalledThemes, type InstalledTheme } from './useThemeRegistry'
import { apiClient } from '@/utils/ApiClient'

const adopted = new Set<string>()

async function ensureThemeStylesheet(id: string): Promise<void> {
  if (adopted.has(id)) return
  const css = await apiClient.get<string>(`/api/themes/${id}/theme.css`, { responseType: 'text' } as never)
  const sheet = new CSSStyleSheet()
  await sheet.replace(typeof css === 'string' ? css : String(css))
  document.adoptedStyleSheets = [...document.adoptedStyleSheets, sheet]
  adopted.add(id)
}

async function loadInstalledThemes(): Promise<void> {
  installedThemes.value = await fetchInstalledThemes()
  runtimeVariantIds.value = installedThemes.value.map((t) => t.id)
}
```

Extend `applyThemeVariant` so that for an id that is neither `'default'` nor a built-in, it calls `ensureThemeStylesheet(id)` (awaited; on failure, revert to previous variant) before `setAttribute('data-theme-variant', id)`. Export `installedThemes`, `loadInstalledThemes` in the returned object. Call `loadInstalledThemes()` inside `initVariant()` (fire-and-forget) so installed themes appear after load.

- [ ] **Step 4: Run tests (new + existing variant tests)**

Run: `cd autobot-frontend && npx vitest run src/composables/__tests__/useThemeVariant.test.ts src/composables/__tests__/useThemeVariantRuntime.test.ts`
Expected: PASS — new runtime test passes AND the Phase-1 `useThemeVariant.test.ts` still passes (adjust those assertions only if `availableVariants` became a computed: read `.value`).

- [ ] **Step 5: Type-check + commit**

Run: `cd autobot-frontend && npx vue-tsc --noEmit -p tsconfig.app.json` → 0 errors (fix `EmberThemeToggle.vue` to read `availableVariants` reactively if needed).

```bash
git add autobot-frontend/src/composables/useThemeVariant.ts autobot-frontend/src/composables/__tests__/useThemeVariantRuntime.test.ts autobot-frontend/src/components/theme/EmberThemeToggle.vue
git commit -m "feat(frontend): runtime installed-theme delivery via adoptedStyleSheets (#10472)"
```

---

### Task 7: Admin theme-management view

A view to upload, list, and uninstall themes, reachable under the /slm route group, admin-gated.

**Files:**
- Create: `autobot-frontend/src/views/slm/ThemeManagerView.vue`
- Modify: `autobot-frontend/src/router/index.ts` (add `/slm/themes` route)
- Test: `autobot-frontend/src/views/slm/__tests__/ThemeManagerView.test.ts`

**Interfaces:**
- Consumes: `apiClient.post('/api/themes', FormData)`, `apiClient.delete('/api/themes/{id}')`, `fetchInstalledThemes`.
- Produces: route `name: 'slm-themes'`, `path: '/slm/themes'`.

- [ ] **Step 1: Write the failing test**

```ts
// autobot-frontend/src/views/slm/__tests__/ThemeManagerView.test.ts
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('@/composables/useThemeRegistry', () => ({
  fetchInstalledThemes: vi.fn().mockResolvedValue([{ id: 'aqua', name: 'Aqua', author: 'me', version: '1.0.0', supports: ['light'] }]),
}))
vi.mock('@/utils/ApiClient', () => ({ apiClient: { post: vi.fn(), delete: vi.fn() } }))
import ThemeManagerView from '../ThemeManagerView.vue'

describe('ThemeManagerView', () => {
  it('lists installed themes on mount', async () => {
    const wrapper = mount(ThemeManagerView)
    await new Promise((r) => setTimeout(r))
    expect(wrapper.text()).toContain('Aqua')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd autobot-frontend && npx vitest run src/views/slm/__tests__/ThemeManagerView.test.ts`
Expected: FAIL — cannot resolve `../ThemeManagerView.vue`.

- [ ] **Step 3: Write the view + route**

```vue
<!-- autobot-frontend/src/views/slm/ThemeManagerView.vue -->
<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { apiClient } from '@/utils/ApiClient'
import { fetchInstalledThemes, type InstalledTheme } from '@/composables/useThemeRegistry'
import { createLogger } from '@/utils/logger'

const log = createLogger('ThemeManager')
const themes = ref<InstalledTheme[]>([])
const busy = ref(false)
const error = ref('')

async function refresh() {
  themes.value = await fetchInstalledThemes()
}

async function onUpload(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  busy.value = true
  error.value = ''
  try {
    const form = new FormData()
    form.append('file', file)
    await apiClient.post('/api/themes', form)
    await refresh()
  } catch (err) {
    error.value = (err as Error).message
    log.error('Theme upload failed', err)
  } finally {
    busy.value = false
  }
}

async function remove(id: string) {
  await apiClient.delete(`/api/themes/${id}`)
  await refresh()
}

onMounted(refresh)
</script>

<template>
  <section class="theme-manager">
    <h1>Themes</h1>
    <p>Upload a theme package (.zip) to make it available to all users.</p>
    <input type="file" accept=".zip" :disabled="busy" @change="onUpload" />
    <p v-if="error" class="error">{{ error }}</p>
    <ul>
      <li v-for="t in themes" :key="t.id">
        <strong>{{ t.name }}</strong> <small>v{{ t.version }} — {{ t.author }}</small>
        <button @click="remove(t.id)">Uninstall</button>
      </li>
    </ul>
  </section>
</template>
```

In `router/index.ts`, add to the routes array:

```ts
{
  path: '/slm/themes',
  name: 'slm-themes',
  component: () => import('@/views/slm/ThemeManagerView.vue'),
  meta: { requiresAuth: true, requiresAdmin: true, title: 'Theme Manager' },
},
```

(Match the `meta` keys to the existing admin routes — `grep -n "requiresAdmin\|requiresAuth" src/router/index.ts` and copy the convention used by other /slm or admin routes.)

- [ ] **Step 4: Run test + type-check**

Run: `cd autobot-frontend && npx vitest run src/views/slm/__tests__/ThemeManagerView.test.ts && npx vue-tsc --noEmit -p tsconfig.app.json`
Expected: PASS + 0 type errors.

- [ ] **Step 5: Commit**

```bash
git add autobot-frontend/src/views/slm/ThemeManagerView.vue autobot-frontend/src/views/slm/__tests__/ThemeManagerView.test.ts autobot-frontend/src/router/index.ts
git commit -m "feat(frontend): admin theme-manager view + /slm/themes route (#10472)"
```

---

### Task 8: Final verification

- [ ] **Step 1: Backend suite (new modules)**

Run: `cd autobot-backend && python -m pytest archive_safety_test.py theme_css_validator_test.py theme_install_test.py api/themes_test.py -q && python -m pytest -k plugin_install -q`
Expected: all PASS (themes green + plugin regression green).

- [ ] **Step 2: Frontend checks**

Run: `cd autobot-frontend && npx vue-tsc --noEmit -p tsconfig.app.json && npx vitest run src/composables/__tests__/useThemeRegistry.test.ts src/composables/__tests__/useThemeVariant.test.ts src/composables/__tests__/useThemeVariantRuntime.test.ts src/views/slm/__tests__/ThemeManagerView.test.ts && npx eslint src/composables/useThemeRegistry.ts src/composables/useThemeVariant.ts src/views/slm/ThemeManagerView.vue`
Expected: 0 type errors, all tests pass, eslint clean.

- [ ] **Step 3: Open PR**

Rebase onto `origin/Dev_new_gui`, push, and open a PR titled `feat(ui/slm): pluggable theme packages — upload + install via /slm (#10472)` with the standard headings (Thinking Path · What Changed · Verification · Model Used) and `Fixes #10472`.

---

## Self-Review

**Spec coverage:** package format + manifest → Task 3 (`ThemeManifest`/`theme.json`); /slm upload+install+uninstall → Tasks 3–4 + 7; registry feeding `availableVariants` → Tasks 5–6; runtime delivery (adoptedStyleSheets, CSP-safe) → Task 6; strict CSS scope/sanitise → Task 2; reuse plugin hardening → Task 1; admin-gating → Task 4; serve assets/path-traversal → Task 3 (`theme_asset_path`) + Task 4; error handling/graceful fallback → Tasks 5–6; tests → every task. No-flash caveat: built-ins unchanged (Phase 1), installed themes apply post-load (Task 6) — matches spec.

**Placeholder scan:** every code step contains complete code; the two "match existing convention" notes (logger import, router meta keys) include the exact grep to confirm — not deferred logic.

**Type consistency:** `ThemeDescriptor`/`InstalledTheme` share `{id,name,author,version,supports}` across backend (Task 3) and frontend (Task 5); `validate_theme_css(css, variant_id)` signature consistent (Tasks 2–3); `fetchInstalledThemes()`/`loadInstalledThemes()` names consistent (Tasks 5–6–7); router prefix `/api/themes` consistent (Task 4) with frontend calls (Tasks 5–7).
