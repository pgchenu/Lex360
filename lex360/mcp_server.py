"""Serveur MCP (Model Context Protocol) pour Lexis 360 Intelligence.

Expose les fonctionnalités de Lexis 360 aux LLM via le protocole MCP d'Anthropic.
Transport : stdio uniquement. Token via LEX_TOKEN env var.

Complète OpenLégi (textes bruts, codes, JORF) en apportant :
- Doctrine (JurisClasseur, revues)
- Navigation inter-documents
- Frises chronologiques procédurales
- Métadonnées enrichies
"""

from __future__ import annotations

import logging
from datetime import datetime

from mcp.server.fastmcp import FastMCP

from lex360.client import Lex360Client
from lex360.exceptions import AuthError, Lex360Error, NotFoundError

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Serveur MCP
# ──────────────────────────────────────────────

mcp = FastMCP(
    "lex360",
    instructions=(
        "Serveur Lexis 360 Intelligence — doctrine juridique française, "
        "jurisprudence enrichie, navigation inter-documents. "
        "Complémentaire à OpenLégi (textes de loi, codes, JORF). "
        "Commencez par l'outil `guide` pour découvrir les outils disponibles."
    ),
)

# ──────────────────────────────────────────────
# Client singleton lazy
# ──────────────────────────────────────────────

_client: Lex360Client | None = None


def _get_client() -> Lex360Client:
    """Retourne un client Lex360 prêt à l'emploi (singleton lazy)."""
    global _client
    if _client is None or not _client._started:
        _client = Lex360Client()
        _client.start()
    if _client.auth.is_expired:
        _client.close()
        _client = Lex360Client()
        _client.start()
    return _client


# ──────────────────────────────────────────────
# Catalogue d'outils pour le guide
# ──────────────────────────────────────────────

_TOOL_CATALOG = {
    "doctrine": {
        "outils": ["rechercher (type_doc='DOCTRINE')", "lire_doctrine", "metadata_document"],
        "description": "Fascicules JurisClasseur, articles de revue, synthèses doctrinales",
        "mots_clés": [
            "doctrine", "fascicule", "jurisclasseur", "revue", "article",
            "commentaire", "auteur", "analyse", "encyclopédie", "synthèse",
        ],
    },
    "codes_et_textes": {
        "outils": ["arborescence_code", "lire_article_code", "lire_texte", "liens_document"],
        "description": "Codes annotés, articles de loi, textes législatifs et réglementaires",
        "mots_clés": [
            "code", "article", "loi", "décret", "ordonnance", "législation",
            "réglementation", "texte", "légifrance", "code civil", "code pénal",
            "code du travail", "annoté", "annotation",
        ],
    },
    "analyse_procédurale": {
        "outils": ["rechercher_decision", "frise_chronologique", "liens_document (jurisprudence=True)"],
        "description": "Historique procédural, décisions liées, parcours d'une affaire",
        "mots_clés": [
            "chronologie", "frise", "procédure", "historique", "pourvoi",
            "appel", "cassation", "renvoi", "parcours", "instance",
        ],
    },
    "navigation": {
        "outils": ["liens_document", "table_des_matieres", "metadata_document"],
        "description": "Liens croisés entre documents, textes visés, commentaires citant",
        "mots_clés": [
            "lien", "cité", "vise", "visé", "commentaire", "référence", "connexe",
            "table des matières", "sommaire", "structure", "texte",
        ],
    },
    "recherche": {
        "outils": ["rechercher", "rechercher_decision"],
        "description": "Recherche full-text et par numéro de décision",
        "mots_clés": [
            "chercher", "trouver", "recherche", "quel", "existe",
            "décision", "arrêt", "jugement",
        ],
    },
}


# ──────────────────────────────────────────────
# Codes connus (nom → ID stable Légifrance)
# ──────────────────────────────────────────────

