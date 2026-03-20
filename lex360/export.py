"""Export PDF et DOCX depuis Lexis 360."""

from __future__ import annotations

from pathlib import Path

from lex360.transport import Transport


def export_pdf(
    transport: Transport,
    doc_id: str,
    output: str | Path,
    filename: str | None = None,
) -> Path:
    """
    Exporte un document en PDF.

    Endpoint : POST /api/document/records/{docId}/pdf
    """
    output = Path(output)
    body = {"filename": filename or f"{doc_id}.pdf"}
    data = transport.post_binary(f"/api/document/records/{doc_id}/pdf", body)
    output.write_bytes(data)
    return output


def export_docx(
    transport: Transport,
    doc_id: str,
    output: str | Path,
    filename: str | None = None,
) -> Path:
    """
    Exporte un document en DOCX.

    Endpoint : POST /api/document/records/{docId}/docx
    """
    output = Path(output)
    body = {"filename": filename or f"{doc_id}.docx"}
    data = transport.post_binary(f"/api/document/records/{doc_id}/docx", body)
    output.write_bytes(data)
    return output
