"""FastAPI app — entry point.

Serves the JWT-paste page, the OAuth 2.1 endpoints, and the MCP
Streamable-HTTP endpoint. All on one port. Behind a Caddy sidecar that
terminates TLS.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Form, Header, Query, Request, Response
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    StreamingResponse,
)
from fastapi.templating import Jinja2Templates

from . import auth, oauth
from .bridge import SessionManager

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("gateway")

DOMAIN = os.environ.get("DOMAIN", "").strip()
SESSION_IDLE_TIMEOUT = float(os.environ.get("SESSION_IDLE_TIMEOUT", "1800"))

# Signing/encryption secret for OAuth artifacts (client_ids, authorization
# codes, access tokens). Never read from disk, never logged, never written
# anywhere. Regenerated in-memory on every container start — which means a
# restart invalidates already-issued OAuth artifacts. Raw Bearer flows
# (Claude Code, Cursor, Le Chat, Perplexity) are unaffected.
GATEWAY_SECRET = secrets.token_urlsafe(48)
logger.info("ephemeral OAuth secret generated for this run")

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

session_manager = SessionManager(idle_timeout=SESSION_IDLE_TIMEOUT)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await session_manager.start()
    try:
        yield
    finally:
        await session_manager.stop()


app = FastAPI(lifespan=lifespan, title="lex360 MCP gateway", docs_url=None, redoc_url=None)


@app.get("/logo.png", include_in_schema=False)
async def logo():
    return FileResponse(str(BASE_DIR / "templates" / "logo.png"), media_type="image/png")


def _issuer(request: Request) -> str:
    """Public-facing https://<DOMAIN> origin. Caddy sets X-Forwarded-* headers."""
    if DOMAIN:
        return f"https://{DOMAIN}"
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.headers.get("host", "localhost"))
    return f"{proto}://{host}"


# ---------------------------------------------------------------------------
# HTML page + form submit
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "issuer": _issuer(request),
            "oauth_mode": False,
            "oauth_params": {},
            "result": None,
            "error": None,
        },
    )


@app.get("/authorize", response_class=HTMLResponse)
async def authorize_get(
    request: Request,
    response_type: str = Query(...),
    client_id: str = Query(...),
    redirect_uri: str = Query(...),
    code_challenge: str = Query(...),
    code_challenge_method: str = Query(...),
    state: str | None = Query(None),
    scope: str | None = Query(None),
):
    try:
        oauth.validate_authorize_request(
            client_id=client_id,
            redirect_uri=redirect_uri,
            response_type=response_type,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            secret=GATEWAY_SECRET,
        )
    except ValueError as e:
        return HTMLResponse(
            f"<h1>Authorization request rejected</h1><p>{e}</p>",
            status_code=400,
        )

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "issuer": _issuer(request),
            "oauth_mode": True,
            "oauth_params": {
                "response_type": response_type,
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "code_challenge": code_challenge,
                "code_challenge_method": code_challenge_method,
                "state": state or "",
                "scope": scope or "",
            },
            "result": None,
            "error": None,
        },
    )


@app.post("/authorize/submit")
async def authorize_submit(
    request: Request,
    lexis_jwt: str = Form(...),
    client_id: str = Form(...),
    redirect_uri: str = Form(...),
    code_challenge: str = Form(...),
    code_challenge_method: str = Form(...),
    response_type: str = Form(...),
    state: str = Form(""),
    scope: str = Form(""),
):
    lexis_jwt = lexis_jwt.strip()
    try:
        oauth.validate_authorize_request(
            client_id=client_id,
            redirect_uri=redirect_uri,
            response_type=response_type,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            secret=GATEWAY_SECRET,
        )
    except ValueError as e:
        return HTMLResponse(f"<h1>Bad request</h1><p>{e}</p>", status_code=400)

    try:
        code = oauth.issue_authorization_code(
            lexis_jwt=lexis_jwt,
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_challenge=code_challenge,
            secret=GATEWAY_SECRET,
        )
    except auth.AuthError as e:
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "issuer": _issuer(request),
                "oauth_mode": True,
                "oauth_params": {
                    "response_type": response_type,
                    "client_id": client_id,
                    "redirect_uri": redirect_uri,
                    "code_challenge": code_challenge,
                    "code_challenge_method": code_challenge_method,
                    "state": state,
                    "scope": scope,
                },
                "result": None,
                "error": str(e),
            },
            status_code=400,
        )

    return RedirectResponse(
        oauth.build_redirect(redirect_uri, code, state or None),
        status_code=302,
    )


@app.post("/", response_class=HTMLResponse)
async def landing_submit(request: Request, lexis_jwt: str = Form(...)):
    """Non-OAuth form submission — just validates the JWT and confirms.

    Used by users who land on `/` without an OAuth flow and want to verify
    their token before configuring a client like Claude Code or Cursor.
    """
    try:
        auth.validate_lexis_jwt(lexis_jwt.strip())
        result = "Your JWT is valid. Configure your MCP client below."
        error = None
    except auth.AuthError as e:
        result = None
        error = str(e)
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "issuer": _issuer(request),
            "oauth_mode": False,
            "oauth_params": {},
            "result": result,
            "error": error,
        },
    )


# ---------------------------------------------------------------------------
# OAuth 2.1 endpoints
# ---------------------------------------------------------------------------

@app.get("/.well-known/oauth-protected-resource")
async def well_known_protected_resource(request: Request):
    return JSONResponse(oauth.build_resource_metadata(_issuer(request)))


