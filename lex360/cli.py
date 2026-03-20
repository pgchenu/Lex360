"""Interface en ligne de commande pour Lexis 360."""

from __future__ import annotations

import json
import sys

import click

from lex360.auth import TokenManager, decode_jwt_payload, is_token_expired
from lex360.client import Lex360Client
from lex360.search import detect_number_type


def _make_client() -> Lex360Client:
    """Crée un client Lex360."""
    return Lex360Client()


def _json(data) -> None:
    """Affiche des données en JSON formaté."""
    if hasattr(data, "model_dump"):
        data = data.model_dump(by_alias=True, exclude_none=True)
    click.echo(json.dumps(data, indent=2, ensure_ascii=False, default=str))


@click.group()
def main():
    """Client CLI pour l'API Lexis 360 Intelligence."""


# ──────────────────────────────────────────────
# Auth
# ──────────────────────────────────────────────

@main.command()
@click.option("--token", "-t", help="Token JWT à sauvegarder")
def login(token):
    """Sauvegarde un token JWT pour l'authentification."""
    tm = TokenManager()
    if token is None:
        click.echo("Collez votre access_token (depuis le localStorage du navigateur) :")
        token = click.get_text_stream("stdin").readline().strip()

    if not token:
        click.echo("Erreur : token vide.", err=True)
        sys.exit(1)

    try:
        payload = decode_jwt_payload(token)
        name = payload.get("name", payload.get("sub", "inconnu"))
        click.echo(f"Token pour : {name}")
        if is_token_expired(token):
            click.echo("Attention : ce token est déjà expiré.", err=True)
    except Exception as e:
        click.echo(f"Attention : impossible de décoder le JWT ({e})", err=True)

    tm.save(token)
    click.echo(f"Token sauvegardé dans {tm._token_path}")


# ──────────────────────────────────────────────
# Recherche
# ──────────────────────────────────────────────

@main.command()
@click.argument("query")
@click.option("--type", "-t", "doc_type", help="Filtre par type : JURISPRUDENCE, REVUES, DOCTRINE_FASCICULE (encyclopédies), FORMULE, FICHES_PRATIQUES, PUBLICATION_OFFICIELLE, ACTUALITIES")
@click.option("--limit", "-l", default=10, help="Nombre de résultats")
@click.option("--sort", "-s", type=click.Choice(["score", "date"]), default="score")
@click.option("--strict/--no-strict", default=True, help="Recherche par numéro : --strict (défaut) ne garde que les décisions portant ce numéro ; --no-strict inclut aussi les décisions qui le citent")
@click.option("--json", "-j", "as_json", is_flag=True, help="Sortie JSON brute")
def search(query, doc_type, limit, sort, strict, as_json):
    """Recherche full-text sur Lexis 360.

    Détecte automatiquement les numéros de pourvoi (22-84.760),
    JurisData (2025-017611) et numéros RG (19/01466).
    """
    with _make_client() as client:
        # Détection automatique de numéro
        num_type = detect_number_type(query)
        if num_type:
            click.echo(f"Recherche par {num_type} : {query}", err=True)
            result = client.search_by_number(query, size=limit, strict=strict)
        else:
            filters = []
            if doc_type:
                filters.append({"name": "typeDoc", "values": [doc_type]})
            sort_field = "SCORE" if sort == "score" else "DOCUMENT_DATE"
            result = client.search(query, filters=filters, sort=sort_field, size=limit)

        if as_json:
            _json(result)
        else:
            n_hits = len(result.data.hits)
            total = result.data.total_text or result.data.total
            click.echo(f"{total} résultats" + (f" ({n_hits} après filtrage)" if num_type and strict else ""))
            for i, hit in enumerate(result.data.hits, 1):
                date_str = f" ({hit.date_dt:%d/%m/%Y})" if hit.date_dt else ""
                click.echo(f"  {i}. [{hit.doc_type}] {hit.title}{date_str}")
                click.echo(f"     {hit.id}")


# ──────────────────────────────────────────────
# Documents
# ──────────────────────────────────────────────

@main.group()
def doc():
    """Opérations sur les documents."""


