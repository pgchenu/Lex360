"""Tests de la CLI (exécutés en subprocess)."""

import os
import subprocess
import sys

import pytest


@pytest.fixture
def cli_env():
    """Environnement avec LEX_TOKEN pour les commandes CLI."""
    env = os.environ.copy()
    token = env.get("LEX_TOKEN")
    if not token:
        from tests.conftest import TOKEN_ENV_PATH
        if TOKEN_ENV_PATH.exists():
            token = TOKEN_ENV_PATH.read_text(encoding="utf-8").strip()
            env["LEX_TOKEN"] = token
    if not token:
        pytest.skip("LEX_TOKEN non défini")
    return env


def run_cli(*args, env):
    """Lance lex360 en subprocess et retourne le résultat."""
    result = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.argv[0] = 'lex360'; from lex360.cli import main; main()",
         *args],
        capture_output=True, text=True, env=env, timeout=120,
    )
    return result


class TestCliLogin:

    def test_login_with_token(self, cli_env):
        """lex360 login --token sauvegarde le token."""
        token = cli_env["LEX_TOKEN"]
        result = run_cli("login", "--token", token, env=cli_env)
        assert result.returncode == 0
        assert "sauvegardé" in result.stdout.lower() or "Token" in result.stdout


@pytest.mark.integration
class TestCliSearch:

    def test_search(self, cli_env):
        """lex360 search retourne des résultats."""
        result = run_cli("search", "contrat de travail", "--limit", "2", env=cli_env)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "résultats" in result.stdout.lower()

    def test_search_by_number(self, cli_env):
        """lex360 search avec un numéro de pourvoi."""
        result = run_cli("search", "22-84.760", env=cli_env)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "pourvoi" in result.stderr.lower()


@pytest.mark.integration
class TestCliDoc:

    def test_doc_meta(self, cli_env):
        """lex360 doc meta affiche les métadonnées en JSON."""
        result = run_cli("doc", "meta", "EN_KEJC-238100_0KR8", env=cli_env)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "{" in result.stdout

    def test_doc_read(self, cli_env):
        """lex360 doc read affiche le contenu."""
        result = run_cli("doc", "read", "EN_KEJC-238100_0KR8", env=cli_env)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert len(result.stdout) > 100


@pytest.mark.integration
class TestCliLinks:

    def test_links(self, cli_env):
        """lex360 links affiche les liens."""
        result = run_cli("links", "JP_KODCASS-0519779_0KRH", "--jp", env=cli_env)
        assert result.returncode == 0, f"stderr: {result.stderr}"
