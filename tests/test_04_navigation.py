"""Tests des endpoints de navigation."""

import pytest

from lex360.models import NavigationSection, TimelineEntry
from tests.conftest import DOC_ID_FASCICULE, DOC_ID_JP_CASS


@pytest.mark.integration
class TestLinks:

    def test_links_fascicule(self, client):
        """Liens de navigation pour un fascicule (jp=false)."""
        sections = client.get_links(DOC_ID_FASCICULE, jp=False)
        assert isinstance(sections, list)
        # Un fascicule peut avoir des liens ou non

    def test_links_jurisprudence(self, client):
        """Liens de navigation pour une décision (jp=true)."""
        sections = client.get_links(DOC_ID_JP_CASS, jp=True)
        assert isinstance(sections, list)
        # Une décision Cass. a typiquement des liens
        if sections:
            section = sections[0]
            assert isinstance(section, NavigationSection)
            assert section.title


@pytest.mark.integration
class TestTimeline:

    def test_timeline(self, client):
        """Frise chronologique pour une décision."""
        result = client.get_timeline([DOC_ID_JP_CASS])
        assert isinstance(result, dict)


@pytest.mark.integration
class TestToc:

    def test_toc(self, client):
        """Table des matières d'un document."""
        toc = client.get_toc(DOC_ID_FASCICULE)
        assert isinstance(toc, dict)
