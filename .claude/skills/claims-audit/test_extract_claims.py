#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for claim extraction."""

import json
import re
import tempfile
from pathlib import Path

# `extract_claims` resolves through pytest.ini's `pythonpath`, like the other
# claims-audit modules (#14986). It was `extract-claims.py`, which no import
# statement could name, until the skill moved to one naming style (#20805).
from extract_claims import ClaimExtractor


def test_infrastructure_patterns():
    """Test infrastructure claim extraction."""
    test_cases = [
        ("Backend runs 4 uvicorn workers in prod", "service_count", "4 uvicorn"),
        ("Redis is used for caching", "service_mention", "Redis"),
        ("FastAPI on port 8001", "port_binding", "8001"),
        ("main database stores sessions", "database", "main"),
        ("ChromaDB vector store for embeddings", "service_mention", "ChromaDB"),
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        patterns_dir = Path(tmpdir) / "patterns"
        patterns_dir.mkdir()

        # Create test infrastructure pattern
        infrastructure_patterns = {
            "category": "infrastructure",
            "patterns": [
                {
                    "type": "service_count",
                    "pattern": r"(\d+)\s+(uvicorn|gunicorn|celery|redis|postgresql|worker|process|thread)s?",
                    "description": "Numeric claims about service instances",
                },
                {
                    "type": "service_mention",
                    "pattern": r"\b(Redis|PostgreSQL|ChromaDB|Celery|FastAPI|Uvicorn)\b",
                    "description": "Infrastructure service mentions",
                },
                {
                    "type": "port_binding",
                    "pattern": r"port\s+(\d+)|:(\d{4,5})\b",
                    "description": "Port number claims",
                },
                {
                    "type": "database",
                    "pattern": r"database\s+(\w+)|\b(main|knowledge|prompts|analytics)\s+database",
                    "description": "Database name claims",
                },
            ],
        }

        with open(patterns_dir / "infrastructure.json", "w", encoding="utf-8") as f:
            json.dump(infrastructure_patterns, f)

        extractor = ClaimExtractor(patterns_dir)

        # Test each case
        for claim_text, expected_type, expected_match in test_cases:
            test_file = Path(tmpdir) / "test.md"
            test_file.write_text(claim_text)

            claims = extractor.extract_from_file(test_file)
            assert len(claims) > 0, f"No claims found for: {claim_text}"

            found = False
            for claim in claims:
                if claim["type"] == expected_type and expected_match in claim["matched_text"]:
                    found = True
                    assert claim["category"] == "infrastructure"
                    assert claim["source"]["file"] == str(test_file)
                    assert claim["source"]["line"] == 1
                    break

            assert found, f"Expected match '{expected_match}' of type '{expected_type}' not found in: {claims}"

    print("✓ Infrastructure pattern tests passed")


def test_feature_patterns():
    """Test feature claim extraction."""
    test_cases = [
        ("AutoBot supports NPU acceleration", "capability", "NPU acceleration"),
        ("Integrates with OpenAI and Anthropic", "model_provider", "OpenAI"),
        ("WebSocket streaming for realtime updates", "protocol", "WebSocket"),
        ("Supports JSON and YAML formats", "format", "JSON"),
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        patterns_dir = Path(tmpdir) / "patterns"
        patterns_dir.mkdir()

        # Create test feature pattern
        feature_patterns = {
            "category": "features",
            "patterns": [
                {
                    "type": "capability",
                    "pattern": r"\b(NPU acceleration|GPU acceleration|multi-modal|voice|realtime|streaming)\b",
                    "description": "Feature capability claims",
                },
                {
                    "type": "model_provider",
                    "pattern": r"\b(OpenAI|Anthropic|Ollama|Groq|Claude|GPT)\b",
                    "description": "AI model provider mentions",
                },
                {
                    "type": "protocol",
                    "pattern": r"\b(WebSocket|SSE|REST|GraphQL|gRPC)\b",
                    "description": "Protocol support claims",
                },
                {
                    "type": "format",
                    "pattern": r"\b(JSON|YAML|Markdown|CSV|XML)\b",
                    "description": "Data format support",
                },
            ],
        }

        with open(patterns_dir / "features.json", "w", encoding="utf-8") as f:
            json.dump(feature_patterns, f)

        extractor = ClaimExtractor(patterns_dir)

        for claim_text, expected_type, expected_match in test_cases:
            test_file = Path(tmpdir) / "test.md"
            test_file.write_text(claim_text)

            claims = extractor.extract_from_file(test_file)
            assert len(claims) > 0, f"No claims found for: {claim_text}"

            found = any(
                c["type"] == expected_type and expected_match.lower() in c["matched_text"].lower() for c in claims
            )
            seen = [{"type": c["type"], "matched": c["matched_text"]} for c in claims]
            assert found, f"Expected match '{expected_match}' of type '{expected_type}' not found in claims: {seen}"

    print("✓ Feature pattern tests passed")


def test_api_patterns():
    """Test API claim extraction."""
    test_cases = [
        ("GET /api/chat/sessions", "endpoint", "GET /api/chat/sessions"),
        ("/api/knowledge/query endpoint", "route_path", "/api/knowledge"),
        ("Returns 200 OK with JSON", "status_code", "200"),
        ("JWT token authentication required", "auth", "JWT"),
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        patterns_dir = Path(tmpdir) / "patterns"
        patterns_dir.mkdir()

        # Create test API pattern
        api_patterns = {
            "category": "api",
            "patterns": [
                {
                    "type": "endpoint",
                    "pattern": r"(?:GET|POST|PUT|DELETE|PATCH)\s+(/api/[\w/-]+)",
                    "description": "API endpoint declarations",
                },
                {
                    "type": "route_path",
                    "pattern": r"/api/([\w/-]+)",
                    "description": "API route paths",
                },
                {
                    "type": "status_code",
                    "pattern": r"\b(200|201|204|400|401|403|404|500|502|503)\b",
                    "description": "HTTP status code mentions",
                },
                {
                    "type": "auth",
                    "pattern": r"\b(JWT|token|bearer|API key|authentication|authorization)\b",
                    "description": "Authentication mechanism claims",
                },
            ],
        }

        with open(patterns_dir / "api.json", "w", encoding="utf-8") as f:
            json.dump(api_patterns, f)

        extractor = ClaimExtractor(patterns_dir)

        for claim_text, expected_type, expected_match in test_cases:
            test_file = Path(tmpdir) / "test.md"
            test_file.write_text(claim_text)

            claims = extractor.extract_from_file(test_file)
            assert len(claims) > 0, f"No claims found for: {claim_text}"

            found = any(
                c["type"] == expected_type and expected_match.lower() in c["matched_text"].lower() for c in claims
            )
            seen = [{"type": c["type"], "matched": c["matched_text"]} for c in claims]
            assert found, f"Expected match '{expected_match}' of type '{expected_type}' not found in claims: {seen}"

    print("✓ API pattern tests passed")


def test_architecture_patterns():
    """Test architecture claim extraction."""
    test_cases = [
        ("Backend uses event-driven architecture", "communication", "event-driven"),
        ("SLM control plane is separate from autobot-backend", "separation", "SLM"),
        ("Deployed using Docker and Ansible", "deployment", "Docker"),
        ("Frontend communicates via WebSocket", "component", "frontend"),
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        patterns_dir = Path(tmpdir) / "patterns"
        patterns_dir.mkdir()

        # Create test architecture pattern
        architecture_patterns = {
            "category": "architecture",
            "patterns": [
                {
                    "type": "component",
                    "pattern": r"\b(frontend|backend|control plane|agent loop|workflow engine)\b",
                    "description": "Architectural component mentions",
                },
                {
                    "type": "separation",
                    "pattern": r"\b(SLM|control plane).*separate.*\b(autobot-backend|managed service)",
                    "description": "Component separation claims",
                },
                {
                    "type": "communication",
                    "pattern": r"\b(synchronous|asynchronous|async|event-driven|message-based)\b",
                    "description": "Communication pattern claims",
                },
                {
                    "type": "deployment",
                    "pattern": r"\b(containerized|Docker|Kubernetes|systemd|Ansible)\b",
                    "description": "Deployment architecture claims",
                },
            ],
        }

        with open(patterns_dir / "architecture.json", "w", encoding="utf-8") as f:
            json.dump(architecture_patterns, f)

        extractor = ClaimExtractor(patterns_dir)

        for claim_text, expected_type, expected_match in test_cases:
            test_file = Path(tmpdir) / "test.md"
            test_file.write_text(claim_text)

            claims = extractor.extract_from_file(test_file)
            assert len(claims) > 0, f"No claims found for: {claim_text}"

            found = any(
                c["type"] == expected_type and expected_match.lower() in c["matched_text"].lower() for c in claims
            )
            seen = [{"type": c["type"], "matched": c["matched_text"]} for c in claims]
            assert found, f"Expected match '{expected_match}' of type '{expected_type}' not found in claims: {seen}"

    print("✓ Architecture pattern tests passed")


def test_deduplication():
    """Test claim deduplication."""
    with tempfile.TemporaryDirectory() as tmpdir:
        patterns_dir = Path(tmpdir) / "patterns"
        patterns_dir.mkdir()

        # Simple pattern for testing
        test_patterns = {
            "category": "test",
            "patterns": [
                {
                    "type": "simple",
                    "pattern": r"\bRedis\b",
                    "description": "Test pattern",
                }
            ],
        }

        with open(patterns_dir / "test.json", "w", encoding="utf-8") as f:
            json.dump(test_patterns, f)

        extractor = ClaimExtractor(patterns_dir)

        # Create duplicate claims
        claims = [
            {
                "category": "test",
                "type": "simple",
                "claim": "Redis is used for caching",
                "matched_text": "Redis",
                "source": {"file": "test.md", "line": 1},
                "pattern_description": "Test pattern",
            },
            {
                "category": "test",
                "type": "simple",
                "claim": "Redis is used for caching",
                "matched_text": "Redis",
                "source": {"file": "test.md", "line": 1},
                "pattern_description": "Test pattern",
            },
            {
                "category": "test",
                "type": "simple",
                "claim": "Redis is used for caching",
                "matched_text": "Redis",
                "source": {"file": "other.md", "line": 1},
                "pattern_description": "Test pattern",
            },
        ]

        unique = extractor.deduplicate_claims(claims)
        assert len(unique) == 2, f"Expected 2 unique claims, got {len(unique)}"

    print("✓ Deduplication tests passed")


_PATTERNS_DIR = Path(__file__).parent / "patterns"
_REPO_ROOT = Path(__file__).resolve().parents[3]

# Overlapping matches, URLs, badges, code blocks, short headers, short matches
# and lines no pattern matches -- every branch the extraction loop takes.
_SAMPLE_DOC = """# Title
The backend uses Redis and PostgreSQL on port 8001 with 4 uvicorn workers.
See https://example.com/api/v1/redis for the REST API docs.
[docs](https://example.com/redis)
https://example.com/only-a-url
![build](https://example.com/badge.svg)
```
Redis inside a code block is ignored
```
GET /api/users returns JSON with a JWT token; integrates with Ollama.
Supports streaming voice and multi-modal input via WebSocket.
The control plane runs separate from autobot-backend as an async event bus.
Nothing to see on this line at all.
## A header that is long enough to be scanned, mentioning Docker and Kubernetes and Ansible too
"""


def _reference_extract(extractor, file_path):
    """The extraction loop as it was before #20805: per-line recompiling scan."""
    claims, in_code_block = [], False
    for line_num, line in enumerate(file_path.read_text(encoding="utf-8").split("\n"), start=1):
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            continue
        stripped = line.strip()
        if in_code_block or not stripped:
            continue
        if extractor._is_url_line(line) or extractor._is_badge_line(line):
            continue
        if stripped.startswith("#") and len(stripped) < 100:
            continue
        for category, pattern_data in extractor.patterns.items():
            for pattern_def in pattern_data.get("patterns", []):
                for match in re.finditer(pattern_def["pattern"], line, re.IGNORECASE):
                    urls = re.finditer(r"https?://[^\s\)]+", line)
                    if any(u.start() <= match.start() < u.end() for u in urls):
                        continue
                    if len(match.group(0).strip()) < 2:
                        continue
                    claims.append(extractor._claim(category, pattern_def, line, match, line_num, file_path))
    return claims


def test_compiled_scan_matches_the_reference_scan():
    """The precompiled, prefiltered scan yields exactly the old claims, in order (#20805)."""
    extractor = ClaimExtractor(_PATTERNS_DIR, _REPO_ROOT)
    with tempfile.TemporaryDirectory() as tmpdir:
        sample = Path(tmpdir) / "sample.md"
        sample.write_text(_SAMPLE_DOC, encoding="utf-8")
        expected = _reference_extract(extractor, sample)
        assert len(expected) > 20, "control: the sample must exercise many patterns"
        assert extractor.extract_from_file(sample) == expected
    for doc in (_REPO_ROOT / "README.md", _REPO_ROOT / "CLAUDE.md"):
        if doc.exists():
            assert extractor.extract_from_file(doc) == _reference_extract(extractor, doc), doc


def test_a_line_no_pattern_matches_yields_no_claims():
    """The combined prefilter skips a line only when no single pattern matches it."""
    extractor = ClaimExtractor(_PATTERNS_DIR)
    line = "Nothing to see on this line at all."
    assert not any(regex.search(line) for _, _, regex in extractor._compiled)
    assert extractor._claims_in_line(line, 1, Path("x.md")) == []


if __name__ == "__main__":
    test_infrastructure_patterns()
    test_feature_patterns()
    test_api_patterns()
    test_architecture_patterns()
    test_deduplication()
    print("\n✅ All extraction tests passed!")
