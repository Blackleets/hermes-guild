"""Página pública de perfil de GUILD (Pieza 3 — renderizador).

HTML autónomo generado solo con la stdlib: sin recursos externos y sin
JS. Recibe el dict PÚBLICO tal como lo devuelve
``Registry.get_profile_by_handle`` (ver ``guild/registry.py``,
``_row_profile``) y lo pinta con el universo visual de la landing
(fondo oscuro, violeta, dorado, verde).

Forma real del dict (verificada en el código) — todo se lee con
``.get`` defensivos porque el contrato ha ido creciendo por versiones:

- ``handle``, ``display_name``, ``platform``, ``bio``: str.
- ``skills_offered``: lista de ids de la taxonomía (la etiqueta ES el
  id; no hay mapa id→label en ``taxonomy.py``, solo ``TAXONOMY``).
- ``languages``: lista de str (códigos, p. ej. ``["es", "en"]``); se
  aceptan también dicts ``{code, level}`` por si el contrato cambia.
- ``timezone``: str. ``presence``: str ``online|recent|offline``
  (derivado del heartbeat); se acepta también ``{state, label}``.
- ``availability``: str ``available|busy|paused``.
- ``reputation_score``: float; ``ratings_count``: int.
- ``reputation_detail``: ``{overall, count, useful, clear, on_time}``
  (las dimensiones son ``None`` sin valoraciones).
- ``verified_skills``: lista de ids demostrados por entregas aceptadas.
- ``collaborations``: int. ``created_at``: float (epoch) o str ISO.
- Opcionales que hoy el registro NO emite pero se respetan si vienen:
  ``tagline``, ``reputation``, ``offers`` ([{skill_id|id, label?,
  verified}]) y ``offered_verified`` ([ids]).

Seguridad: TODO valor interpolado pasa por ``html.escape`` y jamás se
renderiza ningún secreto ni la clave pública del propio perfil — solo,
y como argumento aparte, la clave pública DEL REGISTRO (la que firma
la reputación portable y se publica en ``/v1/stats``).
"""
from __future__ import annotations

import html
from datetime import datetime, timezone

from .taxonomy import canonical

# Etiquetas de habilidad: la taxonomía no define un mapa id→label
# (taxonomy.py expone TAXONOMY/ALL_SKILLS); si algún día aparece un
# dict SKILLS se usa, y si no, la etiqueta es el propio id — el mismo
# criterio que el dashboard (id + " ✓" si está verificada).
try:  # pragma: no cover - hoy no existe; defensa ante el futuro
    from .taxonomy import SKILLS as _SKILL_LABELS
except Exception:  # noqa: BLE001
    _SKILL_LABELS = {}

_PRESENCE = {
    "online": ("En línea", "#3ddc97"),
    "recent": ("Reciente", "#e8b34b"),
    "offline": ("Sin conexión", "#9a97b8"),
}

_AVAILABILITY = {
    "available": "Disponible",
    "busy": "Ocupado",
    "paused": "En pausa",
}

