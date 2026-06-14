# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for file-issues.py
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Import the module under test
import sys
sys.path.insert(0, str(Path(__file__).parent))
from file_issues import (
    load_inventory,
    save_inventory,
    check_duplicate_issue,
    create_issue_body,
    process_broken_claims,
)


@pytest.fixture
def sample_inventory():
    """Sample verification inventory for testing."""
    return {
        "meta": {
            "generated_at": "2026-06-03",
            "generated_by": "claims-audit skill",
            "source_issue": "https://github.com/mrveiss/AutoBot-AI/issues/7359",
            "schema_version": "1"
        },
        "summary": {
            "total": 3,
            "wired": 1,
            "partial": 0,
            "broken": 2
        },
        "claims": [
            {
                "id": "test-wired-claim",
                "capability": "Test Wired Feature",
                "claim": "This feature works perfectly",
                "source": {"file": "README.md", "line": 100},
                "status": "wired",
                "evidence": [
                    {"kind": "endpoint", "file": "api/test.py", "line": 50}
                ]
            },
            {
                "id": "test-broken-claim",
                "capability": "Test Broken Feature",
                "claim": "This feature is broken",
                "source": {"file": "docs/test.md", "line": 42},
                "status": "broken",
                "notes": "Implementation exists but endpoint is missing",
                "evidence": [
                    {"kind": "implementation", "file": "services/test.py", "line": 10}
                ]
            },
            {
                "id": "test-broken-filed",
                "capability": "Test Already Filed",
                "claim": "This was already filed",
                "source": {"file": "docs/test.md", "line": 50},
                "status": "broken",
                "notes": "Already has a discovery issue",
                "discovery_issue": "https://github.com/mrveiss/AutoBot-AI/issues/9999"
            }
        ]
    }


class TestLoadSaveInventory:
    """Test inventory loading and saving."""

    def test_load_inventory_success(self, sample_inventory, tmp_path):
        """Test loading a valid inventory file."""
        inventory_path = tmp_path / "inventory.json"
        with open(inventory_path, 'w', encoding='utf-8') as f:
            json.dump(sample_inventory, f)

        loaded = load_inventory(inventory_path)
        assert loaded == sample_inventory

    def test_load_inventory_not_found(self):
        """Test loading a non-existent inventory file."""
        with pytest.raises(FileNotFoundError):
            load_inventory(Path("/nonexistent/path.json"))

    def test_save_inventory(self, sample_inventory, tmp_path):
        """Test saving inventory to file."""
        inventory_path = tmp_path / "inventory.json"
        save_inventory(sample_inventory, inventory_path)

        # Verify file was created and contains correct data
        assert inventory_path.exists()
        with open(inventory_path, encoding='utf-8') as f:
            loaded = json.load(f)
        assert loaded == sample_inventory


class TestCheckDuplicateIssue:
    """Test duplicate issue checking."""

    @patch('subprocess.run')
    def test_check_duplicate_found(self, mock_run):
        """Test when a duplicate issue is found."""
        mock_run.return_value = MagicMock(
            stdout=json.dumps([
                {
                    "url": "https://github.com/mrveiss/AutoBot-AI/issues/1234",
                    "title": "discovery(docs): Test Capability not verified"
                }
            ]),
            returncode=0
        )

        result = check_duplicate_issue("Test Capability", "Some claim text")
        assert result == "https://github.com/mrveiss/AutoBot-AI/issues/1234"
        mock_run.assert_called_once()

    @patch('subprocess.run')
    def test_check_duplicate_not_found(self, mock_run):
        """Test when no duplicate is found."""
        mock_run.return_value = MagicMock(
            stdout=json.dumps([]),
            returncode=0
        )

        result = check_duplicate_issue("Test Capability", "Some claim text")
        assert result is None

    @patch('subprocess.run')
    def test_check_duplicate_command_error(self, mock_run):
        """Test error handling when gh command fails."""
        mock_run.side_effect = Exception("Command failed")

        result = check_duplicate_issue("Test Capability", "Some claim text")
        assert result is None


class TestCreateIssueBody:
    """Test issue body generation."""

    def test_create_issue_body_with_evidence(self):
        """Test creating issue body with evidence."""
        claim_data = {
            "capability": "Test Feature",
            "claim": "This is a test claim",
            "source": {"file": "README.md", "line": 42},
            "notes": "Implementation exists but not wired",
            "evidence": [
                {"kind": "implementation", "file": "test.py", "line": 10}
            ]
        }

        body = create_issue_body(claim_data)

        # Verify key sections are present
        assert "## Finding" in body
        assert "**Capability:** Test Feature" in body
        assert "**Claim source:** [README.md:42]" in body
        assert "**Status:** ❌ broken" in body
        assert "## Evidence" in body
        assert "implementation: `test.py:10`" in body
        assert "## Details" in body
        assert "Implementation exists but not wired" in body
        assert "## Suggested Fix" in body
        assert "## Related" in body
        assert "Filed by `/claims-audit`" in body

    def test_create_issue_body_no_evidence(self):
        """Test creating issue body without evidence."""
        claim_data = {
            "capability": "Test Feature",
            "claim": "This is a test claim",
            "source": {"file": "README.md", "line": 42},
            "notes": "Nothing found",
            "evidence": []
        }

        body = create_issue_body(claim_data)
        assert "**No evidence found**" in body


class TestProcessBrokenClaims:
    """Test processing broken claims."""

    def test_process_broken_claims_dry_run(self, sample_inventory):
        """Test processing in dry-run mode."""
        with patch('file_issues.file_issue') as mock_file:
            mock_file.return_value = None

            filed = process_broken_claims(sample_inventory, dry_run=True)

            # Should process the one broken claim without discovery_issue
            assert mock_file.call_count == 1
            assert len(filed) == 0  # dry run returns no URLs

    @patch('file_issues.check_duplicate_issue')
    @patch('subprocess.run')
    def test_process_broken_claims_files_new_issue(
        self, mock_run, mock_check_dup, sample_inventory
    ):
        """Test filing a new issue for broken claim."""
        # No duplicate found
        mock_check_dup.return_value = None

        # gh issue create succeeds
        mock_run.return_value = MagicMock(
            stdout="https://github.com/mrveiss/AutoBot-AI/issues/5555\n",
            returncode=0
        )

        filed = process_broken_claims(sample_inventory, dry_run=False)

        assert len(filed) == 1
        assert filed[0]['capability'] == "Test Broken Feature"
        assert filed[0]['url'] == "https://github.com/mrveiss/AutoBot-AI/issues/5555"

        # Verify the inventory was updated
        broken_claim = next(
            c for c in sample_inventory['claims']
            if c['id'] == 'test-broken-claim'
        )
        assert broken_claim['discovery_issue'] == "https://github.com/mrveiss/AutoBot-AI/issues/5555"

    def test_process_broken_claims_skips_already_filed(self, sample_inventory):
        """Test that already-filed claims are skipped."""
        with patch('file_issues.file_issue') as mock_file:
            filed = process_broken_claims(sample_inventory, dry_run=False)

            # Should only process the one claim without discovery_issue
            # The claim with existing discovery_issue should be skipped
            assert mock_file.call_count == 1

    def test_process_broken_claims_skips_wired(self, sample_inventory):
        """Test that wired claims are not processed."""
        with patch('file_issues.file_issue') as mock_file:
            filed = process_broken_claims(sample_inventory, dry_run=False)

            # Should not process wired claims
            assert all(c['capability'] != "Test Wired Feature" for c in filed)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
