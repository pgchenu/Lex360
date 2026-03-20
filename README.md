# lex360

Client Python pour l'API privée de [Lexis 360 Intelligence](https://www.lexis360intelligence.fr/) (LexisNexis France).

Contourne le TLS fingerprinting via `curl_cffi` pour accéder aux endpoints non documentés : recherche, documents (SSE), navigation, export PDF/DOCX.

## Extension MCP pour Claude

Installez l'extension MCP (`.mcpb`) dans Claude Desktop et accédez directement à la doctrine, la jurisprudence et la navigation Lexis 360 depuis une conversation Claude.

![Claude consulte le JurisClasseur Administratif via Lexis 360](screenshots/screenshot9.png)

### Installation rapide

1. Télécharger `lex360-0.1.0.mcpb` depuis les [releases](.)
2. Glisser le fichier dans **Paramètres > Extensions** de Claude Desktop
3. Coller votre token JWT et cliquer **Enregistrer**

Le guide d'installation détaillé avec captures d'écran est disponible dans [`INSTALL.md`](INSTALL.md).

### Outils disponibles (9)

| Outil | Description |
|-------|-------------|
| `guide` | Recommande les outils selon le contexte juridique (appeler en premier) |
| `rechercher` | Recherche full-text (doctrine, JP, revues) avec filtres et tri |
| `rechercher_decision` | Recherche par n° de pourvoi, JurisData ou RG |
| `lire_doctrine` | Contenu d'un fascicule JurisClasseur ou article de revue (Markdown) |
| `lire_decision` | Texte d'une décision de justice (texte brut) |
| `metadata_document` | Métadonnées enrichies (auteur, juridiction, thématique) |
| `liens_document` | Liens croisés : doctrine citant, décisions liées, textes visés |
| `frise_chronologique` | Historique procédural (TGI → CA → Cass.) |
| `table_des_matieres` | Table des matières d'un document structuré |

### Construire le bundle

```bash
npm install -g @anthropic-ai/mcpb
mcpb pack .
```

---

## Interface web

Application Flask avec recherche, lecture de documents, export PDF/DOCX et navigation (liens, frise chronologique, arborescence des codes).

![Recherche avec filtres](screenshots/screenshot1.png)
![Consultation de document](screenshots/screenshot2.png)

```bash
pip install -e ".[web]"
python web/app.py
# → http://localhost:5000
```

## Installation (développement)

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
