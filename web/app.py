"""Interface web Flask pour Lex360 Intelligence."""

from __future__ import annotations

import io
import json
import logging
import tempfile
from datetime import datetime
from pathlib import Path

from flask import (
    Flask,
    jsonify,
    render_template,
    request,
    send_file,
)

from lex360.client import Lex360Client
from lex360.auth import TokenManager, is_token_expired
from lex360.exceptions import AuthError, NotFoundError, TransportError, APIError
from lex360.export import export_pdf, export_docx

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False

logger = logging.getLogger(__name__)

# Client global (initialisé au premier appel)
_client: Lex360Client | None = None


def get_client() -> Lex360Client:
    """Retourne le client Lex360, le démarre si nécessaire."""
    global _client
    if _client is None or not _client._started:
        _client = Lex360Client()
        _client.start()
    return _client


# ──────────────────────────────────────────────
# Gestion d'erreurs globale
# ──────────────────────────────────────────────

@app.errorhandler(AuthError)
def handle_auth_error(e):
    return jsonify({
        "error": str(e),
        "type": "auth",
        "message": "Token invalide ou expiré. Configurez un nouveau token.",
    }), 401


@app.errorhandler(NotFoundError)
def handle_not_found(e):
    return jsonify({
        "error": str(e),
        "type": "not_found",
        "message": "Document non trouvé. Vérifiez l'identifiant.",
    }), 404


@app.errorhandler(TransportError)
def handle_transport_error(e):
    return jsonify({
        "error": str(e),
        "type": "transport",
        "message": "Erreur de connexion à Lexis 360. Vérifiez votre token et réessayez.",
    }), 502


@app.errorhandler(APIError)
def handle_api_error(e):
    return jsonify({
        "error": str(e),
        "type": "api",
        "status_code": getattr(e, "status_code", None),
        "message": "Erreur inattendue de l'API Lexis 360.",
    }), getattr(e, "status_code", 500) or 500


def _serialize(obj) -> dict | list | str:
    """Sérialise un objet Pydantic ou dict pour JSON."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump(by_alias=True)
    if isinstance(obj, list):
        return [_serialize(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    return obj


# ──────────────────────────────────────────────
# Pages
# ──────────────────────────────────────────────

@app.route("/")
def index():
    """Page principale."""
    # Vérifier le statut du token
    auth = TokenManager()
    token = auth.load()
    token_info = None
    if token:
        try:
            info = auth.get_token_info()
            exp = info.get("exp")
            token_info = {
                "valid": not is_token_expired(token),
                "expires": datetime.fromtimestamp(exp).isoformat() if exp else None,
                "email": info.get("email", info.get("sub", "?")),
            }
        except Exception:
            token_info = {"valid": False, "expires": None, "email": "?"}
    return render_template("index.html", token_info=token_info)


# ──────────────────────────────────────────────
# API : Auth
# ──────────────────────────────────────────────

@app.route("/api/token", methods=["POST"])
def set_token():
    """Enregistre un JWT token."""
    data = request.get_json()
    token = data.get("token", "").strip()
    if not token:
        return jsonify({"error": "Token requis"}), 400
    auth = TokenManager()
    auth.save(token)
    # Forcer le redémarrage du client
    global _client
    if _client and _client._started:
        _client.close()
    _client = None
    return jsonify({"ok": True})


@app.route("/api/token/info")
def token_info():
    """Retourne les infos du token courant."""
    try:
        auth = TokenManager()
        token = auth.access_token
        info = auth.get_token_info()
        return jsonify({
            "valid": not is_token_expired(token),
            "info": info,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 401


# ──────────────────────────────────────────────
# API : Recherche
# ──────────────────────────────────────────────

@app.route("/api/search")
def api_search():
    """Recherche full-text."""
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"error": "Paramètre 'q' requis"}), 400

    doc_type = request.args.get("type", "")
    sort = request.args.get("sort", "SCORE").upper()
    size = min(int(request.args.get("size", 10)), 50)
    offset = int(request.args.get("offset", 0))

    filters = []
    if doc_type:
        filters.append({"name": "typeDoc", "values": [doc_type]})

    try:
        client = get_client()
        result = client.search(
            query, filters=filters, sort=sort, size=size, offset=offset,
        )
        return jsonify(_serialize(result))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/search/number")
def api_search_number():
    """Recherche par numéro juridique."""
    number = request.args.get("number", "").strip()
    if not number:
        return jsonify({"error": "Paramètre 'number' requis"}), 400

    strict = request.args.get("strict", "true").lower() == "true"
    size = min(int(request.args.get("size", 5)), 20)

    try:
        client = get_client()
        result = client.search_by_number(number, size=size, strict=strict)
        return jsonify(_serialize(result))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ──────────────────────────────────────────────
# API : Documents
# ──────────────────────────────────────────────

@app.route("/api/document/<path:doc_id>/metadata")
def api_metadata(doc_id: str):
    """Métadonnées d'un document."""
    try:
        client = get_client()
        meta = client.get_metadata(doc_id)
        return jsonify(_serialize(meta))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/document/<path:doc_id>/content")
def api_content(doc_id: str):
    """Contenu d'un document."""
    fmt = request.args.get("format", "auto")
    try:
        client = get_client()
        content = client.get_document(doc_id, format=fmt)
        return jsonify({"doc_id": doc_id, "format": fmt, "content": content})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/document/<path:doc_id>/export/<fmt>")
def api_export(doc_id: str, fmt: str):
    """Export PDF ou DOCX."""
    if fmt not in ("pdf", "docx"):
        return jsonify({"error": "Format doit être 'pdf' ou 'docx'"}), 400

    try:
        client = get_client()
        with tempfile.NamedTemporaryFile(suffix=f".{fmt}", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        if fmt == "pdf":
            export_pdf(client.transport, doc_id, tmp_path)
            mimetype = "application/pdf"
        else:
            export_docx(client.transport, doc_id, tmp_path)
            mimetype = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

        return send_file(
            tmp_path,
            mimetype=mimetype,
            as_attachment=True,
            download_name=f"{doc_id}.{fmt}",
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ──────────────────────────────────────────────
# API : Navigation
# ──────────────────────────────────────────────

@app.route("/api/document/<path:doc_id>/links")
def api_links(doc_id: str):
    """Liens de navigation d'un document."""
    jp = request.args.get("jp", "false").lower() == "true"
    try:
        client = get_client()
        links = client.get_links(doc_id, jp=jp)
        return jsonify(_serialize(links))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/document/<path:doc_id>/toc")
def api_toc(doc_id: str):
    """Table des matières d'un document."""
    try:
        client = get_client()
        toc = client.get_toc(doc_id)
        return jsonify(toc)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/document/<path:doc_id>/timeline")
def api_timeline(doc_id: str):
    """Frise chronologique."""
    try:
        client = get_client()
        timeline = client.get_timeline([doc_id])
        return jsonify(_serialize(timeline))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/codes/<path:code_id>")
def api_code_tree(code_id: str):
    """Arborescence d'un code."""
    try:
        client = get_client()
        tree = client.get_code_tree(code_id)
        return jsonify(_serialize(tree))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ──────────────────────────────────────────────
# Lancement
# ──────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app.run(debug=True, port=5000)