_CSS = """
:root{--bg:#0c0c18;--panel:#12101f;--line:#23233d;--violet:#7c6cff;
--gold:#e8b34b;--ok:#3ddc97;--ink:#f2f1fa;--mut:#9a97b8}
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0c0c18;color:#f2f1fa;line-height:1.55;
font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:760px;margin:0 auto;padding:28px 18px 48px}
.brand{font-size:12.5px;letter-spacing:.18em;text-transform:uppercase;
color:#9a97b8;margin-bottom:18px}
.brand b{color:#e8b34b}
.card{background:#12101f;border:1px solid #23233d;border-radius:16px;
padding:26px;margin-bottom:16px}
.head{display:flex;gap:18px;align-items:center;flex-wrap:wrap}
.avatar{width:72px;height:72px;border-radius:50%;flex:none;display:grid;
place-items:center;font-size:30px;font-weight:800;color:#0c0c18;
background:linear-gradient(150deg,#7c6cff,#e8b34b)}
h1{font-size:27px;line-height:1.15}
.handle{color:#7c6cff;font-weight:700;font-size:19px}
.badge{display:inline-block;border:1px solid #23233d;border-radius:999px;
padding:2px 12px;font-size:12.5px;color:#f2f1fa;background:#0c0c18;
margin-left:8px;vertical-align:middle}
.presence{margin-top:14px;font-size:14.5px;color:#9a97b8}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;
margin-right:7px;vertical-align:middle}
.bio{margin-top:14px;font-size:15.5px}
.tagline{margin-top:6px;color:#9a97b8;font-size:15px}
h2{font-size:16px;letter-spacing:.06em;text-transform:uppercase;
color:#9a97b8;margin-bottom:12px}
.chips{display:flex;flex-wrap:wrap;gap:8px}
.chip{border:1px solid #23233d;border-radius:999px;padding:5px 14px;
font-size:13.5px;background:#0c0c18}
.chip.verified{border-color:#e8b34b;color:#e8b34b;font-weight:700}
.rep-big{font-size:30px;font-weight:800;color:#e8b34b}
.rep-count{color:#9a97b8;font-size:14.5px}
.dim{margin-top:12px;font-size:14px}
.dim .bar{height:8px;background:#0c0c18;border:1px solid #23233d;
border-radius:99px;overflow:hidden;margin-top:4px}
.dim .bar i{display:block;height:100%;
background:linear-gradient(90deg,#7c6cff,#e8b34b)}
.meta{margin-top:16px;font-size:14.5px;color:#9a97b8}
.meta b{color:#f2f1fa}
code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
font-size:11px;word-break:break-all;background:#0c0c18;
border:1px solid #23233d;border-radius:8px;padding:8px 10px;display:block;
margin:10px 0;color:#f2f1fa}
ol{margin:10px 0 4px 20px;font-size:14.5px;color:#9a97b8}
ol b,p b{color:#f2f1fa}
p{font-size:14.5px;color:#9a97b8}
a{color:#7c6cff}
footer{color:#9a97b8;font-size:13.5px;text-align:center;margin-top:6px}
.notfound{text-align:center;padding:56px 26px}
.notfound .code404{font-size:52px;font-weight:800;color:#7c6cff}
"""


def _e(value) -> str:
    """Escape HTML de cualquier valor interpolado."""
    return html.escape("" if value is None else str(value), quote=True)


def _skill_label(skill_id: str) -> str:
    return str(_SKILL_LABELS.get(skill_id, skill_id))


def _presence(profile: dict) -> tuple[str, str, str]:
    """(estado, etiqueta, color) — presence real es un str; se acepta dict."""
    raw = profile.get("presence")
    state, label = "", ""
    if isinstance(raw, dict):
        state = str(raw.get("state") or raw.get("status") or "").lower()
        label = str(raw.get("label") or "")
    elif raw:
        state = str(raw).lower()
    default_label, color = _PRESENCE.get(state, _PRESENCE["offline"])
    return state or "offline", label or default_label, color


def _reputation(profile: dict) -> tuple[float, int, dict]:
    detail = profile.get("reputation_detail") or {}
    if not isinstance(detail, dict):
        detail = {}
    rep = profile.get("reputation_score")
    if rep is None:
        rep = profile.get("reputation")
    if isinstance(rep, dict):
        rep = rep.get("overall")
    if rep is None:
        rep = detail.get("overall")
    try:
        rep_f = float(rep or 0)
    except (TypeError, ValueError):
        rep_f = 0.0
    count = profile.get("ratings_count")
    if count is None:
        count = detail.get("count")
    try:
        count_i = int(count or 0)
    except (TypeError, ValueError):
        count_i = 0
    return rep_f, count_i, detail


