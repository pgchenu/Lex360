Voici comment fonctionne l'authentification sur **Lexis 360 Intelligence** :

---

## Mécanisme d'authentification

### 1. OpenID Connect (OIDC) — Protocole principal

Le site utilise le protocole **OpenID Connect (OIDC)**, qui est une couche d'identité construite au-dessus d'OAuth 2.0. Le fournisseur d'identité (Identity Provider) est **LexisNexis** lui-même, via :

- **Issuer** : `https://login.lexisnexis.com/`
- **Flux** : Authorization Code (`responseType: "code"`) — le plus sécurisé pour les applications web
- **Scopes** : `openid offline` (l'accès `offline` permet l'obtention d'un refresh token)
- **Redirect URI** : `https://www.lexis360intelligence.fr/oidc/callback`

Lorsqu'un utilisateur non connecté tente d'accéder au site, il est redirigé vers `login.lexisnexis.com` pour s'authentifier, puis renvoyé vers le site avec un code d'autorisation qui est échangé contre des tokens.

### 2. Tokens JWT

Une fois authentifié, deux tokens **JWT (JSON Web Token)** sont stockés dans le `localStorage` du navigateur :

- **`access_token`** : signé avec l'algorithme `HS256`, émis par `legan-api-user`. Il contient les informations de l'utilisateur (nom, email, rôles, permissions, marchés, packs) et est envoyé à chaque appel API.
- **`refresh_token`** : également un JWT, utilisé pour obtenir un nouvel access token sans redemander les identifiants.

### 3. WAM (Web Access Management) — Accès par IP

Le site supporte également un mode d'authentification par **adresse IP** via un système WAM (probablement SiteMinder ou équivalent LexisNexis), adapté aux institutions (cabinets d'avocats, universités) :

- Endpoint : `https://signin.lexisnexis.com/lnaccess/app/signin`
- Un endpoint `/api/user/wam/ip-check` est appelé à chaque session pour vérifier si l'IP de l'utilisateur est autorisée.
- Des accès spécifiques existent pour les établissements scolaires (`school.login.url`).

### 4. Intégrations SSO (OIDC clients)

Lexis 360 joue aussi le rôle de **fournisseur d'identité** pour des applications partenaires via OIDC :

- **Fidnet** (fidroit.fr) — base de données juridique
- **JobExit** (jobexit.fr) — RH/social
- **Case Law Analytics** (caselawanalytics.com) — analyse jurisprudentielle
- **Docebo** (formation en ligne LexisNexis)

### 5. Gestion des sessions

- Un appel à `/api/user/usersessions/check` est effectué à chaque chargement pour vérifier la validité de la session.
- Un appel à `/api/user/whoami` récupère le profil de l'utilisateur courant.
- Le site semble supporter la **monosession** (une seule session active à la fois par utilisateur).

---

**En résumé** : l'authentification repose sur OIDC/OAuth 2.0 avec LexisNexis comme Identity Provider central, des tokens JWT stockés localement, et un mécanisme complémentaire d'accès par IP pour les institutions.

### 6. Protection anti-bot : TLS fingerprinting

> **Testé le 2026-03-19** : L'envoi du `access_token` JWT dans le header `Authorization` depuis un client externe (curl, Python `requests`) retourne systématiquement **401 Unauthorized**, même avec les bons headers (`Origin`, `Referer`, `User-Agent`, `sec-fetch-*`).
>
> En revanche, depuis le contexte du navigateur, le token seul suffit (`credentials: 'omit'` → 200). Il n'y a **pas de cookies d'authentification** — seuls `OptanonConsent` (consentement cookies) et `_dd_s` (Datadog monitoring) sont présents.
>
> Le blocage provient d'un **WAF/proxy Envoy** (`x-envoy-decorator-operation: api-user.front.svc.cluster.local`) qui effectue du **TLS fingerprinting** (JA3/JA4). Les requêtes dont l'empreinte TLS ne correspond pas à un navigateur sont rejetées au niveau du proxy avant d'atteindre le backend (`x-envoy-upstream-service-time: 0`).
>
> **Conséquences pour l'automatisation** :
> - Les appels API **doivent** être effectués depuis un vrai contexte navigateur, ou via une librairie imitant le fingerprint TLS d'un navigateur.
> - **Playwright** (navigateur headless) est une option viable pour automatiser l'accès en Python : il exécute un vrai Chrome, donc le fingerprint TLS est authentique.
> - Les librairies `curl_cffi` ou `tls-client` (Python) permettent d'imiter le fingerprint TLS de Chrome sans lancer un navigateur complet, mais leur compatibilité n'a pas été testée sur ce site.

### 7. Durée de vie du token

> **Testé le 2026-03-19** : Le JWT `access_token` a une durée de vie de **24 heures** exactement (`iat` et `exp` séparés de 86 400 secondes). Le `refresh_token` (également un JWT, stocké dans le `localStorage`) permet d'obtenir un nouveau `access_token` sans ré-authentification.

---

## API Endpoints

Base URL : `https://www.lexis360intelligence.fr`

Tous les appels API nécessitent un `access_token` JWT dans le header `Authorization`. Les appels depuis un client externe (curl, Python) sont bloqués par TLS fingerprinting — voir section 6 ci-dessus.

### 1. Recherche (`/api/recherche/`)

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `POST` | `/api/recherche//search` | Recherche principale (full-text) |
| `POST` | `/api/recherche//aggregate` | Agrégation des résultats (compteurs par type de contenu, facettes) |
| `POST` | `/api/recherche//ror` | Résultats connexes / "Related or Recommended" |
| `GET` | `/api/recherche/suggest?t={terme}` | Autocomplétion / suggestions de recherche |
| `POST` | `/api/recherche/ror` | Variante de l'endpoint ROR (sans double slash) |

> **Note** : Le double slash `//` dans certains endpoints est bien présent dans les appels réels.

### 2. Documents (`/api/document/`)

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `GET` | `/api/document/metadata/{docId}` | Métadonnées d'un document (titre, auteur, date, type) |
| `GET` | `/api/document/records/{docId}` | Contenu d'un document (voir format SSE ci-dessous) |

#### Format de réponse de `/api/document/records/{docId}`

> **Testé le 2026-03-19** : Cet endpoint retourne du **`text/event-stream`** (Server-Sent Events), **pas du JSON**.

```
id: EN_KEJC-238100_0KR8
event: DOCVIEW
data: <?xml version="1.0" encoding="UTF-8"?><html xmlns:frm="http://www.lexis-nexis.com/glp/frm"><head><title>Fascicule</title><link type="text/css" rel="stylesheet" href="/css/CommonStyles.css"/>...
```

| Champ SSE | Description |
|-----------|-------------|
| `id` | Le docId du document |
| `event` | Type d'événement : `DOCVIEW` |
| `data` | Contenu HTML/XML complet du document, incluant les meta tags (`doc-id`, `kid`, `combining-id`, `lnf-doctype`, etc.) et le corps du texte |

Pour extraire le HTML, parser les lignes commençant par `data: ` et concaténer :

```javascript
const html = raw.split('\n')
  .filter(line => line.startsWith('data: '))
  .map(line => line.substring(6))
  .join('');
```

