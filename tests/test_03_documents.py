"""Tests des endpoints documents."""

import pytest

from lex360.models import DocumentMetadata
from tests.conftest import DOC_ID_FASCICULE, DOC_ID_JP_CASS


@pytest.mark.integration
class TestMetadata:

    def test_metadata_fascicule(self, client):
        """Métadonnées d'un fascicule d'encyclopédie."""
        meta = client.get_metadata(DOC_ID_FASCICULE)
        assert isinstance(meta, DocumentMetadata)
        assert meta.document.id == DOC_ID_FASCICULE
        assert meta.document.type == "DOCTRINE_FASCICULE"
        assert meta.document.title
        assert meta.encyclo is not None
        assert meta.encyclo.code_publication_label
        assert len(meta.encyclo.auteur) > 0

    def test_metadata_jurisprudence(self, client):
        """Métadonnées d'une décision de jurisprudence."""
        meta = client.get_metadata(DOC_ID_JP_CASS)
        assert isinstance(meta, DocumentMetadata)
        assert meta.document.type == "JURISPRUDENCE_COURCASSATION"
        assert meta.jurisprudence is not None
        assert meta.jurisprudence.classe_juridiction == "Cour de cassation"
        assert len(meta.jurisprudence.numero_jurisprudence) > 0


@pytest.mark.integration
class TestGetDocument:

    def test_fascicule_markdown(self, client):
        """Un fascicule est retourné en Markdown (format auto)."""
        content = client.get_document(DOC_ID_FASCICULE)
        assert len(content) > 100
        # Markdown : doit contenir des headings
        assert "#" in content
        # Pas de balises HTML
        assert "<html" not in content.lower()
        assert "<div" not in content.lower()

    def test_jurisprudence_text(self, client):
        """Une décision est retournée en texte brut (format auto)."""
        content = client.get_document(DOC_ID_JP_CASS)
        assert len(content) > 50
        assert "<html" not in content.lower()

    def test_force_html(self, client):
        """Le format HTML brut peut être forcé."""
        html = client.get_document(DOC_ID_FASCICULE, format="html")
        assert "<" in html

    def test_force_text(self, client):
        """Le format texte brut peut être forcé."""
        text = client.get_document(DOC_ID_FASCICULE, format="text")
        assert "<html" not in text.lower()

    def test_force_markdown(self, client):
        """Le format Markdown peut être forcé sur une décision."""
        md = client.get_document(DOC_ID_JP_CASS, format="markdown")
        assert "<html" not in md.lower()