_CODES_CONNUS = {
    "code civil": "SLD-LEGITEXT000006070721",
    "code pénal": "SLD-LEGITEXT000006070719",
    "code du travail": "SLD-LEGITEXT000006072050",
    "code de commerce": "SLD-LEGITEXT000005634379",
    "code de procédure civile": "SLD-LEGITEXT000006070716",
    "code de procédure pénale": "SLD-LEGITEXT000006071154",
    "code général des impôts": "SLD-LEGITEXT000006069577",
    "code de la consommation": "SLD-LEGITEXT000006069565",
    "code de la santé publique": "SLD-LEGITEXT000006072665",
    "code de l'environnement": "SLD-LEGITEXT000006074220",
    "code de l'urbanisme": "SLD-LEGITEXT000006074075",
    "code de la propriété intellectuelle": "SLD-LEGITEXT000006069414",
    "code de la sécurité sociale": "SLD-LEGITEXT000006073189",
    "code général des collectivités territoriales": "SLD-LEGITEXT000006070633",
    "code de justice administrative": "SLD-LEGITEXT000006070933",
}


def _resolve_code_id(code_id_ou_nom: str) -> str:
    """Résout un nom de code ou un ID technique en ID stable."""
    normalized = code_id_ou_nom.strip().lower()
    if normalized in _CODES_CONNUS:
        return _CODES_CONNUS[normalized]
    if code_id_ou_nom.startswith("SLD-"):
        return code_id_ou_nom
    noms = ", ".join(n.title() for n in sorted(_CODES_CONNUS))
    raise ValueError(
        f"Code inconnu : « {code_id_ou_nom} ». "
        f"Codes disponibles : {noms}. "
        f"Ou passez directement un ID (SLD-LEGITEXT...)."
    )


def _guide_impl(contexte_juridique: str) -> str:
    """Implémentation du guide, sans dépendance au client."""
    contexte_lower = contexte_juridique.lower()
    scored: list[tuple[int, str, dict]] = []

    for name, group in _TOOL_CATALOG.items():
        score = sum(1 for kw in group["mots_clés"] if kw in contexte_lower)
        if score > 0:
            scored.append((score, name, group))

    scored.sort(key=lambda x: x[0], reverse=True)

    # Si aucun match, recommander la recherche par défaut
    if not scored:
        scored = [(1, "recherche", _TOOL_CATALOG["recherche"])]

    parts = [f"# Guide Lexis 360 — « {contexte_juridique} »\n"]

    parts.append("## Outils recommandés\n")
    for _score, name, group in scored:
        parts.append(f"### {name.replace('_', ' ').title()}")
        parts.append(f"{group['description']}\n")
        parts.append("Séquence d'appel :")
        for i, outil in enumerate(group["outils"], 1):
            parts.append(f"  {i}. `{outil}`")
        parts.append("")

    parts.append("## Lexis 360 vs OpenLégi\n")
    parts.append(
        "- **Lexis 360** : doctrine (JurisClasseur, revues), **codes annotés** "
        "(annotations doctrine + JP sous chaque article), métadonnées enrichies, "
        "liens croisés, frises procédurales, jurisprudence annotée\n"
        "- **OpenLégi** : textes de loi bruts (sans annotations), codes, "
        "Journal Officiel, conventions collectives\n"
    )
    parts.append("## Obtenir un doc_id\n")
    parts.append(
        "Les doc_id s'obtiennent via `rechercher`, `rechercher_decision` "
        "ou `arborescence_code` (pour les articles de codes). "
        "Format : `{PREFIX}_{KID}_{SUFFIX}` — ex. `EN_KEJC-238100_0KR8` (fascicule), "
        "`JP_KODCASS-0519779_0KRH` (Cass.), `LG_SLD-LEGIARTI..._0WJN` (article de code)."
    )

    return "\n".join(parts)


# ──────────────────────────────────────────────
# Gestion d'erreurs
# ──────────────────────────────────────────────