**Format des identifiants de documents** :
- Encyclopédies : `EN_KEJC-{id}_0K{XX}` (ex: `EN_KEJC-246880_0KSE`)
- Jurisprudence Cass. : `JP_KODCASS-{id}_0KRH` (ex: `JP_KODCASS-0540779_1_0KRH`)
- Jurisprudence CA : `JU_KODCA-{id}_0KRJ` (ex: `JU_KODCA-0151692_0KRJ`)
- Jurisprudence autre : `JK_KJ-{id}_0KRJ` (ex: `JK_KJ-1621418_0KRJ`)
- Revues/Presse : `PS_KPRE-{id}_0KTZ` (ex: `PS_KPRE-714606_0KTZ`)
- Fiches pratiques : `FP_FP-{id}_0KT0` (ex: `FP_FP-683498_0KT0`)

### 3. Navigation (`/api/navigation/`)

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `POST` | `/api/navigation/links` | Liens de navigation entre documents (résultats de recherche) |
| `GET` | `/api/navigation/links/{docId}?jp=false` | Liens de navigation pour un document spécifique |
| `POST` | `/api/navigation/time-line` | Frise chronologique des résultats |
| `GET` | `/api/navigation/generate-toc/{docId}` | Table des matières d'un document |
| `GET` | `/api/navigation/encyclos/fascicule/{docId}` | Navigation spécifique encyclopédies (fascicule) |
| `GET` | `/api/navigation/encyclos/{docId}?typeContribution=` | Navigation encyclopédies (plan de document) |
| `GET` | `/api/navigation/jurisprudence/toc/{docId}` | Table des matières d'une décision de jurisprudence |
| `GET` | `/api/navigation/revues/{docId}` | Navigation spécifique revues |

### 4. Adapter (`/api/adapter/`)

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `GET` | `/api/adapter/docks` | Liste des docks / widgets de la page d'accueil |
| `POST` | `/api/adapter/content-types` | Types de contenu disponibles pour l'utilisateur |
| `POST` | `/api/adapter/explore-content` | Contenu éditorial de la page d'accueil (explorer) |

### 5. Utilisateur (`/api/user/`)

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `GET` | `/api/user/whoami` | Profil de l'utilisateur connecté |
| `GET` | `/api/user/features/enabled` | Liste des feature flags activés |
| `GET` | `/api/user/features/enabled/{feature}` | Vérifier un feature flag spécifique (ex: `docebo`, `redirect-to-lexis-plus`) |
| `GET` | `/api/user/usersessions/check` | Vérification de validité de session |
| `GET` | `/api/user/wam/ip-check` | Vérification d'accès WAM par IP |
| `GET` | `/api/user/pinnings/create` | Création d'un épinglage utilisateur |

### 6. Historique & Favoris (`/api/data-history/`)

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `GET` | `/api/data-history/history/load` | Charger l'historique de recherche |
| `POST` | `/api/data-history/history` | Enregistrer une entrée d'historique |
| `POST` | `/api/data-history/history/update` | Mettre à jour l'historique |
| `GET` | `/api/data-history/history/document` | Historique de consultation de documents |
| `POST` | `/api/data-history/history/document` | Enregistrer une consultation de document |
| `GET` | `/api/data-history/favoris/load` | Charger les favoris |
| `POST` | `/api/data-history/favoris/create` | Créer un favori |
| `POST` | `/api/data-history/favoris/update` | Modifier un favori |
| `DELETE` | `/api/data-history/favoris/delete/{id}` | Supprimer un favori |

### 7. Recherches programmées & Alertes (`/api/scheduled-searches/`)

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `GET` | `/api/scheduled-searches/scheduled-searches?start={n}&num={n}` | Liste des recherches programmées (paginées) |
| `GET` | `/api/scheduled-searches/scheduled-searches/{id}` | Détail d'une recherche programmée |
| `GET` | `/api/scheduled-searches/scheduled-searches/legacy-preference` | Préférences legacy |
| `GET` | `/api/scheduled-searches/scheduled-searches/multiple/legacy-migrations` | Migrations legacy |
| `GET` | `/api/scheduled-searches/alert/my-subscribes/REVUE` | Abonnements alertes revues |
| `GET` | `/api/scheduled-searches/alert/my-subscribes/NEWS` | Abonnements alertes actualités |
| `POST` | `/api/scheduled-searches/alert/subscribe` | S'abonner à une alerte |
| `POST` | `/api/scheduled-searches/alert/unsubscribe` | Se désabonner d'une alerte |
| `GET` | `/api/scheduled-searches/notifications/my-notifications?notificationType=WEB` | Notifications web |
| `GET` | `/api/scheduled-searches/notifications/events/web` | Événements de notification (WebSocket) |
| `POST` | `/api/scheduled-searches/notifications/acquit/web` | Acquitter une notification |

### 8. Dossiers de travail (`/api/workfolder/`)

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `GET` | `/api/workfolder/v1/workfolders/CanUseWorkfolder` | Vérifier si l'utilisateur peut utiliser les dossiers |
| `GET` | `/api/workfolder/v1/workfolders/itemlist/load` | Charger la liste des éléments d'un dossier |
| `POST` | `/api/workfolder/v1/workfolders/ItemTree/item` | Gérer les éléments de l'arborescence |

### 9. Compteurs & Rapports (`/api/counter-report/`)

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `POST` | `/api/counter-report/api/usages/search-activities` | Tracer une activité de recherche |
| `POST` | `/api/counter-report/api/usages/document-activities` | Tracer une activité de consultation document |

### 10. Routes frontend (pages)

| URL pattern | Description |
|-------------|-------------|
| `/home` | Page d'accueil |
| `/search?q={terme}&typeDoc={type}&sort={sort}&from={ts}&to={ts}` | Résultats de recherche |
| `/document/{docId}` | Consultation d'un document (jurisprudence, générique) |
| `/encyclopedies/{nomEncyclo}/{tocId}/document/{docId}` | Consultation d'un fascicule d'encyclopédie |
| `/revues/{nomRevue}/{pubId}/document/{docId}` | Consultation d'un article de revue |
| `/fiches-pratiques/document/{docId}` | Consultation d'une fiche pratique |
| `/oidc/callback` | Callback d'authentification OIDC |

### 11. Facettes de recherche

Les types de contenu disponibles pour le filtrage :
- **Doctrine** : Revues, Encyclopédies, Synthèses, Formules
- **Jurisprudence** : Cour de cassation, Cours d'appel, Conseil constitutionnel, juridictions européennes, juridictions administratives
- **Sources officielles** : Codes, Législation française, Droit européen/international, Conventions collectives
- **Sources publications officielles** : JORF, BOFiP, Autorités indépendantes, Réponses ministérielles
- **Contenus pratiques** : Fiches pratiques, Guides, Modèles
- **Actualités**

---

## Volet droit des décisions — Décisions liées & Articles citant

Lorsqu'on consulte une décision de jurisprudence, un **volet droit** affiche des informations contextuelles enrichies. Ces données proviennent de l'endpoint :

```
GET /api/navigation/links/{docId}?jp=true
```

> Pour les documents non-jurisprudence (encyclopédies, fiches pratiques), le paramètre est `?jp=false`.

### Structure de la réponse

La réponse est un **tableau d'objets**, chaque objet représentant une section du volet droit :

