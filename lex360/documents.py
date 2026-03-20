"""Endpoints documents /api/document/."""

from __future__ import annotations

from lex360.models import DocumentMetadata
from lex360.text import parse_sse, html_to_text
from lex360.transport import Transport


def get_metadata(transport: Transport, doc_id: str) -> DocumentMetadata:
    """
    Récupère les métadonnées d'un document.

    Endpoint : GET /api/document/metadata/{docId}
    """
    data = transport.get(f"/api/document/metadata/{doc_id}")
    return DocumentMetadata.model_validate(data)


def get_content(transport: Transport, doc_id: str) -> str:
    """
    Récupère le contenu HTML d'un document (parsing SSE).

    Endpoint : GET /api/document/records/{docId}
    Retourne du text/event-stream, parsé pour extraire le HTML.
    """
    raw = transport.get_text(f"/api/document/records/{doc_id}")
    return parse_sse(raw)


def get_content_text(transport: Transport, doc_id: str) -> str:
    """
    Récupère le contenu d'un document en texte brut (pour LLM).

    Télécharge le HTML via SSE puis le convertit en texte.
    """
    html = get_content(transport, doc_id)
    return html_to_text(html)
