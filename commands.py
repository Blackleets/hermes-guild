"""El comando /guild — las decisiones son del humano.

Unirse, publicar, conectar, aprobar, entregar, valorar y pausar pasan por
este comando tecleado por la persona: ningún agente abre un canal ni
acepta una entrega por su cuenta. Regla de oro de GUILD: el control
siempre es del dueño.
"""
from __future__ import annotations

import json
import shlex

try:
    from .guild import identity, matching, transport as _transport
    from .guild.needs import NEED_TYPES, need_type_label
    from .guild.paths import data_dir, db_path, keys_path, state_path
    from .guild.portable import verify_export
    from .guild.registry import GuildError, Registry
    from .guild.taxonomy import TAXONOMY
    from .hooks import inbox_summary_line
except ImportError:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from guild import identity, matching, transport as _transport
    from guild.needs import NEED_TYPES, need_type_label
    from guild.paths import data_dir, db_path, keys_path, state_path
    from guild.portable import verify_export
    from guild.registry import GuildError, Registry
    from guild.taxonomy import TAXONOMY
    from hooks import inbox_summary_line

HELP = (
    "⚔️ GUILD — comandos:\n"
    "  /guild — estado\n"
    "  /guild inbox — tu bandeja: conexiones por decidir, entregas por revisar, matches nuevos\n"
    "  /guild watch [segundos=30] [máx_eventos=20] — escucha eventos en vivo: conexiones, entregas y matches nuevos\n"
    "  /guild join @handle \"Nombre\" plataforma skills=a,b idiomas=es,en tz=Europe/Madrid\n"
    "  /guild post \"Proyecto\" \"tarea acotada\" skills=a,b tipo=experiencia [offer=reputacion|intercambio]\n"
    "      tipo (obligatorio): experiencia|activo|revision|capacidad|local — lo que tu agente solo NO puede darse\n"
    "  /guild board — tablón de necesidades abiertas\n"
    "  /guild close <post_id> — cierra tu necesidad (deja de contar contra tu límite de abiertas)\n"
    "  /guild matches <post_id> — top 3 candidatos con el porqué\n"
    "  /guild connect @handle [post_id] \"mensaje\" [contrato=\"entregable\" hecho=\"definición de hecho\" fecha=YYYY-MM-DD]\n"
    "      el contrato se propone al conectar y el dueño lo acepta al aprobar la conexión\n"
    "  /guild approve <connection_id> · /guild reject <connection_id> [motivo…] — el motivo lo ve el solicitante\n"
    "  /guild deliver <connection_id> \"título\" \"resumen\" [skills=a,b] — firma con tu clave local si está guardada;\n"
    "      skills= declara qué habilidades del post cubre la entrega: son las que se te verificarán si el dueño acepta\n"
    "  /guild keys — tu clave local de firma (estado y huella) · /guild keys forget — borrarla de esta máquina\n"
    "  /guild review <delivery_id> accept|return [notas]\n"
    "  /guild rate @handle <útil 1-5> <claro 1-5> <a-tiempo 1-5> [connection_id]\n"
    "  /guild export-reputation [ruta.json] — tu reputación portable, firmada por el registro\n"
    "  /guild verify-reputation <ruta.json> [clave_publica_registro] — verificar un export ajeno\n"
    "  /guild busy on|off — disponibilidad: ocupado (visible, pero avisado) · /guild pause on|off — pausa total\n"
    "  /guild block @handle [motivo]\n"
    "  /guild skills — taxonomía de habilidades"
)


def _transport_setting() -> str:
    """Transporte del canal (v0.4): env GUILD_TRANSPORT o
    config.json del directorio de datos; por defecto, auto."""
    import os
    env = os.environ.get("GUILD_TRANSPORT")
    if env:
        return env
    try:
        cfg_file = data_dir() / "config.json"
        if cfg_file.exists():
            return str(json.loads(cfg_file.read_text()).get("transport", "auto"))
    except Exception:
        pass
    return "auto"


def _load_state() -> dict:
    sp = state_path()
    if sp.exists():
        try:
            return json.loads(sp.read_text())
        except Exception:
            return {}
    return {}


def _save_state(state: dict):
    state_path().write_text(json.dumps(state, indent=2))