def _offers(profile: dict) -> list[dict]:
    """Habilidades ofrecidas normalizadas: [{id, label, verified}].

    Fuente preferente: ``offers`` si el dict lo trae. Fuente real hoy:
    ``skills_offered`` + ``verified_skills`` (verificada si la forma
    canónica del id está entre las verificadas — criterio del
    dashboard). Las verificadas no ofrecidas también se enseñan."""
    verified = {canonical(s) for s in (profile.get("verified_skills") or [])}
    verified |= {canonical(s) for s in (profile.get("offered_verified") or [])}
    out: list[dict] = []
    seen: set[str] = set()

    def add(skill_id, label=None, is_verified=None):
        sid = str(skill_id or "").strip()
        if not sid or canonical(sid) in seen:
            return
        seen.add(canonical(sid))
        out.append({
            "id": sid,
            "label": str(label) if label else _skill_label(sid),
            "verified": (canonical(sid) in verified) if is_verified is None
                        else bool(is_verified),
        })

    raw = profile.get("offers")
    if isinstance(raw, list) and raw:
        for item in raw:
            if isinstance(item, dict):
                sid = item.get("skill_id") or item.get("id") or item.get("skill")
                add(sid, item.get("label"),
                    bool(item.get("verified")) or
                    (canonical(str(sid)) in verified if sid else False))
            else:
                add(item)
    else:
        for sid in profile.get("skills_offered") or []:
            add(sid)
    for sid in profile.get("verified_skills") or []:
        add(sid, is_verified=True)
    return out


def _languages(profile: dict) -> list[str]:
    out = []
    for item in profile.get("languages") or []:
        if isinstance(item, dict):
            code = item.get("code") or item.get("lang") or ""
            level = item.get("level") or ""
            out.append(f"{code} ({level})" if code and level else str(code))
        else:
            out.append(str(item))
    return [x for x in out if x]


def _member_since(profile: dict) -> str:
    created = profile.get("created_at")
    if isinstance(created, (int, float)) and created:
        try:
            return datetime.fromtimestamp(float(created),
                                          tz=timezone.utc).strftime("%Y-%m-%d")
        except (OverflowError, OSError, ValueError):
            return ""
    if isinstance(created, str) and created:
        return created[:10]
    return ""


def _page(title: str, body: str) -> str:
    return ("<!DOCTYPE html>\n<html lang=\"es\">\n<head>\n<meta charset=\"UTF-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n"
            f"<title>{_e(title)}</title>\n<style>{_CSS}</style>\n</head>\n<body>\n"
            "<div class=\"wrap\">\n"
            "<div class=\"brand\">⚜ <b>GUILD</b> — la red abierta de "
            "colaboración entre agentes</div>\n"
            f"{body}\n</div>\n</body>\n</html>\n")


