"""Unit tests for entity relations."""

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


def fake_relation(relation_id=12, target_id=116, mirror_id=None, visibility_id=1):
    """Build a stand-in for a python-kanka Relation."""
    relation = MagicMock()
    relation.id = relation_id
    relation.owner_id = 115
    relation.target_id = target_id
    relation.relation = "allea con"
    relation.attitude = 50
    relation.visibility_id = visibility_id
    relation.mirror_id = mirror_id
    return relation


class TestServiceRelations:
    """Relations are entity_id on both sides, so nothing is translated."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service, self.mock_client = make_service()
        self.manager = self.mock_client.characters

    def test_create_relation_maps_is_hidden_to_visibility(self):
        """Test that is_hidden becomes visibility_id 2, like posts."""
        self.manager.create_relation.return_value = fake_relation(mirror_id=13)

        result = self.service.create_relation(
            115, 116, "allea con", attitude=50, is_hidden=True, two_way=True
        )

        self.manager.create_relation.assert_called_once_with(
            115, 116, "allea con", attitude=50, visibility_id=2, two_way=True
        )
        assert result == {
            "relation_id": 12,
            "entity_id": 115,
            "target_entity_id": 116,
            "mirror_id": 13,
        }

    def test_create_relation_defaults_to_one_direction(self):
        """Test that a relation is one-directional unless asked otherwise."""
        self.manager.create_relation.return_value = fake_relation()

        self.service.create_relation(115, 116, "conosce")

        _, kwargs = self.manager.create_relation.call_args
        assert kwargs["two_way"] is False
        assert kwargs["visibility_id"] == 1

    def test_delete_relation_removes_the_mirror_by_default(self):
        """Test that both sides go, so no half relation is left behind."""
        self.manager.list_relations.return_value = [fake_relation(mirror_id=13)]

        result = self.service.delete_relation(115, 12)

        assert self.manager.delete_relation.call_args_list[0].args == (115, 12)
        assert self.manager.delete_relation.call_args_list[1].args == (116, 13)
        assert result["mirror_deleted"] is True

    def test_delete_relation_without_mirror_does_one_call(self):
        """Test that a one-directional relation costs a single delete."""
        self.manager.list_relations.return_value = [fake_relation(mirror_id=None)]

        result = self.service.delete_relation(115, 12)

        assert self.manager.delete_relation.call_count == 1
        assert result["mirror_deleted"] is False

    def test_delete_mirror_false_skips_the_lookup(self):
        """Test that opting out avoids the extra request."""
        result = self.service.delete_relation(115, 12, delete_mirror=False)

        self.manager.list_relations.assert_not_called()
        assert self.manager.delete_relation.call_count == 1
        assert result["mirror_deleted"] is False

    def test_failing_mirror_deletion_says_the_link_is_half_removed(self):
        """Test that a partial deletion is reported, not swallowed."""
        self.manager.list_relations.return_value = [fake_relation(mirror_id=13)]
        self.manager.delete_relation.side_effect = [None, RuntimeError("boom")]

        with pytest.raises(ValueError, match="half removed"):
            self.service.delete_relation(115, 12)

    def test_relation_to_dict_translates_visibility(self):
        """Test that visibility_id 2 reads back as is_hidden."""
        as_dict = self.service._relation_to_dict(
            fake_relation(mirror_id=13, visibility_id=2)
        )

        assert as_dict == {
            "relation_id": 12,
            "target_entity_id": 116,
            "relation": "allea con",
            "attitude": 50,
            "is_hidden": True,
            "mirror_id": 13,
        }


class TestOperationsRelations:
    """The batch layer reports one result per relation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_service = MagicMock()
        self.operations = KankaOperations(service=self.mock_service)

    @pytest.mark.asyncio
    async def test_create_relations_reports_each_failure_separately(self):
        """Test that one failure does not hide the other results."""
        self.mock_service.create_relation.side_effect = [
            {
                "relation_id": 12,
                "entity_id": 115,
                "target_entity_id": 116,
                "mirror_id": None,
            },
            ValueError("Resource not found: entities/999999"),
        ]

        results = await self.operations.create_relations(
            [
                {"entity_id": 115, "target_entity_id": 116, "relation": "allea con"},
                {"entity_id": 115, "target_entity_id": 999999, "relation": "conosce"},
            ]
        )

        assert results[0]["success"] is True
        assert results[0]["relation_id"] == 12
        assert results[1]["success"] is False
        assert results[1]["relation_id"] is None
        assert "999999" in results[1]["error"]

    @pytest.mark.asyncio
    async def test_delete_relations_reports_the_mirror(self):
        """Test that the caller learns whether the mirror went too."""
        self.mock_service.delete_relation.return_value = {
            "entity_id": 115,
            "relation_id": 12,
            "mirror_deleted": True,
        }

        results = await self.operations.delete_relations(
            [{"entity_id": 115, "relation_id": 12}]
        )

        assert results[0]["mirror_deleted"] is True
        assert results[0]["success"] is True

    @pytest.mark.asyncio
    async def test_get_entities_includes_relations_on_request(self):
        """Test that include_relations reaches the service and the result."""
        self.mock_service.get_entity_by_id.return_value = {
            "id": 1,
            "entity_id": 115,
            "name": "Raven",
            "entity_type": "character",
            "relations": [{"relation_id": 12, "relation": "allea con"}],
        }

        results = await self.operations.get_entities([115], include_relations=True)

        self.mock_service.get_entity_by_id.assert_called_once_with(115, False, True)
        assert results[0]["relations"][0]["relation_id"] == 12
