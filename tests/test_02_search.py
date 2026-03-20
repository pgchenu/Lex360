"""Tests des endpoints de recherche."""

import pytest

from lex360.models import SearchResponse
from lex360.search import detect_number_type


class TestDetectNumberType:
    """Tests unitaires de la détection de numéros (pas besoin de token)."""

    def test_pourvoi(self):
        assert detect_number_type("22-84.760") == "pourvoi"
        assert detect_number_type("24-15.901") == "pourvoi"

    def test_jurisdata(self):
        assert detect_number_type("2025-017611") == "jurisdata"
        assert detect_number_type("2024-010199") == "jurisdata"

    def test_rg(self):
        assert detect_number_type("19/01466") == "rg"
        assert detect_number_type("22/03456") == "rg"

    def test_requete(self):
        assert detect_number_type("1900123") == "requete"
        assert detect_number_type("456789") == "requete"

    def test_unknown(self):
        assert detect_number_type("licenciement abusif") is None
        assert detect_number_type("") is None


@pytest.mark.integration
class TestSearch:

    def test_search_basic(self, client):
        """Recherche simple retourne des résultats."""
        result = client.search("licenciement abusif", size=3)
        assert isinstance(result, SearchResponse)
        assert result.data.total > 0
        assert len(result.data.hits) > 0
        assert len(result.data.hits) <= 3

    def test_search_hit_structure(self, client):
        """Les hits contiennent les champs attendus."""
        result = client.search("contrat de travail", size=1)
        hit = result.data.hits[0]
        assert hit.id
        assert hit.title
        assert hit.doc_type

    def test_search_with_type_filter(self, client):
        """Recherche filtrée par type de document."""
        result = client.search(
            "responsabilité civile",
            filters=[{"name": "typeDoc", "values": ["JURISPRUDENCE"]}],
            size=3,
        )
        assert result.data.total > 0
        for hit in result.data.hits:
            assert "JURISPRUDENCE" in hit.doc_type

    def test_search_sort_by_date(self, client):
        """Recherche triée par date."""
        result = client.search(
            "droit du travail",
            sort="DOCUMENT_DATE",
            size=3,
        )
        assert result.data.total > 0

    def test_search_pagination(self, client):
        """La pagination fonctionne."""
        page1 = client.search("contrat", size=2, offset=0)
        page2 = client.search("contrat", size=2, offset=2)
        assert page1.data.hits[0].id != page2.data.hits[0].id


@pytest.mark.integration
class TestSearchByNumber:

    def test_search_by_pourvoi(self, client):
        """Recherche par numéro de pourvoi."""
        result = client.search_by_number("22-84.760")
        assert isinstance(result, SearchResponse)
        assert result.data.total > 0
        # Au moins un résultat doit être de la jurisprudence
        assert any("JURISPRUDENCE" in h.doc_type for h in result.data.hits)