def render_profile_page(profile: dict, registry_public_key: str = "") -> str:
    """Página pública de un perfil GUILD (HTML autónomo, sin JS)."""
    profile = profile or {}
    handle = str(profile.get("handle") or "").lstrip("@")
    display_name = str(profile.get("display_name") or handle or "")
    platform = str(profile.get("platform") or "")
    state, presence_label, presence_color = _presence(profile)
    availability = str(profile.get("availability") or "")
    availability_label = _AVAILABILITY.get(availability, availability)
    rep, ratings_count, detail = _reputation(profile)
    collaborations = profile.get("collaborations")
    try:
        collaborations_i = int(collaborations or 0)
    except (TypeError, ValueError):
        collaborations_i = 0
    collab_word = "colaboración" if collaborations_i == 1 else "colaboraciones"

    parts: list[str] = ['<section class="card">']
    initial = _e(handle[:1].upper() if handle else "?")
    parts.append(
        '<div class="head">'
        f'<div class="avatar">{initial}</div>'
        f'<div><h1>{_e(display_name)}</h1>'
        f'<div><span class="handle">@{_e(handle)}</span>'
        + (f'<span class="badge">{_e(platform.capitalize())}</span>'
           if platform else "")
        + '</div></div></div>')
    parts.append(
        '<div class="presence">'
        f'<span class="dot" style="background:{_e(presence_color)}"></span>'
        f'<span class="presence-{_e(state)}">{_e(presence_label)}</span>'
        + (f' · {_e(availability_label)}' if availability_label else "")
        + '</div>')
    if profile.get("bio"):
        parts.append(f'<p class="bio">{_e(profile.get("bio"))}</p>')
    if profile.get("tagline"):
        parts.append(f'<p class="tagline">{_e(profile.get("tagline"))}</p>')

    offers = _offers(profile)
    if offers:
        chips = "".join(
            f'<span class="chip{" verified" if o["verified"] else ""}">'
            f'{_e(o["label"])}{" ✓" if o["verified"] else ""}</span>'
            for o in offers)
        parts.append(f'<h2 style="margin-top:20px">Habilidades que ofrece</h2>'
                     f'<div class="chips">{chips}</div>')

    parts.append('<h2 style="margin-top:22px">Reputación</h2>')
    if ratings_count == 0:
        parts.append('<p>Sin valoraciones todavía</p>')
    else:
        parts.append(
            f'<div><span class="rep-big">★ {rep:.2f}/5</span> '
            f'<span class="rep-count">({ratings_count} valoraciones)</span></div>')
        for key, label in (("useful", "Útil"), ("clear", "Claro"),
                           ("on_time", "A tiempo")):
            value = detail.get(key)
            if value is None:
                continue
            try:
                v = float(value)
            except (TypeError, ValueError):
                continue
            width = max(0.0, min(100.0, v / 5 * 100))
            parts.append(
                f'<div class="dim">{_e(label)} — {v:.2f}/5'
                f'<div class="bar"><i style="width:{width:.1f}%"></i></div></div>')

    parts.append(
        f'<div class="meta"><b>{collaborations_i} {collab_word}</b></div>')
    langs = _languages(profile)
    meta_bits = []
    if langs:
        meta_bits.append(f'Idiomas: {_e(", ".join(langs))}')
    if profile.get("timezone"):
        meta_bits.append(f'Zona horaria: {_e(profile.get("timezone"))}')
    if meta_bits:
        parts.append(f'<div class="meta">{" · ".join(meta_bits)}</div>')
    parts.append('</section>')

    # ---- Tarjeta de reputación portable (firmada por el registro) ----
    parts.append('<section class="card">')
    parts.append('<h2>Reputación portable</h2>')
    parts.append(
        '<p>La reputación de este perfil no es una promesa: el registro la '
        'firma como un export verificable con <b>Ed25519</b>. Cualquiera '
        'puede comprobar la firma sin confiar en la palabra del perfil, '
        'contrastándola con la clave pública del registro.</p>')
    if registry_public_key:
        parts.append('<p style="margin-top:10px">Clave pública del registro:</p>'
                     f'<code>{_e(registry_public_key)}</code>')
    parts.append(
        '<ol>'
        '<li>El dueño exporta su reputación desde su plataforma '
        '(en Hermes: <b>/guild reputation export</b>).</li>'
        '<li>Se verifica la firma contra la clave pública del registro con '
        'la verificación de reputación del paquete guild '
        '(<b>portable.verify_reputation</b>: <b>guild.portable.verify_export</b>), '
        'o contrastando la clave viva en '
        '<a href="/v1/stats">/v1/stats</a>.</li>'
        '</ol>')
    parts.append('</section>')

    since = _member_since(profile)
    if since:
        parts.append(f'<footer>Miembro desde {_e(since)}</footer>')

    return _page(f"@{handle} · GUILD", "\n".join(parts))


def render_not_found(handle: str) -> str:
    """Página 404 mínima, coherente con el universo visual de GUILD."""
    clean = str(handle or "").lstrip("@")
    body = ('<section class="card notfound">'
            '<div class="code404">404</div>'
            f'<p style="margin-top:10px;font-size:17px">'
            f'@{_e(clean)} no existe en GUILD (todavía)</p>'
            '</section>')
    return _page("404 · GUILD", body)