```json
[
  {
    "title": "Nom de la section",
    "qualif": "QUALIF_CODE",
    "direction": "DIRECT" | null,
    "ordre": 1,
    "links": [ ... ]
  }
]
```

### Sections identifiées (qualificatifs)

| Ordre | Section | `qualif` | Description |
|-------|---------|----------|-------------|
| 1 | **Voir aussi** | `COMBINING` | Autres versions du même document (ex: Texte intégral ↔ Analyse JurisData). Lien via `combiningId` partagé. |
| 2 | **Commenté par** | `QRSC_QRSCPRSANALYSEDJP` | Articles de doctrine (revues) qui commentent/analysent cette décision |
| 3 | **Cité par** | `null` | Fascicules d'encyclopédie, synthèses et articles qui citent cette décision. **Note** : le `qualif` est `null` pour cette section (contrairement aux autres sections qui ont un code explicite). |
| 7 | **Jurisprudence dans le même sens** | `QRSC_QRSCRAPMSENS` | Autres décisions rendues dans le même sens |
| 8 | **Suggérées par notre algorithme** | `SIMILAR_RELATED` | Décisions similaires identifiées algorithmiquement (direction: `DIRECT`) |
| 11 | **Texte(s) visé(s) dans les Motifs** | `QRSC_QRSCTXTVISEMOT` | Articles de codes et textes de loi visés dans les motifs de la décision |

> Les ordres 4, 5, 6, 9, 10 existent potentiellement pour d'autres types de liens (jurisprudence contraire, textes visés dans les moyens, etc.) mais n'ont pas été observés sur les décisions testées.

### Structure d'un lien (`links[]`)

Chaque lien dans une section a la structure suivante :

```json
{
  "docId": "PS_KPRE-689781_0KTZ",
  "title": "Titre du document lié",
  "type": "DOCTRINE_REVUE",
  "date": 1732492800000,
  "metas": {
    "document": { "date": ..., "type": ... },
    "jurisprudence": { "typeLitiges": [...], "themes": [...], "typeJp": "ANALYSE" },
    "encyclo": { ... }
  }
}
```

**Types de documents liés observés** :
- `DOCTRINE_REVUE` — Articles de revues
- `DOCTRINE_FASCICULE` — Fascicules d'encyclopédie (JurisClasseur)
- `JURISPRUDENCE_COURCASSATION` — Décisions de la Cour de cassation
- `SOURCES_CODEARTICLE` — Articles de codes

### Chronologie (timeline)

La frise chronologique visible sur les décisions de jurisprudence provient de :

```
POST /api/navigation/time-line
```

Elle affiche la chaîne procédurale (ex: TGI → CA → Cass.) avec les liens entre les décisions.

### Table des matières d'une décision

```
GET /api/navigation/jurisprudence/toc/{docId}
```

Retourne la structure du document (En-tête, Exposé, Moyens, Motifs, Dispositif) avec des ancres (`mark_10`, `mark_20`, etc.) pour la navigation interne.

---

## Format JurisData

### Qu'est-ce que JurisData ?

**JurisData** est le système de numérotation propriétaire de LexisNexis pour les décisions de jurisprudence. Chaque décision analysée par LexisNexis reçoit un numéro JurisData unique.

### Format du numéro

```
JurisData n° YYYY-NNNNNN
```

- `YYYY` : année de la décision
- `NNNNNN` : numéro séquentiel (6 chiffres, parfois moins)
- Exemples : `2025-017611`, `2024-010199`

### Stockage dans l'API

Le numéro JurisData est stocké dans le champ `jurisprudence.numeroJurisprudence` du endpoint `/api/document/metadata/{docId}`, **aux côtés du numéro de pourvoi** :

```json
{
  "jurisprudence": {
    "numeroJurisprudence": [
      "24-15.901",        // numéro de pourvoi
      "2025-017611"       // numéro JurisData
    ]
  }
}
```

> Le numéro JurisData n'a **pas de champ dédié** — il est mélangé avec les autres numéros dans le tableau `numeroJurisprudence`. Il se distingue par son format `YYYY-NNNNNN` (année sur 4 chiffres, tiret, numéro sur 6 chiffres).

### Deux versions d'une décision (combining)

Chaque décision de jurisprudence peut exister en **deux versions**, reliées par un `combiningId` commun :

| Version | `typeJp` | `typeContenu` | Suffixe docId | Description |
|---------|----------|---------------|---------------|-------------|
| **Texte intégral** | `DECISION` | `TCO_TCNJURBRT` | `_0KRH` | Texte brut de la décision tel que rendu par la juridiction |
| **Analyse JurisData** | `ANALYSE` | `TCO_TCNSYNTHJD` | `_1_0KRH` | Analyse enrichie par LexisNexis avec résumé, abstract, mots-clés, etc. |

Exemple pour le pourvoi 22-84.760 :
- Texte intégral : `JP_KODCASS-0519779_0KRH` (kid: `KODCASS-0519779`)
- Analyse JurisData : `JP_KODCASS-0519779_1_0KRH` (kid: `KAJD-214199`)

Le `combiningId` (`31704103`) est partagé entre les deux versions.

### Structure complète des metadata de jurisprudence

```
GET /api/document/metadata/{docId}
```

```json
{
  "_id": "JP_KODCASS-0519779_0KRH",
  "creationDate": 1719596512815,
  "document": {
    "docIdStable": "JP_KODCASS-0519779_0KRH",
    "id": "JP_KODCASS-0519779_0KRH",
    "kid": "KODCASS-0519779",
    "title": "Cour de cassation, Assemblée plénière, 28 Juin 2024 – n° 22-84.760",
    "type": "JURISPRUDENCE_COURCASSATION",
    "typeContenu": "TCO_TCNJURBRT",
    "combiningId": "31704103",
    "date": 1719532800000,
    "creationDate": 1719595853000,
    "codePublication": "CPU_CPUBBULL",
    "commentedBy": 6,
    "nbDecSimilaire": 1,
    "signatures": ["3#2024-06-28|CJ_IJCASS|22-84.760"],
    "thematique": "CT_CTFR",
    "ror": ["Cass. numéro 22-84.760 28/06/2024", "..."]
  },
  "jurisprudence": {
    "annee": 2024,
    "classeJuridiction": "Cour de cassation",
    "classeJuridictionShort": "Cass.",
    "dateDeDecision": 1719532800000,
    "numeroJurisprudence": ["22-84.760"],
    "solutionJuridique": "SO_SLCASPAR",
    "solutionJuridiqueLabel": "Cassation partielle",
    "codePublications": ["CPU_CPUBRAPP", "CPU_CPUBNONCLASSE", "CPU_CPUBBULL"],
    "typeFormation": "assemblée plénière",
    "typeFormationCode": "FO_FO%7BT%7DTFASS%7BL%7DFQPLENIE",
    "typeDecision": "arrêt",
    "typeJp": "DECISION",
    "typeLitiges": ["Responsabilité civile"],
    "themes": ["responsabilité délictuelle"],
    "legiRef": { "label": "{\"hash\":{\"LinkType\":\"TC\",\"NomCode\":\"NC_CCIVIL\",\"NumArt\":\"1242\"}, ...}", "all": ["hash1", "hash2", "..."], "motifs": ["hash1", "..."] },
    "critSelection": ["CSINSELECT"]
  },
  "from": "countRenvois"
}
```

