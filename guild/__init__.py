"""GUILD core — protocolo y registro de la red abierta de colaboración."""
from .client import GuildClient
from .registry import GuildError, Registry

__all__ = ["GuildClient", "GuildError", "Registry"]
__version__ = "0.6.1"
