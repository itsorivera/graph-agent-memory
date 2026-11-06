"""Environment configuration. Env vars beat .env (ADR 003 secrets strategy)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    # AuraDB (memory-enabled support agents in modules 2-5, Bolt backend)
    neo4j_uri: str = ""
    neo4j_username: str = "neo4j"
    neo4j_password: str = Field(default="", repr=False)
    neo4j_database: str = "neo4j"

    # OpenAI — chat, embeddings, LLM extraction (ADR 001)
    openai_api_key: str = Field(default="", repr=False)
    openai_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"

    # Chat model provider: OpenAI (default) or AWS Bedrock
    model_provider: Literal["openai", "bedrock"] = "openai"
    bedrock_model: str = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    aws_region: str = Field(
        default="us-east-1",
        validation_alias=AliasChoices("AWS_REGION", "AWS_DEFAULT_REGION"),
    )
    aws_access_key_id: str = Field(default="", repr=False)
    aws_secret_access_key: str = Field(default="", repr=False)
    aws_session_token: str = Field(default="", repr=False)

    # NAMS (module 5)
    nams_api_key: str = Field(default="", repr=False)
    nams_base_url: str = "https://memory.neo4jlabs.com"

    # Workshop machinery
    data_dir: Path = ROOT / "data"
    memory_namespace: str = "workshop"
    ontology: str = "acme_cloud"
    agent_reasoning_retrieval: bool = True
    validation_mode: Literal["permissive", "strict"] = "permissive"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "acme_cloud.db"


def _home_database(s: AppSettings) -> str | None:
    """The user's home database on the server, or None if it cannot be reached.

    Newer AuraDB Free instances name their database after the instance ID, not
    "neo4j". Asking the server avoids making every participant look it up.
    """
    try:
        from neo4j import GraphDatabase

        with GraphDatabase.driver(
            s.neo4j_uri, auth=(s.neo4j_username, s.neo4j_password), connection_timeout=10
        ) as driver:
            records = driver.execute_query("CALL db.info() YIELD name RETURN name").records
        return records[0]["name"] if records else None
    except Exception:  # make check reports connection problems with full detail.
        return None


@lru_cache
def get_settings() -> AppSettings:
    s = AppSettings()
    # NEO4J_DATABASE unset (env and .env): use the server's home database.
    if "neo4j_database" not in s.model_fields_set and s.neo4j_uri and s.neo4j_password:
        s.neo4j_database = _home_database(s) or s.neo4j_database
    # The neo4j-agent-memory OpenAI adapter and PydanticAI both read the raw
    # env var, not pydantic-settings — export it so .env-only setups work.
    if s.openai_api_key and not os.environ.get("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = s.openai_api_key
    return s
