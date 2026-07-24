# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Test SSRF protection in ExternalSkillImporter (MVA-2584)
"""

import pytest

from skills.external_importer import ExternalSkillImporter


@pytest.mark.asyncio
async def test_import_http_catalog_rejects_invalid_scheme():
    """SSRF guard: reject non-HTTP(S) schemes."""
    importer = ExternalSkillImporter()

    with pytest.raises(RuntimeError, match="must use http or https scheme"):
        await importer.import_http_catalog("file:///etc/passwd")

    with pytest.raises(RuntimeError, match="must use http or https scheme"):
        await importer.import_http_catalog("ftp://example.com/catalog")

    with pytest.raises(RuntimeError, match="must use http or https scheme"):
        await importer.import_http_catalog("gopher://example.com/catalog")


@pytest.mark.asyncio
async def test_import_http_catalog_rejects_missing_hostname():
    """SSRF guard: reject URLs without hostname."""
    importer = ExternalSkillImporter()

    with pytest.raises(RuntimeError, match="missing hostname"):
        await importer.import_http_catalog("http://")

    with pytest.raises(RuntimeError, match="missing hostname"):
        await importer.import_http_catalog("https://")


@pytest.mark.asyncio
async def test_import_http_catalog_rejects_private_ips():
    """SSRF guard: reject private/internal IPs (via is_public_url_async)."""
    importer = ExternalSkillImporter()

    # These should be blocked by is_public_url_async
    private_urls = [
        "http://127.0.0.1/catalog",
        "http://localhost/catalog",
        "http://10.0.0.1/catalog",
        "http://192.168.1.1/catalog",
        "http://172.16.0.1/catalog",
        "http://169.254.169.254/catalog",  # AWS metadata
    ]

    for url in private_urls:
        with pytest.raises(RuntimeError, match="blocked by SSRF guard"):
            await importer.import_http_catalog(url)


@pytest.mark.asyncio
async def test_import_git_repo_rejects_invalid_schemes():
    """SSRF guard: reject disallowed git schemes."""
    importer = ExternalSkillImporter()

    with pytest.raises(RuntimeError, match="Git URL rejected"):
        await importer.import_git_repo("file:///etc/passwd")

    with pytest.raises(RuntimeError, match="Git URL rejected"):
        await importer.import_git_repo("http://example.com/repo.git")

    with pytest.raises(RuntimeError, match="Git URL rejected"):
        await importer.import_git_repo("git://example.com/repo.git")


@pytest.mark.asyncio
async def test_import_git_repo_rejects_private_ips():
    """SSRF guard: reject private IPs in git URLs."""
    importer = ExternalSkillImporter()

    with pytest.raises(RuntimeError, match="blocked by SSRF guard"):
        await importer.import_git_repo("https://127.0.0.1/repo.git")

    with pytest.raises(RuntimeError, match="blocked by SSRF guard"):
        await importer.import_git_repo("https://10.0.0.1/repo.git")


@pytest.mark.asyncio
async def test_import_http_catalog_public_url_passes_and_pins_ip():
    """A valid public catalog URL is fetched via an IP-pinned connector (#12278)."""
    from unittest.mock import AsyncMock, MagicMock, patch

    importer = ExternalSkillImporter()
    fake_infos = [(2, 1, 6, "", ("93.184.216.34", 0))]

    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={"skills": [{"name": "demo"}]})
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    mock_get = MagicMock(return_value=mock_response)
    mock_session = MagicMock()
    mock_session.get = mock_get
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("autobot_shared.url_safety.socket.getaddrinfo", return_value=fake_infos):
        with patch("aiohttp.ClientSession", return_value=mock_session) as mk_session:
            skills = await importer.import_http_catalog("https://catalog.example.com/skills")

    assert skills == [{"name": "demo"}]
    # A pinned connector must be supplied to the session (DNS-rebind defence).
    assert mk_session.call_args.kwargs.get("connector") is not None
    # Redirects must be disabled so a 3xx cannot bypass the SSRF check.
    assert mock_get.call_args.kwargs.get("allow_redirects") is False


@pytest.mark.asyncio
async def test_import_http_catalog_blocks_dns_rebind_to_private():
    """is_public passes on check, but the pinned resolve sees a private IP → blocked."""
    from unittest.mock import AsyncMock, patch

    importer = ExternalSkillImporter()

    fake_private = [(2, 1, 6, "", ("10.0.0.1", 0))]
    # First-stage is_public check is forced True; the pinned resolve then sees a
    # private IP and must reject (defence-in-depth against DNS-rebind).
    with patch("autobot_shared.url_safety.is_public_url_async", AsyncMock(return_value=True)):
        with patch("autobot_shared.url_safety.socket.getaddrinfo", return_value=fake_private):
            with pytest.raises(RuntimeError, match="blocked by SSRF guard"):
                await importer.import_http_catalog("https://rebind.example.com/skills")