def _handle_error(e: Exception) -> str:
    """Transforme une exception en message lisible."""
    if isinstance(e, NotFoundError):
        return "❌ Document non trouvé. Vérifiez le doc_id."
    if isinstance(e, AuthError):
        return "❌ Token expiré ou invalide. Mettez à jour LEX_TOKEN."
    if isinstance(e, Lex360Error):
        return f"❌ Erreur Lexis 360 : {e}"
    return f"❌ Erreur inattendue : {e}"


# ──────────────────────────────────────────────
# Formatage des réponses
# ──────────────────────────────────────────────


def _format_search_results(response) -> str:
    """Formate les résultats de recherche en Markdown."""
    hits = response.data.hits
    total = response.data.total

    if not hits:
        return "Aucun résultat trouvé."

    parts = [f"**{total} résultats** (affichage des {len(hits)} premiers)\n"]
    for i, hit in enumerate(hits, 1):
        date_str = ""
        if hit.date_dt:
            date_str = f" — {hit.date_dt.strftime('%d/%m/%Y')}"
        parts.append(
            f"{i}. **{hit.title}**\n"
            f"   Type : `{hit.doc_type}`{date_str}\n"
            f"   ID : `{hit.id}`"
        )

    return "\n".join(parts)


def _format_metadata(meta) -> str:
    """Formate les métadonnées en Markdown."""
    doc = meta.document
    parts = [f"# {doc.title}\n"]

    pairs = [
        ("Type", doc.type),
        ("ID", doc.doc_id_stable or meta.id),
        ("Date", datetime.fromtimestamp(doc.date / 1000).strftime("%d/%m/%Y") if doc.date else None),
        ("Thématique", doc.thematique),
    ]

    if meta.jurisprudence:
        jp = meta.jurisprudence
        pairs.extend([
            ("Juridiction", jp.classe_juridiction),
            ("Date de décision", jp.date_de_decision),
            ("N° pourvoi", ", ".join(jp.numero_jurisprudence) if jp.numero_jurisprudence else None),
            ("Solution", jp.solution_juridique),
            ("Type de litige", ", ".join(jp.type_litiges) if jp.type_litiges else None),
        ])

    if meta.encyclo:
        enc = meta.encyclo
        pairs.extend([
            ("Publication", enc.code_publication),
            ("Auteur(s)", ", ".join(enc.auteur) if enc.auteur else None),
            ("Type contribution", enc.type_contribution),
        ])

    if meta.revue:
        rev = meta.revue
        pairs.extend([
            ("Revue", rev.matiere_code),
            ("Numéro", ", ".join(str(n) for n in rev.numero) if rev.numero else rev.numero_label),
            ("Date revue", rev.date),
        ])

    for key, val in pairs:
        if val:
            parts.append(f"- **{key}** : {val}")

    return "\n".join(parts)


def _format_links(sections: list) -> str:
    """Formate les liens de navigation en Markdown."""
    if not sections:
        return "Aucun lien trouvé pour ce document."

    parts = []
    for section in sections:
        parts.append(f"## {section.title}\n")
        for link in section.links[:20]:  # Limiter à 20 par section
            date_str = f" ({link.date_dt.strftime('%d/%m/%Y')})" if link.date_dt else ""
            parts.append(f"- **{link.title}**{date_str}\n  `{link.doc_id}`")
        if len(section.links) > 20:
            parts.append(f"_… et {len(section.links) - 20} autres liens_")
        parts.append("")

    return "\n".join(parts)


