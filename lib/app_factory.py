"""Shared HTTP transport; every lesson supplies its own complete agent factory."""

from __future__ import annotations

import asyncio
import json
import re
from contextlib import asynccontextmanager
from typing import Any, Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .graph import bolt_graph
from .settings import get_settings
from .workshop import AgentFactory


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    request_id: str | None = None
    account_email: str | None = None
    incident_id: str | None = None
    authorize_refund: bool = False
    policy_plan: str | None = None


class EvalRequest(BaseModel):
    id: str | None = None


def create_app(agent_factory: AgentFactory, *, title: str, nams_graph_reader=None) -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with agent_factory(settings) as chat:
            app.state.memory = chat.memory
            app.state.chat = chat
            try:
                yield
            finally:
                pending = list(jobs.values())
                for task in pending:
                    task.cancel()
                if pending:
                    await asyncio.gather(*pending, return_exceptions=True)

    app = FastAPI(title=title, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
    )

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "module": app.state.chat.module,
            "memory_layers": app.state.chat.memory_layers,
        }

    @app.post("/api/chat")
    async def chat(req: ChatRequest) -> dict[str, Any]:
        return await app.state.chat.chat(**req.model_dump())

    @app.get("/api/graph")
    async def graph(
        layer: Literal["all", "short_term", "long_term", "reasoning"] = "all",
        session_id: str | None = None,
    ) -> dict[str, Any]:
        if app.state.memory is None:
            return {"nodes": [], "relationships": []}
        return await bolt_graph(app.state.memory, layer, session_id=session_id)

    @app.get("/api/graph/nams")
    async def graph_nams() -> dict[str, Any]:
        if nams_graph_reader is None:
            return {"nodes": [], "relationships": [], "unavailable": True}
        return await nams_graph_reader(settings)

    def artifact_path(folder, identifier):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", identifier):
            raise HTTPException(400, "Invalid artifact ID")
        return settings.data_dir / folder / (identifier + ".json")

    @app.get("/api/accounts")
    async def accounts():
        from . import db as dbx

        with dbx.connect(settings.db_path) as db:
            return [dict(r) for r in db.execute("SELECT name,email FROM customers ORDER BY name")]

    @app.get("/api/cases")
    async def cases():
        from . import db as dbx

        with dbx.connect(settings.db_path) as db:
            return dbx.billing_cases(db)

    jobs = {}

    @app.post("/api/eval")
    async def start_eval(req: EvalRequest | None = None):
        from scripts.eval import run_isolated_eval

        identifier = (req.id if req else None) or uuid4().hex
        path = artifact_path("evaluations", identifier)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            return json.loads(path.read_text())
        path.write_text(json.dumps({"id": identifier, "status": "running", "questions": []}))
        task = asyncio.create_task(
            run_isolated_eval(app.state.chat.module, settings, run_id=identifier, output_path=path)
        )
        jobs[identifier] = task
        task.add_done_callback(lambda _: jobs.pop(identifier, None))
        return JSONResponse({"id": identifier, "status": "running"}, status_code=202)

    @app.get("/api/eval")
    async def eval_results():
        folder = settings.data_dir / "evaluations"
        return {
            "runs": [
                json.loads(p.read_text())
                for p in sorted(
                    folder.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True
                )[:20]
            ]
        }

    @app.get("/api/eval/{identifier}")
    async def eval_result(identifier: str):
        path = artifact_path("evaluations", identifier)
        if not path.exists():
            raise HTTPException(404, "Evaluation not found")
        return json.loads(path.read_text())

    @app.get("/api/replays")
    async def replay_results():
        folder = settings.data_dir / "replays"
        runs = []
        for path in sorted(folder.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[
            :30
        ]:
            result = json.loads(path.read_text())
            turns = result.get("turns", []) + [
                turn for branch in result.get("branches", []) for turn in branch.get("turns", [])
            ]
            sessions = sorted(
                {t["result"]["session_id"] for t in turns if t.get("result", {}).get("session_id")}
            )
            runs.append(
                {
                    "id": path.stem,
                    "title": result.get("title", path.stem),
                    "module": result.get("module"),
                    "session_ids": sessions,
                }
            )
        return {"runs": runs}

    @app.get("/api/replays/{identifier}")
    async def replay_result(identifier: str):
        path = artifact_path("replays", identifier)
        if not path.exists():
            raise HTTPException(404, "Replay not found")
        return json.loads(path.read_text())

    @app.get("/api/operations/{identifier}")
    async def operation(identifier: str):
        from .operations import read_receipt

        result = read_receipt(settings.data_dir, f"m{app.state.chat.module}:{identifier}")
        if result is None:
            raise HTTPException(404, "Operation not found")
        return result

    return app
