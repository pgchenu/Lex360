"""Classe principale orchestrant transport, auth et modules API."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from lex360.auth import TokenManager, DEFAULT_TOKEN_PATH
from lex360.transport_curl import CurlCffiTransport
from lex360.models import (
    DocumentMetadata,
    SearchResponse,
    NavigationSection,
    CodeTree,
    TimelineEntry,
)

logger = logging.getLogger(__name__)

# Types de documents dont le contenu est structuré (headings) → Markdown
_STRUCTURED_TYPES = {
    "DOCTRINE_FASCICULE",
    "DOCTRINE_REVUE",
    "DOCTRINE_SYNTHESE",
    "PRATIQUE",
    "FORMULE",
    "ACTUALITIES",
    "SOURCES_CODE",
    "SOURCES_LEGISLATION",
    "PUBLICATION_OFFICIELLE",
}


class Lex360Client:
    """
    Client principal pour l'API Lexis 360 Intelligence.

    Conventions de sortie :
    - Liens / navigation / métadonnées → objets Pydantic (sérialisables en JSON)
    - Contenu d'un document → str (Markdown pour les docs structurés, texte brut pour la JP)

    Usage :
        with Lex360Client() as client:
            results = client.search("licenciement abusif")
            text = client.get_document("JP_KODCASS-0519779_0KRH")
    """

    def __init__(
        self,
        token_path: Path | str = DEFAULT_TOKEN_PATH,
    ):
        self.auth = TokenManager(token_path)
        self.transport = CurlCffiTransport()
        self._started = False

    def start(self) -> None:
        """Démarre le transport et charge le token."""
        token = self.auth.access_token
        self.transport.start(token)
        self._started = True
        logger.info("Client Lex360 démarré.")

    def close(self) -> None:
        """Ferme la session."""
        self.transport.close()
        self._started = False

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.close()

    # ──────────────────────────────────────────────
    # Recherche (→ JSON)
    # ──────────────────────────────────────────────

    def search(
        self,
        query: str,
        *,
        filters: list[dict[str, Any]] | None = None,
        sort: str = "SCORE",
        sort_order: str = "DESC",
        offset: int = 0,
        size: int = 10,
        **kwargs,
    ) -> SearchResponse:
        """Recherche full-text sur Lexis 360."""
        from lex360.search import search
        return search(
            self.transport, query,
            filters=filters, sort=sort, sort_order=sort_order,
            offset=offset, size=size, **kwargs,
        )

    def search_by_number(
        self, number: str, *, size: int = 5, strict: bool = True,
    ) -> SearchResponse:
        """Recherche une décision par numéro (pourvoi, JurisData, RG, requête).

        strict=True : ne garde que les décisions portant ce numéro.
        strict=False : inclut aussi les décisions qui le citent.
        """
        from lex360.search import search_by_number
        return search_by_number(self.transport, number, size=size, strict=strict)

    # ──────────────────────────────────────────────
    # Métadonnées (→ JSON)
    # ──────────────────────────────────────────────

    def get_metadata(self, doc_id: str) -> DocumentMetadata:
        """Récupère les métadonnées d'un document."""
        from lex360.documents import get_metadata
        return get_metadata(self.transport, doc_id)

    # ──────────────────────────────────────────────
    # Contenu (→ Markdown ou texte brut)
    # ──────────────────────────────────────────────

    def get_document(self, doc_id: str, *, format: str = "auto") -> str:
        """
        Récupère le contenu d'un document.

        Formats :
        - "auto" : Markdown pour les docs structurés, texte brut pour la JP
        - "markdown" : force le Markdown
        - "text" : force le texte brut
        - "html" : retourne le HTML brut
        """
        from lex360.documents import get_content
        from lex360.text import html_to_text, html_to_markdown

        html = get_content(self.transport, doc_id)

        if format == "html":
            return html
        if format == "markdown":
            return html_to_markdown(html)
        if format == "text":
            return html_to_text(html)

        # Auto : détecter le type depuis le préfixe du docId
        doc_type = self._guess_type(doc_id)
        if doc_type in _STRUCTURED_TYPES:
            return html_to_markdown(html)
        return html_to_text(html)

    # ──────────────────────────────────────────────
    # Navigation / liens (→ JSON)
    # ──────────────────────────────────────────────

    def get_links(self, doc_id: str, jp: bool = False) -> list[NavigationSection]:
        """
        Récupère les liens de navigation pour un document.

        Pour la jurisprudence (jp=True) : décisions liées, commentaires,
        articles citant, textes visés.
        Pour les autres (jp=False) : liens généraux.
        """
        from lex360.navigation import get_links
        return get_links(self.transport, doc_id, jp=jp)

    def get_toc(self, doc_id: str) -> dict[str, Any]:
        """Récupère la table des matières d'un document."""
        from lex360.navigation import get_toc
        return get_toc(self.transport, doc_id)

    def get_timeline(self, doc_ids: list[str]) -> dict[str, list[TimelineEntry]]:
        """Récupère la frise chronologique procédurale."""
        from lex360.navigation import get_timeline
        return get_timeline(self.transport, doc_ids)

    def get_code_tree(self, code_id: str) -> CodeTree:
        """Récupère l'arborescence d'un code."""
        from lex360.navigation import get_code_tree
        return get_code_tree(self.transport, code_id)

    # ──────────────────────────────────────────────
    # Utilitaires internes
    # ──────────────────────────────────────────────

    @staticmethod
    def _guess_type(doc_id: str) -> str:
        """Devine le type de document à partir du préfixe du docId."""
        prefixes = {
            "EN_": "DOCTRINE_FASCICULE",
            "PS_": "DOCTRINE_REVUE",
            "FP_": "PRATIQUE",
            "KC_NEWS": "ACTUALITIES",
            "LG_": "SOURCES_CODE",
            "JP_": "JURISPRUDENCE_COURCASSATION",
            "JU_": "JURISPRUDENCE_COUAPPEL",
            "JK_": "JURISPRUDENCE",
        }
        for prefix, doc_type in prefixes.items():
            if doc_id.startswith(prefix):
                return doc_type
        return ""