def _format_timeline(timeline: dict) -> str:
    """Formate la frise chronologique en Markdown."""
    if not timeline:
        return "Aucune frise chronologique disponible."

    parts = ["# Frise chronologique procédurale\n"]
    for doc_id, entries in timeline.items():
        if not entries:
            continue
        for entry in entries:
            date_str = ""
            if entry.date:
                date_str = "/".join(str(d) for d in reversed(entry.date))
            juridiction = entry.classeJuridiction or ""
            solution = entry.solutionLabel or ""
            numeros = ", ".join(entry.numeros) if entry.numeros else ""

            line = f"- **{date_str}** — {juridiction}"
            if solution:
                line += f" — {solution}"
            if numeros:
                line += f" (n° {numeros})"
            if entry.title:
                line += f"\n  {entry.title}"
            line += f"\n  `{entry.docId}`"
            parts.append(line)

    return "\n".join(parts)


def _format_code_tree(tree, profondeur: int = 3) -> str:
    """Formate l'arborescence d'un code en Markdown."""
    parts = [f"# {tree.title}\n"]

    def _walk(nodes, depth=0):
        if depth >= profondeur:
            return
        for node in nodes:
            if node.children:
                # Noeud structurel (livre, titre, chapitre…)
                level = min(depth + 2, 6)  # h2 → h6
                parts.append(f"{'#' * level} {node.title}")
                _walk(node.children, depth + 1)
            else:
                # Feuille (article)
                doc_id = f"LG_{node.doc_id_stable}_0WJN" if node.doc_id_stable else ""
                if doc_id:
                    parts.append(f"- {node.title} (`{doc_id}`)")
                else:
                    parts.append(f"- {node.title}")

    _walk(tree.root)
    return "\n".join(parts)


def _format_toc(toc: dict) -> str:
    """Formate la table des matières en Markdown."""
    if not toc:
        return "Aucune table des matières disponible."

    parts = ["# Table des matières\n"]

    def _walk(nodes, depth=0):
        if isinstance(nodes, list):
            for node in nodes:
                _walk(node, depth)
        elif isinstance(nodes, dict):
            title = nodes.get("title") or nodes.get("label") or ""
            if title:
                indent = "  " * depth
                parts.append(f"{indent}- {title}")
            children = nodes.get("children") or nodes.get("items") or []
            for child in children:
                _walk(child, depth + 1)

    _walk(toc)
    return "\n".join(parts)


# ──────────────────────────────────────────────
# Implémentations des outils (testables sans MCP)
# ──────────────────────────────────────────────


def _rechercher_impl(
    client: Lex360Client,
    requete: str,
    type_doc: str = "",
    limite: int = 10,
    tri: str = "pertinence",
) -> str:
    """Implémentation de l'outil rechercher."""
    sort = "SCORE" if tri == "pertinence" else "DOCUMENT_DATE"
    filters = None
    if type_doc:
        filters = [{"name": "typeDoc", "values": [type_doc]}]
    response = client.search(requete, filters=filters, sort=sort, size=limite)
    return _format_search_results(response)


def _rechercher_decision_impl(
    client: Lex360Client,
    numero: str,
    strict: bool = True,
) -> str:
    """Implémentation de l'outil rechercher_decision."""
    response = client.search_by_number(numero, strict=strict)
    return _format_search_results(response)


def _lire_doctrine_impl(client: Lex360Client, doc_id: str) -> str:
    """Implémentation de l'outil lire_doctrine."""
    return client.get_document(doc_id, format="markdown")


def _lire_decision_impl(client: Lex360Client, doc_id: str) -> str:
    """Implémentation de l'outil lire_decision."""
    return client.get_document(doc_id, format="text")


def _metadata_document_impl(client: Lex360Client, doc_id: str) -> str:
    """Implémentation de l'outil metadata_document."""
    meta = client.get_metadata(doc_id)
    return _format_metadata(meta)


def _liens_document_impl(
    client: Lex360Client,
    doc_id: str,
    jurisprudence: bool = False,
) -> str:
    """Implémentation de l'outil liens_document."""
    sections = client.get_links(doc_id, jp=jurisprudence)
    return _format_links(sections)


def _frise_chronologique_impl(client: Lex360Client, doc_id: str) -> str:
    """Implémentation de l'outil frise_chronologique."""
    timeline = client.get_timeline([doc_id])
    return _format_timeline(timeline)


