#!/usr/bin/env python3
"""
Kanka MCP Server

An MCP server that provides tools for interacting with Kanka campaigns.
"""

import asyncio
import contextlib
import hmac
import logging
import os
from collections.abc import AsyncIterator
from typing import Any

import mcp.server.stdio
import mcp.types as types
import uvicorn
from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import AnyUrl
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route
from starlette.types import Receive, Scope, Send

from .resources import get_kanka_context
from .tools import (
    handle_check_entity_updates,
    handle_create_entities,
    handle_create_members,
    handle_create_posts,
    handle_create_relations,
    handle_delete_entities,
    handle_delete_members,
    handle_delete_posts,
    handle_delete_relations,
    handle_find_entities,
    handle_get_entities,
    handle_update_entities,
    handle_update_members,
    handle_update_posts,
    handle_update_relations,
)

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=os.getenv("MCP_LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Create the MCP server instance
app: Server[None] = Server("mcp-kanka")


@app.list_resources()  # type: ignore[no-untyped-call, untyped-decorator]
async def list_resources() -> list[types.Resource]:
    """List available resources."""
    return [
        types.Resource(
            uri=AnyUrl("kanka://context"),
            name="Kanka Context",
            description="Information about Kanka's structure and this MCP server's capabilities",
            mimeType="application/json",
        )
    ]


@app.read_resource()  # type: ignore[no-untyped-call, untyped-decorator]
async def read_resource(uri: str) -> str:
    """Read a resource by URI."""
    if uri == "kanka://context":
        return get_kanka_context()
    raise ValueError(f"Unknown resource: {uri}")


@app.list_tools()  # type: ignore[no-untyped-call, untyped-decorator]
async def list_tools() -> list[types.Tool]:
    """List available tools."""
    return [
        types.Tool(
            name="find_entities",
            description="Find entities by search and/or filtering",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search term (searches names and content)",
                    },
                    "entity_type": {
                        "type": "string",
                        "enum": [
                            "ability",
                            "character",
                            "creature",
                            "event",
                            "family",
                            "item",
                            "location",
                            "organization",
                            "race",
                            "note",
                            "journal",
                            "quest",
                            "tag",
                            "timeline",
                        ],
                        "description": (
                            "Entity type to filter by. A search without this "
                            "does not cover 'tag', 'ability', 'item' or "
                            "'timeline': name the type here to search those"
                        ),
                    },
                    "name": {
                        "type": "string",
                        "description": "Filter by name (partial match by default, e.g. 'Test' matches 'Test Character')",
                    },
                    "name_exact": {
                        "type": "boolean",
                        "description": "Use exact matching on name filter (case-insensitive)",
                        "default": False,
                    },
                    "name_fuzzy": {
                        "type": "boolean",
                        "description": "Use fuzzy matching on name filter (typo-tolerant)",
                        "default": False,
                    },
                    "type": {
                        "type": "string",
                        "description": "Filter by Type field (e.g., 'NPC', 'City')",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter by tags (matches entities having ALL specified tags)",
                    },
                    "date_range": {
                        "type": "object",
                        "properties": {
                            "start": {"type": "string", "format": "date"},
                            "end": {"type": "string", "format": "date"},
                        },
                        "description": "For filtering journals by date",
                    },
                    "include_full": {
                        "type": "boolean",
                        "description": "Include full entity details",
                        "default": True,
                    },
                    "page": {
                        "type": "integer",
                        "description": "Page number for pagination",
                        "default": 1,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Results per page (default 25, max 100, use 0 for all)",
                        "default": 25,
                    },
                    "last_synced": {
                        "type": "string",
                        "description": "ISO 8601 timestamp to get only entities modified after this time",
                    },
                },
            },
        ),
        types.Tool(
            name="create_entities",
            description="Create one or more entities",
            inputSchema={
                "type": "object",
                "properties": {
                    "entities": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "entity_type": {
                                    "type": "string",
                                    "enum": [
                                        "ability",
                                        "character",
                                        "creature",
                                        "event",
                                        "family",
                                        "item",
                                        "location",
                                        "organization",
                                        "race",
                                        "note",
                                        "journal",
                                        "quest",
                                        "tag",
                                        "timeline",
                                    ],
                                    "description": "Entity type",
                                },
                                "name": {
                                    "type": "string",
                                    "description": "Entity name",
                                },
                                "type": {
                                    "type": "string",
                                    "description": "The Type field (e.g., 'NPC', 'Player Character')",
                                },
                                "entry": {
                                    "type": "string",
                                    "description": "Description in Markdown format",
                                },
                                "tags": {"type": "array", "items": {"type": "string"}},
                                "is_hidden": {
                                    "type": "boolean",
                                    "description": "If true, hidden from players (admin-only)",
                                },
                                "fields": {
                                    "type": "object",
                                    "additionalProperties": True,
                                    "description": (
                                        "Any other Kanka API field, merged into the "
                                        "request payload as-is. Names must match the "
                                        "API exactly: 'parent_id' (parent location or "
                                        "organisation), and for characters 'title', "
                                        "'age', 'sex', 'pronouns', 'is_dead', plus the "
                                        "arrays 'races', 'locations', 'families'. "
                                        "WARNING - the two kinds of ID are NOT "
                                        "interchangeable and the API accepts the wrong "
                                        "one without complaining, silently linking the "
                                        "wrong thing: 'parent_id' takes an entity_id, "
                                        "while 'races'/'locations'/'families' take the "
                                        "module-internal id, i.e. the 'id' of the "
                                        "race/location/family, NOT its entity_id. Read "
                                        "the target back and check before trusting a "
                                        "link. Values are sent verbatim: no Markdown "
                                        "conversion, no tag-name resolution. Takes "
                                        "precedence over the parameters above."
                                    ),
                                },
                            },
                            "required": ["entity_type", "name"],
                        },
                    }
                },
                "required": ["entities"],
            },
        ),
        types.Tool(
            name="update_entities",
            description="Update one or more entities",
            inputSchema={
                "type": "object",
                "properties": {
                    "updates": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "entity_id": {
                                    "type": "integer",
                                    "description": "Entity ID",
                                },
                                "name": {
                                    "type": "string",
                                    "description": "Entity name (required by Kanka API even if unchanged)",
                                },
                                "type": {
                                    "type": "string",
                                    "description": "The Type field",
                                },
                                "entry": {
                                    "type": "string",
                                    "description": "Content in Markdown format",
                                },
                                "tags": {"type": "array", "items": {"type": "string"}},
                                "is_hidden": {"type": "boolean"},
                                "fields": {
                                    "type": "object",
                                    "additionalProperties": True,
                                    "description": (
                                        "Any other Kanka API field, merged into the "
                                        "request payload as-is. Names must match the "
                                        "API exactly: 'parent_id' (parent location or "
                                        "organisation), and for characters 'title', "
                                        "'age', 'sex', 'pronouns', 'is_dead', plus the "
                                        "arrays 'races', 'locations', 'families'. "
                                        "WARNING - the two kinds of ID are NOT "
                                        "interchangeable and the API accepts the wrong "
                                        "one without complaining, silently linking the "
                                        "wrong thing: 'parent_id' takes an entity_id, "
                                        "while 'races'/'locations'/'families' take the "
                                        "module-internal id, i.e. the 'id' of the "
                                        "race/location/family, NOT its entity_id. Read "
                                        "the target back and check before trusting a "
                                        "link. Values are sent verbatim: no Markdown "
                                        "conversion, no tag-name resolution. Takes "
                                        "precedence over the parameters above."
                                    ),
                                },
                            },
                            "required": ["entity_id", "name"],
                        },
                    }
                },
                "required": ["updates"],
            },
        ),
        types.Tool(
            name="get_entities",
            description="Retrieve specific entities by ID with their posts",
            inputSchema={
                "type": "object",
                "properties": {
                    "entity_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Array of entity IDs to retrieve",
                    },
                    "include_posts": {
                        "type": "boolean",
                        "description": "Include posts for each entity",
                        "default": False,
                    },
                    "include_relations": {
                        "type": "boolean",
                        "description": (
                            "Include the relations each entity owns, with the "
                            "relation_id needed to update or delete them. Costs "
                            "one extra request per entity"
                        ),
                        "default": False,
                    },
                },
                "required": ["entity_ids"],
            },
        ),
        types.Tool(
            name="delete_entities",
            description="Delete one or more entities",
            inputSchema={
                "type": "object",
                "properties": {
                    "entity_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Array of entity IDs to delete",
                    }
                },
                "required": ["entity_ids"],
            },
        ),
        types.Tool(
            name="create_posts",
            description="Create posts on entities",
            inputSchema={
                "type": "object",
                "properties": {
                    "posts": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "entity_id": {
                                    "type": "integer",
                                    "description": "The entity ID to attach post to",
                                },
                                "name": {"type": "string", "description": "Post title"},
                                "entry": {
                                    "type": "string",
                                    "description": "Post content in Markdown format",
                                },
                                "is_hidden": {
                                    "type": "boolean",
                                    "description": "If true, hidden from players (admin-only)",
                                },
                            },
                            "required": ["entity_id", "name"],
                        },
                    }
                },
                "required": ["posts"],
            },
        ),
        types.Tool(
            name="update_posts",
            description="Update existing posts",
            inputSchema={
                "type": "object",
                "properties": {
                    "updates": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "entity_id": {
                                    "type": "integer",
                                    "description": "The entity ID",
                                },
                                "post_id": {
                                    "type": "integer",
                                    "description": "The post ID to update",
                                },
                                "name": {
                                    "type": "string",
                                    "description": "Post title (required by API even if unchanged)",
                                },
                                "entry": {
                                    "type": "string",
                                    "description": "Post content in Markdown format",
                                },
                                "is_hidden": {
                                    "type": "boolean",
                                    "description": "If true, hidden from players (admin-only)",
                                },
                            },
                            "required": ["entity_id", "post_id", "name"],
                        },
                    }
                },
                "required": ["updates"],
            },
        ),
        types.Tool(
            name="delete_posts",
            description="Delete posts from entities",
            inputSchema={
                "type": "object",
                "properties": {
                    "deletions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "entity_id": {
                                    "type": "integer",
                                    "description": "The entity ID",
                                },
                                "post_id": {
                                    "type": "integer",
                                    "description": "The post ID to delete",
                                },
                            },
                            "required": ["entity_id", "post_id"],
                        },
                    }
                },
                "required": ["deletions"],
            },
        ),
        types.Tool(
            name="create_members",
            description=(
                "Add characters to organisations. Members are not a field of "
                "the organisation: writing 'members' through 'fields' is "
                "accepted by the API and does nothing"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "members": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "organisation_entity_id": {
                                    "type": "integer",
                                    "description": "Entity ID of the organisation",
                                },
                                "character_entity_id": {
                                    "type": "integer",
                                    "description": "Entity ID of the character",
                                },
                                "role": {
                                    "type": "string",
                                    "description": "The character's role in the organisation (optional)",
                                },
                                "is_hidden": {
                                    "type": "boolean",
                                    "description": "If true, hidden from players (admin-only)",
                                },
                            },
                            "required": [
                                "organisation_entity_id",
                                "character_entity_id",
                            ],
                        },
                    }
                },
                "required": ["members"],
            },
        ),
        types.Tool(
            name="update_members",
            description="Update existing organisation memberships",
            inputSchema={
                "type": "object",
                "properties": {
                    "updates": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "organisation_entity_id": {
                                    "type": "integer",
                                    "description": "Entity ID of the organisation",
                                },
                                "member_id": {
                                    "type": "integer",
                                    "description": (
                                        "The membership ID, from create_members or "
                                        "from the 'members' list returned by "
                                        "get_entities on the organisation. NOT the "
                                        "character's entity ID"
                                    ),
                                },
                                "role": {
                                    "type": "string",
                                    "description": "New role, if changing it",
                                },
                                "is_hidden": {
                                    "type": "boolean",
                                    "description": "New visibility, if changing it",
                                },
                            },
                            "required": ["organisation_entity_id", "member_id"],
                        },
                    }
                },
                "required": ["updates"],
            },
        ),
        types.Tool(
            name="delete_members",
            description=(
                "Remove memberships from organisations. Only the membership is "
                "removed, the character itself is untouched"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "deletions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "organisation_entity_id": {
                                    "type": "integer",
                                    "description": "Entity ID of the organisation",
                                },
                                "member_id": {
                                    "type": "integer",
                                    "description": (
                                        "The membership ID, NOT the character's "
                                        "entity ID"
                                    ),
                                },
                            },
                            "required": ["organisation_entity_id", "member_id"],
                        },
                    }
                },
                "required": ["deletions"],
            },
        ),
        types.Tool(
            name="create_relations",
            description=(
                "Create relations between entities. Relations are directed: "
                "by default only the side you create exists"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "relations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "entity_id": {
                                    "type": "integer",
                                    "description": "Entity that owns the relation",
                                },
                                "target_entity_id": {
                                    "type": "integer",
                                    "description": "Entity the relation points at",
                                },
                                "relation": {
                                    "type": "string",
                                    "description": "The label, e.g. 'Capomastro di'",
                                },
                                "attitude": {
                                    "type": "integer",
                                    "description": "Numeric attitude towards the target, may be negative",
                                },
                                "is_hidden": {
                                    "type": "boolean",
                                    "description": "If true, hidden from players (admin-only)",
                                },
                                "two_way": {
                                    "type": "boolean",
                                    "description": (
                                        "Also create the mirror relation on the "
                                        "target, so the link shows on both sides"
                                    ),
                                    "default": False,
                                },
                            },
                            "required": [
                                "entity_id",
                                "target_entity_id",
                                "relation",
                            ],
                        },
                    }
                },
                "required": ["relations"],
            },
        ),
        types.Tool(
            name="update_relations",
            description=(
                "Update existing relations. The mirror is not touched: update "
                "it separately to keep both sides in step"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "updates": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "entity_id": {
                                    "type": "integer",
                                    "description": "Entity that owns the relation",
                                },
                                "relation_id": {
                                    "type": "integer",
                                    "description": (
                                        "The relation ID, from create_relations or "
                                        "from get_entities with include_relations"
                                    ),
                                },
                                "relation": {
                                    "type": "string",
                                    "description": "New label, if changing it",
                                },
                                "attitude": {
                                    "type": "integer",
                                    "description": "New attitude, if changing it",
                                },
                                "is_hidden": {
                                    "type": "boolean",
                                    "description": "New visibility, if changing it",
                                },
                            },
                            "required": ["entity_id", "relation_id"],
                        },
                    }
                },
                "required": ["updates"],
            },
        ),
        types.Tool(
            name="delete_relations",
            description=(
                "Delete relations. The mirror on the other entity is deleted "
                "too unless delete_mirror is false"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "deletions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "entity_id": {
                                    "type": "integer",
                                    "description": "Entity that owns the relation",
                                },
                                "relation_id": {
                                    "type": "integer",
                                    "description": "The relation ID",
                                },
                                "delete_mirror": {
                                    "type": "boolean",
                                    "description": (
                                        "Also delete the mirror on the target. "
                                        "Leaving this false is how half a relation "
                                        "is left behind"
                                    ),
                                    "default": True,
                                },
                            },
                            "required": ["entity_id", "relation_id"],
                        },
                    }
                },
                "required": ["deletions"],
            },
        ),
        types.Tool(
            name="check_entity_updates",
            description="Check which entity_ids have been modified since last sync",
            inputSchema={
                "type": "object",
                "properties": {
                    "entity_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Array of entity IDs to check",
                    },
                    "last_synced": {
                        "type": "string",
                        "description": "ISO 8601 timestamp to check updates since",
                    },
                },
                "required": ["entity_ids", "last_synced"],
            },
        ),
    ]


