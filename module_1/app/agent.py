"""Module 1: the stateless baseline.

Every turn calls the model with only the new message: no history and no
retrieved memory. Whatever the customer said a moment ago is gone. SQL tools can
still look up business facts when given an identifier, but that is lookup, not
memory.

Read this file top to bottom, then tools.py. guardrails.py holds business safety
checks that are the same in every module.
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from uuid import uuid4

from pydantic_ai import Agent
from pydantic_ai.models import Model

from lib.operations import ReceiptGuard
from lib.response import build_response
from lib.settings import AppSettings

from .guardrails import checked_reply, failure_reply, scope_turn
from .tools import SQLITE_TOOLS, ToolDeps

INSTRUCTIONS = """You are SupportBot for Acme Cloud, a fictional SaaS company.

Facts: use tools for every business fact. Never invent an email, account, price,
policy, refund, escalation or service status. Say what is unknown, and ask a
clarifying question when identities are ambiguous.

Actions: a confirmed billing case is the only authority for a refund. Another
person's account never inherits the previous speaker's identity or plan. For an
update, read the account's refund history instead of issuing a new refund. No
escalation tool is available.

Service status: call check_service_status. An empty or unknown result means there
is no verified status source. Wikipedia company information is not service status.

Keep responses short."""


def build_model(settings: AppSettings) -> Model | str:
    """Return the chat model for this module: OpenAI by default, Bedrock optional."""
    if settings.model_provider == "bedrock":
        # Imported lazily so OpenAI-only setups do not need the Bedrock extra.
        from pydantic_ai.models.bedrock import BedrockConverseModel
        from pydantic_ai.providers.bedrock import BedrockProvider

        provider = BedrockProvider(
            aws_access_key_id=settings.aws_access_key_id or None,
            aws_secret_access_key=settings.aws_secret_access_key or None,
            aws_session_token=settings.aws_session_token or None,
            region_name=settings.aws_region,
        )
        return BedrockConverseModel(settings.bedrock_model, provider=provider)
    return f"openai:{settings.openai_model}"


class ChatService:
    module = 1
    memory = None  # Module 2 adds a Neo4j memory client.
    memory_layers: list[str] = []

    def __init__(self, settings: AppSettings, *, business_tools=True, evaluation=False):
        # `evaluation` disables memory writes in later modules; module 1 writes none.
        self.settings = settings
        self.business_tools = business_tools
        self.receipts = ReceiptGuard(settings.data_dir, f"m{self.module}")
        self.agent = Agent(
            build_model(settings),
            deps_type=ToolDeps,
            tools=SQLITE_TOOLS if business_tools else [],
            output_type=str,
            instructions=INSTRUCTIONS,
        )

    async def chat(
        self,
        message: str,
        session_id: str | None = None,
        *,
        request_id: str | None = None,
        account_email: str | None = None,
        incident_id: str | None = None,
        authorize_refund: bool = False,
        policy_plan: str | None = None,
    ) -> dict:
        """Handle one support turn. Retrying a request_id returns the saved receipt."""
        request_id = request_id or uuid4().hex
        namespace = self.settings.memory_namespace
        session_id = session_id or uuid4().hex[:12]
        if not session_id.startswith(namespace + ":"):
            session_id = f"{namespace}:{session_id}"
        deps = ToolDeps(
            db_path=self.settings.db_path,
            account_email=account_email,
            incident_id=incident_id,
            authorize_refund=authorize_refund and self.business_tools,
        )
        return await self.receipts.run_once(
            request_id, lambda: self._turn(message, session_id, request_id, deps, policy_plan)
        )

    async def _turn(self, message, session_id, request_id, deps: ToolDeps, policy_plan):
        warnings: list[dict] = []
        timing: dict = {}
        started = time.monotonic()
        execution_ok = True
        try:
            scope = scope_turn(deps, policy_plan)
            timing["context_seconds"] = round(time.monotonic() - started, 3)

            # The whole lesson: the model sees this message and nothing before it.
            result = await self.agent.run(message, deps=deps, instructions=scope.instructions)

            timing.update(model_timing(result, started + timing["context_seconds"]))
            reply = checked_reply(message, result.output, deps, scope)
        except Exception as error:
            execution_ok = False
            warnings.append({"phase": "execution", "error": type(error).__name__})
            reply = failure_reply(message, deps)
        timing["total_seconds"] = round(time.monotonic() - started, 3)
        return build_response(
            reply=reply,
            session_id=session_id,
            request_id=request_id,
            tool_calls=deps.collector,
            execution_ok=execution_ok,
            warnings=warnings,
            timing=timing,
        )


def model_timing(result, model_started: float) -> dict:
    return {
        "model_seconds": round(time.monotonic() - model_started, 3),
        "input_tokens": result.usage.input_tokens,
        "output_tokens": result.usage.output_tokens,
    }


@asynccontextmanager
async def open_agent(settings: AppSettings, *, business_tools=True, evaluation=False):
    yield ChatService(settings, business_tools=business_tools, evaluation=evaluation)
