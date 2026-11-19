"""Atomic local receipts; an HTTP retry can recover the completed operation."""

import asyncio
import hashlib
import json
import os
from collections.abc import Awaitable, Callable
from pathlib import Path


def read_receipt(data_dir: Path, request_id: str):
    path = data_dir / "operations" / (hashlib.sha256(request_id.encode()).hexdigest() + ".json")
    return json.loads(path.read_text()) if path.exists() else None


def write_receipt(data_dir: Path, request_id: str, response: dict):
    directory = data_dir / "operations"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (hashlib.sha256(request_id.encode()).hexdigest() + ".json")
    temporary = path.with_suffix(f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(response, default=str))
    temporary.replace(path)


class ReceiptGuard:
    """Run each request ID at most once; a retry returns the saved receipt.

    Lessons wrap their turn in this so that retrying an uncertain HTTP request
    can never repeat a business action such as a refund.
    """

    def __init__(self, data_dir: Path, prefix: str):
        self._data_dir = data_dir
        self._prefix = prefix
        self._locks: dict[str, asyncio.Lock] = {}

    async def run_once(self, request_id: str, turn: Callable[[], Awaitable[dict]]) -> dict:
        key = f"{self._prefix}:{request_id}"
        async with self._locks.setdefault(request_id, asyncio.Lock()):
            cached = read_receipt(self._data_dir, key)
            if cached is not None:
                return cached
            response = await turn()
            write_receipt(self._data_dir, key, response)
            return response