@doc.command("meta")
@click.argument("doc_id")
def doc_metadata(doc_id):
    """Affiche les métadonnées d'un document (JSON)."""
    with _make_client() as client:
        meta = client.get_metadata(doc_id)
        _json(meta)


@doc.command("read")
@click.argument("doc_id")
@click.option("--format", "-f", "fmt", type=click.Choice(["auto", "markdown", "text", "html"]), default="auto")
@click.option("--output", "-o", "output_file", help="Fichier de sortie")
def doc_read(doc_id, fmt, output_file):
    """Récupère le contenu d'un document.

    Par défaut : Markdown pour les docs structurés (fascicules, articles),
    texte brut pour la jurisprudence.
    """
    with _make_client() as client:
        content = client.get_document(doc_id, format=fmt)

        if output_file:
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(content)
            click.echo(f"Sauvegardé dans {output_file} ({len(content)} octets)", err=True)
        else:
            click.echo(content)


# ──────────────────────────────────────────────
# Navigation / liens
# ──────────────────────────────────────────────

@main.command()
@click.argument("doc_id")
@click.option("--jp/--no-jp", default=False, help="Mode jurisprudence (décisions liées, commentaires)")
@click.option("--json", "-j", "as_json", is_flag=True, help="Sortie JSON brute")
def links(doc_id, jp, as_json):
    """Liens de navigation d'un document.

    --jp : active le mode jurisprudence (commentaires, décisions liées,
    articles citant, textes visés dans les motifs).
    """
    with _make_client() as client:
        sections = client.get_links(doc_id, jp=jp)

        if as_json:
            _json([s.model_dump(by_alias=True, exclude_none=True) for s in sections])
        else:
            for section in sections:
                click.echo(f"\n{'─' * 40}")
                click.echo(f"{section.title} ({len(section.links)} liens)")
                click.echo(f"{'─' * 40}")
                for link in section.links:
                    date_str = ""
                    if link.date_dt:
                        date_str = f" ({link.date_dt:%d/%m/%Y})"
                    click.echo(f"  [{link.type}] {link.title}{date_str}")
                    click.echo(f"  {link.doc_id}")


@main.command()
@click.argument("doc_id")
@click.option("--json", "-j", "as_json", is_flag=True, help="Sortie JSON brute")
def timeline(doc_id, as_json):
    """Frise chronologique procédurale d'une décision."""
    with _make_client() as client:
        result = client.get_timeline([doc_id])

        if as_json:
            data = {
                k: [e.model_dump(by_alias=True, exclude_none=True) for e in v]
                for k, v in result.items()
            }
            _json(data)
        else:
            entries = result.get(doc_id, [])
            if not entries:
                click.echo("Aucune chronologie trouvée.")
                return
            for entry in entries:
                date_str = ""
                if entry.date:
                    date_str = f"{entry.date[2]:02d}/{entry.date[1]:02d}/{entry.date[0]}"
                solution = f" → {entry.solution_label}" if entry.solution_label else ""
                nums = f" n° {', '.join(entry.numeros)}" if entry.numeros else ""
                click.echo(f"  {date_str} | {entry.classe_juridiction} {entry.siege}{nums}{solution}")
                if entry.doc_id:
                    click.echo(f"           {entry.doc_id}")


@main.command()
@click.argument("code_id", required=False)
@click.option("--json", "-j", "as_json", is_flag=True, help="Sortie JSON brute")
def codes(code_id, as_json):
    """Arborescence d'un code.

    CODE_ID : identifiant stable (ex: SLD-LEGITEXT000006070721 pour le Code civil).
    """
    if not code_id:
        click.echo("Usage : lex360 codes <code_id>")
        click.echo("Exemple : lex360 codes SLD-LEGITEXT000006070721")
        return

    with _make_client() as client:
        tree = client.get_code_tree(code_id)
        if as_json:
            _json(tree)
        else:
            click.echo(f"Code : {tree.title}")
            _print_tree(tree.root, indent=0)


def _print_tree(nodes: list, indent: int = 0) -> None:
    """Affiche une arborescence de code."""
    prefix = "  " * indent
    for node in nodes:
        click.echo(f"{prefix}- {node.title}")
        if node.children:
            _print_tree(node.children, indent + 1)
