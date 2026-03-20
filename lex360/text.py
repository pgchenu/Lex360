"""Parsing SSE et extraction de texte depuis le HTML/XML Lexis 360."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, NavigableString, Tag


def parse_sse(raw: str) -> str:
    """
    Parse une réponse text/event-stream et extrait le contenu HTML.

    Le format SSE de /api/document/records/{docId} :
        id: DOC_ID
        event: DOCVIEW
        data: <html>...</html>

    Les lignes commençant par 'data: ' sont concaténées pour former le HTML.
    """
    lines = raw.split("\n")
    data_lines = [line[6:] for line in lines if line.startswith("data: ")]
    return "".join(data_lines)


# --- Conversion HTML → texte brut ---

def html_to_text(html: str) -> str:
    """
    Convertit du HTML/XML en texte brut lisible.

    Adapté pour les décisions de justice et contenus non structurés.
    """
    soup = _clean_soup(html)
    body = soup.find("body") or soup

    parts: list[str] = []
    _walk_text(body, parts)

    text = "\n".join(parts)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# Tags dont le contenu est inline (texte courant, pas de bloc)
_INLINE_TAGS = frozenset({
    "a", "abbr", "b", "bdi", "bdo", "br", "cite", "code", "data", "dfn",
    "em", "i", "kbd", "mark", "q", "rp", "rt", "ruby", "s", "samp",
    "small", "span", "strong", "sub", "sup", "time", "u", "var", "wbr",
})

# Tags qui délimitent des blocs (paragraphes, sections, etc.)
_BLOCK_TAGS = frozenset({
    "p", "div", "section", "article", "aside", "header", "footer", "main",
    "nav", "figure", "figcaption", "details", "summary", "address",
    "blockquote", "pre", "hr", "table", "ul", "ol", "li", "dl", "dt", "dd",
    "h1", "h2", "h3", "h4", "h5", "h6",
})


def _is_inline_container(tag: Tag) -> bool:
    """Vérifie si un tag ne contient que du contenu inline (pas de sous-blocs)."""
    for child in tag.descendants:
        if isinstance(child, Tag) and child.name in _BLOCK_TAGS:
            return False
    return True


def _collect_inline_text(tag: Tag) -> str:
    """Collecte tout le texte inline d'un élément, en préservant le flux."""
    parts: list[str] = []
    for child in tag.children:
        if isinstance(child, NavigableString):
            parts.append(str(child))
            continue
        if not isinstance(child, Tag):
            continue
        if child.name == "br":
            parts.append("\n")
        elif child.name in _INLINE_TAGS or _is_inline_container(child):
            parts.append(_collect_inline_text(child))
        else:
            # Bloc inattendu dans un contexte inline : saut de ligne
            parts.append("\n" + child.get_text() + "\n")
    result = "".join(parts)
    # Normaliser les sauts de ligne internes au paragraphe en espaces
    result = result.replace("\n", " ")
    result = re.sub(r"[ \t]+", " ", result)
    return result


def _walk_text(element: Tag, parts: list[str]) -> None:
    """Parcourt le DOM et extrait du texte brut avec sauts de ligne aux blocs."""
    for child in element.children:
        if isinstance(child, NavigableString):
            text = str(child).strip()
            if text:
                # Texte orphelin au niveau bloc — l'ajouter au dernier paragraphe
                if parts and not parts[-1].endswith("\n"):
                    parts[-1] += " " + text
                else:
                    parts.append(text)
            continue
        if not isinstance(child, Tag):
            continue

        name = child.name

        if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            text = child.get_text(strip=True)
            if text:
                parts.append("")
                parts.append(text)
                parts.append("")
            continue

        if name == "hr":
            parts.append("")
            continue

        if name == "table":
            parts.append(child.get_text(" ", strip=True))
            parts.append("")
            continue

        if name in ("ul", "ol"):
            for li in child.find_all("li", recursive=False):
                text = _collect_inline_text(li).strip()
                if text:
                    parts.append("  - " + text)
            parts.append("")
            continue

        # Paragraphes et divs inline : collecter le texte en flux
        if name in ("p", "li") or (name in _BLOCK_TAGS and _is_inline_container(child)):
            text = _collect_inline_text(child).strip()
            if text:
                parts.append(text)
                parts.append("")
            continue

        # Conteneurs avec sous-blocs : descendre récursivement
        _walk_text(child, parts)


# --- Conversion HTML → Markdown ---

# Correspondance heading → niveau Markdown
_HEADING_LEVELS = {"h1": "#", "h2": "##", "h3": "###", "h4": "####", "h5": "#####", "h6": "######"}


