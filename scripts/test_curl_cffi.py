#!/usr/bin/env python3
"""Test rapide : curl_cffi passe-t-il le TLS fingerprinting de Lexis 360 ?"""

import os
import sys

try:
    from curl_cffi.requests import Session
except ImportError:
    print("ERREUR : curl_cffi non installé. Lancez : pip install curl_cffi")
    sys.exit(1)

token = os.environ.get("LEX_TOKEN")
if not token:
    # Essayer de charger depuis token.env
    from pathlib import Path
    token_path = Path(__file__).parent.parent / "token.env"
    if token_path.exists():
        token = token_path.read_text(encoding="utf-8").strip()

if not token:
    print("ERREUR : LEX_TOKEN non défini et token.env absent.")
    sys.exit(1)

BASE_URL = "https://www.lexis360intelligence.fr"

with Session(impersonate="chrome") as s:
    resp = s.get(
        f"{BASE_URL}/api/user/whoami",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    print(f"Status : {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        name = data.get("name", data.get("sub", "?"))
        print(f"Utilisateur : {name}")
        print("curl_cffi passe le TLS fingerprinting !")
    elif resp.status_code == 401:
        print("401 — TLS fingerprinting bloqué ou token expiré.")
        sys.exit(1)
    else:
        print(f"Réponse inattendue : {resp.text[:500]}")
        sys.exit(1)
