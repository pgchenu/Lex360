"""Client Python pour l'API Lexis 360 Intelligence."""

__version__ = "0.1.0"

from lex360.client import Lex360Client
from lex360.exceptions import Lex360Error, AuthError, TransportError, NotFoundError, APIError

__all__ = [
    "Lex360Client",
    "Lex360Error",
    "AuthError",
    "TransportError",
    "NotFoundError",
    "APIError",
]
