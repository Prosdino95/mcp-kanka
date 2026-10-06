"""Resources provided by the Kanka MCP server."""

import json

from .types import KankaContext


def get_kanka_context() -> str:
    """
    Get the Kanka context resource.

    Returns:
        JSON string with Kanka context information
    """
    context: KankaContext = {
        "description": "Kanka is a worldbuilding and campaign management tool. This MCP server provides limited access to manage core entity types and their descriptions.",
        "supported_entities": {
            "character": "People in your world (PCs, NPCs, etc)",
            "creature": "Monster types and animals (templates, not individuals)",
            "location": "Places, regions, buildings, landmarks",
            "organization": "Groups, guilds, governments, companies",
            "race": "Species and ancestries",
            "note": "Private GM notes and session digests",
            "journal": "Session summaries and campaign chronicles",
            "quest": "Missions, objectives, and story arcs",
            "event": "Things that happened, with an optional date field",
            "ability": "Spells, powers, feats and other named capabilities",
            "item": "Objects, equipment and treasure",
            "timeline": (
                "Chronologies of the world. Their eras live on a separate "
                "endpoint and cannot be written yet"
            ),
            "family": "Bloodlines, houses, and clans",
            "tag": (
                "Labels used to categorise entities. Also usable by name "
                "through the tags field on any entity. Their colour field "
                "accepts only: aqua, black, brown, grey, green, light-blue, "
                "maroon, navy, orange, pink, purple, red, teal, yellow"
            ),
        },
        "core_fields": {
            "name": "Required. The entity's name",
            "type": "Optional. Subtype like 'NPC', 'City', 'Guild' (user-defined)",
            "entry": "Optional. Main description in Markdown format",
            "tags": "Optional. String array for categorization",
            "is_hidden": "Optional. If true, hidden from players (admin-only)",
        },
        "terminology": {
            "entity_type": "The main category (character, location, etc.) - fixed list",
            "type": "User-defined subtype within a category (e.g., 'NPC' for characters, 'City' for locations)",
        },
        "posts": "Additional notes/comments can be attached to any entity",
        "mentions": {
            "description": "Cross-reference entities using [entity:ID] or [entity:ID|custom text] in entry fields",
            "examples": ["[entity:1234]", "[entity:1234|the ancient dragon]"],
            "note": "The MCP server preserves these during Markdown/HTML conversion",
        },
        "limitations": "Entity-specific fields are written through the fields parameter. Attributes and inventory live on their own endpoints and are not available yet; organisation members and relations are, through the member and relation tools. Relations are directed: create them with two_way to have both sides, and read them with include_relations on get_entities to get the relation_id needed to change them. A search that does not name an entity_type does not cover tags, abilities, items or timelines: name the type to search those.",
    }

    return json.dumps(context, indent=2)