@app.call_tool()  # type: ignore[untyped-decorator]
async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    """Handle tool calls."""
    logger.info(f"Tool called: {name} with arguments: {arguments}")

    try:
        result: Any
        if name == "find_entities":
            result = await handle_find_entities(**arguments)
        elif name == "create_entities":
            result = await handle_create_entities(**arguments)
        elif name == "update_entities":
            result = await handle_update_entities(**arguments)
        elif name == "get_entities":
            result = await handle_get_entities(**arguments)
        elif name == "delete_entities":
            result = await handle_delete_entities(**arguments)
        elif name == "create_posts":
            result = await handle_create_posts(**arguments)
        elif name == "update_posts":
            result = await handle_update_posts(**arguments)
        elif name == "delete_posts":
            result = await handle_delete_posts(**arguments)
        elif name == "create_members":
            result = await handle_create_members(**arguments)
        elif name == "update_members":
            result = await handle_update_members(**arguments)
        elif name == "delete_members":
            result = await handle_delete_members(**arguments)
        elif name == "create_relations":
            result = await handle_create_relations(**arguments)
        elif name == "update_relations":
            result = await handle_update_relations(**arguments)
        elif name == "delete_relations":
            result = await handle_delete_relations(**arguments)
        elif name == "check_entity_updates":
            result = await handle_check_entity_updates(**arguments)
        else:
            raise ValueError(f"Unknown tool: {name}")

        return [types.TextContent(type="text", text=str(result))]
    except Exception as e:
        logger.error(f"Error in tool {name}: {str(e)}", exc_info=True)
        return [types.TextContent(type="text", text=f"Error: {str(e)}")]


