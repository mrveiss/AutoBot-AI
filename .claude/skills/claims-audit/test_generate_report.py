#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for generate-report.py"""
import json
import tempfile
from pathlib import Path
import pytest

# Import functions from generate-report
import sys
sys.path.insert(0, str(Path(__file__).parent))
from generate_report import (
    calculate_percentages,
    format_status_emoji,
    get_category,
    get_github_permalink,
    format_evidence_list,
    generate_summary_section,
    generate_claim_entry,
    group_claims_by_category,
    generate_report,
    load_inventory
)


def test_format_status_emoji():
    """Test status to emoji conversion."""
    assert format_status_emoji('wired') == '✅'
    assert format_status_emoji('partial') == '⚠️'
    assert format_status_emoji('broken') == '❌'
    assert format_status_emoji('unknown') == '❓'


def test_get_category():
    """Test category inference from claim ID."""
    assert get_category('docker-compose-deployment') == 'infrastructure'
    assert get_category('redis-cache-queue') == 'infrastructure'
    assert get_category('fastapi-rest-api') == 'api'
    assert get_category('multi-turn-chat-streaming') == 'features'
    assert get_category('uvicorn-workers') == 'architecture'


def test_get_github_permalink():
    """Test GitHub permalink generation."""
    # With line number
    link = get_github_permalink('README.md', 188)
    assert link == '../README.md#L188'

    # Without line number
    link = get_github_permalink('README.md', None)
    assert link == '../README.md'


def test_calculate_percentages():
    """Test percentage calculation."""
    summary = {
        'total': 17,
        'wired': 13,
        'partial': 3,
        'broken': 1
    }

    percentages = calculate_percentages(summary)

    assert percentages['wired'] == pytest.approx(76.47, abs=0.01)
    assert percentages['partial'] == pytest.approx(17.65, abs=0.01)
    assert percentages['broken'] == pytest.approx(5.88, abs=0.01)


def test_calculate_percentages_zero_total():
    """Test percentage calculation with zero total."""
    summary = {'total': 0}
    percentages = calculate_percentages(summary)

    assert percentages['wired'] == 0.0
    assert percentages['partial'] == 0.0
    assert percentages['broken'] == 0.0


def test_format_evidence_list_empty():
    """Test evidence list formatting with no evidence."""
    assert format_evidence_list([]) == '*(no evidence)*'


def test_format_evidence_list_with_url():
    """Test evidence list formatting with URL."""
    evidence = [
        {
            'kind': 'endpoint',
            'file': 'autobot-backend/api/websockets.py',
            'line': 1,
            'url': 'ws://<host>/ws'
        }
    ]

    result = format_evidence_list(evidence)
    assert 'endpoint' in result
    assert 'ws://<host>/ws' in result
    assert '../autobot-backend/api/websockets.py#L1' in result


def test_format_evidence_list_no_line():
    """Test evidence list formatting without line number."""
    evidence = [
        {
            'kind': 'implementation',
            'file': 'autobot-backend/celery_app.py',
            'line': None
        }
    ]

    result = format_evidence_list(evidence)
    assert 'implementation' in result
    assert '../autobot-backend/celery_app.py' in result


def test_generate_summary_section():
    """Test summary section generation."""
    summary = {
        'total': 17,
        'wired': 13,
        'partial': 3,
        'broken': 1
    }

    percentages = calculate_percentages(summary)
    result = generate_summary_section(summary, percentages)

    assert '## Summary' in result
    assert '✅ wired' in result
    assert '13' in result
    assert '76.5%' in result or '76.4%' in result
    assert '**17**' in result


def test_group_claims_by_category():
    """Test claim grouping by category."""
    claims = [
        {'id': 'fastapi-rest-api', 'capability': 'FastAPI'},
        {'id': 'redis-cache-queue', 'capability': 'Redis'},
        {'id': 'multi-turn-chat', 'capability': 'Chat'},
        {'id': 'uvicorn-workers', 'capability': 'Workers'}
    ]

    grouped = group_claims_by_category(claims)

    assert len(grouped['api']) == 1
    assert len(grouped['infrastructure']) == 1
    assert len(grouped['features']) == 1
    assert len(grouped['architecture']) == 1


