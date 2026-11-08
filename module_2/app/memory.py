"""Open the neo4j-agent-memory client for module 2: Bolt backend, no extraction yet.

Messages are stored and embedded. Entity extraction stays off (`extractor_type=
"none"`) until module 3, so this module shows short-term memory on its own.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from neo4j_agent_memory import MemoryClient, MemorySettings

from lib.settings import AppSettings


def build_settings(settings: AppSettings) -> MemorySettings:
    return MemorySettings(
        backend="bolt",
        neo4j={
            "uri": settings.neo4j_uri,
            "username": settings.neo4j_username,
            "password": settings.neo4j_password,
            "database": settings.neo4j_database,
            "connection_timeout": 10,
            "max_transaction_retry_time": 5,
        },
        llm=f"openai/{settings.openai_model}",
        embedding=f"openai/{settings.embedding_model}",
        extraction={"extractor_type": "none"},
    )


@asynccontextmanager
async def open_memory(settings: AppSettings):
    """Persist messages without extracting entities."""
    async with MemoryClient(build_settings(settings)) as memory:
        yield memory
