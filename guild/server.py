"""Servidor del registro GUILD — REST real con la stdlib (http.server).

Implementa los endpoints del protocolo (PROTOCOL.md v1.6) sobre el
Registry SQLite: sin frameworks externos. Pensado para ejecutarse como
el registro central de una comunidad (o en local para desarrollo):

    python3 -m guild.server --db ~/.guild/registry.db --port 8787
    GUILD_DB=... GUILD_PORT=8787 python3 -m guild.server

Autenticación: `Authorization: Bearer <api_key>` en todo excepto el
alta de perfil, el tablón, los matches, el perfil público y las stats
(lecturas públicas de la red). Las decisiones (aprobar conexión,
aceptar entrega) exigen ser parte de la conexión — y el autor de una
entrega nunca puede aceptarla él mismo.

Códigos de error del protocolo: 201 creado · 401 sin API key válida ·
403 sin canal / parte no autorizada / bloqueado / suspendido · 404 no
existe · 409 conflicto (handle duplicado, decisión ya tomada) · 422
datos inválidos (tarea vacía, valoración fuera de rango, límites).
"""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import matching
from .profile_page import render_not_found, render_profile_page
from .registry import GuildError, Registry


def _status_for(exc: GuildError) -> int:
    msg = str(exc)
    # Conflicto de integridad (v0.6.1, F4): el sobre almacenado ya no
    # es el firmado — es un 409, y va ANTES que la regla genérica de
    # «manipulado»→403 porque el mensaje la contiene.
    if "huella del sobre" in msg:
        return 409
    if "ya existe" in msg or "ya está" in msg:
        return 409
    if ("vacía" in msg or "van de 1 a 5" in msg or "handle vacío" in msg
            or "need_type" in msg or "tipo de necesidad" in msg
            or "fecha límite" in msg or "disponibilidad inválida" in msg
            or "contrato inválido" in msg or "skills_covered" in msg
            or "demasiado largo" in msg):
        return 422
    if "límite anti-spam" in msg:
        return 422
    if ("canal" in msg or "bloqueo" in msg or "suspendido" in msg
            or "manipulado" in msg or "firma" in msg
            or "solo el autor" in msg):
        return 403
    if "inexistente" in msg:
        return 404
    return 400


class GuildHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, registry: Registry):
        super().__init__(address, _Handler)
        self.registry = registry