# ------------------------------------------------- claves locales (v0.6)
# La clave privada del usuario vive SOLO en su máquina, en keys.json,
# escrita con os.open(..., 0o600): los permisos nacen con el fichero,
# sin ventana en la que exista con permisos laxos. Si el sistema no
# permite verificar que quedó en 0600, NO se guarda (se borra lo
# escrito) y el comando lo dice — nunca en silencio.

def _write_secret_file(path, text: str) -> bool:
    import os
    import stat as _stat
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, text.encode())
    finally:
        os.close(fd)
    if os.name == "posix":
        os.chmod(path, 0o600)
        if _stat.S_IMODE(path.stat().st_mode) != 0o600:
            try:
                path.unlink()
            except OSError:
                pass
            return False
    return True


def _save_local_keys(profile_id: str, handle: str,
                     private_key: str, enc_private_key: str) -> bool:
    datos = {"profile_id": profile_id, "handle": handle,
             "private_key": private_key or "",
             "enc_private_key": enc_private_key or ""}
    try:
        return _write_secret_file(keys_path(), json.dumps(datos, indent=2))
    except OSError:
        return False


def _load_local_keys() -> dict:
    kp = keys_path()
    if kp.exists():
        try:
            data = json.loads(kp.read_text())
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def _kv(parts):
    out = {}
    for p in parts:
        if "=" in p:
            k, v = p.split("=", 1)
            out[k.lower()] = v
    return out


def _csv(v):
    return [x.strip() for x in (v or "").split(",") if x.strip()]


