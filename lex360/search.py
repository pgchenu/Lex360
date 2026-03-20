"""Endpoints de recherche /api/recherche/."""

from __future__ import annotations

import re
import time
from typing import Any

from lex360.models import SearchHit, SearchResponse
from lex360.transport import Transport

# Agrégations par défaut (toutes les facettes)
DEFAULT_AGGREGATIONS = [
    "TYPELITIGES", "CLASSEJURIDICTION", "ANNEE", "THEMATIQUE",
    "CODEPUBLICATIONENCYCLO", "CODEPUBLICATIONJP", "MATIERE", "CODE",
    "TYPEDOC", "NEWSTHEMATIQUE", "PARTIE", "OFFICIALPUBLICATIONS",
    "CRITERESSELECTION", "COMMENTEDBY", "FILTRECONCLUSIONS",
    "SOLUTIONJURIDIQUE", "LEGIREFDE", "LEGIFILTRE",
]

# Mapping des types affichés (hits) vers les valeurs acceptées par l'API.
# L'enum backend DocumentType ne correspond pas aux types retournés dans les résultats.
# Ex : le filtre API "DOCTRINE" retourne des hits de type "DOCTRINE_FASCICULE" (encyclopédies),
#      le filtre API "REVUES" retourne des hits de type "DOCTRINE_REVUE" (articles de revue).
TYPEDOC_ALIASES: dict[str, str] = {
    # Alias utilisateur → valeur API
    "DOCTRINE_FASCICULE": "DOCTRINE",
    "ENCYCLOPEDIE": "DOCTRINE",
    "FASCICULE": "DOCTRINE",
    "DOCTRINE_REVUE": "REVUES",
    "PRATIQUE": "FICHES_PRATIQUES",
    "FICHE_PRATIQUE": "FICHES_PRATIQUES",
    "DOCTRINE_SYNTHESE": "DOCTRINE",  # pas de filtre dédié, inclus dans DOCTRINE
    "SOURCES_CODE": "REVUES",  # non supporté directement
    "SOURCES_LEGISLATION": "REVUES",  # non supporté directement
}

# Valeurs acceptées directement par l'enum DocumentType de l'API
VALID_API_TYPEDOC = {
    "JURISPRUDENCE", "REVUES", "DOCTRINE", "FORMULE",
    "FICHES_PRATIQUES", "PUBLICATION_OFFICIELLE", "ACTUALITIES",
    # Sous-types jurisprudence
    "JURISPRUDENCE_COURCASSATION", "JURISPRUDENCE_COUAPPEL",
}


def resolve_typedoc(value: str) -> str:
    """Résout un alias typeDoc vers la valeur acceptée par l'API."""
    upper = value.upper()
    return TYPEDOC_ALIASES.get(upper, upper)


# Patterns de numéros juridiques
# Pourvoi Cass. : 22-84.760, 24-15.901, etc.
_RE_POURVOI = re.compile(r"^\d{2}-\d{2}\.\d{3}$")
# JurisData : 2025-017611 (année sur 4 chiffres, tiret, 6 chiffres)
_RE_JURISDATA = re.compile(r"^\d{4}-\d{5,6}$")
# N° de requête (juridictions administratives) : 1900123, 456789, etc.
_RE_REQUETE = re.compile(r"^\d{5,7}$")
# N° RG (cours d'appel, TJ) : 19/01466, 22/03456
_RE_RG = re.compile(r"^\d{2}/\d{4,5}$")


def _collect_post_filter_types(
    filters: list[dict[str, Any]] | None,
) -> set[str] | None:
    """
    Détermine les types à post-filtrer côté client.

    Si l'utilisateur demande un type qui est un alias (ex: DOCTRINE_FASCICULE),
    l'API reçoit le type parent (DOCTRINE) qui peut retourner des sous-types
    non désirés. On retourne l'ensemble des types originaux demandés pour
    filtrer les hits après réception.

    Retourne None si aucun post-filtrage n'est nécessaire.
    """
    if not filters:
        return None
    for f in filters:
        if f.get("name") != "typeDoc":
            continue
        needs_post_filter = False
        for v in f["values"]:
            if v.upper() in TYPEDOC_ALIASES:
                needs_post_filter = True
                break
        if needs_post_filter:
            return {v.upper() for v in f["values"]}
    return None


