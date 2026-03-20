"""Fixtures partagées pour les tests d'intégration Lexis 360."""

import os
from pathlib import Path

import pytest

from lex360.auth import TokenManager
from lex360.client import Lex360Client
from lex360.transport_curl import CurlCffiTransport

# DocIds de test connus
DOC_ID_FASCICULE = "EN_KEJC-238100_0KR8"  # Fasc. 212 Alsace-Moselle
DOC_ID_JP_CASS = "JP_KODCASS-0519779_0KRH"  # Cass. Ass. plén. 28/06/2024

# Chemin vers token.env à la racine du projet
TOKEN_ENV_PATH = Path(__file__).parent.parent / "token.env"


def get_token() -> str | None:
    """Récupère le token depuis l'environnement, token.env, ou ~/.lex360/token.json."""
    # 1. Charger token.env dans l'environnement si présent
    if TOKEN_ENV_PATH.exists() and not os.environ.get("LEX_TOKEN"):
        token = TOKEN_ENV_PATH.read_text(encoding="utf-8").strip()
        if token:
            os.environ["LEX_TOKEN"] = token

    tm = TokenManager()
    return tm.load()


@pytest.fixture(scope="session")
def token():
    """Token JWT valide. Skip le test si absent."""
    t = get_token()
    if not t:
        pytest.skip("LEX_TOKEN non défini — test d'intégration ignoré")
    return t


@pytest.fixture(scope="session")
def transport(token):
    """Transport curl_cffi démarré avec un token valide."""
    t = CurlCffiTransport()
    t.start(token)
    yield t
    t.close()


@pytest.fixture(scope="session")
def curl_transport(transport):
    """Alias de transport pour les tests spécifiques curl_cffi."""
    return transport


@pytest.fixture(scope="session")
def client(token, transport):
    """Client Lex360 réutilisant le transport existant."""
    c = Lex360Client()
    c.auth.set_token(token)
    c.transport = transport
    c._started = True
    yield c