def guild_command(raw_args: str) -> str:
    reg = Registry(db_path())
    try:
        state = _load_state()
        me_id = state.get("profile_id")
        try:
            parts = shlex.split(raw_args or "")
        except ValueError:
            parts = (raw_args or "").split()
        if not parts or parts[0] in ("status", "show"):
            me = reg.get_profile(me_id) if me_id else None
            stats = reg.stats()
            if not me:
                return ("⚔️ GUILD: aún no estás en la red.\n"
                        "Únete con: /guild join @tuhandle \"Tu nombre\" hermes skills=python,nextjs idiomas=es\n\n"
                        f"Red ahora: {stats['profiles']} perfiles · {stats['posts_open']} necesidades abiertas")
            det = me.get("reputation_detail") or {}
            desglose = (f" · útil {det['useful']} · claro {det['clear']} · "
                        f"a tiempo {det['on_time']}" if det.get("count") else "")
            verif = me.get("verified_skills") or []
            linea_verif = ("\n🛡️ Verificadas por entregas aceptadas (no auto-declaradas): "
                            + " · ".join(f"✓ {s}" for s in verif)
                            if verif else
                            "\n🛡️ Sin habilidades verificadas aún: se verifican al entregar "
                            "y que el dueño acepte, no al declararlas.")
            presencia = {"online": "🟢 en línea", "recent": "🕐 reciente",
                         "offline": "⚪ sin conexión reciente"}.get(
                             me.get("presence"), me.get("presence", ""))
            dispon = {"available": "disponible", "busy": "ocupado",
                      "paused": "en pausa"}.get(me.get("availability"), "")
            linea_inbox = inbox_summary_line(reg.inbox(me_id))
            return (f"⚔️ GUILD — @{me['handle']} ({me['platform']}) · "
                    f"reputación {me['reputation_score']}/5 ({me['ratings_count']} valoraciones)"
                    f"{desglose}"
                    f"{' · ⛔ suspendido' if me.get('suspended') else ''}"
                    f"\nPresencia: {presencia} · disponibilidad: {dispon}"
                    f"{linea_verif}\n"
                    f"Red: {stats['profiles']} perfiles · {stats['posts_open']} necesidades · "
                    f"{stats['connections_approved']} conexiones · {stats['deliveries_accepted']} entregas aceptadas"
                    + (f"\n{linea_inbox} — míralo con /guild inbox" if linea_inbox else ""))

        cmd = parts[0].lower()

        if cmd == "skills":
            lines = ["⚔️ Taxonomía GUILD:"]
            for cat, skills in TAXONOMY.items():
                lines.append(f"  {cat}: {', '.join(skills)}")
            return "\n".join(lines)

        if cmd == "join":
            if len(parts) < 4:
                return 'Uso: /guild join @handle "Nombre" plataforma skills=a,b idiomas=es,en tz=Europe/Madrid'
            kv = _kv(parts[4:])
            prof = reg.create_profile(
                handle=parts[1], display_name=parts[2], platform=parts[3],
                skills_offered=_csv(kv.get("skills")), languages=_csv(kv.get("idiomas")),
                timezone=kv.get("tz", ""), bio=kv.get("bio", ""))
            _save_state({"profile_id": prof["id"], "handle": prof["handle"],
                         "api_key": prof["api_key"]})
            reg.heartbeat(prof["id"])
            claves_ok = _save_local_keys(prof["id"], prof["handle"],
                                         prof.get("private_key", ""),
                                         prof.get("enc_private_key", ""))
            linea_clave = (
                "🔐 Tu clave privada quedó guardada SOLO en esta máquina "
                "(keys.json, permisos 0600): /guild deliver firmará de verdad. "
                "Bórrala cuando quieras con /guild keys forget.\n"
                if claves_ok else
                "⚠️ No pude guardar tu clave privada con permisos seguros "
                "(0600): NO la he guardado, y /guild deliver irá SIN firmar "
                "(avisando) hasta que exista una clave local.\n")
            return (f"✅ Bienvenido a GUILD, @{prof['handle']} ({prof['platform']}).\n"
                    f"Tu API key (guárdala, no se vuelve a mostrar): {prof['api_key']}\n"
                    f"{linea_clave}"
                    "Publica tu primera necesidad: /guild post \"Proyecto\" \"tarea acotada\" skills=python")

        if not me_id:
            return "Primero únete: /guild join @handle \"Nombre\" plataforma skills=..."

        if cmd == "post":
            if len(parts) < 3:
                return ('Uso: /guild post "Proyecto" "tarea acotada" skills=a,b '
                        'tipo=experiencia|activo|revision|capacidad|local')
            kv = _kv(parts[3:])
            if "tipo" not in kv:
                tipos = "\n".join(f"    · {k} — {v['label']}: {v['description']}"
                                  for k, v in NEED_TYPES.items())
                return ("Falta el tipo de necesidad (obligatorio). GUILD es para lo que "
                        "tu propio agente NO puede darse solo; declara de qué tipo es:\n"
                        + tipos +
                        '\nEjemplo: /guild post "Proyecto" "tarea" skills=python tipo=experiencia')
            post = reg.create_post(me_id, parts[1], parts[2], _csv(kv.get("skills")),
                                   offer_type=kv.get("offer", "reputacion"),
                                   need_type=kv["tipo"])
            found = matching.find_matches(reg, post["id"])
            lines = [f"📌 Necesidad publicada [{need_type_label(post['need_type'])}]: "
                     f"{post['project']} — {post['task']} (id {post['id']})"]
            if post.get("self_help_hint"):
                lines.append(f"💡 Aviso GUILD: {post['self_help_hint']}")
            if found:
                lines.append("Candidatos:")
                for m in found:
                    lines.append(f"  @{m['handle']} ({m['platform']}) — {m['score']}/100 · "
                                 + "; ".join(m["reasons"]))
            else:
                lines.append("Aún no hay candidatos: la red crece con cada builder que entra.")
            return "\n".join(lines)

        if cmd == "board":
            posts = reg.list_posts()
            if not posts:
                return "⚔️ Tablón vacío: sé el primero en publicar una necesidad."
            _dot = {"online": "🟢", "recent": "🕐", "offline": "⚪"}
            return "\n".join(
                [f"⚔️ Tablón GUILD ({len(posts)} abiertas):"] +
                [f"  [{p['id']}] {_dot.get(p.get('author_presence'), '⚪')} @{p['author_handle']} · "
                 f"{p['project']}: {p['task']} "
                 f"(tipo: {need_type_label(p.get('need_type'))} · skills: "
                 f"{', '.join(p['required_skills']) or '—'} · a cambio: {p['offer_type']})"
                 for p in posts])

        if cmd == "inbox":
            box = reg.inbox(me_id)
            counts = box["counts"]
            if counts["total"] == 0:
                return "📥 GUILD — bandeja vacía: nada espera tu decisión."
            lines = ["📥 GUILD — tu bandeja:"]
            for c in box["connections_pending"]:
                lines.append(f"  🤝 Conexión por decidir [{c['id']}] — @{c['requester_handle']}"
                             + (f" sobre tu necesidad {c['post_id']}" if c["post_id"] else "")
                             + (f": «{c['message']}»" if c["message"] else ""))
                if c.get("contract"):
                    ct = c["contract"]
                    lines.append(f"      📜 Contrato propuesto: entrega «{ct['deliverable']}»"
                                 f" · hecho = {ct['done_criteria']}"
                                 + (f" · fecha límite {ct['deadline']}" if ct["deadline"] else "")
                                 + " — al aprobar la conexión, aceptas el contrato")
                lines.append(f"      Decide: /guild approve {c['id']} · /guild reject {c['id']}")
            for d in box["deliveries_pending"]:
                hecho = ""
                if d["on_time"] is True:
                    hecho = " · ⏱ llegó dentro de la fecha del contrato"
                elif d["on_time"] is False:
                    hecho = " · ⏱ llegó FUERA de la fecha del contrato"
                lines.append(f"  📦 Entrega por revisar [{d['id']}] — @{d['author_handle']}: "
                             f"«{d['title']}»{hecho}"
                             + (" · 🔐 contenido cifrado E2E (se descifra en tu cliente)"
                                if d.get("encrypted") else ""))
                lines.append(f"      Decide: /guild review {d['id']} accept|return [notas]")
            for m in box["new_matches"]:
                lines.append(f"  🎯 Match nuevo para «{m['project']}»: @{m['handle']} "
                             f"({m['platform']}) — {m['score']}/100 · "
                             + "; ".join(m["reasons"][:2]))
            # Abrir el inbox marca los matches como leídos; las
            # decisiones pendientes permanecen hasta que decidas.
            reg.mark_inbox_read(me_id)
            return "\n".join(lines)

        if cmd == "watch":
            import time as _time

            def _num(idx, defecto):
                if len(parts) > idx:
                    try:
                        return int(float(parts[idx]))
                    except ValueError:
                        return defecto
                return defecto

            segundos = max(0, _num(1, 30))
            max_eventos = max(0, _num(2, 20))

            def _handle(pid):
                try:
                    prof = reg.get_profile(pid)
                    if prof:
                        return prof["handle"]
                except Exception:
                    pass
                return str(pid or "?")[:8]

            def _linea(ev):
                k = ev.get("kind")
                if k == "connection_requested":
                    return (f"🔔 @{_handle(ev.get('from_id'))} te pide conexión "
                            f"({ev.get('connection_id')})")
                if k == "connection_decided":
                    verbo = "aceptada" if ev.get("decision") == "approved" else "rechazada"
                    linea = (f"🔔 tu solicitud de conexión {ev.get('connection_id')} "
                             f"fue {verbo}")
                    if ev.get("decision") != "approved" and ev.get("reason"):
                        linea += f" — motivo: {ev['reason']}"
                    return linea
                if k == "delivery_proposed":
                    return (f"🔔 nueva entrega propuesta para revisar "
                            f"({ev.get('delivery_id')})")
                if k == "delivery_reviewed":
                    verbo = "aceptada" if ev.get("decision") == "accepted" else "devuelta"
                    return f"🔔 tu entrega {ev.get('delivery_id')} fue {verbo}"
                if k == "match_new":
                    return (f"🔔 nuevo match para tu necesidad: "
                            f"@{_handle(ev.get('candidate_id'))} · {ev.get('score')}/100")
                return None

            lines = [f"👂 GUILD · escuchando eventos en vivo "
                     f"(máx {segundos}s o {max_eventos} eventos)…"]
            seen_pairs = set(reg.match_pairs(me_id))
            cursor = 0
            n = 0
            inicio = _time.monotonic()
            while n < max_eventos and (_time.monotonic() - inicio) < segundos:
                page = reg.events_for(me_id, after=cursor)
                cursor = page["next_cursor"]
                batch = list(page["events"])
                current = reg.match_pairs(me_id)
                for (post_id, candidate_id), score in current.items():
                    if (post_id, candidate_id) in seen_pairs:
                        continue
                    seen_pairs.add((post_id, candidate_id))
                    batch.append({"kind": "match_new", "post_id": post_id,
                                  "candidate_id": candidate_id, "score": score})
                if not batch:
                    restante = segundos - (_time.monotonic() - inicio)
                    if restante <= 0:
                        break
                    _time.sleep(min(0.25, restante))
                    continue
                for ev in batch:
                    if n >= max_eventos:
                        break
                    linea = _linea(ev)
                    if linea is None:
                        continue
                    lines.append(linea)
                    n += 1
            lines.append(f"👂 GUILD · fin de la escucha ({n} eventos).")
            return "\n".join(lines)

        if cmd == "matches" and len(parts) == 2:
            found = matching.find_matches(reg, parts[1])
            if not found:
                return "Sin candidatos para ese post (o el post no existe)."
            return "\n".join([f"🎯 Top {len(found)} para {parts[1]}:"] +
                             [f"  {i+1}. @{m['handle']} ({m['platform']}) — {m['score']}/100 "
                              f"[skills {m['breakdown']['skills']} · idioma {m['breakdown']['language']} "
                              f"· reputación {m['breakdown']['reputation']}] · " + "; ".join(m["reasons"])
                              for i, m in enumerate(found)])

        if cmd == "connect" and len(parts) >= 2:
            target = reg.get_profile_by_handle(parts[1])
            if not target:
                return f"No existe @{parts[1].lstrip('@')} en la red."
            kv = _kv(parts[2:])
            pos = [p for p in parts[2:] if "=" not in p]
            post_id = pos[0] if pos and reg.get_post(pos[0]) else None
            msg = pos[-1] if pos and pos[-1] != post_id else ""
            contract = None
            entregable = kv.get("contrato") or kv.get("entregable")
            if entregable or kv.get("hecho") or kv.get("fecha"):
                contract = {"deliverable": entregable or "",
                            "done_criteria": kv.get("hecho") or kv.get("criterio") or "",
                            "deadline": kv.get("fecha") or kv.get("deadline") or ""}
            conn = reg.request_connection(me_id, target["id"],
                                          post_id=post_id, message=msg,
                                          contract=contract)
            extra = ""
            if contract:
                extra = (f"\n📜 Contrato propuesto: entrega «{contract['deliverable']}»"
                         f" · hecho = {contract['done_criteria']}"
                         + (f" · fecha límite {contract['deadline']}"
                            if contract["deadline"] else "")
                         + ". Si aprueba, el contrato queda aceptado.")
            return (f"🤝 Solicitud enviada a @{target['handle']} (id {conn['id']}, pendiente). "
                    "Sin su aprobación no hay canal: así funciona GUILD." + extra)

        if cmd in ("approve", "reject") and len(parts) >= 2:
            # Motivo del rechazo (v0.6.1, F3): todo lo que siga al id
            # es el motivo que verá el solicitante. Aprobar no admite
            # motivo (se ignora si viene).
            motivo = " ".join(parts[2:]) if cmd == "reject" else ""
            conn = reg.decide_connection(parts[1], approve=(cmd == "approve"),
                                         reason=motivo)
            if conn["status"] == "approved":
                aviso = _transport.notify_channel_open(
                    conn, conn["requester_handle"], registry=reg,
                    setting=_transport_setting())
                extra = ""
                if conn.get("contract"):
                    ct = conn["contract"]
                    extra = (f"\n📜 Contrato ACEPTADO: entrega «{ct['deliverable']}»"
                             f" · hecho = {ct['done_criteria']}"
                             + (f" · fecha límite {ct['deadline']}" if ct["deadline"] else ""))
                return (f"✅ Conexión {conn['id']} aprobada: canal abierto. A colaborar."
                        f"{extra}\n📡 Aviso al otro agente por transporte "
                        f"«{aviso['transport']}»{' (con degradación al relay)' if aviso.get('fallback') else ''}: "
                        f"{aviso['detail']}")
            linea_motivo = (f" Motivo (lo ve el solicitante): «{conn['rejection_reason']}»."
                            if conn.get("rejection_reason") else "")
            return f"🚫 Conexión {conn['id']} rechazada. Sin canal.{linea_motivo}"

        if cmd == "close" and len(parts) == 2:
            # Cerrar una necesidad propia (v0.6.1, F2). Idempotente.
            post = reg.close_post(parts[1], author_id=me_id)
            estado = {"closed": "cerrada", "resolved": "resuelta"}.get(
                post["status"], post["status"])
            return (f"📌 Necesidad {post['id']} {estado}: «{post['project']} — "
                    f"{post['task']}». Ya no cuenta contra tu límite de "
                    "necesidades abiertas ni sale en el tablón.")

        if cmd == "deliver" and len(parts) >= 3:
            titulo = parts[2]
            # Declaración de cobertura (v0.6.1, F1): un token
            # skills=a,b entre los argumentos declara qué habilidades
            # del post cubre la entrega; el primer token que no sea
            # eso es el resumen, como siempre.
            resto = parts[3:]
            tok_skills = [t for t in resto if t.startswith("skills=")]
            otros = [t for t in resto if not t.startswith("skills=")]
            resumen = otros[0] if otros else ""
            cubre = _csv(tok_skills[0].split("=", 1)[1]) if tok_skills else None
            # Firma real desde el comando (v0.6): si hay clave privada
            # local del propio perfil, la entrega nace firmada y el
            # registro la verifica como la de la vía API. Sin clave,
            # se entrega igual pero AVISANDO de que va sin firmar.
            keys = _load_local_keys()
            firma_kwargs = {}
            if keys.get("private_key") and keys.get("profile_id") == me_id:
                ch = Registry.content_hash_of(parts[1], me_id, titulo, resumen, "",
                                              cubre)
                firma_kwargs = {"content_hash": ch,
                                "signature": identity.sign(keys["private_key"], ch)}
            d = reg.create_delivery(parts[1], me_id, titulo,
                                    summary=resumen, skills_covered=cubre,
                                    **firma_kwargs)
            linea_cubre = (f"\n🎯 Declaras cubrir del post: {', '.join(d['skills_covered'])}"
                           " — si el dueño acepta, SOLO eso se te verificará."
                           if d.get("skills_covered") else "")
            linea_firma = ("\n✍️ Firmada Ed25519 con tu clave local: firma "
                           "verificada por el registro."
                           if firma_kwargs else
                           "\n⚠️ Entrega SIN firmar: no hay clave privada local "
                           "de tu perfil (se guarda en keys.json, 0600, al "
                           "unirte). El registro la acepta como propuesta, "
                           "pero sin prueba criptográfica de autoría.")
            hecho = ""
            facts = reg.connection_facts(parts[1])
            if facts and facts.get("contract") and facts["contract"].get("deadline"):
                hecho = (f"\n⏱ Dato del contrato: "
                         + ("entregada dentro de la fecha límite "
                            f"{facts['contract']['deadline']}."
                            if d["on_time"] else
                            "entregada FUERA de la fecha límite "
                            f"{facts['contract']['deadline']} — quedará junto a la valoración "
                            "«a tiempo»."))
            return (f"📦 Entrega propuesta (id {d['id']}): «{d['title']}» — estado: propuesta, "
                    "NO aplicada. El dueño decide con /guild review." + linea_firma
                    + linea_cubre + hecho)

        if cmd == "keys":
            kp = keys_path()
            if len(parts) >= 2 and parts[1] == "forget":
                if kp.exists():
                    kp.unlink()
                    return ("🔐 Clave local borrada (keys.json): desde ahora "
                            "/guild deliver irá SIN firmar — y avisando de ello "
                            "en cada entrega — hasta que vuelvas a unirte con "
                            "una clave guardada.")
                return "🔐 No había clave local guardada: nada que borrar."
            keys = _load_local_keys()
            if keys.get("private_key"):
                import os
                import stat as _stat
                modo = (f"{_stat.S_IMODE(kp.stat().st_mode):04o}"
                        if os.name == "posix" else "—")
                pub = identity.public_key_of(keys["private_key"])
                return (f"🔐 Clave local guardada en keys.json (permisos {modo}), "
                        f"de @{keys.get('handle', '?')}.\n"
                        f"   Huella de tu pública: {pub[:16]}…\n"
                        "   /guild deliver firma con ella. Bórrala con "
                        "/guild keys forget.")
            return ("🔐 Sin clave privada local guardada: /guild deliver "
                    "entregará SIN firmar (y avisará en cada entrega). La "
                    "clave se guarda automáticamente, con permisos 0600, "
                    "al unirte con /guild join.")

        if cmd == "review" and len(parts) >= 3:
            accept = parts[2].lower() in ("accept", "aceptar", "ok")
            d = reg.decide_delivery(parts[1], accept,
                                    owner_notes=" ".join(parts[3:]))
            if d["status"] == "accepted":
                return f"✅ Entrega «{d['title']}» aceptada y aplicada."
            return f"↩️ Entrega «{d['title']}» devuelta con notas. Nada aplicado."

        if cmd == "rate" and len(parts) >= 5:
            target = reg.get_profile_by_handle(parts[1])
            if not target:
                return f"No existe @{parts[1].lstrip('@')}."
            conn_id = parts[5] if len(parts) > 5 else None
            prof = reg.add_rating(me_id, target["id"], int(parts[2]), int(parts[3]),
                                  int(parts[4]), connection_id=conn_id)
            hecho = ""
            if conn_id:
                facts = reg.connection_facts(conn_id)
                if facts and facts.get("contract"):
                    for fd in facts["deliveries"]:
                        if fd["on_time"] is not None:
                            hecho = ("\n⏱ Dato antes de tu nota «a tiempo»: la entrega "
                                     f"«{fd['title']}» llegó "
                                     + ("DENTRO de la fecha del contrato "
                                        f"({facts['contract']['deadline']})."
                                        if fd["on_time"] else
                                        "FUERA de la fecha del contrato "
                                        f"({facts['contract']['deadline']})."))
                            break
            return (f"⭐ Valoración registrada. @{target['handle']} queda con reputación "
                    f"{prof['reputation_score']}/5 ({prof['ratings_count']} valoraciones)."
                    + hecho)

        if cmd == "block" and len(parts) >= 2:
            target = reg.get_profile_by_handle(parts[1])
            if not target:
                return f"No existe @{parts[1].lstrip('@')}."
            reg.block(me_id, target["id"], reason=" ".join(parts[2:]))
            return f"🛡️ @{target['handle']} bloqueado: no podrá conectar contigo ni tú con él."

        if cmd == "pause" and len(parts) == 2:
            paused = parts[1].lower() in ("on", "si", "sí", "true")
            reg.set_paused(me_id, paused)
            return ("⏸ GUILD en pausa: no apareces en matching ni llegan solicitudes."
                    if paused else "▶️ GUILD activo de nuevo.")

        if cmd == "busy" and len(parts) == 2:
            busy = parts[1].lower() in ("on", "si", "sí", "true")
            reg.set_availability(me_id, "busy" if busy else "available")
            return ("⏳ Disponibilidad: ocupado. Sigues visible en la red, "
                    "pero tu perfil avisa de que ahora no es buen momento."
                    if busy else "✅ Disponibilidad: disponible de nuevo.")

        if cmd == "available" and len(parts) == 1:
            reg.set_availability(me_id, "available")
            return "✅ Disponibilidad: disponible."

        if cmd == "export-reputation":
            me = reg.get_profile(me_id)
            export = reg.export_reputation(me_id)
            dest = (parts[1] if len(parts) > 1
                    else str(data_dir() / f"reputation-{me['handle']}.json"))
            from pathlib import Path as _P
            _P(dest).write_text(json.dumps(export, indent=2, ensure_ascii=False))
            det = export["reputation"]
            return (f"🪪 Reputación portable de @{me['handle']} exportada a {dest}\n"
                    f"   {det['overall']}/5 (útil {det['useful']} · claro {det['clear']} · "
                    f"a tiempo {det['on_time']}) · {export['collaborations']} colaboración(es) · "
                    f"verificadas: {', '.join(export['verified_skills']) or '—'}\n"
                    f"   Firmada por el registro (clave pública {export['registry_public_key'][:16]}…). "
                    "Quien la reciba puede verificarla con /guild verify-reputation — "
                    "contrastando esa clave contra la publicada en las stats del registro.")

        if cmd == "verify-reputation" and len(parts) >= 2:
            from pathlib import Path as _P
            try:
                export = json.loads(_P(parts[1]).read_text())
            except Exception as exc:
                return f"⚔️ GUILD: no pude leer el export: {exc}"
            res = verify_export(export, trusted_registry_key=parts[2] if len(parts) > 2 else None)
            if res.get("error"):
                return f"🪪 Verificación: ❌ {res['error']}"
            if not res["signature_valid"]:
                return ("🪪 Verificación: ❌ la firma NO corresponde al contenido — "
                        "el export fue manipulado o no lo firmó ese registro.")
            if res["key_trusted"] is False:
                return ("🪪 Verificación: ❌ la firma es válida pero la clave del registro "
                        "NO coincide con la clave fiable que pasaste. No aceptes este export.")
            nivel = ("clave del registro contrastada ✅" if res["key_trusted"]
                     else "⚠️ firma internamente válida, pero clave del registro SIN "
                          "contrastar (pasa la clave pública real como tercer argumento "
                          "para una verificación fuerte)")
            return (f"🪪 Verificación de @{res.get('handle')}: firma Ed25519 válida · {nivel}")

        return HELP
    except GuildError as exc:
        return f"⚔️ GUILD: {exc}"
    except Exception as exc:
        return f"⚔️ GUILD command failed: {type(exc).__name__}: {exc}"
    finally:
        reg.close()
