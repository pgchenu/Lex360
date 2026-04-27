"""Tests des primitives ToC + extraction de sections (text.py + client + MCP)."""

from __future__ import annotations

import json

import pytest

from lex360.text import (
    HeadingNode,
    build_toc,
    extract_sections,
    html_to_markdown,
    toc_to_dict,
)


SAMPLE_HTML = """
<html><body>
<h1>Introduction</h1>
<p>Texte d'intro.</p>

<h1>Régime juridique</h1>
<p>Présentation générale du régime.</p>

<h2>Conditions</h2>
<p>Première condition. Deuxième condition.</p>

<h3>Condition particulière</h3>
<p>Détails sur la condition particulière.</p>

<h2>Effets</h2>
<p>Effets juridiques.</p>

<h1>Sanctions</h1>
<p>Sanctions encourues.</p>
</body></html>
"""

# Saut de niveau h1 -> h3 sans h2 intermédiaire.
SKIPPED_LEVEL_HTML = """
<html><body>
<h1>Titre A</h1>
<h3>Titre A.1</h3>
<p>...</p>
<h1>Titre B</h1>
</body></html>
"""

SHORT_HTML = "<html><body><p>Quelques mots.</p></body></html>"


class TestBuildToc:

    def test_uids_hierarchical(self):
        roots, by_uid = build_toc(SAMPLE_HTML)
        # Trois h1 → s1, s2, s3
        assert [r.uid for r in roots] == ["s1", "s2", "s3"]
        assert roots[0].title == "Introduction"
        assert roots[1].title == "Régime juridique"
        # s2 a deux enfants h2 → s2.1, s2.2
        assert [c.uid for c in roots[1].children] == ["s2.1", "s2.2"]
        # s2.1 a un h3 → s2.1.1
        assert [c.uid for c in roots[1].children[0].children] == ["s2.1.1"]
        assert by_uid["s2.1.1"].title == "Condition particulière"

    def test_skipped_level_attaches_to_nearest_lower(self):
        roots, by_uid = build_toc(SKIPPED_LEVEL_HTML)
        # h1 → s1, h3 attaché à s1 → s1.1, h1 → s2
        assert "s1.1" in by_uid
        assert by_uid["s1.1"].title == "Titre A.1"
        assert by_uid["s1.1"].level == 3
        assert [r.uid for r in roots] == ["s1", "s2"]

    def test_no_headings(self):
        roots, by_uid = build_toc(SHORT_HTML)
        assert roots == []
        assert by_uid == {}

    def test_breadcrumb(self):
        _, by_uid = build_toc(SAMPLE_HTML)
        assert by_uid["s2.1.1"].breadcrumb == (
            "Régime juridique > Conditions > Condition particulière"
        )


class TestExtractSections:

    def test_subtree_includes_descendants(self):
        markdown = html_to_markdown(SAMPLE_HTML)
        roots, by_uid = build_toc(SAMPLE_HTML)
        out = extract_sections(markdown, ["s2"], roots, by_uid)

        assert out.startswith("<!-- s2 — Régime juridique -->")
        assert "Régime juridique" in out
        assert "Conditions" in out
        assert "Condition particulière" in out
        assert "Effets" in out
        # Pas de fuite dans s3
        assert "Sanctions" not in out

    def test_leaf_excludes_following_sibling(self):
        markdown = html_to_markdown(SAMPLE_HTML)
        roots, by_uid = build_toc(SAMPLE_HTML)
        out = extract_sections(markdown, ["s2.1"], roots, by_uid)

        assert "Conditions" in out
        assert "Condition particulière" in out  # descendant inclus
        assert "Effets" not in out  # frère, exclu
        assert out.startswith("<!-- s2.1 — Régime juridique > Conditions -->")

    def test_unknown_uid_marker(self):
        markdown = html_to_markdown(SAMPLE_HTML)
        roots, by_uid = build_toc(SAMPLE_HTML)
        out = extract_sections(markdown, ["s99"], roots, by_uid)
        assert out == "<!-- s99 not found -->"

    def test_multiple_sections_separated(self):
        markdown = html_to_markdown(SAMPLE_HTML)
        roots, by_uid = build_toc(SAMPLE_HTML)
        out = extract_sections(markdown, ["s1", "s3"], roots, by_uid)
        assert "<!-- s1 — Introduction -->" in out
        assert "<!-- s3 — Sanctions -->" in out
        assert "\n\n---\n\n" in out


