"""Protocol Transport et utilitaires partagés pour les transports HTTP."""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol, runtime_checkable
from urllib.parse import urlencode

from lex360.exceptions import AuthError, NotFoundError, APIError

logger = logging.getLogger(__name__)

BASE_URL = "https://www.lexis360intelligence.fr"


@runtime_checkable
class Transport(Protocol):
    """Interface commune pour les transports HTTP Lexis 360."""

    def start(self, token: str) -> None: ...
    def close(self) -> None: ...
    def update_token(self, token: str) -> None: ...
    def get(self, path: str, params: dict[str, str] | None = None) -> dict[str, Any]: ...
    def post(self, path: str, body: dict[str, Any] | list | None = None) -> dict[str, Any] | list: ...
    def get_text(self, path: str) -> str: ...
    def post_binary(self, path: str, body: dict[str, Any] | None = None) -> bytes: ...


def build_url(path: str, params: dict[str, str] | None = None) -> str:
    """Construit l'URL complète. Préserve les double-slashes."""
    url = f"{BASE_URL}{path}" if path.startswith("/") else f"{BASE_URL}/{path}"
    if params:
        url += "?" + urlencode(params)
    return url


def check_status(result: dict, url: str) -> None:
    """Vérifie le code HTTP et lève l'exception appropriée."""
    status = result["status"]
    if status == 401:
        raise AuthError(f"Token invalide ou expiré (401) pour {url}")
    if status == 404:
        raise NotFoundError(f"Ressource non trouvée (404) : {url}")
    if status >= 400:
        raise APIError(
            f"Erreur API {status} pour {url}",
            status_code=status,
            body=result.get("body"),
        )


def handle_json_response(result: dict, url: str) -> dict[str, Any] | list:
    """Vérifie le statut et parse le JSON."""
    check_status(result, url)
    try:
        return json.loads(result["body"])
    except json.JSONDecodeError as e:
        raise APIError(
            f"Réponse non-JSON pour {url}: {e}",
            body=result["body"][:500],
        ) from e