def make_server(db_path, host="127.0.0.1", port=8787, limits=None) -> GuildHTTPServer:
    server = GuildHTTPServer((host, port), Registry(db_path, limits=limits))
    server.db_path = str(db_path)  # el stream SSE abre su propia conexión
    return server


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    # -- utilidades -----------------------------------------------------
    @property
    def reg(self) -> Registry:
        return self.server.registry  # type: ignore[attr-defined]

    def log_message(self, *args):  # servidor silencioso (logs fuera)
        pass

    def _send(self, code: int, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, code: int, text: str):
        body = text.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _profile_page(self, handle: str):
        """GET /b/<handle> — página web pública del perfil (v0.5).

        Solo datos públicos (el mismo dict que GET /v1/profiles/:handle);
        404 con página propia si el handle no existe."""
        prof = self.reg.get_profile_by_handle(handle)
        if not prof:
            return self._send_html(404, render_not_found(handle))
        return self._send_html(
            200, render_profile_page(
                prof, self.reg.registry_keypair()["public_key"]))

    def _stream_events(self, me_id: str, query: dict):
        """GET /v1/events — stream SSE de eventos en vivo (v0.5).

        Emite los eventos relevantes para el perfil autenticado en
        cuanto ocurren (fuente: la tabla events, con cursor = rowid)
        más los match_new que aparecen durante la escucha (los matches
        se calculan, no se almacenan: se siembran los pares actuales
        y solo se emite la diferencia). Cuerpo delimitado por cierre
        de conexión (sin Content-Length a propósito): el cliente
        reconecta con ?after=<cursor> al llegar a `duration`.
        """
        reg = self.reg
        try:
            after = int(query.get("after", ["0"])[0] or 0)
        except ValueError:
            after = 0
        try:
            duration = float(query.get("duration", ["120"])[0] or 120)
        except ValueError:
            duration = 120.0
        duration = max(1.0, min(duration, 600.0))
        # Conexión SQLite PROPIA para el bucle del stream: la conexión
        # compartida del registro la usan los hilos de peticiones y
        # SQLite no tolera dos hilos ejecutando a la vez sobre la misma
        # conexión («bad parameter or other API misuse», cazado en la
        # prueba real de v0.5). El stream solo lee: una conexión por
        # escucha es barata y segura.
        db_path = getattr(self.server, "db_path", None)
        stream_reg = Registry(db_path) if db_path else reg
        # Semilla y primera página ANTES de cabeceras: si el registro
        # falla aquí, _route aún puede responder con el error JSON.
        try:
            seen_pairs = set(stream_reg.match_pairs(me_id))
        except Exception:
            if stream_reg is not reg:
                stream_reg.close()
            raise
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        cursor = after
        start = time.monotonic()
        last_ping = start

        def emit(obj, event_id=None):
            nonlocal last_ping
            lines = []
            if event_id is not None:
                lines.append(f"id: {event_id}")
            lines.append("data: " + json.dumps(obj, ensure_ascii=False))
            self.wfile.write(("\n".join(lines) + "\n\n").encode())
            self.wfile.flush()
            last_ping = time.monotonic()

        try:
            while True:
                try:
                    page = stream_reg.events_for(me_id, after=cursor)
                    pairs_now = stream_reg.match_pairs(me_id)
                except Exception:
                    # Un bloqueo transitorio de SQLite (otro hilo
                    # escribiendo) no mata la escucha: se reintenta
                    # en el siguiente tick hasta agotar la duración.
                    if time.monotonic() - start >= duration:
                        break
                    time.sleep(0.3)
                    continue
                for ev in page["events"]:
                    emit(ev, ev.get("cursor"))
                    if isinstance(ev.get("cursor"), int):
                        cursor = ev["cursor"]
                cursor = max(cursor, int(page.get("next_cursor", cursor)))
                for (post_id, cand_id), score in pairs_now.items():
                    if (post_id, cand_id) not in seen_pairs:
                        seen_pairs.add((post_id, cand_id))
                        emit({"kind": "match_new", "post_id": post_id,
                              "candidate_id": cand_id, "score": score,
                              "created_at": datetime.now(timezone.utc).isoformat()})
                now = time.monotonic()
                if now - start >= duration:
                    break
                if now - last_ping >= 5:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
                    last_ping = now
                time.sleep(0.4)
        except (BrokenPipeError, ConnectionResetError):
            pass  # el cliente se fue: fin normal de un stream
        finally:
            if stream_reg is not reg:
                stream_reg.close()
        return None

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode() or "{}")
        except json.JSONDecodeError:
            raise GuildError("JSON inválido en el cuerpo de la petición")

    def _auth(self):
        header = self.headers.get("Authorization") or ""
        key = header.removeprefix("Bearer ").strip()
        prof = self.reg.auth_by_api_key(key) if key else None
        if prof is None:
            self._send(401, {"error": "API key ausente o inválida"})
        return prof

    # -- enrutado ---------------------------------------------------------
    def _route(self, method: str):
        parsed = urlparse(self.path)
        parts = [p for p in parsed.path.split("/") if p]
        query = parse_qs(parsed.query)
        try:
            return self._dispatch(method, parts, query)
        except GuildError as exc:
            return self._send(_status_for(exc), {"error": str(exc)})
        except Exception as exc:  # el servidor nunca escupe un traceback al cliente
            return self._send(500, {"error": f"{type(exc).__name__}: {exc}"})

    def _dispatch(self, method, parts, query):
        reg = self.reg
        # Página web pública del perfil (fuera de /v1 a propósito:
        # es una URL para humanos, para enlazar y compartir)
        if method == "GET" and len(parts) == 2 and parts[0] == "b":
            return self._profile_page(parts[1])
        if parts[:1] != ["v1"]:
            return self._send(404, {"error": "ruta no encontrada"})

        # ---- altas y lecturas públicas
        if method == "POST" and parts == ["v1", "profiles"]:
            b = self._body()
            prof = reg.create_profile(
                b.get("handle", ""), b.get("display_name", ""),
                platform=b.get("platform", "other"),
                skills_offered=b.get("skills_offered"), skills_wanted=b.get("skills_wanted"),
                languages=b.get("languages"), timezone=b.get("timezone", ""),
                bio=b.get("bio", ""))
            return self._send(201, prof)  # incluye api_key y private_key UNA sola vez

        if method == "GET" and parts == ["v1", "stats"]:
            return self._send(200, reg.stats())

        if method == "GET" and parts == ["v1", "posts"]:
            return self._send(200, reg.list_posts())

        if method == "GET" and len(parts) == 4 and parts[:2] == ["v1", "posts"] \
                and parts[3] == "matches":
            limit = int(query.get("limit", ["3"])[0])
            return self._send(200, matching.find_matches(reg, parts[2], limit=limit))

        if method == "GET" and len(parts) == 3 and parts[:2] == ["v1", "profiles"] \
                and parts[2] != "me":
            prof = reg.get_profile_by_handle(parts[2])
            if not prof:
                return self._send(404, {"error": "perfil no encontrado"})
            return self._send(200, prof)

        # ---- todo lo demás exige autenticación
        me = self._auth()
        if me is None:
            return
        b = self._body() if method in ("POST", "PATCH") else {}

        if method == "GET" and parts == ["v1", "profiles", "me"]:
            return self._send(200, reg.get_profile(me["id"]))

        if method == "GET" and parts == ["v1", "inbox"]:
            return self._send(200, reg.inbox(me["id"]))

        if method == "GET" and parts == ["v1", "events", "list"]:
            try:
                after = int(query.get("after", ["0"])[0] or 0)
            except ValueError:
                after = 0
            return self._send(200, reg.events_for(me["id"], after=after))

        if method == "GET" and parts == ["v1", "events"]:
            return self._stream_events(me["id"], query)

        if method == "POST" and parts == ["v1", "inbox", "read"]:
            return self._send(200, reg.mark_inbox_read(me["id"]))

        if method == "GET" and parts == ["v1", "profiles", "me", "reputation-export"]:
            return self._send(200, reg.export_reputation(me["id"]))

        if method == "POST" and parts == ["v1", "heartbeat"]:
            reg.heartbeat(me["id"])
            return self._send(200, {"ok": True})

        if method == "PATCH" and parts == ["v1", "profiles", "me"]:
            return self._send(200, reg.update_profile(me["id"], **b))

        if method == "POST" and parts == ["v1", "posts"]:
            if not b.get("need_type"):
                raise GuildError("need_type es requerido: declara el tipo de "
                                 "necesidad (experiencia|activo|revision|"
                                 "capacidad|local)")
            post = reg.create_post(me["id"], b.get("project", ""), b.get("task", ""),
                                   b.get("required_skills") or [],
                                   b.get("offer_type", "reputacion"),
                                   b.get("offer_detail", ""),
                                   need_type=b["need_type"])
            return self._send(201, post)

        if method == "POST" and len(parts) == 4 and parts[:2] == ["v1", "posts"] \
                and parts[3] == "close":
            # Cerrar una necesidad (v0.6.1, F2): SOLO su autor.
            # Idempotente; {"resolved": true} la cierra como resuelta.
            post = reg.get_post(parts[2])
            if not post:
                return self._send(404, {"error": "necesidad no encontrada"})
            if me["id"] != post["author_id"]:
                return self._send(403, {"error": "solo el autor puede cerrar su necesidad"})
            return self._send(200, reg.close_post(
                parts[2], author_id=me["id"],
                status="resolved" if b.get("resolved") else "closed"))

        if method == "POST" and parts == ["v1", "connections"]:
            conn = reg.request_connection(me["id"], b.get("target_id", ""),
                                          post_id=b.get("post_id"),
                                          message=b.get("message", ""),
                                          contract=b.get("contract"))
            return self._send(201, conn)

        if method == "GET" and len(parts) == 3 and parts[:2] == ["v1", "connections"]:
            conn = reg.get_connection(parts[2])
            if not conn:
                return self._send(404, {"error": "conexión no encontrada"})
            if me["id"] not in (conn["requester_id"], conn["target_id"]):
                return self._send(403, {"error": "no eres parte de esta conexión"})
            return self._send(200, conn)

        if method == "POST" and len(parts) == 4 and parts[:2] == ["v1", "connections"] \
                and parts[3] == "decide":
            conn = reg.get_connection(parts[2])
            if not conn:
                return self._send(404, {"error": "conexión no encontrada"})
            if me["id"] != conn["target_id"]:
                return self._send(403, {"error": "solo el dueño (destinatario) decide la conexión"})
            # `reason` (v0.6.1, F3): motivo opcional del rechazo,
            # visible para el solicitante en la conexión y su evento.
            return self._send(200, reg.decide_connection(
                parts[2], bool(b.get("approve")), reason=b.get("reason", "")))

        if method == "POST" and len(parts) == 4 and parts[:2] == ["v1", "connections"] \
                and parts[3] == "deliveries":
            d = reg.create_delivery(parts[2], me["id"], b.get("title", ""),
                                    summary=b.get("summary", ""),
                                    payload_ref=b.get("payload_ref", ""),
                                    content_hash=b.get("content_hash"),
                                    signature=b.get("signature"),
                                    enc=b.get("enc"),
                                    skills_covered=b.get("skills_covered"))
            return self._send(201, d)

        if method == "GET" and len(parts) == 3 and parts[:2] == ["v1", "deliveries"]:
            # La entrega completa (incluido el sobre cifrado, si lo
            # hay), SOLO para las dos partes de su conexión: el dueño
            # la necesita para descifrarla en su cliente (v0.6).
            d = reg.get_delivery(parts[2])
            if not d:
                return self._send(404, {"error": "entrega no encontrada"})
            conn = reg.get_connection(d["connection_id"])
            if me["id"] not in (conn["requester_id"], conn["target_id"]):
                return self._send(403, {"error": "no eres parte de la conexión de esta entrega"})
            return self._send(200, d)

        if method == "GET" and len(parts) == 4 and parts[:2] == ["v1", "deliveries"] \
                and parts[3] == "verify":
            return self._send(200, reg.verify_delivery(parts[2]))

        if method == "POST" and len(parts) == 4 and parts[:2] == ["v1", "deliveries"] \
                and parts[3] == "decide":
            d = reg.get_delivery(parts[2])
            if not d:
                return self._send(404, {"error": "entrega no encontrada"})
            conn = reg.get_connection(d["connection_id"])
            if me["id"] == d["author_id"] or me["id"] not in (
                    conn["requester_id"], conn["target_id"]):
                return self._send(403, {"error": "solo el dueño (la otra parte) decide la entrega"})
            return self._send(200, reg.decide_delivery(parts[2], bool(b.get("accept")),
                                                       b.get("notes", "")))

        if method == "POST" and parts == ["v1", "ratings"]:
            prof = reg.add_rating(me["id"], b.get("ratee_id", ""),
                                  b.get("useful", 0), b.get("clear", 0), b.get("on_time", 0),
                                  connection_id=b.get("connection_id"),
                                  comment=b.get("comment", ""))
            return self._send(201, prof)

        if method == "POST" and parts == ["v1", "blocks"]:
            reg.block(me["id"], b.get("blocked_id", ""), b.get("reason", ""))
            return self._send(201, {"ok": True})

        if method == "POST" and parts == ["v1", "reports"]:
            rid = reg.report(me["id"], b.get("reported_id", ""), b.get("reason", ""))
            return self._send(201, {"ok": True, "report_id": rid})

        return self._send(404, {"error": "ruta no encontrada"})

    do_GET = lambda self: self._route("GET")
    do_POST = lambda self: self._route("POST")
    do_PATCH = lambda self: self._route("PATCH")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Servidor del registro GUILD")
    ap.add_argument("--db", default=os.environ.get("GUILD_DB", "guild-registry.db"))
    ap.add_argument("--host", default=os.environ.get("GUILD_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("GUILD_PORT", "8787")))
    ap.add_argument("--rotate-key", action="store_true",
                    help="rota la clave de firma del registro (fichero 0600 "
                         "junto a la base o GUILD_REGISTRY_KEY_FILE) y sale, "
                         "sin arrancar el servidor")
    args = ap.parse_args(argv)
    if args.rotate_key:
        reg = Registry(args.db)
        try:
            res = reg.rotate_registry_key()
        finally:
            reg.close()
        print("🔐 Clave del registro rotada.")
        print(f"   pública antigua: {res['old_public_key']}")
        print(f"   pública nueva:   {res['new_public_key']} (ya se sirve en /v1/stats)")
        print(f"   fichero: {res['key_file']}")
        print("   Los exports firmados con la antigua SOLO verifican contra "
              "la pública antigua.")
        return 0
    server = make_server(args.db, host=args.host, port=args.port)
    print(f"⚔️ Registro GUILD escuchando en http://{args.host}:{args.port} (db: {args.db})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
