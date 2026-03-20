# lex360

Client Python pour l'API privée de [Lexis 360 Intelligence](https://www.lexis360intelligence.fr/) (LexisNexis France).

Contourne le TLS fingerprinting via `curl_cffi` pour accéder aux endpoints non documentés : recherche, documents (SSE), navigation, export PDF/DOCX.

## Interface web

Application Flask avec recherche, lecture de documents, export PDF/DOCX et navigation (liens, frise chronologique, arborescence des codes).

![Recherche avec filtres](screenshots/screenshot1.png)
![Consultation de document](screenshots/screenshot2.png)

```bash
pip install -e ".[web]"
python web/app.py
# → http://localhost:5000
```

## Installation

```bash
pip install -e ".[dev]"
```

## Authentification

Le token JWT (`access_token`) se récupère depuis le `localStorage` du navigateur sur une session Lexis 360 connectée.

```bash
# Option 1 : variable d'environnement
export LEX_TOKEN="eyJ..."

# Option 2 : sauvegarde via CLI
lex360 login
```

## CLI

```bash
lex360 search "responsabilité contractuelle" --limit 5
lex360 search "22-84.760"                     # détection auto pourvoi
lex360 doc read EN_KEJC-238100_0KR8            # contenu d'un fascicule
lex360 doc meta JP_KODCASS-123456_0KRH         # métadonnées JSON
lex360 links JP_KODCASS-123456_0KRH --jp       # liens / décisions liées
lex360 timeline JP_KODCASS-123456_0KRH         # frise procédurale
lex360 codes SLD-LEGITEXT000006070721          # arborescence Code civil
```

## Tests

Tests d'intégration (nécessitent un `LEX_TOKEN` valide) :

```bash
pytest tests/ -v
```

## Documentation API

Voir [`docs/lex.md`](docs/lex.md) pour la documentation complète des endpoints reverse-engineerés.
