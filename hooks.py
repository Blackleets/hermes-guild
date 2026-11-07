"""Hooks de GUILD.

Al arrancar la sesión, el hook hace heartbeat (mantiene vivo el
perfil en el registro: la presencia — online/recent/offline — se
deriva de ese instante) y consulta el inbox del dueño: si hay
decisiones pendientes, devuelve UNA línea resumen para que el agente
se la enseñe a su humano. Nada más se inyecta en el contexto.
"""
from __future__ import annotations

import logging

try:
    from .guild.paths import db_path, state_path
    from .guild.registry import Registry
except ImportError:  # cargado como paquete plano (tests, CLI)
    from guild.paths import db_path, state_path
    from guild.registry import Registry

logger = logging.getLogger(__name__)


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def inbox_summary_line(inbox: dict) -> str | None:
    """La línea del inbox: «📥 GUILD: 1 conexión y 1 entrega esperan tu
    decisión» (+ matches nuevos si los hay). None si no hay nada."""
    counts = (inbox or {}).get("counts") or {}
    nc = int(counts.get("connections") or 0)
    nd = int(counts.get("deliveries") or 0)
    nm = int(counts.get("new_matches") or 0)
    parts = []
    if nc:
        parts.append(_plural(nc, "conexión", "conexiones"))
    if nd:
        parts.append(_plural(nd, "entrega", "entregas"))
    line = None
    if parts:
        verbo = "espera" if (nc + nd) == 1 else "esperan"
        line = f"📥 GUILD: {' y '.join(parts)} {verbo} tu decisión"
    if nm:
        extra = _plural(nm, "match nuevo", "matches nuevos") + " para tus necesidades"
        line = f"{line} · {extra}" if line else f"📥 GUILD: {extra}"
    return line


def on_session_start(**kwargs):
    try:
        import json
        sp = state_path()
        if not sp.exists():
            return None
        state = json.loads(sp.read_text())
        pid = state.get("profile_id")
        if not pid:
            return None
        reg = Registry(db_path())
        try:
            reg.heartbeat(pid)
            return inbox_summary_line(reg.inbox(pid))
        finally:
            reg.close()
    except Exception as exc:  # un hook nunca debe romper la sesión
        logger.debug("guild session-start hook failed: %s", exc)
    return None
