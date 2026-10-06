"""Unit tests for the set of supported entity types."""

from unittest.mock import MagicMock, patch

import pytest

from mcp_kanka.operations import (
    ALL_ENTITY_TYPES,
    UNTYPED_SEARCH_EXCLUDED,
    UNTYPED_SEARCH_TYPES,
    KankaOperations,
)
from mcp_kanka.service import KankaService


class FakeEntity:
    """Minimal stand-in for a python-kanka entity model."""

    id = 1
    entity_id = 4
    name = "Sottosuolo"
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


class TestSupportedTypes:
    """The type lists and the service maps must not drift apart."""

    def test_new_types_are_supported(self):
        """Test that the types added after the first eight are supported."""
        for entity_type in ("event", "family", "tag", "ability", "item", "timeline"):
            assert entity_type in ALL_ENTITY_TYPES

    def test_maps_cover_every_supported_type(self):
        """Test that no map forgets a type, which would break reads."""
        assert set(KankaService.API_ENDPOINT_MAP) == set(ALL_ENTITY_TYPES)
        assert set(KankaService.ENTITY_TYPE_MAP) == set(ALL_ENTITY_TYPES)
        assert set(KankaService.API_TYPE_MAP.values()) == set(ALL_ENTITY_TYPES)

    def test_untyped_search_leaves_the_excluded_types_out(self):
        """Test that excluded types are searched only when named explicitly."""
        assert {"tag", "ability", "item", "timeline"} == UNTYPED_SEARCH_EXCLUDED
        assert set(UNTYPED_SEARCH_TYPES) == set(ALL_ENTITY_TYPES) - UNTYPED_SEARCH_EXCLUDED
        assert set(ALL_ENTITY_TYPES) >= UNTYPED_SEARCH_EXCLUDED

    @pytest.mark.asyncio
    async def test_untyped_search_skips_excluded_types(self):
        """Test that an untyped search never hits the excluded endpoints."""
        mock_service = MagicMock()
        mock_service.list_entities.return_value = []
        operations = KankaOperations(service=mock_service)

        await operations.find_entities(name="Nimuen")

        searched = [call.args[0] for call in mock_service.list_entities.call_args_list]
        assert not UNTYPED_SEARCH_EXCLUDED & set(searched)
        assert "character" in searched


class TestTagCacheInvalidation:
    """Changing a tag entity must not leave a stale name-to-ID cache."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service, self.mock_client = make_service()
        self.service._tag_cache = {"vecchio": MagicMock(id=99)}

    def test_creating_a_tag_clears_the_cache(self):
        """Test that a new tag entity invalidates the cache."""
        self.mock_client.tags.create.return_value = FakeEntity()

        self.service.create_entity(entity_type="tag", name="Sottosuolo")

        assert self.service._tag_cache == {}

    def test_creating_another_type_keeps_the_cache(self):
        """Test that unrelated creates leave the cache alone."""
        self.mock_client.characters.create.return_value = FakeEntity()

        self.service.create_entity(entity_type="character", name="Raven")

        assert "vecchio" in self.service._tag_cache

    def test_renaming_a_tag_clears_the_cache(self):
        """Test that a renamed tag invalidates the cache."""
        self.service.get_entity_by_id = MagicMock(
            return_value={"id": 1, "entity_id": 4, "entity_type": "tag"}
        )

        self.service.update_entity(entity_id=4, name="Nuovo nome")

        assert self.service._tag_cache == {}

    def test_deleting_a_tag_clears_the_cache(self):
        """Test that a deleted tag invalidates the cache."""
        self.service.get_entity_by_id = MagicMock(
            return_value={"id": 1, "entity_id": 4, "entity_type": "tag"}
        )

        self.service.delete_entity(entity_id=4)

        assert self.service._tag_cache == {}