def html_to_markdown(html: str) -> str:
    """
    Convertit du HTML/XML Lexis 360 en Markdown lisible.

    Adapté pour les contenus structurés : fascicules JurisClasseur,
    articles de revue, synthèses, fiches pratiques.
    Préserve les titres, listes, gras/italique, liens et notes.
    """
    soup = _clean_soup(html)

    # Trouver le body ou le contenu principal
    body = soup.find("body") or soup

    parts: list[str] = []
    _walk(body, parts)

    text = "\n".join(parts)
    # Normaliser les sauts de ligne excessifs
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _clean_soup(html: str) -> BeautifulSoup:
    """Parse le HTML et supprime les éléments non-contenu."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["style", "script", "link"]):
        tag.decompose()
    return soup


def _walk(element: Tag, parts: list[str]) -> None:
    """Parcourt récursivement l'arbre DOM et génère du Markdown."""
    for child in element.children:
        if isinstance(child, NavigableString):
            text = str(child).strip()
            if text:
                # Texte orphelin au niveau bloc — rattacher au dernier paragraphe
                if parts and parts[-1] and not parts[-1].startswith("#") and parts[-1] != "---":
                    parts[-1] += " " + text
                else:
                    parts.append(text)
            continue

        if not isinstance(child, Tag):
            continue

        name = child.name

        # Headings
        if name in _HEADING_LEVELS:
            text = child.get_text(strip=True)
            if text:
                parts.append("")
                parts.append(f"{_HEADING_LEVELS[name]} {text}")
                parts.append("")
            continue

        # Paragraphes
        if name == "p":
            text = _inline_text(child)
            if text:
                parts.append(text)
                parts.append("")
            continue

        # Listes
        if name in ("ul", "ol"):
            _walk_list(child, parts, ordered=(name == "ol"))
            parts.append("")
            continue

        # Blocs de citation (notes de bas de page, remarques)
        if name == "blockquote":
            for line in _block_text(child).split("\n"):
                parts.append(f"> {line}" if line.strip() else ">")
            parts.append("")
            continue

        # Tables — rendu simplifié en texte
        if name == "table":
            parts.append(_table_to_markdown(child))
            parts.append("")
            continue

        # Séparateurs
        if name == "hr":
            parts.append("---")
            parts.append("")
            continue

        # Divs/sections avec uniquement du contenu inline → traiter comme un paragraphe
        if name in _BLOCK_TAGS and _is_inline_container(child):
            text = _inline_text(child)
            if text:
                parts.append(text)
                parts.append("")
            continue

        # Conteneurs avec sous-blocs : descendre récursivement
        _walk(child, parts)


def _inline_text(tag: Tag) -> str:
    """Extrait le texte inline d'un élément avec gras/italique.

    Gère récursivement les tags inline imbriqués (span, a, etc.)
    courants dans le HTML Lexis 360.
    """
    parts: list[str] = []
    for child in tag.children:
        if isinstance(child, NavigableString):
            parts.append(str(child))
            continue
        if not isinstance(child, Tag):
            continue

        if child.name == "br":
            parts.append("\n")
            continue

        # Récurser dans les tags inline pour préserver le flux
        inner = _inline_text(child)
        if not inner.strip():
            continue

        if child.name in ("b", "strong"):
            parts.append(f"**{inner.strip()}**")
        elif child.name in ("i", "em"):
            parts.append(f"*{inner.strip()}*")
        elif child.name == "sup":
            parts.append(f"^{inner.strip()}")
        else:
            # span, a, cite, abbr, etc. → texte inline direct
            parts.append(inner)

    result = "".join(parts)
    # Normaliser les sauts de ligne HTML en espaces (sauf <br> explicites, déjà gérés)
    result = result.replace("\n", " ")
    result = re.sub(r"[ \t]+", " ", result)
    return result.strip()


def _block_text(tag: Tag) -> str:
    """Extrait le texte bloc d'un élément (paragraphes séparés par des sauts de ligne)."""
    parts: list[str] = []
    _walk(tag, parts)
    return "\n".join(parts)


def _walk_list(tag: Tag, parts: list[str], ordered: bool, depth: int = 0) -> None:
    """Parcourt une liste HTML et génère du Markdown."""
    indent = "  " * depth
    counter = 0
    for child in tag.children:
        if not isinstance(child, Tag):
            continue
        if child.name == "li":
            counter += 1
            sub_list = child.find(["ul", "ol"])
            text = _inline_text(child) if not sub_list else ""
            prefix = f"{indent}{counter}." if ordered else f"{indent}-"
            if text:
                parts.append(f"{prefix} {text}")
            if sub_list:
                _walk_list(sub_list, parts, ordered=(sub_list.name == "ol"), depth=depth + 1)


def _table_to_markdown(table: Tag) -> str:
    """Convertit un tableau HTML en tableau Markdown."""
    rows: list[list[str]] = []
    for tr in table.find_all("tr"):
        cells = [cell.get_text(strip=True) for cell in tr.find_all(["th", "td"])]
        if cells:
            rows.append(cells)

    if not rows:
        return ""

    # Largeur max par colonne
    n_cols = max(len(r) for r in rows)
    # Normaliser le nombre de colonnes
    for row in rows:
        while len(row) < n_cols:
            row.append("")

    lines: list[str] = []
    # Première ligne = header
    lines.append("| " + " | ".join(rows[0]) + " |")
    lines.append("| " + " | ".join("---" for _ in range(n_cols)) + " |")
    for row in rows[1:]:
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)