> **Notes sur les champs (vérifiés le 2026-03-19)** :
> - `commentedBy` : **nombre** (compte de commentaires), pas un booléen. Exemple : `6` = 6 articles commentent cette décision.
> - `from` : valeur variable selon le document. Observé : `"countRenvois"` (jurisprudence Cass.), `"rdf"` (encyclopédies). Indique probablement la source d'indexation.
> - `creationDate` : présent à la racine et dans `document` (timestamps différents — indexation vs publication).
> - `docIdStable` : identique au `id` pour la jurisprudence.
> - `thematique` : chaîne unique (`"CT_CTFR"`), pas un tableau.
> - `ror` : tableau de variantes de citation de la décision (pour la recherche textuelle).
> - `legiRef.label` : JSON stringifié contenant les références législatives avec `LinkType` (`TC` = texte codifié, `TNC` = texte non codifié), `NomCode` et `NumArt`.
```

### Préfixes des identifiants de documents (kid)

| Préfixe kid | Type | Description |
|-------------|------|-------------|
| `KODCASS-` | Jurisprudence | Décision de la Cour de cassation (texte intégral) |
| `KAJD-` | Jurisprudence | Analyse JurisData d'une décision |
| `KODCA-` | Jurisprudence | Décision de Cour d'appel |
| `KJ-` | Jurisprudence | Autre décision de justice |
| `KEJC-` | Encyclopédie | Fascicule JurisClasseur |
| `KPRE-` | Revue | Article de presse/revue juridique |
| `FP-` | Fiche pratique | Fiche pratique |

### Codes de publication jurisprudence (`codePublications`)

| Code | Signification |
|------|---------------|
| `CPU_CPUBBULL` | Publié au Bulletin |
| `CPU_CPUBRAPP` | Publié (R) au Rapport |
| `CPU_CPUBNONCLASSE` | Non classé |

### Solutions juridiques (`solutionJuridique`)

| Code | Label |
|------|-------|
| `SO_SLCASPAR` | Cassation partielle |
| `SO_SLCAS` | Cassation |
| `SO_SLREJ` | Rejet |
| `SO_SLINF` | Infirmation |
| `SO_SLCONF` | Confirmation |

### Critères de sélection (`critSelection`)

| Code | Signification |
|------|---------------|
| `CSINSELECT` | Inédit sélectionné |

---

## Payloads des requêtes POST

### POST `/api/recherche//search` — Recherche principale

**Request body** :

```json
{
  "q": "licenciement abusif",
  "project": "all",
  "highlight": true,
  "offset": 0,
  "size": 10,
  "from": "0",
  "to": "1776592724072",
  "filters": [],
  "sorts": [{ "field": "SCORE", "order": "DESC" }],
  "aggregations": [
    "TYPELITIGES", "CLASSEJURIDICTION", "ANNEE", "THEMATIQUE",
    "CODEPUBLICATIONENCYCLO", "CODEPUBLICATIONJP", "MATIERE", "CODE",
    "TYPEDOC", "NEWSTHEMATIQUE", "PARTIE", "OFFICIALPUBLICATIONS",
    "CRITERESSELECTION", "COMMENTEDBY", "FILTRECONCLUSIONS",
    "SOLUTIONJURIDIQUE", "LEGIREFDE", "LEGIFILTRE"
  ],
  "relevanceProfile": null,
  "combining": null,
  "fields": null
}
```

**Champs** :

| Champ | Type | Description |
|-------|------|-------------|
| `q` | string | Terme de recherche. Supporte les opérateurs booléens : `ET`, `OU`, `SAUF`, `PROX1[a b]`, `PROX2[a b]`. Préfixes de champ : `(a) :titre` (recherche dans les titres), `(a) :texte` (recherche dans le texte). Expressions exactes entre guillemets. |
| `project` | string | Toujours `"all"` |
| `highlight` | boolean | Active le surlignage des termes trouvés dans les résultats |
| `offset` | number | Décalage pour la pagination (0-based) |
| `size` | number | Nombre de résultats par page (défaut : 10) |
| `from` | string | Timestamp de début de la plage de dates (en ms, `"0"` = pas de limite) |
| `to` | string | Timestamp de fin de la plage de dates (en ms) |
| `filters` | array | Filtres actifs (voir structure ci-dessous) |
| `sorts` | array | Tri : `{ "field": "SCORE" \| "DOCUMENT_DATE", "order": "DESC" \| "ASC" }` |
| `aggregations` | array | Facettes à calculer (voir liste complète) |
| `relevanceProfile` | string\|null | Profil de pertinence. `null` pour la recherche générale, `"legal-cases"` pour la jurisprudence filtrée |
| `combining` | any\|null | Combinaison de versions (texte intégral / analyse JurisData) |
| `fields` | array\|null | Champs spécifiques à retourner. `null` = tous. Ex: `["DOCUMENT_ID", "DOCUMENT_ALL_JP", "DOCUMENT_TITLE", "DOCUMENT_TYPE"]` |

**Structure d'un filtre** :

```json
{ "name": "typeDoc", "values": ["JURISPRUDENCE"] }
```

| Nom du filtre | Valeurs possibles |
|---------------|-------------------|
| `typeDoc` | Voir tableau ci-dessous |
| `typeDoc` (sous-types JP) | `JURISPRUDENCE_COURCASSATION`, `JURISPRUDENCE_COUAPPEL`, etc. |
| `legiFiltre` | ID d'un article de code (ex: `"LG_SLD-LEGIARTI000006419280_0WJN"`) — filtre la JP citant cet article |

> **Attention — mapping typeDoc filtre ↔ type affiché** (testé le 2026-03-20) :
>
> L'enum Java `DocumentType` (backend) n'accepte **pas** les mêmes codes que ceux retournés dans le champ `type` des hits. Le tableau ci-dessous donne la correspondance :
>
> | Valeur de filtre API | Type retourné dans les hits | Contenu |
> |---|---|---|
> | `JURISPRUDENCE` | `JURISPRUDENCE_COURCASSATION`, `JURISPRUDENCE_COUAPPEL`, … | Décisions de justice |
> | `DOCTRINE` | `DOCTRINE_FASCICULE` | Fascicules d'encyclopédie (JurisClasseur) |
> | `REVUES` | `DOCTRINE_REVUE` | Articles de revue |
> | `FORMULE` | `DOCTRINE_REVUE` (sous-type formule) | Modèles / formulaires |
> | `FICHES_PRATIQUES` | `PRATIQUE` | Fiches pratiques |
> | `PUBLICATION_OFFICIELLE` | `REPMIN`, … | Réponses ministérielles, JO |
> | `ACTUALITIES` | `ACTUALITES` | Actualités |
>
> Les codes d'agrégation `DOCTRINE_FASCICULE`, `DOCTRINE_SYNTHESE`, `PRATIQUE`, `SOURCES_CODE`, `SOURCES_LEGISLATION` etc. provoquent une **erreur 500** s'ils sont envoyés comme filtre. Le client Python (`search.py`) résout automatiquement ces alias vers les valeurs API correctes.

**Tri disponibles** :

| Champ de tri | Description |
|-------------|-------------|
| `SCORE` | Par pertinence (défaut) |
| `DOCUMENT_DATE` | Par date du document |

### POST `/api/recherche//search` — Format de réponse

