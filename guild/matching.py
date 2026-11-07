"""Matching explicable de GUILD — v2 (protocolo v1.1).

Ponderación v2 (documentada en PROTOCOL.md, suma 100):
- **Habilidades: 50** — fracción de habilidades requeridas que el
  candidato cubre, resolviendo alias/sinónimos de la taxonomía
  («voz» cuenta como «agentes-de-voz», «trading» como
  «trading-algoritmico»…): el builder escribe como habla, no como un
  formulario.
- **Idioma: 12** — idiomas compartidos entre quien pide y el candidato
  (la mitad si alguno no lo especifica).
- **Reputación: 20** — media global dimensional (útil/claro/a tiempo)
  sobre 5. Sin valoraciones: 8/20 neutro de arranque, explicado así.
- **Zona horaria: 8** — bonus por cercanía: mismas horas de solape
  hacen la colaboración fluida. Δ0h = 8, decrece lineal hasta Δ12h = 0;
  sin especificar en algún perfil: 4 neutro.
- **Reciprocidad: 10** — si el candidato BUSCA algo que quien pide
  OFRECE, la colaboración puede ser intercambio real, no favor: bonus
  proporcional a la fracción de lo buscado que el dueño cubre.
- **Sub-bonus verificado (v0.3, DENTRO del factor habilidades):**
  hasta +5 de los 50 si las habilidades cubiertas están además
  VERIFICADAS — respaldadas por entregas aceptadas en posts que las
  requerían (ver `Registry.verified_skills`), no auto-declaradas.
  Los pesos totales no cambian: habilidades sigue valiendo 50 y el
  factor nunca pasa de 50.

Cada match devuelve puntuación, desglose por factor y razones legibles
por factor. Nada de cajas negras. Excluidos siempre: el propio autor,
perfiles en pausa, perfiles SUSPENDIDOS por reportes y perfiles con
bloqueo en cualquier dirección.

**Presencia (v0.4, protocolo v1.3):** la presencia derivada del
heartbeat (online <5 min · recent <24 h · offline) NO suma puntos y
no toca ningún peso: es el **desempate** del ranking. Como la
puntuación se publica redondeada a 0,1, dos candidatos con la misma
puntuación se ordenan por presencia (online antes que recent antes
que offline) y después por handle. La presencia viaja en cada match
para que la interfaz la enseñe, pero jamás infla una cifra.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .taxonomy import canonical, expand_with_aliases

W_SKILL, W_LANG, W_REP, W_TZ, W_RECIP = 50.0, 12.0, 20.0, 8.0, 10.0
W_VERIFIED_SUBBONUS = 5.0  # techo del sub-bonus DENTRO de los 50 de habilidades
NEUTRAL_REP = 8.0   # sobre 20 (mismo 40% neutro de la v1)
NEUTRAL_TZ = 4.0    # sobre 8, si falta la zona en algún perfil


def _utc_offset_hours(tz_name: str, when: datetime | None = None) -> float | None:
    """Offset UTC (horas) de una zona IANA, con la stdlib (zoneinfo).
    None si la zona falta o no se reconoce."""
    if not tz_name:
        return None
    try:
        from zoneinfo import ZoneInfo
        off = (when or datetime.now(timezone.utc)).astimezone(ZoneInfo(tz_name)).utcoffset()
        # OJO: timedelta(0) es falsy — UTC±0 (p. ej. Londres en invierno)
        # es un offset válido, no «sin especificar».
        return off.total_seconds() / 3600.0 if off is not None else None
    except Exception:
        return None


def score_candidate(post: dict, seeker: dict, candidate: dict) -> dict:
    reasons: list[str] = []

    # ---- habilidades (con alias) -------------------------------------
    required_raw = post.get("required_skills") or []
    req_map = expand_with_aliases(required_raw)          # canónica -> original pedida
    off_map = expand_with_aliases(candidate.get("skills_offered"))  # canónica -> original ofrecida
    if req_map:
        covered, alias_notes = [], []
        for canon, orig_req in req_map.items():
            if canon in off_map:
                covered.append(orig_req)
                if off_map[canon] != orig_req:
                    alias_notes.append(
                        f"«{off_map[canon]}» cuenta como «{orig_req}» (alias)")
        skill_pts = W_SKILL * (len(covered) / len(req_map))
        if covered:
            reasons.append(f"habilidades: cubre {len(covered)}/{len(req_map)} pedidas: "
                           + ", ".join(sorted(covered)))
        # Sub-bonus verificado (v0.3): de lo cubierto, lo que además esté
        # verificado por entregas aceptadas suma hasta +5 DENTRO del
        # factor (el factor nunca supera sus 50).
        verified = {canonical(v) for v in (candidate.get("verified_skills") or [])}
        v_covered = sorted(o for c, o in req_map.items()
                           if c in off_map and c in verified)
        if v_covered:
            bonus = min(W_VERIFIED_SUBBONUS * (len(v_covered) / len(req_map)),
                        W_SKILL - skill_pts)
            if bonus > 0:
                skill_pts += bonus
                reasons.append(
                    f"verificado por entregas aceptadas: {', '.join(v_covered)} "
                    f"(+{bonus:g} dentro del factor habilidades)")
        reasons.extend("alias aceptado: " + n for n in alias_notes)
        missing = sorted(set(req_map.values()) - set(covered))
        if missing:
            reasons.append("le falta: " + ", ".join(missing))
    else:
        skill_pts = W_SKILL / 2
        reasons.append("habilidades: la necesidad no pide ninguna concreta")

    # ---- idioma -------------------------------------------------------
    seeker_langs = set(seeker.get("languages") or [])
    cand_langs = set(candidate.get("languages") or [])
    shared = sorted(seeker_langs & cand_langs)
    if shared:
        lang_pts = W_LANG
        reasons.append("idioma compartido: " + ", ".join(shared))
    elif not seeker_langs or not cand_langs:
        lang_pts = W_LANG / 2
        reasons.append("idioma sin especificar en uno de los perfiles (neutro)")
    else:
        lang_pts = 0.0
        reasons.append("sin idioma compartido")

    # ---- reputación (media global dimensional) ------------------------
    count = int(candidate.get("ratings_count") or 0)
    rep_score = float(candidate.get("reputation_score") or 0)
    if count > 0:
        rep_pts = W_REP * (rep_score / 5.0)
        detail = candidate.get("reputation_detail") or {}
        desglose = ""
        if detail.get("useful") is not None:
            desglose = (f" (útil {detail['useful']} · claro {detail['clear']} "
                        f"· a tiempo {detail['on_time']})")
        reasons.append(f"reputación {rep_score:.2f}/5 en {count} valoración(es){desglose}")
    else:
        rep_pts = NEUTRAL_REP
        reasons.append("sin valoraciones aún: reputación neutra de arranque")

    # ---- zona horaria ---------------------------------------------------
    off_s = _utc_offset_hours(seeker.get("timezone") or "")
    off_c = _utc_offset_hours(candidate.get("timezone") or "")
    if off_s is None or off_c is None:
        tz_pts = NEUTRAL_TZ
        reasons.append("zona horaria sin especificar en uno de los perfiles (neutro)")
    else:
        delta = abs(off_s - off_c)
        tz_pts = W_TZ * max(0.0, 1.0 - delta / 12.0)
        if delta == 0:
            reasons.append("misma zona horaria: solape total para colaborar")
        elif delta <= 3:
            reasons.append(f"zona horaria cercana (Δ{delta:g}h): solape fácil")
        else:
            reasons.append(f"zona horaria lejana (Δ{delta:g}h): habrá que coordinar horarios")

    # ---- reciprocidad ---------------------------------------------------
    cand_wants = expand_with_aliases(candidate.get("skills_wanted"))
    seeker_offers = expand_with_aliases(seeker.get("skills_offered"))
    if cand_wants:
        mutual = sorted(set(cand_wants) & set(seeker_offers))
        recip_pts = W_RECIP * (len(mutual) / len(cand_wants))
        if mutual:
            reasons.append("reciprocidad: busca "
                           + ", ".join(sorted(cand_wants[m] for m in mutual))
                           + " y quien pide lo ofrece — intercambio real")
        else:
            reasons.append("sin reciprocidad: no busca nada que quien pide ofrezca")
    else:
        recip_pts = 0.0
        reasons.append("sin reciprocidad declarada (no busca habilidades)")

    total = round(skill_pts + lang_pts + rep_pts + tz_pts + recip_pts, 1)
    return {
        "profile_id": candidate["id"], "handle": candidate["handle"],
        "display_name": candidate.get("display_name", ""), "platform": candidate.get("platform", ""),
        "presence": candidate.get("presence", "offline"),
        "availability": candidate.get("availability", "available"),
        "score": total,
        "breakdown": {"skills": round(skill_pts, 1), "language": round(lang_pts, 1),
                      "reputation": round(rep_pts, 1), "timezone": round(tz_pts, 1),
                      "reciprocity": round(recip_pts, 1)},
        "reasons": reasons,
    }


def find_matches(registry, post_id: str, limit: int = 3) -> list[dict]:
    """Top-N candidatos para un post: excluye al autor, pausados,
    suspendidos y bloqueados en cualquier dirección."""
    post = registry.get_post(post_id)
    if not post:
        return []
    seeker = registry.get_profile(post["author_id"])
    if not seeker or seeker.get("suspended"):
        return []
    scored = []
    for cand in registry.list_profiles(include_paused=False):
        if cand["id"] == post["author_id"]:
            continue
        if cand.get("suspended"):
            continue
        if registry.is_blocked_either_way(post["author_id"], cand["id"]):
            continue
        scored.append(score_candidate(post, seeker, cand))
    # Desempate por presencia (v0.4): misma puntuación → primero quien
    # está en línea. La puntuación NO cambia; solo el orden.
    presence_rank = {"online": 0, "recent": 1, "offline": 2}
    scored.sort(key=lambda m: (-m["score"],
                               presence_rank.get(m.get("presence"), 2),
                               m["handle"]))
    return scored[:limit]
