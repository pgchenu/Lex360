"""Transport HTTP via curl_cffi — imite le fingerprint TLS de Chrome sans navigateur."""

from __future__ import annotations

import json
import logging
from typing import Any

from curl_cffi.requests import Session

from lex360.exceptions import TransportError, AuthError, NotFoundError, APIError
from lex360.transport import BASE_URL, build_url, check_status, handle_json_response

logger = logging.getLogger(__name__)


class CurlCffiTransport:
    """
    Transport HTTP utilisant curl_cffi pour imiter le fingerprint TLS de Chrome.

    Contourne le TLS fingerprinting Envoy de Lexis 360
    en imitant le fingerprint JA3/JA4 de Chrome.
    """

    def __init__(self, impersonate: str = "chrome"):
        self._impersonate = impersonate
        self._session: Session | None = None
        self._token: str | None = None

    def start(self, token: str) -> None:
        """Crée la session curl_cffi avec le token."""
        self._token = token
        self._session = Session(impersonate=self._impersonate)
        logger.info("Transport curl_cffi démarré (impersonate=%s).", self._impersonate)

    def close(self) -> None:
        """Ferme la session."""
        if self._session:
            self._session.close()
            self._session = None

    def update_token(self, token: str) -> None:
        """Met à jour le token."""
        self._token = token

    def _ensure_started(self) -> None:
        if self._session is None:
            raise TransportError("Le transport n'est pas démarré. Appelez start() d'abord.")

    def _headers(self, content_type: str | None = "application/json") -> dict[str, str]:
        """Construit les headers avec le token Bearer."""
        headers = {"Authorization": f"Bearer {self._token}"}
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def get(self, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        """Requête GET JSON vers l'API."""
        self._ensure_started()
        url = build_url(path, params)
        logger.debug("GET %s", url)

        resp = self._session.get(url, headers=self._headers())
        result = {"status": resp.status_code, "body": resp.text}
        return handle_json_response(result, url)

    def post(self, path: str, body: dict[str, Any] | list | None = None) -> dict[str, Any] | list:
        """Requête POST JSON vers l'API."""
        self._ensure_started()
        url = build_url(path)
        logger.debug("POST %s", url)

        resp = self._session.post(
            url,
            headers=self._headers(),
            data=json.dumps(body) if body is not None else None,
        )
        result = {"status": resp.status_code, "body": resp.text}
        return handle_json_response(result, url)

    def get_text(self, path: str) -> str:
        """Requête GET retournant du texte brut (pour SSE/event-stream)."""
        self._ensure_started()
        url = build_url(path)
        logger.debug("GET (text) %s", url)

        resp = self._session.get(url, headers=self._headers(content_type=None))
        result = {"status": resp.status_code, "body": resp.text}
        check_status(result, url)
        return resp.text

    def post_binary(self, path: str, body: dict[str, Any] | None = None) -> bytes:
        """Requête POST retournant du binaire (pour PDF/DOCX)."""
        self._ensure_started()
        url = build_url(path)
        logger.debug("POST (binary) %s", url)

        resp = self._session.post(
            url,
            headers=self._headers(),
            data=json.dumps(body) if body is not None else None,
        )
        result = {"status": resp.status_code, "body": resp.text}
        check_status(result, url)
        return resp.content

    def _build_url(self, path: str, params: dict[str, str] | None = None) -> str:
        """Alias pour compatibilité avec les tests."""
        return build_url(path, params)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