```json
{
  "data": {
    "total": 10000,
    "totalText": "+500",
    "maxScore": 211.11758,
    "hits": [ /* voir structure hit ci-dessous */ ],
    "combining": {
      "lastCombiningOffset": 1,
      "nbHitsCollected": 1,
      "combiningHttpStatus": "OK",
      "hasCombined": true
    },
    "ner_service": {
      "ngrams": [
        { "score": 0.33, "start": 0, "end": 19, "text": "licenciement abusif" }
      ]
    }
  }
}
```

**Structure d'un hit (document de doctrine/revue)** :

```json
{
  "id": "PS_KPRE-715798_0KU0",
  "score": 211.11758,
  "source": {
    "taxo": { /* taxonomie : dates, numéros, scope, références législatives */ },
    "document": {
      "date": 1770854400000,
      "kid": "KPRE-715798",
      "title": "Titre du document",
      "type": "DOCTRINE_REVUE",
      "typeContenu": "...",
      "id": "PS_KPRE-715798_0KU0",
      "thematique": "CT_CTFR",
      "packs": ["..."],
      "markets": ["..."],
      "scopeFilters": "...",
      "docIdStable": "...",
      "fragment": "...",
      "typeContribution": "...",
      "revueTitle": "...",
      "revueText": "...",
      "creationDate": 1770825600000
    },
    "revue": {
      "date": 1770854400000,
      "matiereCode": "PNO_RJCPEA",
      "matricule": 1061,
      "numero": [7],
      "numeroLabel": "7",
      "sommaireId": "PS_SJE_202607SOMMAIREPS_2_0KU0",
      "typeContributionCode": "TCB_TCBPANOJURISP",
      "hasPdf": true,
      "typeContributionLabel": "panorama de Jurisprudence",
      "matiere": "La Semaine Juridique - Entreprise et affaires (JCP E)"
    },
    "doctrine": {
      "thematique": "Affaires"
    }
  },
  "highlights": {
    "document.text": [
      "Extrait avec <em>terme surligné</em>..."
    ]
  }
}
```

**Structure d'un hit (jurisprudence)** :

```json
{
  "id": "JP_KODCASS-0526258_0KRH",
  "score": 785.9901,
  "source": {
    "taxo": { /* decided_date, court_sect, decision_num, leg_refcited_article, scope, act_refcited_lawnum */ },
    "document": {
      "date": 1732665600000,
      "kid": "KODCASS-0526258",
      "combiningId": "32202661",
      "title": "Cour de cassation, Chambre sociale, 27 Novembre 2024 – n° 22-13.694",
      "type": "JURISPRUDENCE_COURCASSATION",
      "nbDecSimilaire": 1,
      "thematique": "CT_CTFR",
      "jpMotif": "..."
    },
    "jurisprudence": {
      "summary": ["Résumé de la décision..."],
      "typeLitigesPrecis": ["..."],
      "solutionJuridique": "SO_SLCASPAR",
      "solutionJuridiqueLabel": "Cassation partielle",
      "annee": 2024,
      "legiRef": { /* ... */ },
      "typeJp": "DECISION",
      "codePublications": ["CPU_CPUBBULL"],
      "typeLitiges": ["Contrat de travail, rupture"],
      "themes": ["..."],
      "numeroJurisprudence": ["22-13.694"],
      "typeFormationCode": "FO_FO%7BT%7DTFCHAMBR%7BL%7DFQSOCIA",
      "titrage": ["..."],
      "classeJuridiction": "Cour de cassation",
      "classeJuridictionShort": "Cass.",
      "dateDeDecision": 1732665600000,
      "typeDecision": "arrêt",
      "typeFormation": "chambre sociale"
    }
  }
}
```

**Structure d'un hit (actualité)** :

Les actualités ont un ID de la forme `KC_NEWS-{id}_0KVW` et une clé `news` dans `source` :

```json
{
  "id": "KC_NEWS-2032807_0KVW",
  "source": {
    "news": {
      "thematique": ["thm482041"],
      "thematiqueLabel": ["public"]
    },
    "taxo": { /* ... */ },
    "document": { /* ... */ }
  }
}
```

---

### POST `/api/recherche//aggregate` — Agrégation / facettes

Même structure de requête que `/search`, mais le champ `aggregations` détermine quelles facettes sont calculées.

**Variantes observées** :

| Contexte | Agrégations demandées |
|----------|----------------------|
| Compteurs par type de contenu (pie chart) | `["TYPEDOC"]` |
| Histogramme par année | `["ANNEE"]` |
| Facettes JP (après filtre Jurisprudence) | `["CLASSEJURIDICTION", "TYPELITIGES", "CODEPUBLICATIONJP", "CRITERESSELECTION", "COMMENTEDBY", "FILTRECONCLUSIONS", "LEGIREFDE", "LEGIFILTRE", "SOLUTIONJURIDIQUE", "ANNEE", "TYPEDOC"]` |
| Facettes JP additionnelles | `["THEMES"]` |
| Compteurs combinés | `["ANNEE", "TYPEDOC"]` |

**Format de réponse** :

```json
[
  {
    "key": "typeDoc",
    "buckets": [
      {
        "code": "JURISPRUDENCE",
        "docType": "JURISPRUDENCE",
        "count": 430243,
        "countText": "+500",
        "key": "Jurisprudence"
      },
      {
        "code": "REVUES",
        "docType": "REVUES",
        "count": 5057,
        "countText": "+500",
        "key": "Revues"
      }
    ]
  }
]
```

**Facette `codePublicationJp`** (spécifique jurisprudence) :

```json
{
  "key": "codePublicationJp",
  "buckets": [
    { "key": "A - Publié au Lebon", "count": 21, "code": "CPU_CPUBA", "type": "ADM", "rang": 1 },
    { "key": "B - Mentionné au Lebon", "count": 21, "code": "CPU_CPUBB", "type": "ADM", "rang": 2 },
    { "key": "R - Inédit – intérêt majeur", "count": 43, "code": "CPU_CPUBR", "type": "ADM", "rang": 3 },
    { "key": "B - Publié au Bulletin", "count": 5625, "code": "CPU_CPUBBULL", "type": "JUD", "rang": 6 },
    { "key": "R - Publié au Rapport", "count": 96, "code": "CPU_CPUBRAPP", "type": "JUD", "rang": 7 },
    { "key": "L - Publié aux Lettres de chambre", "count": 2, "code": "CPU_CPUBL", "type": "JUD", "rang": 8 },
    { "key": "Inédit", "count": 604, "code": "CPU_CPUBINEPUB", "rang": 10 },
    { "key": "Non classé", "count": 43197, "code": "CPU_CPUBNONCLASSE", "rang": 11 }
  ]
}
```

> Les buckets peuvent avoir un champ `type` indiquant la juridiction : `"ADM"` (administrative), `"JUD"` (judiciaire).

**Liste complète des codes `typeDoc` (agrégation)** :

