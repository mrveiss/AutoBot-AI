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