class _MCPEndpoint:
    """ASGI endpoint handing every request on the MCP path to the session manager.

    With an auth token set, a request must carry "Authorization: Bearer
    <token>" or it is refused before reaching the MCP server.
    """

    def __init__(
        self, session_manager: StreamableHTTPSessionManager, auth_token: str | None
    ):
        self.session_manager = session_manager
        self.expected_header = f"Bearer {auth_token}" if auth_token else None

    def _is_authorized(self, scope: Scope) -> bool:
        if self.expected_header is None:
            return True
        headers = dict(scope.get("headers") or [])
        received = headers.get(b"authorization", b"").decode("latin-1")
        # Constant-time comparison, so response timing leaks nothing about the token
        return hmac.compare_digest(received, self.expected_header)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self._is_authorized(scope):
            client = scope.get("client") or ("?", 0)
            logger.warning(f"Rejected MCP request without a valid token from {client[0]}")
            response = JSONResponse(
                {"error": "unauthorized"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
            await response(scope, receive, send)
            return
        await self.session_manager.handle_request(scope, receive, send)


async def _healthz(_request: Request) -> PlainTextResponse:
    """Liveness probe for container orchestration."""
    return PlainTextResponse("ok")


def build_http_app() -> Starlette:
    """Build the ASGI app serving the MCP server over Streamable HTTP.

    The server answers on /mcp. It runs stateless, so no session has to
    survive between requests: a restart or a proxy in front loses nothing.
    DNS rebinding protection stays off unless MCP_ALLOWED_HOSTS lists the
    Host headers to accept, comma separated.

    When MCP_AUTH_TOKEN is set, /mcp only accepts requests carrying it as a
    bearer token; /healthz stays open for the container healthcheck.

    Returns:
        The Starlette application
    """
    allowed_hosts = [
        host.strip()
        for host in os.getenv("MCP_ALLOWED_HOSTS", "").split(",")
        if host.strip()
    ]
    security = (
        TransportSecuritySettings(allowed_hosts=allowed_hosts)
        if allowed_hosts
        else None
    )
    session_manager = StreamableHTTPSessionManager(
        app=app, stateless=True, security_settings=security
    )

    @contextlib.asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncIterator[None]:
        async with session_manager.run():
            yield

    return Starlette(
        routes=[
            Route(
                "/mcp",
                endpoint=_MCPEndpoint(
                    session_manager, os.getenv("MCP_AUTH_TOKEN") or None
                ),
            ),
            Route("/healthz", endpoint=_healthz),
        ],
        lifespan=lifespan,
    )


async def main() -> None:
    """Main entry point for the MCP server.

    MCP_TRANSPORT selects the transport: "stdio" (the default, what Claude
    Desktop launches) or "streamable-http", which listens on MCP_HOST and
    MCP_PORT (127.0.0.1:8000 unless set).
    """
    # Validate required environment variables
    if not os.getenv("KANKA_TOKEN"):
        logger.error("KANKA_TOKEN environment variable is required")
        raise ValueError("KANKA_TOKEN environment variable is required")

    if not os.getenv("KANKA_CAMPAIGN_ID"):
        logger.error("KANKA_CAMPAIGN_ID environment variable is required")
        raise ValueError("KANKA_CAMPAIGN_ID environment variable is required")

    transport = os.getenv("MCP_TRANSPORT", "stdio")
    logger.info(f"Starting Kanka MCP server ({transport})...")

    if transport == "stdio":
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await app.run(
                read_stream,
                write_stream,
                app.create_initialization_options(),
            )
    elif transport == "streamable-http":
        config = uvicorn.Config(
            build_http_app(),
            host=os.getenv("MCP_HOST", "127.0.0.1"),
            port=int(os.getenv("MCP_PORT", "8000")),
            log_level=os.getenv("MCP_LOG_LEVEL", "INFO").lower(),
        )
        await uvicorn.Server(config).serve()
    else:
        raise ValueError(
            f"Unknown MCP_TRANSPORT '{transport}': use 'stdio' or 'streamable-http'"
        )


if __name__ == "__main__":
    asyncio.run(main())
