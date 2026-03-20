"""Endpoints de navigation /api/navigation/."""

from __future__ import annotations

from typing import Any

from lex360.models import NavigationSection, TimelineEntry, CodeTree
from lex360.transport import Transport


def get_links(
    transport: Transport,
    doc_id: str,
    jp: bool = False,
) -> list[NavigationSection]:
    """
    Récupère les liens de navigation pour un document.

    Endpoint : GET /api/navigation/links/{docId}?jp={true|false}

    Pour la jurisprudence, jp=true retourne les décisions liées,
    commentaires, articles citant, etc.
    Pour les autres documents, jp=false.
    """
    data = transport.get(
        f"/api/navigation/links/{doc_id}",
        params={"jp": str(jp).lower()},
    )
    if isinstance(data, list):
        return [NavigationSection.model_validate(item) for item in data]
    return []



def get_toc(transport: Transport, doc_id: str) -> dict[str, Any]:
    """
    Récupère la table des matières d'un document.

    Endpoint : GET /api/navigation/generate-toc/{docId}
    """
    return transport.get(f"/api/navigation/generate-toc/{doc_id}")


def get_jp_toc(transport: Transport, doc_id: str) -> dict[str, Any]:
    """
    Récupère la table des matières d'une décision de jurisprudence.

    Endpoint : GET /api/navigation/jurisprudence/toc/{docId}
    """
    return transport.get(f"/api/navigation/jurisprudence/toc/{doc_id}")


def get_timeline(
    transport: Transport,
    doc_ids: list[str],
) -> dict[str, list[TimelineEntry]]:
    """
    Récupère la frise chronologique procédurale.

    Endpoint : POST /api/navigation/time-line
    Body : tableau de docIds
    """
    data = transport.post("/api/navigation/time-line", doc_ids)
    if not isinstance(data, dict):
        return {}

    result = {}
    directs = data.get("directs", {})
    for doc_id, entries in directs.items():
        result[doc_id] = [TimelineEntry.model_validate(e) for e in entries]
    return result


def get_code_tree(transport: Transport, code_id: str) -> CodeTree:
    """
    Récupère l'arborescence complète d'un code.

    Endpoint : GET /api/navigation/codes/{codeIdStable}
    Exemple : get_code_tree("SLD-LEGITEXT000006070721")
    """
    data = transport.get(f"/api/navigation/codes/{code_id}")
    return CodeTree.model_validate(data)


def get_encyclo_fascicule(transport: Transport, doc_id: str) -> dict[str, Any]:
    """
    Navigation spécifique encyclopédies (fascicule).

    Endpoint : GET /api/navigation/encyclos/fascicule/{docId}
    """
    return transport.get(f"/api/navigation/encyclos/fascicule/{doc_id}")