@app.get("/.well-known/oauth-authorization-server")
async def well_known_as_metadata(request: Request):
    return JSONResponse(oauth.build_authorization_server_metadata(_issuer(request)))


@app.post("/register")
async def dcr(request: Request):
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse(
            {"error": "invalid_client_metadata", "error_description": "body is not JSON"},
            status_code=400,
        )
    try:
        result = oauth.register_client(body, GATEWAY_SECRET)
    except ValueError as e:
        return JSONResponse(
            {"error": "invalid_redirect_uri", "error_description": str(e)},
            status_code=400,
        )
    return JSONResponse(result, status_code=201)


@app.post("/token")
async def token_endpoint(
    grant_type: str = Form(...),
    code: str = Form(...),
    redirect_uri: str = Form(...),
    client_id: str = Form(...),
    code_verifier: str = Form(...),
):
    if grant_type != "authorization_code":
        return JSONResponse(
            {"error": "unsupported_grant_type"},
            status_code=400,
        )
    try:
        tok = oauth.exchange_code_for_access_token(
            code=code,
            code_verifier=code_verifier,
            client_id=client_id,
            redirect_uri=redirect_uri,
            secret=GATEWAY_SECRET,
        )
    except (ValueError, auth.AuthError) as e:
        return JSONResponse(
            {"error": "invalid_grant", "error_description": str(e)},
            status_code=400,
        )
    return JSONResponse(tok)


# ---------------------------------------------------------------------------
# MCP Streamable-HTTP endpoint
# ---------------------------------------------------------------------------

def _challenge_response(request: Request, message: str) -> JSONResponse:
    issuer = _issuer(request)
    return JSONResponse(
        {"error": "unauthorized", "error_description": message},
        status_code=401,
        headers={
            "WWW-Authenticate": (
                f'Bearer realm="lex360", '
                f'resource_metadata="{issuer}/.well-known/oauth-protected-resource"'
            )
        },
    )


@app.post("/mcp")
async def mcp_post(
    request: Request,
    authorization: str | None = Header(default=None),
    mcp_session_id: str | None = Header(default=None, alias="Mcp-Session-Id"),
):
    try:
        jwt = auth.resolve_lexis_jwt(authorization, GATEWAY_SECRET)
    except auth.AuthError as e:
        return _challenge_response(request, str(e))

    try:
        frame = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "invalid_json"}, status_code=400)

    if not isinstance(frame, dict):
        return JSONResponse(
            {"error": "batch_not_supported"},
            status_code=400,
        )

    method = frame.get("method")
    is_request = "id" in frame and method is not None

    # initialize → spawn a fresh session
    if method == "initialize":
        session = await session_manager.create(jwt)
        try:
            response = await session.request(frame)
        except Exception as e:
            await session_manager.drop(session.session_id)
            logger.exception("initialize failed")
            return JSONResponse(
                {"jsonrpc": "2.0", "id": frame.get("id"),
                 "error": {"code": -32000, "message": f"upstream init failed: {e}"}},
                status_code=502,
            )
        return JSONResponse(
            response,
            headers={"Mcp-Session-Id": session.session_id},
        )

    # All other messages require an existing session
    if not mcp_session_id:
        return JSONResponse(
            {"error": "missing_session", "error_description": "Mcp-Session-Id header required"},
            status_code=400,
        )
    session = await session_manager.get(mcp_session_id, jwt)
    if session is None:
        return JSONResponse(
            {"error": "session_not_found"},
            status_code=404,
        )

    if is_request:
        try:
            response = await session.request(frame)
        except Exception as e:
            logger.exception("rpc failed")
            return JSONResponse(
                {"jsonrpc": "2.0", "id": frame.get("id"),
                 "error": {"code": -32000, "message": f"upstream rpc failed: {e}"}},
                status_code=502,
            )
        return JSONResponse(response)

    # Notification or client-side response — fire and forget
    try:
        await session.notify(frame)
    except Exception as e:
        logger.exception("notify failed")
        return JSONResponse({"error": "upstream_unavailable"}, status_code=502)
    return Response(status_code=202)


@app.get("/mcp")
async def mcp_get(
    request: Request,
    authorization: str | None = Header(default=None),
    mcp_session_id: str | None = Header(default=None, alias="Mcp-Session-Id"),
):
    try:
        jwt = auth.resolve_lexis_jwt(authorization, GATEWAY_SECRET)
    except auth.AuthError as e:
        return _challenge_response(request, str(e))

    if not mcp_session_id:
        return JSONResponse({"error": "missing_session"}, status_code=400)
    session = await session_manager.get(mcp_session_id, jwt)
    if session is None:
        return JSONResponse({"error": "session_not_found"}, status_code=404)

    async def event_stream():
        async for msg in session.sse_iter():
            if msg is None:
                yield ": heartbeat\n\n"
                continue
            yield f"data: {json.dumps(msg, separators=(',', ':'))}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.delete("/mcp")
async def mcp_delete(
    request: Request,
    authorization: str | None = Header(default=None),
    mcp_session_id: str | None = Header(default=None, alias="Mcp-Session-Id"),
):
    try:
        jwt = auth.resolve_lexis_jwt(authorization, GATEWAY_SECRET)
    except auth.AuthError as e:
        return _challenge_response(request, str(e))
    if not mcp_session_id:
        return PlainTextResponse("", status_code=204)
    session = await session_manager.get(mcp_session_id, jwt)
    if session is not None:
        await session_manager.drop(mcp_session_id)
    return PlainTextResponse("", status_code=204)


@app.get("/healthz", include_in_schema=False)
async def healthz():
    return PlainTextResponse("ok")