class TestTocToDict:

    def test_shape(self):
        markdown = html_to_markdown(SAMPLE_HTML)
        roots, _ = build_toc(SAMPLE_HTML)
        d = toc_to_dict(roots, markdown, doc_id="EN_TEST")

        assert d["doc_id"] == "EN_TEST"
        assert d["title"] == "Introduction"
        assert d["char_count_total"] == len(markdown)
        assert isinstance(d["sections"], list)
        assert d["sections"][0]["uid"] == "s1"
        assert "chars" in d["sections"][0]

    def test_chars_monotonic(self):
        markdown = html_to_markdown(SAMPLE_HTML)
        roots, _ = build_toc(SAMPLE_HTML)
        d = toc_to_dict(roots, markdown)

        # s2 doit contenir au moins autant de caractères que la somme de ses enfants
        s2 = next(s for s in d["sections"] if s["uid"] == "s2")
        children_sum = sum(c["chars"] for c in s2.get("children", []))
        assert s2["chars"] >= children_sum

    def test_json_serializable(self):
        markdown = html_to_markdown(SAMPLE_HTML)
        roots, _ = build_toc(SAMPLE_HTML)
        d = toc_to_dict(roots, markdown, doc_id="X")
        # Doit s'encoder sans erreur
        json.dumps(d, ensure_ascii=False)


# ──────────────────────────────────────────────
# Wiring MCP : _lire_doctrine_impl avec stub client
# ──────────────────────────────────────────────


class _StubClient:
    """Minimal stand-in pour Lex360Client : intercepte get_doctrine."""

    def __init__(self, html: str):
        self._html = html

    def get_doctrine(self, doc_id, *, sections=None):
        # Réutilise la logique réelle en simulant get_content
        from lex360.text import (
            html_to_markdown,
            build_toc,
            toc_to_dict,
            extract_sections,
        )
        from lex360.client import _TOC_FALLBACK_THRESHOLD

        markdown = html_to_markdown(self._html)
        roots, by_uid = build_toc(self._html)

        if sections == ["*"]:
            return markdown
        if sections:
            return extract_sections(markdown, sections, roots, by_uid)
        if not roots or len(markdown) < _TOC_FALLBACK_THRESHOLD:
            return markdown
        return toc_to_dict(roots, markdown, doc_id=doc_id)


# Document long pour forcer la ToC (au-dessus du seuil de 3000)
LONG_HTML = (
    "<html><body>"
    + "".join(
        f"<h1>Section {i}</h1><p>{'Lorem ipsum ' * 80}</p>"
        for i in range(1, 8)
    )
    + "</body></html>"
)


class TestLireDoctrineImpl:

    def test_default_returns_toc_json(self):
        from lex360.mcp_server import _lire_doctrine_impl
        out = _lire_doctrine_impl(_StubClient(LONG_HTML), "EN_TEST")
        assert isinstance(out, str)
        data = json.loads(out)
        assert data["doc_id"] == "EN_TEST"
        assert data["sections"][0]["uid"] == "s1"

    def test_sections_star_returns_full_markdown(self):
        from lex360.mcp_server import _lire_doctrine_impl
        out = _lire_doctrine_impl(_StubClient(LONG_HTML), "EN_TEST", sections=["*"])
        assert isinstance(out, str)
        assert "# Section 1" in out
        assert "# Section 7" in out
        # Pas du JSON
        with pytest.raises(json.JSONDecodeError):
            json.loads(out)

    def test_sections_uid_returns_subtree(self):
        from lex360.mcp_server import _lire_doctrine_impl
        out = _lire_doctrine_impl(_StubClient(LONG_HTML), "EN_TEST", sections=["s2"])
        assert out.startswith("<!-- s2 — Section 2 -->")
        assert "Section 2" in out
        assert "Section 3" not in out  # frère exclu

    def test_short_doc_fast_path(self):
        from lex360.mcp_server import _lire_doctrine_impl
        out = _lire_doctrine_impl(_StubClient(SHORT_HTML), "EN_TEST")
        # Fast-path : pas de JSON, retourne le markdown brut
        assert "Quelques mots." in out
        with pytest.raises(json.JSONDecodeError):
            json.loads(out)
