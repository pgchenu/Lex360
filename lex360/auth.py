"""Gestion des tokens JWT pour Lexis 360."""

from __future__ import annotations

import base64
import json
import logging
import os
import time
from pathlib import Path

from lex360.exceptions import AuthError

logger = logging.getLogger(__name__)

DEFAULT_TOKEN_PATH = Path.home() / ".lex360" / "token.json"

# Marge de sécurité avant expiration (5 minutes)
EXPIRY_BUFFER_SECONDS = 300


def decode_jwt_payload(token: str) -> dict:
    """Décode le payload d'un JWT sans vérifier la signature."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise AuthError("Format JWT invalide (attendu 3 parties séparées par des points)")
        payload_b64 = parts[1]
        # Ajouter le padding base64 manquant
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        return json.loads(payload_bytes)
    except (IndexError, ValueError, json.JSONDecodeError) as e:
        raise AuthError(f"Impossible de décoder le JWT : {e}") from e


def get_token_expiry(token: str) -> float | None:
    """Retourne le timestamp d'expiration du JWT, ou None si absent."""
    payload = decode_jwt_payload(token)
    exp = payload.get("exp")
    return float(exp) if exp is not None else None


def is_token_expired(token: str) -> bool:
    """Vérifie si le token est expiré (avec marge de sécurité)."""
    exp = get_token_expiry(token)
    if exp is None:
        return False
    return time.time() > (exp - EXPIRY_BUFFER_SECONDS)


class TokenManager:
    """
    Gère le stockage et le chargement des tokens JWT.

    Sources de token (par ordre de priorité) :
    1. Variable d'environnement LEX_TOKEN
    2. Fichier ~/.lex360/token.json
    3. Token passé explicitement
    """

    def __init__(self, token_path: Path | str = DEFAULT_TOKEN_PATH):
        self._token_path = Path(token_path)
        self._access_token: str | None = None
        self._refresh_token: str | None = None

    @property
    def access_token(self) -> str:
        """Retourne le access_token courant, ou lève AuthError."""
        if self._access_token is None:
            self.load()
        if self._access_token is None:
            raise AuthError(
                "Aucun token disponible. "
                "Définissez LEX_TOKEN ou lancez `lex360 login`."
            )
        return self._access_token

    @property
    def is_expired(self) -> bool:
        """Vérifie si le token courant est expiré."""
        if self._access_token is None:
            return True
        return is_token_expired(self._access_token)

    def load(self) -> str | None:
        """Charge le token depuis l'environnement ou le fichier."""
        # 1. Variable d'environnement
        env_token = os.environ.get("LEX_TOKEN")
        if env_token:
            self._access_token = env_token.strip()
            logger.debug("Token chargé depuis la variable d'environnement LEX_TOKEN.")
            return self._access_token

        # 2. Fichier token.json
        if self._token_path.exists():
            try:
                data = json.loads(self._token_path.read_text(encoding="utf-8"))
                self._access_token = data.get("access_token")
                self._refresh_token = data.get("refresh_token")
                logger.debug("Token chargé depuis %s", self._token_path)
                return self._access_token
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Impossible de lire %s : %s", self._token_path, e)

        return None

    def save(self, access_token: str, refresh_token: str | None = None) -> None:
        """Sauvegarde les tokens dans le fichier."""
        self._access_token = access_token
        if refresh_token:
            self._refresh_token = refresh_token

        self._token_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"access_token": access_token}
        if self._refresh_token:
            data["refresh_token"] = self._refresh_token

        # Ajouter expires_at si décodable
        exp = get_token_expiry(access_token)
        if exp:
            data["expires_at"] = exp

        self._token_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("Token sauvegardé dans %s", self._token_path)

    def set_token(self, token: str) -> None:
        """Définit le token manuellement (sans sauvegarder)."""
        self._access_token = token

    def get_token_info(self) -> dict:
        """Retourne les informations du token courant (payload JWT décodé)."""
        return decode_jwt_payload(self.access_token)
