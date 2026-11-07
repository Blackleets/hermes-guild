"""Rutas de datos locales de GUILD."""
from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    env = os.environ.get("GUILD_DATA_DIR")
    d = Path(env) if env else Path.home() / ".guild"
    d.mkdir(parents=True, exist_ok=True)
    return d


def db_path() -> Path:
    return data_dir() / "guild.db"


def state_path() -> Path:
    return data_dir() / "state.json"


def keys_path() -> Path:
    """El fichero de claves locales del plugin (v0.6): guarda las
    claves privadas del usuario (firma Ed25519 y cifrado X25519)
    SOLO en su máquina, creado con permisos 0600 desde el primer
    byte. Separado de state.json a propósito: el estado no es un
    secreto; esto sí."""
    return data_dir() / "keys.json"