def _table_des_matieres_impl(client: Lex360Client, doc_id: str) -> str:
    """Implémentation de l'outil table_des_matieres."""
    toc = client.get_toc(doc_id)
    return _format_toc(toc)


def _arborescence_code_impl(
    client: Lex360Client,
    code_id_ou_nom: str,
    profondeur: int = 3,
) -> str:
    """Implémentation de l'outil arborescence_code."""
    code_id = _resolve_code_id(code_id_ou_nom)
    tree = client.get_code_tree(code_id)
    return _format_code_tree(tree, profondeur=profondeur)


def _lire_article_code_impl(
    client: Lex360Client,
    doc_id: str,
    annotations: bool = True,
) -> str:
    """Implémentation de l'outil lire_article_code."""
    contenu = client.get_document(doc_id, format="markdown")
    if not annotations:
        return contenu

    # Ajouter les annotations (liens doctrine + JP)
    sections = client.get_links(doc_id, jp=False)
    liens = _format_links(sections)
    if liens and liens != "Aucun lien trouvé pour ce document.":
        contenu += "\n\n---\n\n# Annotations\n\n" + liens

    return contenu


def _lire_texte_impl(client: Lex360Client, doc_id: str) -> str:
    """Implémentation de l'outil lire_texte."""
    return client.get_document(doc_id, format="auto")


# ──────────────────────────────────────────────
# Enregistrement des outils MCP
# ──────────────────────────────────────────────


@mcp.tool(
    description=(
        "Recommande les outils Lexis 360 selon le contexte juridique. "
        "À appeler en premier pour savoir quels outils utiliser et dans quel ordre. "
        "Indique aussi ce que Lexis 360 apporte par rapport à OpenLégi."
    ),
)
def guide(contexte_juridique: str) -> str:
    """Recommande les outils selon le besoin juridique."""
    return _guide_impl(contexte_juridique)


