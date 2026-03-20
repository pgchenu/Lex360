"""Tests du transport curl_cffi — validation du contournement TLS."""

import pytest


@pytest.mark.integration
class TestCurlCffiTransport:

    def test_whoami(self, curl_transport):
        """GET /api/user/whoami doit retourner un profil utilisateur."""
        data = curl_transport.get("/api/user/whoami")
        assert isinstance(data, dict)
        assert data, "La réponse whoami est vide"

    def test_session_check(self, curl_transport):
        """GET /api/user/usersessions/check doit retourner 200."""
        data = curl_transport.get("/api/user/usersessions/check")
        assert data is not None

    def test_double_slash_preserved(self, curl_transport):
        """Les URLs avec double-slash doivent être préservées par le transport."""
        url = curl_transport._build_url("/api/recherche//search")
        assert "//search" in url, f"Le double-slash a été normalisé : {url}"

    def test_get_text_sse(self, curl_transport):
        """GET SSE (text/event-stream) ne doit pas être tronqué."""
        # Utilise un fascicule connu
        raw = curl_transport.get_text("/api/document/records/EN_KEJC-238100_0KR8")
        assert raw, "La réponse SSE est vide"
        assert "data:" in raw, "La réponse ne contient pas de lignes SSE"
