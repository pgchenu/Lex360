"""Tests de la gestion des tokens JWT."""

import json
import time

import pytest

from lex360.auth import (
    decode_jwt_payload,
    get_token_expiry,
    is_token_expired,
    TokenManager,
)


class TestJwtDecode:

    def test_decode_valid_jwt(self, token):
        """Décode le payload d'un token JWT valide."""
        payload = decode_jwt_payload(token)
        assert isinstance(payload, dict)
        assert "exp" in payload, "Le token ne contient pas de claim 'exp'"

    def test_get_expiry(self, token):
        """Récupère la date d'expiration du token."""
        exp = get_token_expiry(token)
        assert exp is not None
        assert exp > 0

    def test_token_not_expired(self, token):
        """Le token de test ne doit pas être expiré."""
        assert not is_token_expired(token), "Le token de test est expiré"

    def test_decode_invalid_jwt(self):
        """Un JWT invalide doit lever AuthError."""
        from lex360.exceptions import AuthError
        with pytest.raises(AuthError):
            decode_jwt_payload("not.a.valid-jwt")


class TestTokenManager:

    def test_save_and_load(self, token, tmp_path):
        """Sauvegarde et recharge un token depuis un fichier."""
        path = tmp_path / "token.json"
        tm = TokenManager(token_path=path)
        tm.save(token)

        # Vérifier le fichier
        data = json.loads(path.read_text())
        assert data["access_token"] == token
        assert "expires_at" in data

        # Recharger
        tm2 = TokenManager(token_path=path)
        loaded = tm2.load()
        assert loaded == token

    def test_set_token(self, token):
        """set_token définit le token sans sauvegarder."""
        tm = TokenManager()
        tm.set_token(token)
        assert tm.access_token == token
