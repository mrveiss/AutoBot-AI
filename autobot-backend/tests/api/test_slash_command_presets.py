"""Tests for slash command presets API (GH#8595, MVA-1615)."""

import uuid
from datetime import datetime, timezone

import pytest

from api.slash_command_presets import (
    SlashCommandPresetCreate,
    SlashCommandPresetResponse,
    SlashCommandPresetUpdate,
)
from models.slash_command_preset import SlashCommandPreset


class TestSlashCommandPresetsModel:
    """Test SlashCommandPreset model."""

    def test_preset_model_creation(self) -> None:
        """Test creating a SlashCommandPreset model instance."""
        preset_id = uuid.uuid4()
        user_id = "test_user"
        org_id = uuid.uuid4()

        preset = SlashCommandPreset(
            id=preset_id,
            command="test_cmd",
            description="Test command",
            prompt_template="Answer: {query}",
            user_id=user_id,
            org_id=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        assert preset.id == preset_id
        assert preset.command == "test_cmd"
        assert preset.description == "Test command"
        assert preset.prompt_template == "Answer: {query}"
        assert preset.user_id == user_id
        assert preset.org_id is None

    def test_personal_preset_repr(self) -> None:
        """Test repr for personal preset."""
        preset = SlashCommandPreset(
            command="test_cmd",
            description="Test",
            prompt_template="Test",
            user_id="test_user",
            org_id=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        repr_str = repr(preset)
        assert "test_cmd" in repr_str
        assert "test_user" in repr_str

    def test_org_preset_repr(self) -> None:
        """Test repr for org preset."""
        org_id = uuid.uuid4()
        preset = SlashCommandPreset(
            command="org_cmd",
            description="Org",
            prompt_template="Org template",
            user_id=None,
            org_id=org_id,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        repr_str = repr(preset)
        assert "org_cmd" in repr_str
        assert str(org_id) in repr_str


class TestSlashCommandPresetsValidation:
    """Test request/response model validation."""

    def test_command_slug_validation_valid(self) -> None:
        """Test that valid command slugs are accepted."""
        valid_commands = ["simple_cmd", "cmd_2", "test_123", "a", "_private", "lowercase"]

        for cmd in valid_commands:
            payload = SlashCommandPresetCreate(
                command=cmd,
                description="Test",
                prompt_template="Test template",
                org_id=None,
            )
            assert payload.command == cmd

    def test_command_slug_validation_invalid_uppercase(self) -> None:
        """Test that uppercase commands are rejected."""
        with pytest.raises(ValueError):
            SlashCommandPresetCreate(
                command="InvalidCmd",
                description="Test",
                prompt_template="Test",
                org_id=None,
            )

    def test_command_slug_validation_invalid_dash(self) -> None:
        """Test that dashes are rejected."""
        with pytest.raises(ValueError):
            SlashCommandPresetCreate(
                command="cmd-name",
                description="Test",
                prompt_template="Test",
                org_id=None,
            )

    def test_command_slug_validation_invalid_special_chars(self) -> None:
        """Test that special characters are rejected."""
        invalid_commands = ["cmd@123", "cmd 123", "cmd.name", "cmd/test", ""]

        for cmd in invalid_commands:
            with pytest.raises(ValueError):
                SlashCommandPresetCreate(
                    command=cmd,
                    description="Test",
                    prompt_template="Test",
                    org_id=None,
                )

    def test_create_payload_field_validation(self) -> None:
        """Test that create payload validates field lengths."""
        with pytest.raises(ValueError):
            SlashCommandPresetCreate(
                command="",  # Empty command
                description="Test",
                prompt_template="Test",
                org_id=None,
            )

        with pytest.raises(ValueError):
            SlashCommandPresetCreate(
                command="valid_cmd",
                description="",  # Empty description
                prompt_template="Test",
                org_id=None,
            )

        with pytest.raises(ValueError):
            SlashCommandPresetCreate(
                command="valid_cmd",
                description="Test",
                prompt_template="",  # Empty template
                org_id=None,
            )

    def test_update_payload_validation(self) -> None:
        """Test update payload validation (optional fields with non-empty checks)."""
        # Valid: all None
        update1 = SlashCommandPresetUpdate()
        assert update1.description is None
        assert update1.prompt_template is None

        # Valid: some fields set
        update2 = SlashCommandPresetUpdate(description="Updated", prompt_template=None)
        assert update2.description == "Updated"
        assert update2.prompt_template is None

        # Invalid: empty string
        with pytest.raises(ValueError):
            SlashCommandPresetUpdate(description="")

        with pytest.raises(ValueError):
            SlashCommandPresetUpdate(prompt_template="")

    def test_response_model_structure(self) -> None:
        """Test that response model includes all required fields."""
        response_fields = SlashCommandPresetResponse.model_fields.keys()

        required_fields = {
            "id",
            "org_id",
            "user_id",
            "command",
            "description",
            "prompt_template",
            "created_at",
            "updated_at",
        }

        assert required_fields.issubset(response_fields)

    def test_response_model_from_orm(self) -> None:
        """Test that response model can be created from ORM objects."""
        preset = SlashCommandPreset(
            id=uuid.uuid4(),
            command="test_cmd",
            description="Test",
            prompt_template="Template",
            user_id="test_user",
            org_id=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        response = SlashCommandPresetResponse.model_validate(preset)
        assert response.command == "test_cmd"
        assert response.user_id == "test_user"
        assert response.org_id is None

    def test_response_flags_org_presets(self) -> None:
        """Test that response model flags org presets via org_id field."""
        org_id = uuid.uuid4()

        # Org preset
        org_preset = SlashCommandPreset(
            id=uuid.uuid4(),
            command="org_cmd",
            description="Org",
            prompt_template="Org",
            user_id=None,
            org_id=org_id,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        response = SlashCommandPresetResponse.model_validate(org_preset)
        assert response.org_id == org_id
        assert response.user_id is None

        # Personal preset
        personal_preset = SlashCommandPreset(
            id=uuid.uuid4(),
            command="personal_cmd",
            description="Personal",
            prompt_template="Personal",
            user_id="user123",
            org_id=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        response = SlashCommandPresetResponse.model_validate(personal_preset)
        assert response.org_id is None
        assert response.user_id == "user123"


class TestSlashCommandPresetsScoping:
    """Test preset scoping logic (personal vs org)."""

    def test_personal_preset_fields(self) -> None:
        """Test that personal presets have user_id and no org_id."""
        preset = SlashCommandPreset(
            command="personal",
            description="Personal",
            prompt_template="Personal",
            user_id="user_123",
            org_id=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        assert preset.user_id == "user_123"
        assert preset.org_id is None

    def test_org_preset_fields(self) -> None:
        """Test that org presets have org_id and no user_id."""
        org_id = uuid.uuid4()

        preset = SlashCommandPreset(
            command="org_preset",
            description="Org",
            prompt_template="Org",
            user_id=None,
            org_id=org_id,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        assert preset.user_id is None
        assert preset.org_id == org_id

    def test_command_uniqueness_constraint_definition(self) -> None:
        """Test that model defines uniqueness constraint for (org_id, user_id, command)."""
        # The __table_args__ should contain UniqueConstraint
        table_args = SlashCommandPreset.__table_args__
        assert isinstance(table_args, tuple)

        # Find the unique constraint
        unique_constraint = None
        for arg in table_args:
            if hasattr(arg, "name") and arg.name == "uq_scope_command":
                unique_constraint = arg
                break

        assert unique_constraint is not None
        constraint_columns = {c.name for c in unique_constraint.columns}
        assert constraint_columns == {"org_id", "user_id", "command"}


# Co-Authored-By: Paperclip <noreply@paperclip.ing>