| Code agrégation | Label | Filtre API correspondant | Description |
|------|-------|---|-------------|
| `ACTUALITIES` | Actualités | `ACTUALITIES` | Articles d'actualité juridique |
| `REVUES` | Revues | `REVUES` | Articles de revues/presse juridique |
| `DOCTRINE_FASCICULE` | Encyclopédies | **`DOCTRINE`** ⚠️ | Fascicules JurisClasseur |
| `DOCTRINE_SYNTHESE` | Synthèses | ❌ pas de filtre dédié | Documents de synthèse |
| `FORMULE` | Formules | `FORMULE` | Modèles et formules |
| `PRATIQUE` | Fiches pratiques | **`FICHES_PRATIQUES`** ⚠️ | Fiches pratiques |
| `JURISPRUDENCE` | Jurisprudence | `JURISPRUDENCE` | Décisions de justice |
| `SOURCES_CODE` | Codes | ❌ erreur 500 | Articles de codes |
| `SOURCES_LEGISLATION` | Législation française | ❌ erreur 500 | Textes législatifs et réglementaires |
| `SOURCES_LEGISLATIONEUROINTER` | Législation euro/inter. | ❌ erreur 500 | Droit européen et international |
| `SOURCES_CONVCOLL` | Conventions collectives | ❌ erreur 500 | Conventions et accords collectifs |
| `PUBLICATION_OFFICIELLE` | Publications officielles | `PUBLICATION_OFFICIELLE` | JORF, BOFiP, rép. ministérielles |

> ⚠️ Les codes marqués d'un avertissement ont un **nom de filtre différent** du code d'agrégation. Le client Python résout automatiquement ces alias.

---

### POST `/api/navigation/time-line` — Chronologie procédurale

**Depuis la page de résultats** (pour les résultats affichés) :

```json
["PS_KPRE-715798_0KU0", "PS_KPRE-685506_0KT6", ...]
```

Le body est un **tableau de docIds** correspondant aux résultats de recherche affichés. La réponse est `{}` si aucun des documents n'est une décision de jurisprudence.

**Depuis une décision de jurisprudence** (pour une décision unique) :

```json
["JP_KODCASS-0526258_0KRH"]
```

**Format de réponse** :

```json
{
  "directs": {
    "JP_KODCASS-0526258_0KRH": [
      {
        "solutionLabel": null,
        "docIdSource": "JU_KJ-1983133_0KRJ",
        "docId": null,
        "qualif": "QRSC_QRSCANT",
        "title": null,
        "label": null,
        "annee": 2019,
        "classeJuridictionCode": "CJ_TJCPRUDH",
        "classeJuridiction": "cons. prud'h.",
        "date": [2019, 3, 8],
        "numeros": ["17/00528"],
        "siege": "Bordeaux",
        "direction": "DIRECT",
        "qrsc_QRSCANT": true
      },
      {
        "solutionLabel": "Infirmation",
        "docIdSource": "JP_KODCASS-0526258_0KRH",
        "docId": "JU_KJ-1983133_0KRJ",
        "qualif": "QRSC_QRSCANT",
        "title": "Cour d'appel, Bordeaux, Chambre sociale, section A, 19 Janvier 2022 – n° 19/01466",
        "annee": 2022,
        "classeJuridictionCode": "CJ_TJCA",
        "classeJuridiction": "CA",
        "date": [2022, 1, 19],
        "numeros": [],
        "siege": "Bordeaux",
        "direction": "DIRECT",
        "qrsc_QRSCANT": true
      }
    ]
  }
}
```

**Champs d'un élément de la timeline** :

