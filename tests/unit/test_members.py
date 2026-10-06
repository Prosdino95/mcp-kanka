"""Unit tests for organisation members and the unwritable-field guard."""

from unittest.mock import MagicMock, patch

import pytest

from mcp_kanka.operations import KankaOperations
from mcp_kanka.service import KankaService


def make_service():
    """Build a KankaService with a mocked client."""
    with (
        patch("mcp_kanka.service.KankaClient") as mock_client_class,
        patch.dict(
            "os.environ", {"KANKA_TOKEN": "test-token", "KANKA_CAMPAIGN_ID": "123"}
        ),
    ):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        service = KankaService()

    service.client = mock_client
    return service, mock_client


class FakeEntity:
    """Minimal stand-in for a python-kanka entity model."""

    id = 1
    entity_id = 4
    name = "Raven"
    type = None
    entry = None
    tags: list[int] = []
    is_private = False
    created_at = None
    updated_at = None
    image = None
    image_full = None
    image_thumb = None
    image_uuid = None
    header_uuid = None


def entity_payload(entity_id, api_type, type_id):
    """Build an /entities/{id} response as the API returns it."""
    return {
        "id": entity_id,
        "type": api_type,
        "child": {"id": type_id, "name": "Test"},
    }


class TestUnwritableFields:
    """Fields the API accepts and silently ignores must be rejected."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service, self.mock_client = make_service()

    def test_create_rejects_members_field(self):
        """Test that 'members' in fields raises instead of doing nothing."""
        with pytest.raises(ValueError, match="silently ignores"):
            self.service.create_entity(
                entity_type="organization",
                name="I Veglianti",
                fields={"members": [10]},
            )

        self.mock_client.organisations.create.assert_not_called()

    def test_error_names_the_replacement_tool(self):
        """Test that the error says what to use instead."""
        with pytest.raises(ValueError, match="create_members"):
            self.service.create_entity(
                entity_type="organization",
                name="I Veglianti",
                fields={"members": [10]},
            )

    def test_other_fields_still_pass_through(self):
        """Test that ordinary arbitrary fields are untouched by the guard."""
        self.mock_client.characters.create.return_value = FakeEntity()

        self.service.create_entity(
            entity_type="character",
            name="Raven",
            fields={"title": "Sovrintendente", "age": "31"},
        )

        _, kwargs = self.mock_client.characters.create.call_args
        assert kwargs["title"] == "Sovrintendente"
        assert kwargs["age"] == "31"


class TestServiceMembers:
    """Membership operations translate entity_ids into type-specific IDs."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service, self.mock_client = make_service()

    def test_create_member_resolves_both_entity_ids(self):
        """Test that both sides are resolved before calling the API."""
        self.mock_client.entity.side_effect = [
            entity_payload(45, "organisation", 2),
            entity_payload(58, "character", 10),
        ]
        self.mock_client.organisations.add_member.return_value = MagicMock(id=7)

        result = self.service.create_member(45, 58, role="Sovrintendente")

        self.mock_client.organisations.add_member.assert_called_once_with(
            2, 10, role="Sovrintendente", is_private=False
        )
        assert result == {
            "member_id": 7,
            "organisation_entity_id": 45,
            "character_entity_id": 58,
        }

    def test_create_member_rejects_wrong_entity_type(self):
        """Test that passing a location as the organisation fails clearly."""
        self.mock_client.entity.return_value = entity_payload(2, "location", 2)

        with pytest.raises(ValueError, match="is a location, expected a organisation"):
            self.service.create_member(2, 58)

        self.mock_client.organisations.add_member.assert_not_called()

    def test_create_member_does_not_swallow_api_errors(self):
        """Test that an API failure propagates instead of becoming 'not found'."""
        self.mock_client.entity.side_effect = RuntimeError(
            "Invalid authentication token"
        )

        with pytest.raises(RuntimeError, match="Invalid authentication token"):
            self.service.create_member(45, 58)

    def test_update_member_sends_only_the_organisation_lookup(self):
        """Test that updating a role resolves just the organisation."""
        self.mock_client.entity.return_value = entity_payload(45, "organisation", 2)

        assert self.service.update_member(45, 7, role="Guardiano") is True

        self.mock_client.organisations.update_member.assert_called_once_with(
            2, 7, role="Guardiano", is_private=None
        )

    def test_delete_member(self):
        """Test removing a membership."""
        self.mock_client.entity.return_value = entity_payload(45, "organisation", 2)

        assert self.service.delete_member(45, 7) is True

        self.mock_client.organisations.remove_member.assert_called_once_with(2, 7)


class TestOperationsMembers:
    """The batch layer reports one result per membership."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_service = MagicMock()
        self.operations = KankaOperations(service=self.mock_service)

    @pytest.mark.asyncio
    async def test_create_members_reports_each_failure_separately(self):
        """Test that one failure does not hide the other results."""
        self.mock_service.create_member.side_effect = [
            {
                "member_id": 7,
                "organisation_entity_id": 45,
                "character_entity_id": 58,
            },
            ValueError("Entity 99 is a location, expected a character"),
        ]

        results = await self.operations.create_members(
            [
                {"organisation_entity_id": 45, "character_entity_id": 58},
                {"organisation_entity_id": 45, "character_entity_id": 99},
            ]
        )

        assert results[0]["success"] is True
        assert results[0]["member_id"] == 7
        assert results[1]["success"] is False
        assert results[1]["member_id"] is None
        assert "expected a character" in results[1]["error"]

    @pytest.mark.asyncio
    async def test_delete_members(self):
        """Test removing memberships in batch."""
        self.mock_service.delete_member.return_value = True

        results = await self.operations.delete_members(
            [{"organisation_entity_id": 45, "member_id": 7}]
        )

        assert results == [
            {
                "organisation_entity_id": 45,
                "member_id": 7,
                "success": True,
                "error": None,
            }
        ]
