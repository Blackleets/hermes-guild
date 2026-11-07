#!/usr/bin/env python3
"""ENJAMBRE DE PRUEBA de GUILD — red viva simulada de extremo a extremo.

Levanta el servidor de registro REAL (`guild/server.py`) en un puerto
efímero con base temporal y mete por la API HTTP — como harían diez
usuarios de verdad, sin tocar la base salvo en UN ataque simulado y
etiquetado como tal — a 10 builders ficticios pero creíbles (Hermes ×5,
Muse ×3, OpenClaw ×2; ES/EN/FR/PT; Madrid, Berlín, CDMX, Bogotá,
Buenos Aires, Lisboa, París, Tokio). Publican 6 necesidades de proyecto
reales de builders, se hace matching, conexiones con contrato,
aprobaciones, UN rechazo, entregas (5 con payload CIFRADO E2E y todas
firmadas Ed25519), aceptaciones, ratings dimensionales y reputación.

Eventos negativos ejercitados a propósito:
- un gemelo que nunca hace heartbeat frente a su gemelo en línea
  (desempate por presencia del matching v0.4) y, después, el mismo par
  desempatado por reputación;
- una entrega cifrada manipulada EN TRÁNSITO (copia del sobre alterada
  antes de descifrar: el MAC debe rechazarla);
- una entrega cifrada manipulada EN LA BASE (única escritura directa a
  SQLite de todo el guion, etiquetada como simulación de ataque sobre
  el sobre almacenado: el MAC debe rechazarla al leerla por la API);
- un builder ruidoso que choca con el límite anti-spam de posts
  (máx. 5 abiertos) y acaba SUSPENDIDO tras 3 reportes de perfiles
  distintos, fuera del matching.

Uso:
    python3 scripts/swarm_test.py [--presence-wait 305 | --presence-offset 305]

Sin `--presence-wait`, el enjambre corre en segundos y el desempate por
presencia se observa con ambos gemelos «online» (manda el handle, y el
guion lo dice). Con `--presence-wait 305`, el guion espera a que el
gemelo silencioso envejezca a «recent» (>300 s sin heartbeat) mientras
el resto de la red sigue latiendo: el desempate por presencia se observa
entonces de forma diagnóstica (el gemelo en línea gana pese a tener el
handle alfabéticamente posterior).

Desde v0.6.1 el modo rápido oficial es `--presence-offset 305`: en vez
de esperar 305 s reales, el guion desplaza el reloj de DESARROLLO del
registro (`GUILD_DEV_TIME_OFFSET_S`, F5 — solo infraestructura de
pruebas) y late una vez más con todos menos con el gemelo silencioso:
su presencia envejece a «recent» al instante y el desempate debe dar
el MISMO orden que la corrida oficial de 305 s. La corrida con
`--presence-wait 305` sigue disponible como referencia de reloj real.

La re-corrida de v0.6.1 ejercita además los arreglos de las fricciones
del primer enjambre: entregas que DECLARAN `skills_covered` (F1) y
verificación precisa resultante, necesidades que se RESUELVEN al
aceptarse su entrega y cierre manual por API con liberación de cupo
(F2), rechazo de conexión CON motivo legible por el solicitante (F3),
y el intento de ACEPTAR el sobre manipulado en la base, que el
servidor ahora bloquea con 409 (F4).

Salida: progreso legible + un bloque SWARM_JSON con todas las cifras.
Código de salida 0 si todos los invariantes del protocolo se cumplen;
1 si alguno falla (los tops de matching esperados son OBSERVACIONES:
si la realidad difiere de lo previsto, se avisa, no se maquilla).
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import threading
import time
import urllib.request
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from guild.client import GuildClient
from guild.registry import GuildError
from guild.server import make_server

# ---------------------------------------------------------------- utilidades
RESULTS: dict = {
    "builders": [], "posts": [], "match_snapshots": [], "twin_experiment": {},
    "connections": [], "deliveries": [], "ratings": 0, "spam": {},
    "suspension": {}, "scan": {}, "metrics": {}, "reputations": [],
    "warnings": [], "failures": [],
}


def step(n, text):
    print(f"\n[{n}] {text}", flush=True)


def check(cond, label, detail=""):
    """Invariante del protocolo: si falla, el enjambre sale con error."""
    if cond:
        print(f"    ✓ {label}", flush=True)
    else:
        RESULTS["failures"].append(f"{label} — {detail}")
        print(f"    ✗ FALLO DE INVARIANTE: {label} — {detail}", flush=True)
    return cond


def observe(cond, label, detail=""):
    """Observación esperada: si difiere, se avisa (warning), no se fuerza."""
    if cond:
        print(f"    ✓ {label}", flush=True)
    else:
        RESULTS["warnings"].append(f"{label} — {detail}")
        print(f"    ⚠ OBSERVACIÓN DISTINTA A LA PREVISTA: {label} — {detail}", flush=True)
    return cond


def raw_get(client: GuildClient, path: str) -> str:
    """GET crudo (texto sin parsear) contra la API, con la key del cliente."""
    req = urllib.request.Request(client.base_url + path, method="GET")
    if client.api_key:
        req.add_header("Authorization", f"Bearer {client.api_key}")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode()


def public_profile(client: GuildClient, handle: str) -> dict:
    """Perfil público de otro miembro por la ruta HTTP oficial."""
    return client._http("GET", f"/v1/profiles/{handle}")


# ---------------------------------------------------------------- el elenco
# handle, nombre, plataforma, idiomas, zona, ofrece, busca, ¿heartbeat?
BUILDERS = [
    ("bruno",  "Bruno (gemelo A)", "openclaw", ["es", "en"], "America/Argentina/Buenos_Aires",
     ["react", "nextjs", "typescript", "tailwind"], ["backtesting"], False),
    ("santi",  "Santi (gemelo B)", "hermes",   ["es", "en"], "America/Argentina/Buenos_Aires",
     ["react", "nextjs", "typescript", "tailwind"], ["backtesting"], True),
    ("lee",    "Lee",              "muse",     ["es", "en"], "Europe/Madrid",
     ["python", "whatsapp-api", "twilio-voz", "nextjs"], ["stripe", "video-ia", "backtesting"], True),
    ("marco",  "Marco",            "hermes",   ["es", "en"], "Europe/Berlin",
     ["stripe", "webhooks", "python", "apis-rest"], ["whatsapp-api", "backtesting"], True),
    ("sofia",  "Sofía",            "hermes",   ["es", "en"], "America/Mexico_City",
     ["whatsapp-api", "twilio-voz", "twilio-sms", "a2p-registro", "agentes-de-voz"], ["stripe"], True),
    ("hana",   "Hana",             "muse",     ["en", "es"], "Asia/Tokyo",
     ["video-ia", "edicion-video", "motion-graphics", "guiones"], ["python"], True),
    ("diego",  "Diego",            "hermes",   ["es", "en"], "America/Bogota",
     ["backtesting", "trading-algoritmico", "python", "risk-management", "paper-trading"], ["stripe"], True),
    ("claire", "Claire",           "openclaw", ["fr", "en"], "Europe/Paris",
     ["react", "seo", "copywriting", "ui-ux", "tailwind"], ["ventas-locales"], True),
    ("tomas",  "Tomás",            "hermes",   ["pt", "es", "en"], "Europe/Lisbon",
     ["hermes-plugins", "testing-qa", "evaluacion-llm", "python", "docker"], ["ui-ux"], True),
    ("spamo",  "Spamo",            "muse",     ["es"],       "Europe/Madrid",
     ["python", "react"], [], True),
]

# Las 6 necesidades: (clave, autor, proyecto, tarea, skills, need_type, top esperado)
NEEDS = [
    ("a", "lee", "ReservasPro (SaaS ficticio)",
     "Integrar pagos con Stripe (checkout y webhooks verificados) en un SaaS de reservas ya en producción",
     ["stripe", "webhooks"], "experiencia", "marco"),
    ("b", "lee", "Salón Bella (ficticio)",
     "Montar la recepcionista de WhatsApp con Twilio, con el registro A2P hecho, para un salón de belleza",
     ["whatsapp-api", "twilio-voz", "a2p-registro"], "experiencia", "sofia"),
    ("c", "lee", "CanalCorto (ficticio)",
     "Construir el pipeline de vídeo vertical 9:16 con consistencia de personaje entre episodios",
     ["video-ia", "edicion-video"], "capacidad", "hana"),
    ("d", "marco", "QuantDesk (ficticio)",
     "Revisar un backtest de estrategia intradía hecho con datos reales: segunda mirada sobre sesgos y sobreajuste",
     ["backtesting", "risk-management"], "revision", "diego"),
    ("e", "bruno", "ZürichHome Services (ficticio)",
     "Landing que convierta para un servicio local en Zúrich: implementación y copy/SEO",
     ["nextjs", "seo"], "capacidad", "santi"),
    ("f", "lee", "hermes-guild",
     "Revisión de seguridad de un plugin de Hermes antes de publicarlo: claves, permisos y superficie HTTP",
     ["hermes-plugins", "testing-qa", "evaluacion-llm"], "revision", "tomas"),
]

PAYLOADS = {
    "a": ("PACK DE INTEGRACIÓN STRIPE — SaaS de reservas (datos 100% ficticios)\n"
          "- Webhook: POST /api/stripe/webhook con verificación de firma "
          "(secreto de PRUEBA: ENJAMBRE-A1-whsec-falso).\n"
          "- checkout.session.completed → crear la reserva con idempotencia por event.id.\n"
          "- Responder 200 en <5 s; el trabajo pesado, asíncrono.\n"
          "- Clave restringida rk_test_ENJAMBRE (falsa), solo lectura, para reconciliación."),
    "b": ("CHECKLIST RECEPCIONISTA WHATSAPP — salón (todo ficticio)\n"
          "- A2P: brand aprobado y campaign «transaccional-citas» (SID ficticio ENJAMBRE-B2-AC-falso).\n"
          "- Plantillas: confirmación, recordatorio 24 h y recordatorio 2 h.\n"
          "- Opt-out: STOP/BAJA procesado en el webhook de entrada.\n"
          "- Objetivo: primera respuesta del agente en <60 s en horario de salón."),
    "c": ("PAQUETE DE CONSISTENCIA DE PERSONAJE — vídeo vertical (ficticio)\n"
          "- Hoja ancla: 3 vistas del personaje y paleta fija (token ENJAMBRE-C3-SEED-falsa).\n"
          "- Prompt maestro v7; prohibido cambiar peinado o vestuario entre episodios.\n"
          "- QC: cara y manos revisadas en el 100% de los frames clave antes de publicar."),
    "c2": ("ANEXO: variantes de miniatura A/B para los episodios 4–6 "
           "(token ENJAMBRE-C4-ANEXO-falso). Se decide por CTR a las 24 h."),
    "f": ("INFORME DE REVISIÓN DE SEGURIDAD — plugin (hallazgos de ejemplo, ficticios)\n"
          "- H1 (media): un token de API aparece en un log de depuración "
          "(valor de ejemplo ENJAMBRE-F5-TOKEN-falso).\n"
          "- H2 (baja): el endpoint de estado no limita peticiones.\n"
          "- Sin críticos: las claves privadas no salen del cliente; los permisos, correctos."),
}
MARKERS = ["ENJAMBRE-A1-whsec-falso", "ENJAMBRE-B2-AC-falso", "ENJAMBRE-C3-SEED-falsa",
           "ENJAMBRE-C4-ANEXO-falso", "ENJAMBRE-F5-TOKEN-falso"]

JUNK_POSTS = [
    ("SeguidoresYA", "Consigo 1000 seguidores en 24 horas, garantizado", ["seo"]),
    ("BacklinksBaratos", "500 backlinks SEO en un día por muy poco dinero", ["seo"]),
    ("ResenasTop", "Reseñas de 5 estrellas para tu negocio, pack de 50", ["copywriting"]),
    ("MensajesMasivos", "Automatizo mensajes masivos a 10000 contactos de golpe", ["crm"]),
    ("DatosFrescos", "Vendo base de datos de emails de salones de España", ["crm"]),
]
JUNK_SIXTH = ("TradingMilagro", "Curso milagro: gana 1000 al día sin riesgo", ["trading-algoritmico"])


def deadline(days: int) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    presence_wait = 0
    if "--presence-wait" in argv:
        presence_wait = int(argv[argv.index("--presence-wait") + 1])
    presence_offset = 0
    if "--presence-offset" in argv:
        presence_offset = int(argv[argv.index("--presence-offset") + 1])
    RESULTS["presence_mode"] = {"wait_s": presence_wait, "offset_s": presence_offset}

    tmp = tempfile.mkdtemp(prefix="guild-swarm-")
    db_path = Path(tmp) / "swarm.db"
    server = make_server(db_path, port=0)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}"
    clients: dict[str, GuildClient] = {}
    join_at: dict[str, float] = {}
    try:
        step(1, f"REGISTRO — servidor GUILD real en {url} (DB temporal {db_path.name})")

        step(2, "JOIN ×10 — Hermes ×5 · Muse ×3 · OpenClaw ×2 · ES/EN/FR/PT · 8 zonas horarias")
        for handle, name, platform, langs, tz, offers, wants, beats in BUILDERS:
            c = GuildClient(base_url=url)
            prof = c.join(handle, name, platform, skills_offered=offers,
                          skills_wanted=wants, languages=langs, timezone=tz,
                          bio=f"Builder de prueba del enjambre ({platform})")
            clients[handle] = c
            join_at[handle] = time.time()
            RESULTS["builders"].append({
                "handle": handle, "platform": platform, "languages": langs,
                "timezone": tz, "skills_offered": offers, "heartbeat": beats,
                "enc_public_key": bool(prof.get("enc_public_key"))})
            print(f"    @{handle:<7} {platform:<8} {','.join(langs):<8} {tz:<38} "
                  f"enc_key={'sí' if prof.get('enc_public_key') else 'NO'}")
        check(all(b["enc_public_key"] for b in RESULTS["builders"]),
              "los 10 perfiles publican su clave de cifrado X25519 (enc_public_key)")

        def beat_all(except_handle="bruno"):
            for h, c in clients.items():
                if h != except_handle:
                    c.heartbeat()

        beat_all()
        print("    heartbeats iniciales: 9/10 (bruno, el gemelo A, no late nunca más)")

        step(3, "POSTS ×6 — las seis necesidades de proyecto, con su tipo correcto")
        posts: dict[str, dict] = {}
        for key, author, project, task, skills, ntype, _top in NEEDS:
            p = clients[author].post_need(project, task, skills,
                                          offer_type="intercambio" if key in "ab" else "reputacion",
                                          offer_detail="intercambio de habilidades dentro de la red",
                                          need_type=ntype)
            posts[key] = p
            RESULTS["posts"].append({"key": key, "author": author, "project": project,
                                      "need_type": ntype, "required_skills": skills,
                                      "id": p["id"]})
            print(f"    ({key}) @{author} · {project} · [{ntype}] · pide: {', '.join(skills)}")

        step(4, "MATCHING S1 — snapshot inicial de las 6 necesidades (top + desglose)")
        total_matches = 0
        for key, author, _project, _task, _skills, _nt, expected_top in NEEDS:
            found = clients[author].matches_for(posts[key]["id"], limit=10)
            total_matches += len(found)
            top = found[0] if found else {}
            b = top.get("breakdown", {})
            RESULTS["match_snapshots"].append({
                "key": key, "author": author, "candidates": len(found),
                "top_handle": top.get("handle"), "top_score": top.get("score"),
                "top_breakdown": b,
                "ranking": [{"handle": m["handle"], "score": m["score"],
                             "presence": m.get("presence")} for m in found]})
            print(f"    ({key}) top: @{top.get('handle')} — {top.get('score')}/100 "
                  f"[skills {b.get('skills')} · idioma {b.get('language')} · reputación "
                  f"{b.get('reputation')} · zona {b.get('timezone')} · reciprocidad "
                  f"{b.get('reciprocity')}] · {len(found)} candidatos")
            observe(top.get("handle") == expected_top,
                    f"({key}) el top match es @{expected_top}",
                    f"fue @{top.get('handle')} con {top.get('score')}")
        RESULTS["metrics"]["matches_returned_s1"] = total_matches
        print(f"    matches devueltos en S1 (suma de las 6 consultas, limit=10): {total_matches}")

        twins_d = {m["handle"]: m for m in RESULTS["match_snapshots"][3]["ranking"]}
        RESULTS["twin_experiment"]["s1"] = {
            h: {"score": twins_d[h]["score"], "presence": twins_d[h]["presence"]}
            for h in ("bruno", "santi") if h in twins_d}
        order_s1 = [m["handle"] for m in RESULTS["match_snapshots"][3]["ranking"]]
        print(f"    gemelos en (d) S1: bruno {twins_d.get('bruno')} · santi {twins_d.get('santi')} "
              f"· orden: {[h for h in order_s1 if h in ('bruno', 'santi')]}")

        step(5, "SPAM — @spamo publica sin freno: 5 posts basura pasan, el 6º debe chocar")
        spam_ok = 0
        first_junk_id = None
        for project, task, skills in JUNK_POSTS:
            p = clients["spamo"].post_need(project, task, skills, need_type="capacidad")
            if first_junk_id is None:
                first_junk_id = p["id"]
            spam_ok += 1
        sixth_error = ""
        try:
            clients["spamo"].post_need(JUNK_SIXTH[0], JUNK_SIXTH[1], JUNK_SIXTH[2],
                                       need_type="capacidad")
        except GuildError as exc:
            sixth_error = str(exc)
        RESULTS["spam"] = {"posts_accepted": spam_ok, "sixth_error": sixth_error,
                           "first_post_id": first_junk_id}
        print(f"    posts basura aceptados: {spam_ok}/5 · sexto intento → {sixth_error or 'PASÓ (!!)'}")
        check(spam_ok == 5 and "límite anti-spam" in sixth_error,
              "el 6º post abierto de @spamo choca con el límite anti-spam (máx. 5)",
              f"aceptados={spam_ok}, error={sixth_error!r}")

        if presence_offset > 0:
            step(6, f"PRESENCIA (modo rápido, F5) — reloj de DESARROLLO del registro "
                    f"desplazado +{presence_offset}s (GUILD_DEV_TIME_OFFSET_S), sin espera real")
            os.environ["GUILD_DEV_TIME_OFFSET_S"] = str(presence_offset)
            beat_all()  # todos laten en el «futuro» menos @bruno, que nunca late
            print("    @bruno nunca late: su último heartbeat queda ~"
                  f"{presence_offset}s en el pasado del registro (recent); "
                  "el resto, online")
        elif presence_wait > 0:
            step(6, f"PRESENCIA — esperando {presence_wait}s a que @bruno envejezca a «recent» "
                    f"(el resto de la red sigue latiendo cada 20 s)")
            while time.time() - join_at["bruno"] < presence_wait:
                beat_all()
                rest = presence_wait - (time.time() - join_at["bruno"])
                print(f"    … edad de @bruno: {time.time() - join_at['bruno']:.0f}s "
                      f"(faltan {max(0, rest):.0f}s)", flush=True)
                time.sleep(min(20, max(1, rest)))
            beat_all()
        else:
            step(6, "PRESENCIA — sin espera (--presence-wait 0): ambos gemelos siguen «online»")

        step(7, "MATCHING S2 — el desempate de los gemelos en la necesidad (d)")
        found_d = clients["marco"].matches_for(posts["d"]["id"], limit=10)
        rank_d = {m["handle"]: m for m in found_d}
        order_d = [m["handle"] for m in found_d if m["handle"] in ("bruno", "santi")]
        RESULTS["twin_experiment"]["s2"] = {
            h: {"score": rank_d[h]["score"], "presence": rank_d[h]["presence"]}
            for h in ("bruno", "santi") if h in rank_d}
        RESULTS["twin_experiment"]["s2_order"] = order_d
        tb, ts = rank_d.get("bruno", {}), rank_d.get("santi", {})
        print(f"    bruno: {tb.get('score')} · presencia {tb.get('presence')} | "
              f"santi: {ts.get('score')} · presencia {ts.get('presence')} | orden: {order_d}")
        check(tb.get("score") == ts.get("score"),
              "los gemelos empatan en puntuación en S2 (mismo perfil efectivo)",
              f"bruno={tb.get('score')} santi={ts.get('score')}")
        if presence_wait >= 300 or presence_offset >= 300:
            check(order_d == ["santi", "bruno"] and ts.get("presence") == "online"
                  and tb.get("presence") == "recent",
                  "desempate por PRESENCIA: @santi (online) precede a @bruno (recent) "
                  "pese a ir después en orden alfabético"
                  + (" (con el reloj desplazado, F5: mismo orden que los 305 s reales)"
                     if presence_offset >= 300 else ""),
                  f"orden={order_d}, presencias={tb.get('presence')}/{ts.get('presence')}")
        else:
            print("    (sin espera ni desplazamiento: la presencia empata y el orden lo "
                  "decide el handle — queda registrado tal cual)")

        # ------------------------------------------------------------ ciclo de vida
        step(8, "CICLO DE VIDA — conexiones con contrato, entregas, aceptaciones, ratings")

        def run_connection(key, helper, owner, message, contract, ratings):
            """Solicitud → decisión del dueño → (entrega la hace el llamante)."""
            conn = clients[helper].connect(clients[owner].profile_id,
                                           post_id=posts[key]["id"],
                                           message=message, contract=contract)
            RESULTS["connections"].append({"need": key, "helper": helper, "owner": owner,
                                           "id": conn["id"], "status_final": None})
            return conn

        def approve(conn, owner):
            out = clients[owner].approve_connection(conn["id"], approve=True)
            for r in RESULTS["connections"]:
                if r["id"] == conn["id"]:
                    r["status_final"] = out["status"]
            print(f"    ✓ @{owner} aprueba la conexión {conn['id'][:8]}… "
                  f"(contrato: {out.get('contract_status')})")
            return out

        def deliver_and_close(key, conn, helper, owner, title, summary, payload=None,
                              payload_ref="", accept=True, ratings=(), skills=None):
            d = clients[helper].deliver(conn["id"], title, summary=summary,
                                        payload_ref=payload_ref, payload=payload,
                                        skills_covered=skills)
            entry = {"need": key, "id": d["id"], "author": helper, "owner": owner,
                     "title": title, "encrypted": bool(d.get("encrypted")),
                     "signed": bool(d.get("signature")), "verify_valid": None,
                     "skills_covered": d.get("skills_covered"),
                     "decrypt_ok": None, "status": d["status"], "on_time": d.get("on_time")}
            ver = clients[owner].verify_delivery(d["id"])
            entry["verify_valid"] = ver.get("valid")
            print(f"    → entrega «{title}» · cifrada={entry['encrypted']} · "
                  f"firmada={entry['signed']} · verify={ver} · a tiempo={d.get('on_time')}")
            check(entry["signed"] and ver.get("valid") is True,
                  f"({key}) la entrega de @{helper} va firmada y el dueño la verifica",
                  f"signed={entry['signed']} verify={ver}")
            if payload is not None:
                fetched = clients[owner].get_delivery(d["id"])
                try:
                    plain = clients[owner].decrypt_delivery(fetched)
                    entry["decrypt_ok"] = plain == payload.encode()
                except GuildError as exc:
                    entry["decrypt_ok"] = False
                    entry["decrypt_error"] = str(exc)
                check(entry["decrypt_ok"] is True,
                      f"({key}) el dueño descifra el payload y coincide byte a byte",
                      f"decrypt_ok={entry['decrypt_ok']}")
            if accept:
                d2 = clients[owner].decide_delivery(d["id"], accept=True,
                                                    notes="aceptada en el enjambre")
                entry["status"] = d2["status"]
                check(d2["status"] == "accepted" and d2["applied"] is True,
                      f"({key}) el dueño acepta la entrega y queda aplicada",
                      f"status={d2['status']} applied={d2.get('applied')}")
                for ratee, u, c_, t_, cmt in ratings:
                    clients[owner].rate(clients[ratee].profile_id, u, c_, t_,
                                        connection_id=conn["id"], comment=cmt)
                    RESULTS["ratings"] += 1
            RESULTS["deliveries"].append(entry)
            return d

        # (a) Stripe — E2E nº1
        print("  (a) Stripe para ReservasPro — marco → lee, payload CIFRADO")
        conn_a = run_connection("a", "marco", "lee",
                                "He integrado Stripe en dos SaaS en producción; webhooks con idempotencia incluidos.",
                                {"deliverable": "Integración Stripe: checkout + webhook verificado",
                                 "done_criteria": "pago de prueba completado y reserva creada una sola vez por evento",
                                 "deadline": deadline(7)}, ())
        approve(conn_a, "lee")
        deliver_and_close("a", conn_a, "marco", "lee",
                          "Integración Stripe completa (checkout + webhook)",
                          "Pack de integración con verificación de firma e idempotencia",
                          payload=PAYLOADS["a"], skills=["stripe", "webhooks"],
                          ratings=(("marco", 5, 5, 5, "impecable: idempotencia incluida"),))
        clients["marco"].rate(clients["lee"].profile_id, 5, 4, 5,
                              connection_id=conn_a["id"], comment="necesidad muy bien acotada")
        RESULTS["ratings"] += 1

        # (b) WhatsApp/Twilio — E2E nº2 + manipulación EN TRÁNSITO
        print("  (b) Recepcionista WhatsApp — sofia → lee, payload CIFRADO + ataque en tránsito")
        conn_b = run_connection("b", "sofia", "lee",
                                "He hecho el registro A2P para tres negocios locales; te dejo la recepcionista andando.",
                                {"deliverable": "Recepcionista WhatsApp con A2P registrado y 3 plantillas",
                                 "done_criteria": "mensaje de prueba confirmado y recordatorio disparado",
                                 "deadline": deadline(10)}, ())
        approve(conn_b, "lee")
        d_b = clients["sofia"].deliver(conn_b["id"], "Recepcionista WhatsApp + A2P",
                                       summary="Checklist A2P y plantillas de la recepcionista",
                                       payload=PAYLOADS["b"],
                                       skills_covered=["whatsapp-api", "twilio-voz",
                                                       "a2p-registro"])
        entry_b = {"need": "b", "id": d_b["id"], "author": "sofia", "owner": "lee",
                   "title": d_b["title"], "encrypted": bool(d_b.get("encrypted")),
                   "signed": bool(d_b.get("signature")),
                   "verify_valid": clients["lee"].verify_delivery(d_b["id"]).get("valid"),
                   "decrypt_ok": None, "status": d_b["status"], "on_time": d_b.get("on_time")}
        fetched_b = clients["lee"].get_delivery(d_b["id"])
        tampered = dict(fetched_b)
        ct = tampered["enc_ciphertext"]
        tampered["enc_ciphertext"] = ("0" if ct[0] != "0" else "1") + ct[1:]
        transit_error = ""
        try:
            clients["lee"].decrypt_delivery(tampered)
        except GuildError as exc:
            transit_error = str(exc)
        entry_b["tamper_transit_error"] = transit_error
        print(f"    ⚔ copia del sobre manipulada en tránsito → descifrado: "
              f"{transit_error or '¡¡DESCIFRÓ!!'}")
        check(bool(transit_error),
              "(b) la copia manipulada en tránsito es rechazada al descifrar (MAC)",
              "decrypt_delivery aceptó un sobre alterado")
        plain_b = clients["lee"].decrypt_delivery(fetched_b)
        entry_b["decrypt_ok"] = plain_b == PAYLOADS["b"].encode()
        check(entry_b["decrypt_ok"], "(b) el sobre íntegro descifra y coincide byte a byte")
        d_b2 = clients["lee"].decide_delivery(d_b["id"], accept=True, notes="A2P verificado")
        entry_b["status"] = d_b2["status"]
        RESULTS["deliveries"].append(entry_b)
        clients["lee"].rate(clients["sofia"].profile_id, 5, 5, 4,
                            connection_id=conn_b["id"], comment="A2P sin fricción")
        clients["sofia"].rate(clients["lee"].profile_id, 5, 5, 5,
                              connection_id=conn_b["id"], comment="brief clarísimo")
        RESULTS["ratings"] += 2

        # (c) Vídeo — E2E nº3 + anexo manipulado EN LA BASE
        print("  (c) Pipeline de vídeo — hana → lee, payload CIFRADO + anexo atacado en la base")
        conn_c = run_connection("c", "hana", "lee",
                                "Mi canal usa exactamente este sistema de hoja ancla; consistencia probada en 40 episodios.",
                                {"deliverable": "Pipeline 9:16 con hoja ancla y prompt maestro versionado",
                                 "done_criteria": "dos episodios generados con el mismo personaje reconocible",
                                 "deadline": deadline(5)}, ())
        approve(conn_c, "lee")
        deliver_and_close("c", conn_c, "hana", "lee",
                          "Pipeline de vídeo con hoja ancla v7",
                          "Paquete de consistencia de personaje",
                          payload=PAYLOADS["c"], skills=["video-ia", "edicion-video"],
                          ratings=(("hana", 5, 4, 5, "la hoja ancla funciona tal cual"),))
        # Anexo: segunda entrega cifrada en la MISMA conexión; se ataca su
        # sobre EN LA BASE (única escritura directa a SQLite del guion:
        # simulación de un registro/almacén comprometido, no un paso del flujo).
        d_c2 = clients["hana"].deliver(conn_c["id"], "Anexo: miniaturas A/B",
                                       summary="Variantes de miniatura para episodios 4–6",
                                       payload=PAYLOADS["c2"],
                                       skills_covered=["video-ia"])
        entry_c2 = {"need": "c-anexo", "id": d_c2["id"], "author": "hana", "owner": "lee",
                    "title": d_c2["title"], "encrypted": bool(d_c2.get("encrypted")),
                    "signed": bool(d_c2.get("signature")), "decrypt_ok": None,
                    "status": d_c2["status"], "on_time": d_c2.get("on_time")}
        con = sqlite3.connect(str(db_path))
        row = con.execute("SELECT enc_ciphertext FROM deliveries WHERE id=?",
                          (d_c2["id"],)).fetchone()
        flipped = ("0" if row[0][0] != "0" else "1") + row[0][1:]
        con.execute("UPDATE deliveries SET enc_ciphertext=? WHERE id=?",
                    (flipped, d_c2["id"]))
        con.commit()
        con.close()
        fetched_c2 = clients["lee"].get_delivery(d_c2["id"])
        ref_hash = fetched_c2["payload_ref"].removeprefix("e2e:")
        real_hash = hashlib.sha256(bytes.fromhex(fetched_c2["enc_ciphertext"])).hexdigest()
        entry_c2["ref_hash_matches"] = (ref_hash == real_hash)
        db_error = ""
        try:
            clients["lee"].decrypt_delivery(fetched_c2)
        except GuildError as exc:
            db_error = str(exc)
        entry_c2["tamper_db_error"] = db_error
        entry_c2["verify_valid"] = clients["lee"].verify_delivery(d_c2["id"]).get("valid")
        print(f"    ⚔ sobre manipulado EN LA BASE → al leerlo por la API: "
              f"descifrado: {db_error or '¡¡DESCIFRÓ!!'} · sha256(ciphertext)≠payload_ref: "
              f"{not entry_c2['ref_hash_matches']} · verify de firma: {entry_c2['verify_valid']}")
        check(bool(db_error),
              "(c-anexo) el sobre manipulado en la base es rechazado al descifrar (MAC)",
              "decrypt_delivery aceptó el sobre alterado en la base")
        check(entry_c2["ref_hash_matches"] is False,
              "(c-anexo) la huella e2e:<sha256> del payload_ref ya no casa con el ciphertext guardado",
              "el hash de la referencia seguía casando tras manipular el ciphertext")
        # F4 (v0.6.1): en v0.6.0 la entrega quedaba «proposed» porque
        # nadie la aceptaba; ahora se INTENTA aceptar por la vía cruda
        # (sin el descifrado previo del cliente, para aislar al
        # servidor) y el servidor debe BLOQUEARLO con 409.
        ver_c2 = clients["lee"].verify_delivery(d_c2["id"])
        entry_c2["envelope_ok"] = ver_c2.get("envelope_ok")
        accept_err = ""
        try:
            clients["lee"]._http("POST", f"/v1/deliveries/{d_c2['id']}/decide",
                                 {"accept": True,
                                  "notes": "intento de aceptación directa (F4)"})
        except GuildError as exc:
            accept_err = str(exc)
        entry_c2["accept_blocked_error"] = accept_err
        print(f"    ⚔ intento de ACEPTAR el sobre manipulado → {accept_err or '¡¡SE ACEPTÓ!!'}")
        check(ver_c2.get("valid") is True and ver_c2.get("envelope_ok") is False,
              "(F4) verify separa las dos cosas: firma válida (valid) pero sobre "
              "ya no íntegro (envelope_ok=False)",
              f"verify={ver_c2}")
        check("409" in accept_err and "huella del sobre" in accept_err,
              "(F4) el SERVIDOR bloquea la aceptación del sobre manipulado "
              "(409 · huella del sobre), aunque el dueño no descifre antes",
              accept_err or "la aceptación pasó")
        check(clients["lee"].get_delivery(d_c2["id"])["status"] == "proposed",
              "(F4) la entrega atacada sigue «proposed» tras el intento de aceptación")
        print("    → la entrega atacada queda «proposed» para siempre: ya no es que "
              "nadie la acepte — es que el servidor no deja.")
        RESULTS["deliveries"].append(entry_c2)

        # (d) Backtest — entrega de solo metadatos, firmada
        print("  (d) Revisión de backtest — diego → marco, entrega de metadatos firmada")
        conn_d = run_connection("d", "diego", "marco",
                                "Reviso backtests buscando look-ahead y sobreajuste; informe con hallazgos numerados.",
                                {"deliverable": "Informe de revisión del backtest con hallazgos y veredicto",
                                 "done_criteria": "informe entregado con sesgos comprobados uno a uno",
                                 "deadline": deadline(7)}, ())
        approve(conn_d, "marco")
        deliver_and_close("d", conn_d, "diego", "marco",
                          "Informe de revisión del backtest",
                          "3 sesgos encontrados: look-ahead en festivos, costes sin modelar, ventana única",
                          payload_ref="doc:informe-backtest-v1",
                          skills=["backtesting", "risk-management"],
                          ratings=(("diego", 4, 5, 4, "riguroso; el hallazgo de festivos era real"),))

        # (e) Landing — dos colaboradores: claire (copy/SEO) y santi (implementación)
        print("  (e) Landing Zúrich — claire y santi → bruno, metadatos firmados")
        conn_e1 = run_connection("e", "claire", "bruno",
                                 "Copy y SEO local para servicios en Zúrich: FR/EN y ficha local optimizada.",
                                 {"deliverable": "Copy completo ES/EN + SEO local de la landing",
                                  "done_criteria": "textos finales y metadatos listos para publicar",
                                  "deadline": deadline(14)}, ())
        approve(conn_e1, "bruno")
        deliver_and_close("e", conn_e1, "claire", "bruno",
                          "Copy + SEO local de la landing",
                          "Titulares, prueba social y metadatos en ES/EN",
                          payload_ref="doc:landing-copy-v1", skills=["seo"],
                          ratings=(("claire", 5, 5, 5, "copy que convierte, sin humo"),))
        conn_e2 = run_connection("e", "santi", "bruno",
                                 "Te implemento la landing en Next.js con el copy de Claire.",
                                 {"deliverable": "Landing implementada en Next.js, responsive y rápida",
                                  "done_criteria": "Lighthouse ≥90 y formulario funcionando",
                                  "deadline": deadline(14)}, ())
        approve(conn_e2, "bruno")
        deliver_and_close("e", conn_e2, "santi", "bruno",
                          "Landing implementada en Next.js",
                          "Página publicada en staging con formulario y analítica",
                          payload_ref="url:staging-landing-zurich", skills=["nextjs"],
                          ratings=(("santi", 5, 4, 4, "rápido y limpio"),))

        # (f) Revisión de seguridad — tomas sí; spamo, RECHAZADO
        print("  (f) Revisión de seguridad — tomas → lee (E2E nº4) y RECHAZO a @spamo")
        conn_f = run_connection("f", "tomas", "lee",
                                "Audito plugins de Hermes: claves, permisos y superficie HTTP, con informe firmado.",
                                {"deliverable": "Informe de revisión con hallazgos por severidad",
                                 "done_criteria": "informe entregado y hallazgos reproducibles",
                                 "deadline": deadline(7)}, ())
        approve(conn_f, "lee")
        deliver_and_close("f", conn_f, "tomas", "lee",
                          "Informe de revisión de seguridad",
                          "Informe con 2 hallazgos (media/baja), sin críticos",
                          payload=PAYLOADS["f"],
                          skills=["hermes-plugins", "testing-qa", "evaluacion-llm"],
                          ratings=(("tomas", 5, 5, 4, "directo y reproducible"),))
        conn_spam = clients["spamo"].connect(
            clients["lee"].profile_id, post_id=posts["f"]["id"],
            message="Yo te hago la revisión y además 1000 seguidores de regalo, precio amigo")
        # F3 (v0.6.1): el rechazo lleva MOTIVO y el solicitante lo lee.
        MOTIVO_RECHAZO = ("oferta genérica sin relación con la revisión pedida "
                          "+ historial de posts masivos")
        rej = clients["lee"].approve_connection(conn_spam["id"], approve=False,
                                                reason=MOTIVO_RECHAZO)
        vista_spamo = clients["spamo"].get_connection(conn_spam["id"])
        RESULTS["connections"].append({"need": "f", "helper": "spamo", "owner": "lee",
                                       "id": conn_spam["id"], "status_final": rej["status"],
                                       "rejection_reason": MOTIVO_RECHAZO,
                                       "reason_visible_to_requester":
                                           vista_spamo.get("rejection_reason") == MOTIVO_RECHAZO})
        print(f"    ✗ @lee RECHAZA la solicitud de @spamo → estado: {rej['status']} · "
              f"motivo: «{MOTIVO_RECHAZO}»")
        check(rej["status"] == "rejected", "(f) la conexión de @spamo queda rechazada",
              f"status={rej['status']}")
        check(vista_spamo.get("rejection_reason") == MOTIVO_RECHAZO,
              "(F3) el motivo del rechazo llega al SOLICITANTE por la API "
              "(en v0.6.0 solo vivía en el informe)",
              f"rejection_reason={vista_spamo.get('rejection_reason')!r}")
        check(clients["spamo"].channel_open(conn_spam["id"]) is False,
              "(f) sin aprobación no hay canal para @spamo")

        step("8.5", "CIERRE DE POSTS (F2) — resueltos automáticos, cierre por API y cupo")
        stats_mid = clients["lee"].status()["network"]
        print(f"    posts_open tras el ciclo de vida: {stats_mid['posts_open']} "
              "(en v0.6.0 quedaban 11: las 6 de proyecto seguían «abiertas» para siempre)")
        check(stats_mid["posts_open"] == 5,
              "(F2) las 6 necesidades de proyecto quedaron RESUELTAS al aceptarse "
              "sus entregas: solo quedan abiertas las 5 basura de @spamo",
              f"posts_open={stats_mid['posts_open']}")
        junk_id = RESULTS["spam"]["first_post_id"]
        close_err = ""
        try:
            clients["marco"].close_post(junk_id)
        except GuildError as exc:
            close_err = str(exc)
        check("403" in close_err,
              "(F2) un tercero NO puede cerrar la necesidad de otro (403)",
              close_err or "el cierre ajeno pasó")
        cerrado = clients["spamo"].close_post(junk_id)
        check(cerrado["status"] == "closed",
              "(F2) el autor cierra su propia necesidad por la API",
              f"status={cerrado.get('status')}")
        otra_vez = clients["spamo"].close_post(junk_id)
        check(otra_vez["status"] == "closed",
              "(F2) cerrar dos veces es idempotente (sin error)",
              f"status={otra_vez.get('status')}")
        extra = clients["spamo"].post_need(
            "OtroHumo", "Más humo, ahora que cerré una necesidad propia",
            ["seo"], need_type="capacidad")
        RESULTS["spam"]["extra_after_close"] = 1
        check(bool(extra.get("id")),
              "(F2) cerrar LIBERA el cupo anti-spam: @spamo (5 abiertas) vuelve "
              "a poder publicar tras cerrar una",
              f"extra={extra}")

        step(9, "RE-MATCHING (d) — el desempate por REPUTACIÓN tras los ratings")
        found_d2 = clients["marco"].matches_for(posts["d"]["id"], limit=10)
        rank_d2 = {m["handle"]: m for m in found_d2}
        RESULTS["twin_experiment"]["s3"] = {
            h: {"score": rank_d2[h]["score"],
                "reputation_pts": rank_d2[h]["breakdown"]["reputation"]}
            for h in ("bruno", "santi") if h in rank_d2}
        print(f"    bruno: {rank_d2.get('bruno', {}).get('score')} "
              f"(reputación {rank_d2.get('bruno', {}).get('breakdown', {}).get('reputation')}) · "
              f"santi: {rank_d2.get('santi', {}).get('score')} "
              f"(reputación {rank_d2.get('santi', {}).get('breakdown', {}).get('reputation')})")
        check(rank_d2["santi"]["score"] > rank_d2["bruno"]["score"],
              "tras ganar reputación, @santi puntúa por encima de su gemelo @bruno en (d)",
              f"santi={rank_d2['santi']['score']} bruno={rank_d2['bruno']['score']}")

        step(10, "REPORTES — 3 perfiles distintos reportan a @spamo: suspensión")
        reporters = [("lee", "posts masivos de servicios engañosos y solicitud sin relación con la necesidad"),
                     ("marco", "spam repetido en el tablón"),
                     ("sofia", "ofertas de reseñas falsas: fuera de las normas de la red")]
        for handle, reason in reporters:
            clients[handle].report(clients["spamo"].profile_id, reason)
            prof_spam = public_profile(clients["lee"], "spamo")
            print(f"    reporte de @{handle} → @spamo suspended={prof_spam.get('suspended')}")
        RESULTS["suspension"] = {"suspended": bool(prof_spam.get("suspended")),
                                  "reports": len(reporters)}
        check(prof_spam.get("suspended") is True,
              "@spamo queda suspendido al llegar a 3 reportes de perfiles distintos")
        found_a2 = clients["lee"].matches_for(posts["a"]["id"], limit=10)
        check(all(m["handle"] != "spamo" for m in found_a2),
              "@spamo desaparece de los resultados de matching tras la suspensión")
        post_err = ""
        try:
            clients["spamo"].post_need("OtraCosa", "Sigo vendiendo humo tras la suspensión",
                                        ["seo"], need_type="capacidad")
        except GuildError as exc:
            post_err = str(exc)
        RESULTS["suspension"]["post_after_suspension_error"] = post_err
        print(f"    @spamo intenta publicar estando suspendido → {post_err or '¡¡PUBLICÓ!!'}")
        check(bool(post_err), "un perfil suspendido no puede seguir publicando",
              "post_need de un suspendido pasó")

        step(11, "ESCANEO — ningún payload en claro ni en la base ni en respuestas HTTP")
        db_bytes = Path(db_path).read_bytes()
        raw_texts = [raw_get(clients["lee"], "/v1/posts"),
                     raw_get(clients["lee"], "/v1/stats")]
        for entry in RESULTS["deliveries"]:
            if entry["encrypted"]:
                owner_client = clients[entry["owner"]]
                raw_texts.append(raw_get(owner_client, f"/v1/deliveries/{entry['id']}"))
        leaks = []
        for marker in MARKERS:
            if marker.encode() in db_bytes:
                leaks.append(f"{marker} EN LA BASE")
            if any(marker in t for t in raw_texts):
                leaks.append(f"{marker} EN UNA RESPUESTA HTTP")
        RESULTS["scan"] = {"markers_checked": MARKERS, "leaks": leaks,
                           "responses_scanned": len(raw_texts)}
        check(not leaks,
              "los 5 marcadores secretos no aparecen en la SQLite ni en las respuestas HTTP escaneadas",
              f"fugas: {leaks}")
        print(f"    respuestas HTTP escaneadas en crudo: {len(raw_texts)} "
              f"(tablón, stats y GET de cada entrega cifrada)")

        step(12, "CIERRE — reputaciones, habilidades verificadas y métricas de la red")
        reps = []
        for handle, *_ in BUILDERS:
            prof = public_profile(clients["lee"], handle)
            det = prof.get("reputation_detail", {})
            reps.append({"handle": handle, "score": prof.get("reputation_score"),
                         "ratings": det.get("count"), "useful": det.get("useful"),
                         "clear": det.get("clear"), "on_time": det.get("on_time"),
                         "verified_skills": prof.get("verified_skills", []),
                         "suspended": prof.get("suspended"),
                         "presence": prof.get("presence")})
        reps.sort(key=lambda r: (-(r["score"] or 0), r["handle"]))
        RESULTS["reputations"] = reps
        for r in reps:
            print(f"    @{r['handle']:<7} reputación {r['score']}/5 · n={r['ratings']} · "
                  f"útil {r['useful']} · claro {r['clear']} · a tiempo {r['on_time']} · "
                  f"verificadas: {', '.join(r['verified_skills']) or '—'}"
                  f"{' · SUSPENDIDO' if r['suspended'] else ''}")
        check(any(r["verified_skills"] for r in reps),
              "al menos un builder gana habilidades VERIFICADAS por entregas aceptadas")
        por_handle = {r["handle"]: r for r in reps}
        check(por_handle["claire"]["verified_skills"] == ["seo"],
              "(F1) @claire queda SOLO con «seo» verificada: el «nextjs» que el "
              "primer enjambre le atribuyó sin ofrecerlo ya NO aparece",
              f"{por_handle['claire']['verified_skills']}")
        check(por_handle["santi"]["verified_skills"] == ["nextjs"],
              "(F1) @santi queda SOLO con «nextjs» verificada: el «seo» "
              "sobre-atribuido ya NO aparece",
              f"{por_handle['santi']['verified_skills']}")

        stats = clients["lee"].status()["network"]
        conns = RESULTS["connections"]
        approved = sum(1 for c in conns if c["status_final"] == "approved")
        dl = RESULTS["deliveries"]
        RESULTS["metrics"].update({
            "profiles": len(BUILDERS),
            "posts_created": len(RESULTS["posts"]) + RESULTS["spam"]["posts_accepted"]
                             + RESULTS["spam"].get("extra_after_close", 0),
            "posts_project": len(RESULTS["posts"]),
            "posts_junk_accepted": RESULTS["spam"]["posts_accepted"],
            "connections_requested": len(conns),
            "connections_approved": approved,
            "connections_rejected": sum(1 for c in conns if c["status_final"] == "rejected"),
            "deliveries_total": len(dl),
            "deliveries_encrypted": sum(1 for d in dl if d["encrypted"]),
            "deliveries_signed": sum(1 for d in dl if d["signed"]),
            "deliveries_verify_valid": sum(1 for d in dl if d.get("verify_valid") is True),
            "deliveries_accepted": sum(1 for d in dl if d["status"] == "accepted"),
            "deliveries_decrypted_ok": sum(1 for d in dl if d.get("decrypt_ok") is True),
            "ratings_total": RESULTS["ratings"],
            "verified_skills_total": sum(len(r["verified_skills"]) for r in reps),
            "verified_skills_builders": sum(1 for r in reps if r["verified_skills"]),
            "server_stats": stats,
        })
        m = RESULTS["metrics"]
        check(m["verified_skills_total"] == 14,
              "(F1) habilidades verificadas en total: 14 — las 16 de v0.6.0 menos "
              "las 2 sobre-atribuidas (nextjs de @claire, seo de @santi); las 14 "
              "restantes son exactamente las declaradas y entregadas",
              f"{m['verified_skills_total']}")
        print(f"\n    MÉTRICAS: perfiles {m['profiles']} · posts {m['posts_created']} "
              f"({m['posts_project']} de proyecto + {m['posts_junk_accepted']} basura"
              f"{' + 1 tras cerrar cupo' if RESULTS['spam'].get('extra_after_close') else ''}) · "
              f"conexiones {approved}/{m['connections_requested']} aprobadas · "
              f"entregas {m['deliveries_total']} ({m['deliveries_encrypted']} cifradas, "
              f"{m['deliveries_signed']} firmadas, {m['deliveries_accepted']} aceptadas) · "
              f"ratings {m['ratings_total']} · habilidades verificadas "
              f"{m['verified_skills_total']} en {m['verified_skills_builders']} builders")
        print(f"    stats del servidor: {stats}")

        print("\nSWARM_JSON_BEGIN")
        print(json.dumps(RESULTS, ensure_ascii=False, indent=1, default=str))
        print("SWARM_JSON_END")
        if RESULTS["failures"]:
            print(f"\n❌ ENJAMBRE CON {len(RESULTS['failures'])} FALLO(S) DE INVARIANTE")
            return 1
        print("\n✅ ENJAMBRE COMPLETO: todos los invariantes del protocolo se cumplen")
        return 0
    finally:
        server.shutdown()
        server.server_close()
        server.registry.close()


if __name__ == "__main__":
    sys.exit(main())