| Champ | Description |
|-------|-------------|
| `qualif` | Type de lien : `QRSC_QRSCANT` = décision antérieure dans la chaîne procédurale |
| `classeJuridictionCode` | Code de la juridiction (`CJ_TJCPRUDH`, `CJ_TJCA`, `CJ_TJCASS`) |
| `classeJuridiction` | Label court (`cons. prud'h.`, `CA`, `Cass.`) |
| `solutionLabel` | Solution de la décision (`Infirmation`, `Rejet`, `Cassation partielle`, etc.) |
| `date` | Tableau `[année, mois, jour]` |
| `siege` | Ville du siège de la juridiction |
| `direction` | `"DIRECT"` pour la chaîne procédurale directe |
| `docId` | ID du document lié (peut être `null` si la décision n'est pas dans la base) |
| `docIdSource` | ID du document source de la relation |

---

### POST `/api/navigation/links` — Liens entre documents (depuis les résultats)

Appelé automatiquement après une recherche pour enrichir les résultats avec les liens.

**Request body** :

```json
{
  "docIds": ["PS_KPRE-715798_0KU0", "PS_KPRE-685506_0KT6", ...],
  "qualifications": ["CITATION", "SIMILAR_RELATED", "COMBINING"]
}
```

**Format de réponse** :

```json
[
  {
    "PS_KPRE-684975_0KU2": {
      "citations": [
        {
          "docId": "PS_SJS_202435SOMMAIREPS_2_0KU2",
          "title": "La Semaine Juridique Social",
          "type": "DOCTRINE_REVUE",
          "tocId": "PNO_RJCPS",
          "date": 1725321600000,
          "metas": {
            "revue": { "date": 1725321600000, "conclusionsRappPubl": false, "numero": [35] },
            "document": { "date": 1725321600000, "type": "DOCTRINE_REVUE" }
          }
        }
      ]
    }
  }
]
```

---

## Navigation des Codes

### URL de la page des codes

```
/codes
```

Liste tous les codes disponibles avec indication `commenté` pour ceux ayant des annotations.

### URL d'un code spécifique

```
/codes/{NomCode}/{codeIdStable}
```

Exemple : `/codes/Code_civil/SLD-LEGITEXT000006070721`

### GET `/api/navigation/codes/{codeIdStable}` — Arborescence d'un code

Retourne la table des matières complète d'un code.

**Format de réponse** :

```json
{
  "title": "Table des matières",
  "doc_id_stable": "SLD-LEGITEXT000006070721",
  "root": [
    {
      "title": "Titre préliminaire : De la publication, des effets et de l'application des lois en général",
      "doc_id_stable": "LG_SLD-LEGISCTA000006089696_0WJN",
      "indice": 0,
      "children": [
        {
          "title": "Article 1",
          "doc_id_stable": "LG_SLD-LEGIARTI000006419280_0WJN"
        }
      ]
    },
    {
      "title": "Livre Ier : Des personnes",
      "children": [
        {
          "title": "Titre Ier : Des droits civils",
          "children": [ /* sous-titres et articles */ ]
        }
      ]
    }
  ]
}
```

L'arborescence est récursive : chaque nœud a un `title`, un `doc_id_stable`, et optionnellement des `children`.

### Consultation d'un article de code

**URL** : `/codes/{NomCode}/{codeIdStable}/document/{articleDocId}?source=navigation`

**Endpoints appelés** :
1. `GET /api/document/metadata/{articleDocId}` — Métadonnées de l'article
2. `GET /api/navigation/codes/{codeIdStable}` — Arborescence pour la navigation latérale
3. `GET /api/navigation/links/{articleDocId}?jp=false` — Liens depuis cet article
4. `POST /api/recherche//search` avec filtre `legiFiltre` — Jurisprudence citant cet article :

```json
{
  "q": null,
  "project": "all",
  "highlight": true,
  "offset": 0,
  "size": 2,
  "filters": [
    { "name": "legiFiltre", "values": ["LG_SLD-LEGIARTI000006419280_0WJN"] },
    { "name": "typeDoc", "values": ["JURISPRUDENCE"] }
  ],
  "sorts": [{ "field": "DOCUMENT_DATE", "order": "DESC" }],
  "fields": ["DOCUMENT_ID", "DOCUMENT_ALL_JP", "DOCUMENT_TITLE", "DOCUMENT_TYPE"]
}
```

**Identifiants des articles de code** :
- Format du docId : `LG_SLD-{LegifranceId}_0WJN`
- Le `LegifranceId` correspond à l'identifiant Légifrance (ex: `LEGIARTI000006419280`, `LEGISCTA000006089696`)

---

## Recherche avancée

### URL

```
/search/assistance/advanced-search
```

### Fonctionnement

La recherche avancée est un **formulaire frontend** qui construit une requête textuelle avec des opérateurs booléens, puis redirige vers la page de recherche standard.

**URL de redirection** :
```
/search?q=(contrat bail)&sort=score&from=0&to={timestamp}&source=advanced-search
```

### POST `/api/recherche/analyse` — Analyse de requête avancée

Endpoint appelé pour parser/valider la requête du formulaire avancé.

**Request body** :

```json
[
  {
    "termQuery": { "field": "ALL", "term": "contrat" },
    "searchType": "ALL_TERMS",
    "proximity": { "distance": 0, "distanceType": "ANY" }
  }
]
```

**Champs de `termQuery`** :

| Champ | Valeurs | Description |
|-------|---------|-------------|
| `field` | `"ALL"`, `"TITLE"`, `"TEXT"` | Champ de recherche : tout, titre, texte |
| `term` | string | Terme recherché |

**Champs de `proximity`** :

| `distanceType` | `distance` | Description |
|----------------|-----------|-------------|
| `"ANY"` | 0 | Sans proximité définie |
| `"WORDS"` | 1 | PROX1 — termes accolés |
| `"WORDS"` | ~5 | PROX2 — termes proches (environ 1 phrase) |

**`searchType`** :

| Valeur | Opérateur | Description |
|--------|-----------|-------------|
| `ALL_TERMS` | ET | Comprenant tous les termes suivants |
| `ANY_TERMS` | OU | Comprenant l'un des termes suivants |
| `NONE_TERMS` | SAUF | Ne comprenant aucun des termes suivants |

**Syntaxe de la requête dans le champ `q`** :

| Opérateur | Exemple | Description |
|-----------|---------|-------------|
| `ET` | `contrat ET bail` | Les deux termes doivent être présents |
| `OU` | `contrat OU bail` | L'un ou l'autre terme |
| `SAUF` | `contrat SAUF bail` | Le premier mais pas le second |
| `PROX1[a b]` | `PROX1[contrat bail]` | Termes accolés |
| `PROX2[a b]` | `PROX2[contrat bail]` | Termes proches (~1 phrase) |
| `"..."` | `"contrat de bail"` | Expression exacte |
| `(a) :titre` | `(contrat) :titre` | Recherche dans les titres uniquement |
| `(a) :texte` | `(contrat) :texte` | Recherche dans le texte uniquement |
| `( )` | `(a ET b) OU c` | Parenthèses de groupement |

---

## Export / Impression

### Export PDF

```
POST /api/document/records/{docId}/pdf
```

**Request body** :

```json
{
  "filename": "Cour de cassation, Chambre sociale, 27 Novembre 2024 – n° 22-13.694.pdf"
}
```

**Réponse** : Le fichier PDF en binaire (`Content-Type: application/pdf`).

### Export Word (DOCX)

```
POST /api/document/records/{docId}/docx
```

**Request body** :

```json
{
  "filename": "Cour de cassation, Chambre sociale, 27 Novembre 2024 – n° 22-13.694.docx"
}
```

**Réponse** : Le fichier DOCX en binaire (`Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document`).

### Impression

Le bouton d'impression utilise `window.print()` du navigateur — aucun appel API spécifique.

---

## Dossiers de travail (Workfolders)

### Vérification d'accès

```
GET /api/workfolder/v1/workfolders/CanUseWorkfolder
```

### Liste des éléments d'un dossier

```
GET /api/workfolder/v1/workfolders/itemlist/load
```

### Ajout d'un document à un dossier

```
POST /api/workfolder/v1/workfolders/ItemTree/item
```

**Request body** :

```json
{
  "id": null,
  "type": "JURISPRUDENCE_COURCASSATION",
  "label": "Cour de cassation, Chambre sociale, 27 Novembre 2024 – n° 22-13.694",
  "title": null,
  "suffixId": null,
  "userPermId": null,
  "docId": "JP_KODCASS-0526258_0KRH",
  "folderId": "ab5b296e-7a1f-4e2c-9202-be92b2b8bb99",
  "itemType": "document",
  "coreDataItemDetails": {
    "documentDate": "1732665600000",
    "annee": "2024",
    "classeJuridiction": "Cour de cassation",
    "dateDeDecision": "1732665600000",
    "numeroJurisprudence": "",
    "priorLinks": "",
    "solutionJuridique": "SO_SLCASPAR",
    "codePublications": "",
    "typeFormation": "chambre sociale",
    "typeFormationCode": "FO_FO%7BT%7DTFCHAMBR%7BL%7DFQSOCIA",
    "typeDecision": "arrêt",
    "typeJp": "DECISION",
    "typeLitiges": "",
    "typeLitigesPrecis": "",
    "themes": "",
    "legiRef": "",
    "classeJuridictionShort": "Cass.",
    "solutionJuridiqueLabel": "Cassation partielle"
  }
}
```

**Champs principaux** :

| Champ | Description |
|-------|-------------|
| `id` | `null` pour un ajout, ID existant pour une modification |
| `type` | Type du document (`JURISPRUDENCE_COURCASSATION`, `DOCTRINE_REVUE`, etc.) |
| `label` | Titre affiché du document |
| `docId` | Identifiant du document |
| `folderId` | UUID du dossier cible |
| `itemType` | `"document"` |
| `coreDataItemDetails` | Métadonnées du document (spécifiques au type) |

**Interface** : Le bouton "Classer dans" propose :
1. **Dossier par défaut** — ajoute directement au dossier par défaut de l'utilisateur
2. **Choisir un autre dossier** — ouvre un sélecteur de dossiers

---

## Actualités, Synthèses et Formules

Ces types de contenu utilisent les **mêmes endpoints** que les autres documents :

| Type | Code `typeDoc` | Préfixe docId | Endpoint de consultation |
|------|---------------|---------------|--------------------------|
| **Actualités** | `ACTUALITIES` | `KC_NEWS-{id}_0KVW` | `/api/document/metadata/{docId}` + `/api/document/records/{docId}` |
| **Synthèses** | `DOCTRINE_SYNTHESE` | Variable | Idem |
| **Formules** | `FORMULE` | `PS_KPRE-{id}_0KTC` | Idem — stockées comme des articles de revue (`type: DOCTRINE_REVUE`) |

> **Note** : Les Formules sont techniquement des articles de revue avec un `typeDoc` spécifique dans l'agrégation. Elles ont les mêmes clés `source` que les revues (`taxo`, `revue`, `document`, `doctrine`).

> **Note** : Les Actualités ont une clé supplémentaire `news` dans `source` avec des informations de thématique.

### Identifiants de documents (compléments)

| Préfixe docId | Type | Description |
|---------------|------|-------------|
| `KC_NEWS-` | Actualité | Article d'actualité juridique |
| `LG_SLD-` | Source officielle | Article de code ou texte législatif (ID Légifrance) |
| `SLD-` | Code | Identifiant de code (sans préfixe `LG_`, utilisé dans les URL de navigation) |

---

## Endpoints supplémentaires identifiés

### POST `/api/recherche//ror` — Résultats connexes

**Request body** :

```json
{ "query": "licenciement abusif" }
```

Retourne des résultats recommandés/connexes à la requête.

### POST `/api/counter-report/api/usages/search-activities` — Traçage recherche

Appelé automatiquement à chaque recherche pour le comptage d'usage.

### POST `/api/counter-report/api/usages/document-activities` — Traçage consultation

**Request body** :

```json
{
  "docId": "JP_KODCASS-0526258_0KRH",
  "docType": "JURISPRUDENCE_COURCASSATION",
  "sessionId": "uuid-session",
  "customerId": "urn:ecm:XXXXX",
  "date": "2026-03-19T10:07:13.222Z",
  "investigation": false,
  "investigationOnly": false,
  "yop": 2024,
  "parentId": ""
}
```

### POST `/api/data-history/history/document` — Enregistrer consultation

**Request body** :

```json
{
  "docId": "LG_SLD-LEGIARTI000006419280_0WJN",
  "docType": "SOURCES_CODE",
  "suffixId": "SLD-LEGITEXT000006070721"
}
```

Le champ `suffixId` contient l'ID du code parent pour les articles de code.

### Liste complète des facettes d'agrégation

| Code d'agrégation | Description |
|--------------------|-------------|
| `TYPEDOC` | Type de document |
| `ANNEE` | Année |
| `CLASSEJURIDICTION` | Classe de juridiction |
| `TYPELITIGES` | Type de litiges |
| `THEMES` | Thèmes (JP) |
| `THEMATIQUE` | Thématique |
| `MATIERE` | Matière |
| `CODE` | Code (législatif) |
| `CODEPUBLICATIONENCYCLO` | Code publication encyclopédies |
| `CODEPUBLICATIONJP` | Code publication jurisprudence |
| `NEWSTHEMATIQUE` | Thématique actualités |
| `PARTIE` | Partie |
| `OFFICIALPUBLICATIONS` | Publications officielles |
| `CRITERESSELECTION` | Critères de sélection |
| `COMMENTEDBY` | Commenté par (oui/non) |
| `FILTRECONCLUSIONS` | Filtre conclusions |
| `SOLUTIONJURIDIQUE` | Solution juridique |
| `LEGIREFDE` | Références législatives |
| `LEGIFILTRE` | Filtre législatif (article de code spécifique) |

---

## Structure des metadata d'encyclopédie (fascicule)

> **Testé le 2026-03-19** sur le fascicule 212 du JurisClasseur Alsace-Moselle (`EN_KEJC-238100_0KR8`).

```
GET /api/document/metadata/EN_KEJC-238100_0KR8
```

```json
{
  "_id": "EN_KEJC-238100_0KR8",
  "creationDate": 1725507438912,
  "doctrine": {
    "thematique": "Public"
  },
  "document": {
    "date": 1719792000000,
    "docIdStable": "EN_KEJC-238100_0KR8",
    "id": "EN_KEJC-238100_0KR8",
    "kid": "KEJC-238100",
    "thematique": "CT_CTFR",
    "title": "Fasc. 212 : Droit de l'eau en Alsace-Moselle",
    "type": "DOCTRINE_FASCICULE",
    "typeContenu": "TCO_TCNCONTRIBLNF",
    "typeContribution": "TCB_TCBFACOM",
    "signatures": ["ENOI_ELNFAL0|212"],
    "creationDate": 1725507072000
  },
  "encyclo": {
    "type": "FASCICULE",
    "codePublication": "ENOI_ELNFAL0",
    "codePublicationLabel": "JurisClasseur Alsace-Moselle",
    "matricule": "212",
    "auteur": ["Elsa WOELFLI", "Jean-Materne STAUB"],
    "typeContribution": "COMMENTAIRE"
  },
  "from": "rdf"
}
```

> **Différences avec la jurisprudence** :
> - Clé `encyclo` au lieu de `jurisprudence`, contenant l'encyclopédie parente, le matricule (numéro de fascicule) et les auteurs.
> - Clé `doctrine` avec la thématique éditoriale.
> - `from` vaut `"rdf"` pour les encyclopédies (vs `"countRenvois"` pour la jurisprudence Cass.).
> - `document.signatures` : format `"{codePublication}|{matricule}"`.

---

## Automatisation avec Playwright (Python)

L'API Lexis 360 est protégée par **TLS fingerprinting** au niveau du proxy Envoy (voir section 6). Les clients HTTP classiques (curl, Python `requests`) sont bloqués. **Playwright** est une option viable pour automatiser l'accès :

```python
# pip install playwright && playwright install chromium
from playwright.sync_api import sync_playwright
import json

def download_fascicule(doc_id, output_path=None):
    """
    Télécharge un fascicule depuis Lexis 360 via Playwright.
    Pré-requis : être connecté à Lexis 360 dans le navigateur Chromium géré par Playwright,
    ou fournir un storage_state sauvegardé après un login manuel.
    """
    with sync_playwright() as p:
        # Utiliser un contexte persistant pour réutiliser la session
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        # Naviguer vers Lexis 360 (déclenche le login OIDC si pas de session)
        page.goto("https://www.lexis360intelligence.fr/home")
        page.wait_for_url("**/home**", timeout=60000)

        # Récupérer le token depuis le localStorage
        token = page.evaluate("localStorage.getItem('access_token')")

        # Appeler l'API metadata
        meta = page.evaluate(f"""
            fetch('/api/document/metadata/{doc_id}', {{
                headers: {{ 'Authorization': 'Bearer ' + localStorage.getItem('access_token') }}
            }}).then(r => r.json())
        """)
        title = meta.get('document', {}).get('title', doc_id)
        print(f"Titre : {{title}}")

        # Appeler l'API records (SSE → HTML)
        html = page.evaluate(f"""
            fetch('/api/document/records/{doc_id}', {{
                headers: {{ 'Authorization': 'Bearer ' + localStorage.getItem('access_token') }}
            }}).then(r => r.text()).then(raw => {{
                return raw.split('\\n')
                    .filter(line => line.startsWith('data: '))
                    .map(line => line.substring(6))
                    .join('');
            }})
        """)

        # Sauvegarder
        fname = output_path or f"{{title.replace('/', '_').replace(':', '_')}}.html"
        with open(fname, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"Sauvegardé : {{fname}} ({{len(html)}} octets)")

        # Sauvegarder le state pour les prochaines fois
        context.storage_state(path="lexis_session.json")
        browser.close()

# Exemple : télécharger le fascicule 212 Alsace-Moselle
# download_fascicule("EN_KEJC-238100_0KR8")
```

> **Notes** :
> - Au premier lancement (`headless=False`), une fenêtre Chrome s'ouvre pour le login OIDC. Les fois suivantes, charger `storage_state` pour réutiliser la session.
> - Le token dure **24 heures**. Après expiration, le navigateur headless doit refaire le login OIDC ou utiliser le `refresh_token`.
> - Pour un usage en production, préférer `headless=True` avec un `storage_state` pré-authentifié.