@mcp.tool(
    description=(
        "Recherche full-text dans Lexis 360 (doctrine, jurisprudence, revues, etc.). "
        "Retourne une liste de résultats avec titre, type, date et doc_id. "
        "Utilisez type_doc pour filtrer : JURISPRUDENCE, DOCTRINE, REVUES, FICHES_PRATIQUES, etc. "
        "Tri par 'pertinence' (défaut) ou 'date'."
    ),
)
def rechercher(
    requete: str,
    type_doc: str = "",
    limite: int = 10,
    tri: str = "pertinence",
) -> str:
    """Recherche full-text sur Lexis 360."""
    try:
        client = _get_client()
        return _rechercher_impl(client, requete, type_doc=type_doc, limite=limite, tri=tri)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    description=(
        "Recherche une décision de justice par numéro : pourvoi (22-84.760), "
        "JurisData (2025-017611), RG (19/01466). "
        "strict=True ne retourne que les décisions portant ce numéro."
    ),
)
def rechercher_decision(numero: str, strict: bool = True) -> str:
    """Recherche par numéro de décision."""
    try:
        client = _get_client()
        return _rechercher_decision_impl(client, numero, strict=strict)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    description=(
        "Lit le contenu d'un fascicule de doctrine ou article de revue. "
        "Retourne le texte en Markdown (titres, listes, tableaux préservés). "
        "Idéal pour : fascicules JurisClasseur (EN_*), articles de revue (PS_*), "
        "fiches pratiques (FP_*)."
    ),
)
def lire_doctrine(doc_id: str) -> str:
    """Contenu d'un fascicule ou article en Markdown."""
    try:
        client = _get_client()
        return _lire_doctrine_impl(client, doc_id)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    description=(
        "Lit le texte d'une décision de justice (texte brut). "
        "Pour : arrêts de cassation (JP_*), cours d'appel (JU_*), "
        "autres juridictions (JK_*)."
    ),
)
def lire_decision(doc_id: str) -> str:
    """Texte d'une décision de justice."""
    try:
        client = _get_client()
        return _lire_decision_impl(client, doc_id)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    description=(
        "Métadonnées enrichies d'un document : titre, type, date, auteur, "
        "juridiction, solution, thématique. "
        "Fonctionne pour tous types de documents."
    ),
)
def metadata_document(doc_id: str) -> str:
    """Métadonnées d'un document."""
    try:
        client = _get_client()
        return _metadata_document_impl(client, doc_id)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    description=(
        "Liens croisés d'un document : doctrine citant, décisions liées, "
        "textes visés dans les motifs, articles connexes. "
        "jurisprudence=True active le mode JP (commentaires, décisions dans le même sens)."
    ),
)
def liens_document(doc_id: str, jurisprudence: bool = False) -> str:
    """Liens de navigation d'un document."""
    try:
        client = _get_client()
        return _liens_document_impl(client, doc_id, jurisprudence=jurisprudence)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    description=(
        "Frise chronologique procédurale d'une décision : parcours de l'affaire "
        "à travers les instances (TGI → CA → Cass.), avec dates, solutions et numéros."
    ),
)
def frise_chronologique(doc_id: str) -> str:
    """Historique procédural d'une décision."""
    try:
        client = _get_client()
        return _frise_chronologique_impl(client, doc_id)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    description=(
        "Table des matières d'un document structuré (fascicule, code, fiche pratique). "
        "Retourne l'arborescence des sections avec titres."
    ),
)
def table_des_matieres(doc_id: str) -> str:
    """Table des matières d'un document."""
    try:
        client = _get_client()
        return _table_des_matieres_impl(client, doc_id)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    description=(
        "Arborescence d'un code juridique français (parties, livres, titres, "
        "chapitres, articles). Retourne la structure avec les doc_id de chaque article. "
        "Accepte un nom humain ('Code civil', 'Code du travail', 'Code pénal'…) "
        "ou un ID technique (SLD-LEGITEXT...). "
        "Utilisez profondeur=1 pour un aperçu, profondeur=3 pour le détail."
    ),
)
def arborescence_code(code_id_ou_nom: str, profondeur: int = 3) -> str:
    """Structure hiérarchique d'un code juridique."""
    try:
        client = _get_client()
        return _arborescence_code_impl(client, code_id_ou_nom, profondeur=profondeur)
    except ValueError as e:
        return f"❌ {e}"
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    description=(
        "Lit un article de code annoté depuis Lexis 360. "
        "Retourne le texte de l'article en Markdown, enrichi des annotations "
        "(doctrine, jurisprudence, textes connexes) placées sous l'article. "
        "Les doc_id d'articles s'obtiennent via arborescence_code ou rechercher. "
        "Format : LG_SLD-LEGIARTI..._0WJN. "
        "annotations=True (défaut) ajoute les renvois doctrine et JP."
    ),
)
def lire_article_code(doc_id: str, annotations: bool = True) -> str:
    """Article de code annoté (texte + annotations doctrine/JP)."""
    try:
        client = _get_client()
        return _lire_article_code_impl(client, doc_id, annotations=annotations)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    description=(
        "Lit un texte législatif, réglementaire ou tout document non couvert "
        "par lire_doctrine ou lire_decision. "
        "Pour : lois, décrets, ordonnances, publications officielles, etc. "
        "Le format de sortie est détecté automatiquement (Markdown ou texte brut)."
    ),
)
def lire_texte(doc_id: str) -> str:
    """Lecture d'un texte législatif ou réglementaire."""
    try:
        client = _get_client()
        return _lire_texte_impl(client, doc_id)
    except Exception as e:
        return _handle_error(e)


# ──────────────────────────────────────────────
# Point d'entrée
# ──────────────────────────────────────────────


def main():
    """Lance le serveur MCP en mode stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
