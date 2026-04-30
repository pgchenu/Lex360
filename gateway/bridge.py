"""MCP Streamable-HTTP ⇄ stdio bridge.

One `lex360-mcp` subprocess per MCP session. The subprocess inherits
`LEX_TOKEN` set to the user's Lexis JWT. JSON-RPC frames (line-delimited
JSON) are pumped between the HTTP layer and the subprocess's stdio.

Sessions are identified by `Mcp-Session-Id` (we generate it on
initialize). Each session pins to one Lexis JWT (by its hash) so a
mismatched Authorization header on a later request is rejected.

Logging: subprocess stderr is forwarded but never the JWT.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import os
import secrets
import time
import uuid
from typing import Any

logger = logging.getLogger(__name__)

LEX360_MCP_CMD = os.environ.get("LEX360_MCP_CMD", "lex360-mcp").split()
SUBPROCESS_TERM_GRACE = 5.0
RPC_RESPONSE_TIMEOUT = 120.0


def _hash_jwt(jwt: str) -> str:
    return hashlib.sha256(jwt.encode("utf-8")).hexdigest()[:16]


class Session:
    """One MCP session ↔ one lex360-mcp subprocess."""

    def __init__(self, session_id: str, jwt: str):
        self.session_id = session_id
        self.jwt_hash = _hash_jwt(jwt)
        self._jwt = jwt
        self.created_at = time.time()
        self.last_activity = time.time()
        self.proc: asyncio.subprocess.Process | None = None
        self._pending: dict[Any, asyncio.Future[dict]] = {}
        self._sse_queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=256)
        self._stdout_task: asyncio.Task | None = None
        self._stderr_task: asyncio.Task | None = None
        self._closed = False
        self._write_lock = asyncio.Lock()

    async def start(self) -> None:
        env = {**os.environ, "LEX_TOKEN": self._jwt}
        self.proc = await asyncio.create_subprocess_exec(
            *LEX360_MCP_CMD,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        self._stdout_task = asyncio.create_task(self._read_stdout())
        self._stderr_task = asyncio.create_task(self._read_stderr())
        # The JWT is only needed at spawn time — drop the in-memory copy.
        self._jwt = ""
        logger.info(
            "session %s spawned subprocess pid=%s jwt_hash=%s",
            self.session_id, self.proc.pid, self.jwt_hash,
        )

    async def _read_stdout(self) -> None:
        assert self.proc and self.proc.stdout
        try:
            while True:
                line = await self.proc.stdout.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning("session %s: malformed stdout line", self.session_id)
                    continue
                self._dispatch(msg)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("session %s stdout reader crashed", self.session_id)
        finally:
            self._fail_pending()

    async def _read_stderr(self) -> None:
        assert self.proc and self.proc.stderr
        try:
            while True:
                line = await self.proc.stderr.readline()
                if not line:
                    break
                logger.info("session %s [stderr] %s", self.session_id,
                            line.decode("utf-8", "replace").rstrip())
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("session %s stderr reader crashed", self.session_id)

    def _dispatch(self, msg: dict) -> None:
        if "id" in msg and ("result" in msg or "error" in msg):
            fut = self._pending.pop(msg["id"], None)
            if fut and not fut.done():
                fut.set_result(msg)
                return
            # Server-to-client request response we never asked for, push to SSE.
        # Notifications / server-initiated requests → SSE queue.
        with contextlib.suppress(asyncio.QueueFull):
            self._sse_queue.put_nowait(msg)

    def _fail_pending(self) -> None:
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(RuntimeError("subprocess exited"))
        self._pending.clear()

    async def request(self, frame: dict) -> dict:
        """Send a JSON-RPC request and await the response (matched by id)."""
        if self._closed or not self.proc or not self.proc.stdin:
            raise RuntimeError("session is closed")
        rpc_id = frame.get("id")
        if rpc_id is None:
            raise ValueError("request frame must have an id")
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[dict] = loop.create_future()
        self._pending[rpc_id] = fut
        await self._write_frame(frame)
        try:
            return await asyncio.wait_for(fut, timeout=RPC_RESPONSE_TIMEOUT)
        except asyncio.TimeoutError:
            self._pending.pop(rpc_id, None)
            raise

    async def notify(self, frame: dict) -> None:
        """Send a JSON-RPC notification or response (no reply expected)."""
        if self._closed or not self.proc or not self.proc.stdin:
            raise RuntimeError("session is closed")
        await self._write_frame(frame)

    async def _write_frame(self, frame: dict) -> None:
        line = (json.dumps(frame, separators=(",", ":")) + "\n").encode("utf-8")
        async with self._write_lock:
            assert self.proc and self.proc.stdin
            self.proc.stdin.write(line)
            await self.proc.stdin.drain()
        self.last_activity = time.time()

    async def sse_iter(self):
        """Yield queued server→client messages, one at a time."""
        while not self._closed:
            try:
                msg = await asyncio.wait_for(self._sse_queue.get(), timeout=15.0)
            except asyncio.TimeoutError:
                yield None  # caller can emit a heartbeat
                continue
            yield msg

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for task in (self._stdout_task, self._stderr_task):
            if task and not task.done():
                task.cancel()
        if self.proc and self.proc.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                self.proc.terminate()
            try:
                await asyncio.wait_for(self.proc.wait(), timeout=SUBPROCESS_TERM_GRACE)
            except asyncio.TimeoutError:
                with contextlib.suppress(ProcessLookupError):
                    self.proc.kill()
                    await self.proc.wait()
        logger.info("session %s closed", self.session_id)


class SessionManager:
    def __init__(self, idle_timeout: float = 1800.0):
        self._sessions: dict[str, Session] = {}
        self._lock = asyncio.Lock()
        self._idle_timeout = idle_timeout
        self._reaper_task: asyncio.Task | None = None

    async def start(self) -> None:
        self._reaper_task = asyncio.create_task(self._reaper())

    async def stop(self) -> None:
        if self._reaper_task:
            self._reaper_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reaper_task
        async with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        await asyncio.gather(*(s.close() for s in sessions), return_exceptions=True)

    async def create(self, jwt: str) -> Session:
        session_id = uuid.uuid4().hex + secrets.token_hex(4)
        session = Session(session_id, jwt)
        await session.start()
        async with self._lock:
            self._sessions[session_id] = session
        return session

    async def get(self, session_id: str, jwt: str) -> Session | None:
        async with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            return None
        if session.jwt_hash != _hash_jwt(jwt):
            # Same session id but a different user — treat as not found.
            return None
        session.last_activity = time.time()
        return session

    async def drop(self, session_id: str) -> None:
        async with self._lock:
            session = self._sessions.pop(session_id, None)
        if session is not None:
            await session.close()

    async def _reaper(self) -> None:
        try:
            while True:
                await asyncio.sleep(60.0)
                cutoff = time.time() - self._idle_timeout
                stale: list[Session] = []
                async with self._lock:
                    for sid, s in list(self._sessions.items()):
                        if s.last_activity < cutoff:
                            stale.append(s)
                            self._sessions.pop(sid, None)
                for s in stale:
                    logger.info("session %s reaped (idle)", s.session_id)
                    await s.close()
        except asyncio.CancelledError:
            raise