def search(
    transport: Transport,
    query: str,
    *,
    filters: list[dict[str, Any]] | None = None,
    sort: str = "SCORE",
    sort_order: str = "DESC",
    offset: int = 0,
    size: int = 10,
    date_from: str = "0",
    date_to: str | None = None,
    aggregations: list[str] | None = None,
    highlight: bool = True,
    relevance_profile: str | None = None,
    fields: list[str] | None = None,
) -> SearchResponse:
    """
    Recherche principale sur Lexis 360.

    Endpoint : POST /api/recherche//search (double-slash intentionnel)

    Si un alias typeDoc est utilisé (ex: DOCTRINE_FASCICULE), les résultats
    sont post-filtrés côté client pour ne garder que le sous-type demandé.
    """
    if date_to is None:
        date_to = str(int(time.time() * 1000))

    # Déterminer si un post-filtrage sera nécessaire (avant résolution)
    post_filter_types = _collect_post_filter_types(filters)

    # Résoudre les alias typeDoc avant envoi à l'API
    resolved_filters = []
    for f in (filters or []):
        if f.get("name") == "typeDoc":
            resolved_values = [resolve_typedoc(v) for v in f["values"]]
            resolved_filters.append({"name": "typeDoc", "values": resolved_values})
        else:
            resolved_filters.append(f)

    # Demander plus de résultats si post-filtrage (on risque d'en perdre)
    api_size = size * 3 if post_filter_types else size

    body = {
        "q": query,
        "project": "all",
        "highlight": highlight,
        "offset": offset,
        "size": api_size,
        "from": date_from,
        "to": date_to,
        "filters": resolved_filters,
        "sorts": [{"field": sort, "order": sort_order}],
        "aggregations": aggregations if aggregations is not None else DEFAULT_AGGREGATIONS,
        "relevanceProfile": relevance_profile,
        "combining": None,
        "fields": fields,
    }

    data = transport.post("/api/recherche//search", body)
    response = SearchResponse.model_validate(data)

    # Post-filtrage côté client si nécessaire
    if post_filter_types and response.data.hits:
        response.data.hits = [
            h for h in response.data.hits
            if h.doc_type.upper() in post_filter_types
        ][:size]

    return response


def detect_number_type(number: str) -> str | None:
    """
    Détecte le type d'un numéro juridique.

    Retourne : 'pourvoi', 'jurisdata', 'requete', 'rg', ou None.
    """
    number = number.strip()
    if _RE_POURVOI.match(number):
        return "pourvoi"
    if _RE_JURISDATA.match(number):
        return "jurisdata"
    if _RE_RG.match(number):
        return "rg"
    if _RE_REQUETE.match(number):
        return "requete"
    return None


def search_by_number(
    transport: Transport,
    number: str,
    *,
    size: int = 5,
    strict: bool = True,
) -> SearchResponse:
    """
    Recherche une décision par numéro (pourvoi, JurisData, RG, requête).

    Détecte automatiquement le type de numéro et filtre sur la jurisprudence.
    Le numéro est recherché tel quel comme expression exacte.

    Si strict=True (défaut), ne retourne que les décisions dont le numéro
    apparaît dans le titre ou les signatures (la décision elle-même),
    excluant les décisions qui ne font que citer ce numéro dans leur corps.
    """
    number = number.strip()
    # Demander plus de résultats pour compenser le filtrage strict
    api_size = size * 3 if strict else size
    response = search(
        transport,
        f'"{number}"',
        filters=[{"name": "typeDoc", "values": ["JURISPRUDENCE"]}],
        sort="SCORE",
        size=api_size,
        highlight=False,
        aggregations=[],
    )

    if strict and response.data.hits:
        response.data.hits = [
            h for h in response.data.hits
            if _number_matches_hit(number, h)
        ][:size]

    return response


def _number_matches_hit(number: str, hit: SearchHit) -> bool:
    """Vérifie que le numéro apparaît dans le titre ou les signatures du hit."""
    # Présent dans le titre (ex: "n° 22-84.760")
    if number in hit.title:
        return True
    # Présent dans les signatures (ex: "3#2023-11-28|CJ_IJCASS|22-84.760")
    signatures = hit.source.document.get("signatures", [])
    for sig in signatures:
        if number in sig:
            return True
    return False
