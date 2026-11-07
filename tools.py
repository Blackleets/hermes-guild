"""GUILD tool handlers — vistas de lectura sobre el registro local.
Contrato Hermes: (args: dict, **kwargs), siempre JSON string, nunca raise."""
from __future__ import annotations

import json

try:
    from .guild import matching
    from .guild.paths import db_path, state_path
    from .guild.registry import Registry
except ImportError:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from guild import matching
    from guild.paths import db_path, state_path
    from guild.registry import Registry


def _reg() -> Registry:
    return Registry(db_path())


def guild_board(args: dict, **kwargs) -> str:
    try:
        reg = _reg()
        try:
            posts = reg.list_posts()
            return json.dumps({"ok": True, "count": len(posts), "posts": posts},
                              ensure_ascii=False)
        finally:
            reg.close()
    except Exception as exc:
        return json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"})


def guild_matches(args: dict, **kwargs) -> str:
    try:
        reg = _reg()
        try:
            limit = int((args or {}).get("limit") or 3)
            found = matching.find_matches(reg, (args or {}).get("post_id", ""), limit=limit)
            return json.dumps({"ok": True, "matches": found}, ensure_ascii=False)
        finally:
            reg.close()
    except Exception as exc:
        return json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"})


def guild_inbox(args: dict, **kwargs) -> str:
    """La bandeja del dueño (v0.4): conexiones por decidir, entregas
    por revisar y matches nuevos. Solo lectura — decidir sigue siendo
    el comando humano /guild."""
    try:
        reg = _reg()
        try:
            import json as _json
            sp = state_path()
            if not sp.exists():
                return json.dumps({"ok": True, "inbox": None,
                                   "detail": "aún no estás en la red GUILD"},
                                  ensure_ascii=False)
            state = _json.loads(sp.read_text())
            pid = state.get("profile_id")
            if not pid:
                return json.dumps({"ok": True, "inbox": None,
                                   "detail": "aún no estás en la red GUILD"},
                                  ensure_ascii=False)
            return json.dumps({"ok": True, "inbox": reg.inbox(pid)},
                              ensure_ascii=False)
        finally:
            reg.close()
    except Exception as exc:
        return json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"})


def guild_status(args: dict, **kwargs) -> str:
    try:
        reg = _reg()
        try:
            import json as _json
            me = None
            sp = state_path()
            if sp.exists():
                state = _json.loads(sp.read_text())
                if state.get("profile_id"):
                    me = reg.get_profile(state["profile_id"])
            return json.dumps({"ok": True, "me": me, "network": reg.stats()},
                              ensure_ascii=False)
        finally:
            reg.close()
    except Exception as exc:
        return json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
