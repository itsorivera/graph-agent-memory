"""Open the neo4j-agent-memory client for module 2: Bolt backend, no extraction yet.

Messages are stored and embedded. Entity extraction stays off (`extractor_type=
"none"`) until module 3, so this module shows short-term memory on its own.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from neo4j_agent_memory import MemoryClient, MemorySettings

from lib.settings import AppSettings

if TYPE_CHECKING:
    from neo4j_agent_memory.llm.adapters.bedrock import BedrockEmbeddingProvider


def build_embedding(settings: AppSettings) -> str | BedrockEmbeddingProvider:
    """Return the embedder for MemorySettings: OpenAI by default, Titan V2 optional.

    The Bedrock provider is constructed explicitly so credentials from `.env`
    work; temporary credentials are passed through the standard AWS environment
    variables because the adapter has no session-token parameter.
    """
    if settings.effective_embedding_provider == "bedrock":
        from neo4j_agent_memory.llm.adapters.bedrock import BedrockEmbeddingProvider

        return BedrockEmbeddingProvider(
            f"bedrock/{settings.bedrock_embedding_model}",
            aws_region=settings.aws_region,
            **settings.bedrock_embedding_kwargs(),
            dimensions=settings.bedrock_embedding_dimensions,
        )
    return f"openai/{settings.embedding_model}"


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
        embedding=build_embedding(settings),
        extraction={"extractor_type": "none"},
    )


@asynccontextmanager
async def open_memory(settings: AppSettings):
    """Persist messages without extracting entities."""
    async with MemoryClient(build_settings(settings)) as memory:
        yield memory
