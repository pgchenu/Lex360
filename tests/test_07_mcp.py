"""Tests du serveur MCP Lexis 360."""

import pytest


# ──────────────────────────────────────────────
# Tests unitaires (pas besoin de token)
# ──────────────────────────────────────────────


class TestMCPImport:
    """Vérifie que le module s'importe correctement."""

    def test_import_module(self):
        from lex360 import mcp_server
        assert hasattr(mcp_server, "mcp")
        assert hasattr(mcp_server, "main")

    def test_tool_count(self):
        """Le serveur expose exactement 9 outils."""
        from lex360.mcp_server import mcp
        tools = mcp._tool_manager._tools
        assert len(tools) == 9, f"Attendu 9 outils, trouvé {len(tools)}: {list(tools.keys())}"

    def test_tool_names(self):
        """Les 9 outils attendus sont enregistrés."""
        from lex360.mcp_server import mcp
        tools = set(mcp._tool_manager._tools.keys())
        expected = {
            "guide",
            "rechercher",
            "rechercher_decision",
            "lire_doctrine",
            "lire_decision",
            "metadata_document",
            "liens_document",
            "frise_chronologique",
            "table_des_matieres",
        }
        assert tools == expected, f"Différence: {tools.symmetric_difference(expected)}"


class TestGuide:
    """Tests unitaires de l'outil guide (pas d'appel réseau)."""

    def test_guide_doctrine(self):
        """Le guide recommande les bons outils pour la doctrine."""
        from lex360.mcp_server import _guide_impl
        result = _guide_impl("doctrine sur la responsabilité")
        assert "lire_doctrine" in result
        assert "rechercher" in result

    def test_guide_procedure(self):
        """Le guide recommande la frise pour un contexte procédural."""
        from lex360.mcp_server import _guide_impl
        result = _guide_impl("historique procédural d'un pourvoi en cassation")
        assert "frise_chronologique" in result

    def test_guide_navigation(self):
        """Le guide recommande les liens pour la navigation."""
        from lex360.mcp_server import _guide_impl
        result = _guide_impl("quels textes sont visés par cette décision")
        assert "liens_document" in result

    def test_guide_recherche(self):
        """Le guide recommande la recherche pour une question ouverte."""
        from lex360.mcp_server import _guide_impl
        result = _guide_impl("trouver des décisions sur le licenciement")
        assert "rechercher" in result

    def test_guide_returns_markdown(self):
        """Le guide retourne du Markdown."""
        from lex360.mcp_server import _guide_impl
        result = _guide_impl("doctrine")
        assert result.startswith("#")


class TestToolCatalog:
    """Vérifie la cohérence du catalogue d'outils."""

    def test_catalog_groups(self):
        from lex360.mcp_server import _TOOL_CATALOG
        assert "doctrine" in _TOOL_CATALOG
        assert "analyse_procédurale" in _TOOL_CATALOG
        assert "navigation" in _TOOL_CATALOG
        assert "recherche" in _TOOL_CATALOG

    def test_catalog_structure(self):
        from lex360.mcp_server import _TOOL_CATALOG
        for name, group in _TOOL_CATALOG.items():
            assert "outils" in group, f"Groupe {name} manque 'outils'"
            assert "description" in group, f"Groupe {name} manque 'description'"
            assert "mots_clés" in group, f"Groupe {name} manque 'mots_clés'"
            assert len(group["outils"]) > 0


# ──────────────────────────────────────────────
# Tests d'intégration (nécessitent LEX_TOKEN)
# ──────────────────────────────────────────────


@pytest.mark.integration
class TestRechercher:

    def test_rechercher_basic(self, client):
        """Recherche simple via le formatage MCP."""
        from lex360.mcp_server import _rechercher_impl
        result = _rechercher_impl(client, "licenciement abusif", limite=3)
        assert isinstance(result, str)
        assert "licenciement" in result.lower() or "résultat" in result.lower()
        # Format liste numérotée
        assert "1." in result

    def test_rechercher_with_type(self, client):
        """Recherche filtrée par type."""
        from lex360.mcp_server import _rechercher_impl
        result = _rechercher_impl(client, "responsabilité civile", type_doc="JURISPRUDENCE", limite=3)
        assert isinstance(result, str)
        assert "1." in result


@pytest.mark.integration
class TestRechercherDecision:

    def test_rechercher_decision_pourvoi(self, client):
        """Recherche par numéro de pourvoi."""
        from lex360.mcp_server import _rechercher_decision_impl
        result = _rechercher_decision_impl(client, "22-84.760")
        assert isinstance(result, str)
        assert "22-84.760" in result or "résultat" in result.lower()


@pytest.mark.integration
class TestLireDoctrine:

    def test_lire_doctrine(self, client):
        """Lecture d'un fascicule de doctrine."""
        from lex360.mcp_server import _lire_doctrine_impl
        result = _lire_doctrine_impl(client, "EN_KEJC-238100_0KR8")
        assert isinstance(result, str)
        assert len(result) > 100  # Le contenu doit être substantiel


@pytest.mark.integration
class TestLireDecision:

    def test_lire_decision(self, client):
        """Lecture d'une décision de justice."""
        from lex360.mcp_server import _lire_decision_impl
        result = _lire_decision_impl(client, "JP_KODCASS-0519779_0KRH")
        assert isinstance(result, str)
        assert len(result) > 100


@pytest.mark.integration
class TestMetadata:

    def test_metadata_document(self, client):
        """Récupération des métadonnées."""
        from lex360.mcp_server import _metadata_document_impl
        result = _metadata_document_impl(client, "JP_KODCASS-0519779_0KRH")
        assert isinstance(result, str)
        assert "titre" in result.lower() or "type" in result.lower()


@pytest.mark.integration
class TestLiens:

    def test_liens_document(self, client):
        """Récupération des liens d'un document."""
        from lex360.mcp_server import _liens_document_impl
        result = _liens_document_impl(client, "JP_KODCASS-0519779_0KRH", jurisprudence=True)
        assert isinstance(result, str)


@pytest.mark.integration
class TestFrise:

    def test_frise_chronologique(self, client):
        """Récupération de la frise chronologique."""
        from lex360.mcp_server import _frise_chronologique_impl
        result = _frise_chronologique_impl(client, "JP_KODCASS-0519779_0KRH")
        assert isinstance(result, str)


@pytest.mark.integration
class TestTDM:

    def test_table_des_matieres(self, client):
        """Récupération de la table des matières."""
        from lex360.mcp_server import _table_des_matieres_impl
        result = _table_des_matieres_impl(client, "EN_KEJC-238100_0KR8")
        assert isinstance(result, str)
