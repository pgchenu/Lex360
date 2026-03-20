"""Exceptions du client Lexis 360."""


class Lex360Error(Exception):
    """Erreur de base pour le client Lexis 360."""


class AuthError(Lex360Error):
    """Erreur d'authentification (token expiré, refresh échoué)."""


class TransportError(Lex360Error):
    """Erreur de transport HTTP (TLS rejeté, réseau)."""


class NotFoundError(Lex360Error):
    """Document non trouvé (404)."""


class APIError(Lex360Error):
    """Réponse API inattendue."""

    def __init__(self, message: str, status_code: int | None = None, body: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body