def test_generate_claim_entry():
    """Test claim entry generation."""
    claim = {
        'id': 'test-claim',
        'capability': 'Test Capability',
        'claim': 'Test claim text',
        'source': {
            'file': 'README.md',
            'line': 100
        },
        'evidence': [
            {
                'kind': 'endpoint',
                'file': 'autobot-backend/api/test.py',
                'line': 50
            }
        ],
        'status': 'wired',
        'notes': 'Test notes'
    }

    result = generate_claim_entry(1, claim)

    assert '| 1 ' in result
    assert 'Test Capability' in result
    assert 'Test claim text' in result
    assert 'README.md:100' in result
    assert '✅ wired' in result
    assert 'Test notes' in result


def test_generate_report_complete():
    """Test complete report generation."""
    inventory = {
        'meta': {
            'generated_at': '2026-05-26',
            'source_issue': 'https://github.com/mrveiss/AutoBot-AI/issues/7359'
        },
        'summary': {
            'total': 3,
            'wired': 2,
            'partial': 1,
            'broken': 0
        },
        'claims': [
            {
                'id': 'fastapi-rest-api',
                'capability': 'FastAPI REST API',
                'claim': 'Backend API server',
                'source': {
                    'file': 'README.md',
                    'line': 188
                },
                'evidence': [
                    {
                        'kind': 'implementation',
                        'file': 'autobot-backend/main.py',
                        'line': 1
                    }
                ],
                'status': 'wired',
                'notes': 'Fully implemented'
            },
            {
                'id': 'redis-cache',
                'capability': 'Redis Cache',
                'claim': 'Redis caching',
                'source': {
                    'file': 'README.md',
                    'line': 134
                },
                'evidence': [
                    {
                        'kind': 'service',
                        'file': 'docker-compose.yml',
                        'line': 87
                    }
                ],
                'status': 'wired',
                'notes': 'Docker service'
            },
            {
                'id': 'test-feature',
                'capability': 'Test Feature',
                'claim': 'Test claim',
                'source': {
                    'file': 'README.md',
                    'line': 200
                },
                'evidence': [],
                'status': 'partial',
                'notes': 'Partially implemented'
            }
        ]
    }

    report = generate_report(inventory)

    # Check header
    assert '# AutoBot Capability Verification' in report
    assert '2026-05-26' in report

    # Check summary
    assert '## Summary' in report
    assert '✅ wired' in report
    assert '2' in report
    assert '⚠️ partial' in report
    assert '1' in report

    # Check categories
    assert '## Api' in report or '## Infrastructure' in report or '## Features' in report

    # Check footer
    assert '## How to Regenerate' in report
    assert 'claude /claims-audit' in report


def test_load_inventory(tmp_path):
    """Test inventory loading from file."""
    inventory_data = {
        'meta': {'generated_at': '2026-05-26'},
        'summary': {'total': 1},
        'claims': []
    }

    inventory_file = tmp_path / 'test-inventory.json'
    with inventory_file.open('w', encoding='utf-8') as f:
        json.dump(inventory_data, f)

    loaded = load_inventory(inventory_file)

    assert loaded['meta']['generated_at'] == '2026-05-26'
    assert loaded['summary']['total'] == 1


def test_generate_report_with_discovery_issue():
    """Test report generation with discovery issue link."""
    inventory = {
        'meta': {
            'generated_at': '2026-05-26',
            'source_issue': ''
        },
        'summary': {
            'total': 1,
            'wired': 0,
            'partial': 0,
            'broken': 1
        },
        'claims': [
            {
                'id': 'broken-feature',
                'capability': 'Broken Feature',
                'claim': 'This is broken',
                'source': {
                    'file': 'README.md',
                    'line': 100
                },
                'evidence': [],
                'status': 'broken',
                'notes': 'Not implemented',
                'discovery_issue': 'https://github.com/mrveiss/AutoBot-AI/issues/9999'
            }
        ]
    }

    report = generate_report(inventory)

    assert '## Discovery Issues Filed' in report
    assert 'Broken Feature' in report
    assert 'https://github.com/mrveiss/AutoBot-AI/issues/9999' in report


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
