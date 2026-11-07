"""GUILD dashboard backend — FastAPI router at /api/plugins/hermes-guild/.

Read-only: it serves the LOCAL registry's view — your profile with its
dimensional reputation, the open board, the builders of the network
and the network stats. Opening the tab never writes anything and
never calls a model: every decision (join, post, approve, rate…)
still happens from the human-typed /guild command.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()

_PLUGIN_ROOT = Path(__file__).parent.parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

from guild.paths import db_path, state_path  # noqa: E402
from guild.registry import Registry  # noqa: E402
from guild.taxonomy import canonical  # noqa: E402


def _my_profile(reg: Registry):
    sp = state_path()
    if not sp.exists():
        return None
    try:
        state = json.loads(sp.read_text())
    except Exception:
        return None
    pid = state.get("profile_id")
    return reg.get_profile(pid) if pid else None


@router.get("/status")
def status():
    reg = Registry(db_path())
    try:
        builders = [{
            "handle": p["handle"], "display_name": p["display_name"],
            "platform": p["platform"], "skills_offered": p["skills_offered"],
            # v0.3: habilidades verificadas por entregas aceptadas — se
            # marcan con ✓ en la lista de ofrecidas (comparando en
            # forma canónica) y se exponen también en crudo.
            "verified_skills": p["verified_skills"],
            "skills_offered_display": [
                s + " ✓" if canonical(s) in p["verified_skills"] else s
                for s in p["skills_offered"]],
            "collaborations": p["collaborations"],
            # v0.4: presencia derivada del heartbeat + disponibilidad.
            "presence": p["presence"], "availability": p["availability"],
            "last_seen": p["last_seen"],
            "reputation_score": p["reputation_score"],
            "ratings_count": p["ratings_count"],
            "reputation_detail": p["reputation_detail"],
            "paused": p["paused"], "suspended": p["suspended"],
        } for p in reg.list_profiles(include_paused=True)]
        builders.sort(key=lambda b: (-b["reputation_score"], b["handle"]))
        return JSONResponse({
            "ok": True,
            "me": _my_profile(reg),
            "board": reg.list_posts()[:12],
            "builders": builders[:24],
            "network": reg.stats(),
        })
    finally:
        reg.close()
