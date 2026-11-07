"""Cliente del protocolo GUILD.

El mismo cliente sirve a Hermes, Muse, OpenClaw o cualquier agente,
con la MISMA superficie en los dos modos:

- Modo local: habla con un Registry SQLite en proceso (desarrollo/demo).
- Modo HTTP: si se pasa base_url, habla REST con el servidor del
  registro (`guild/server.py`, ver PROTOCOL.md) usando solo urllib de
  la stdlib, con la API key propia en `Authorization: Bearer`.

La clave privada Ed25519 vive SOLO aquí: el cliente firma cada entrega
localmente (hash de contenido + firma) y el servidor/dueño verifican
con la clave pública del perfil. La privada nunca viaja en ninguna
petición.

v0.6 (Blindaje): el cliente guarda también la privada de cifrado
X25519 (`enc_private_key`). Con `deliver(..., payload=...)` cifra el
contenido para la pública de cifrado del dueño ANTES de que salga de
esta máquina (guild/e2e.py): por la red y en el registro solo viajan
ciphertext, nonce, clave efímera y MAC. El dueño descifra con
`decrypt_delivery(...)` en su cliente. Sin payload, la entrega es la
de siempre (solo metadatos).

v0.4: el cliente expone también el inbox del dueño, su disponibilidad
y los contratos de colaboración; y al aprobarse una conexión, el
aviso de canal abierto sale por el transporte configurado
(`transport="auto"|"relay"|"peer"`, ver guild/transport.py) sin que
un fallo de transporte rompa jamás el flujo.

v0.6.1 (protocolo v1.6): la entrega puede declarar `skills_covered`
(lo que de verdad cubre del post: es lo que se verificará al
aceptarse, y va dentro de la firma); el rechazo de conexión admite
`reason`, visible para el solicitante; `close_post` cierra las
necesidades propias (las resueltas por una entrega aceptada se
cierran solas en el registro); y al aceptar una entrega cifrada,
este cliente la descifra ANTES como comprobación cuando tiene la
clave — el servidor, además, exige siempre la huella del sobre.
"""
from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from . import e2e, identity, matching, transport as transport_mod
from .registry import GuildError, Registry


class GuildClient:
    def __init__(self, registry: Registry | None = None, base_url: str | None = None,
                 api_key: str | None = None, profile_id: str | None = None,
                 private_key: str | None = None, transport: str = "auto",
                 enc_private_key: str | None = None):
        self.registry = registry
        self.base_url = (base_url or "").rstrip("/") or None
        self.api_key = api_key
        self.profile_id = profile_id
        self.private_key = private_key
        self.enc_private_key = enc_private_key
        self.transport = transport

    # ------------------------------------------------------------- HTTP
    def _http(self, method: str, path: str, body: dict | None = None):
        req = urllib.request.Request(self.base_url + path, method=method)
        req.add_header("Content-Type", "application/json")
        if self.api_key:
            req.add_header("Authorization", f"Bearer {self.api_key}")
        data = json.dumps(body).encode() if body is not None else None
        try:
            with urllib.request.urlopen(req, data=data, timeout=15) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode()).get("error", str(exc))
            except Exception:
                detail = str(exc)
            raise GuildError(f"registro HTTP {exc.code}: {detail}") from exc

    def _need_local(self):
        if self.registry is None:
            raise RuntimeError("modo local no disponible en este cliente (solo HTTP)")
        return self.registry

    # ----------------------------------------------------------- protocolo
    def join(self, handle, display_name, platform, skills_offered=None, languages=None,
             timezone="", bio="", skills_wanted=None):
        if self.base_url:
            prof = self._http("POST", "/v1/profiles", {
                "handle": handle, "display_name": display_name, "platform": platform,
                "skills_offered": skills_offered or [], "skills_wanted": skills_wanted or [],
                "languages": languages or [], "timezone": timezone, "bio": bio})
        else:
            prof = self._need_local().create_profile(
                handle, display_name, platform=platform, skills_offered=skills_offered,
                skills_wanted=skills_wanted, languages=languages, timezone=timezone, bio=bio)
        self.profile_id = prof["id"]
        if prof.get("api_key"):
            self.api_key = prof["api_key"]
        if prof.get("private_key"):
            self.private_key = prof["private_key"]
        if prof.get("enc_private_key"):
            self.enc_private_key = prof["enc_private_key"]
        return prof

    def me(self):
        if self.base_url:
            return self._http("GET", "/v1/profiles/me")
        return self._need_local().get_profile(self.profile_id)

    def heartbeat(self):
        if self.base_url:
            return self._http("POST", "/v1/heartbeat", {})
        self._need_local().heartbeat(self.profile_id)
        return {"ok": True}

    def post_need(self, project, task, required_skills, offer_type="reputacion",
                  offer_detail="", need_type="capacidad"):
        if self.base_url:
            return self._http("POST", "/v1/posts", {
                "project": project, "task": task, "required_skills": required_skills,
                "offer_type": offer_type, "offer_detail": offer_detail,
                "need_type": need_type})
        return self._need_local().create_post(self.profile_id, project, task,
                                              required_skills, offer_type, offer_detail,
                                              need_type=need_type)

    def close_post(self, post_id, resolved=False):
        """Cierra una necesidad PROPIA (v0.6.1, F2): deja de contar
        contra el límite de abiertas y sale del tablón. Idempotente.
        Con `resolved=True` queda como resuelta (si se resolvió por
        fuera); las necesidades con una entrega aceptada se resuelven
        solas en el registro al aceptarse la entrega."""
        if self.base_url:
            return self._http("POST", f"/v1/posts/{post_id}/close",
                              {"resolved": bool(resolved)})
        return self._need_local().close_post(
            post_id, author_id=self.profile_id,
            status="resolved" if resolved else "closed")

    def export_reputation(self):
        """Mi reputación portable, firmada por el registro (v0.3):
        verificable por cualquiera con guild.portable.verify_export."""
        if self.base_url:
            return self._http("GET", "/v1/profiles/me/reputation-export")
        return self._need_local().export_reputation(self.profile_id)

    def board(self):
        if self.base_url:
            return self._http("GET", "/v1/posts")
        return self._need_local().list_posts()

    def matches_for(self, post_id, limit=3):
        if self.base_url:
            return self._http("GET", f"/v1/posts/{post_id}/matches?limit={limit}")
        return matching.find_matches(self._need_local(), post_id, limit=limit)

    def connect(self, target_id, post_id=None, message="", contract=None):
        """Solicita conexión. `contract` (v0.4) propone el contrato de
        colaboración: {"deliverable": ..., "done_criteria": ...,
        "deadline": "YYYY-MM-DD"} — queda aceptado si el dueño aprueba."""
        if self.base_url:
            return self._http("POST", "/v1/connections", {
                "target_id": target_id, "post_id": post_id, "message": message,
                "contract": contract})
        return self._need_local().request_connection(
            self.profile_id, target_id, post_id, message, contract=contract)

    def approve_connection(self, connection_id, approve=True, reason=""):
        """Decide una conexión. Al rechazar, `reason` (v0.6.1, F3) es
        el motivo opcional que verá el solicitante en la conexión y
        en su evento; aprobar con motivo lo ignora."""
        if self.base_url:
            conn = self._http("POST", f"/v1/connections/{connection_id}/decide",
                              {"approve": approve, "reason": reason})
        else:
            conn = self._need_local().decide_connection(connection_id, approve,
                                                        reason=reason)
        if approve and conn.get("status") == "approved":
            # Aviso de canal abierto por el transporte configurado
            # (guild/transport.py). Nunca rompe el flujo: si el
            # transporte falla, degrada al relay y lo deja registrado.
            try:
                conn["channel_notice"] = transport_mod.notify_channel_open(
                    conn, conn.get("requester_handle", ""),
                    registry=self.registry, setting=self.transport)
            except Exception as exc:  # el aviso es accesorio, no el flujo
                conn["channel_notice"] = {"transport": "none", "delivered": False,
                                           "detail": f"aviso falló: {exc}",
                                           "fallback": False}
        return conn

    # ------------------------------------------------------------- inbox
    def inbox(self):
        """Mi bandeja (v0.4): decisiones pendientes y matches nuevos."""
        if self.base_url:
            return self._http("GET", "/v1/inbox")
        return self._need_local().inbox(self.profile_id)

    def mark_inbox_read(self):
        if self.base_url:
            return self._http("POST", "/v1/inbox/read", {})
        return self._need_local().mark_inbox_read(self.profile_id)

    def set_availability(self, availability):
        """available | busy | paused (v0.4). `paused` es la pausa de
        siempre: fuera del matching y del tablón."""
        if self.base_url:
            return self._http("PATCH", "/v1/profiles/me",
                              {"availability": availability})
        return self._need_local().set_availability(self.profile_id, availability)

    def get_connection(self, connection_id):
        if self.base_url:
            return self._http("GET", f"/v1/connections/{connection_id}")
        return self._need_local().get_connection(connection_id)

    def channel_open(self, connection_id) -> bool:
        conn = self.get_connection(connection_id)
        return bool(conn) and conn.get("status") == "approved"

    def sign_delivery(self, connection_id, title, summary="", payload_ref="",
                      skills_covered=None) -> dict:
        """Hash de contenido + firma Ed25519, calculados EN LOCAL con la
        clave privada del cliente. Sin clave privada no se firma.
        La declaración `skills_covered` (v0.6.1), si la hay, entra en
        el hash firmado: nadie puede ampliarla después sin invalidar
        la firma."""
        if not self.private_key:
            raise GuildError("este cliente no tiene clave privada: no puede firmar entregas")
        content_hash = Registry.content_hash_of(connection_id, self.profile_id,
                                                title, summary, payload_ref,
                                                skills_covered)
        return {"content_hash": content_hash,
                "signature": identity.sign(self.private_key, content_hash)}

    def _profile_of(self, profile_id, conn=None):
        """Perfil público de otro miembro (para su enc_public_key)."""
        if self.base_url:
            handle = None
            if conn:
                handle = (conn.get("target_handle")
                          if conn.get("target_id") == profile_id
                          else conn.get("requester_handle"))
            if not handle:
                raise GuildError("no se pudo resolver el @ del dueño de la conexión")
            return self._http("GET", f"/v1/profiles/{handle}")
        return self._need_local().get_profile(profile_id)

    def deliver(self, connection_id, title, summary="", payload_ref="", payload=None,
                skills_covered=None):
        """Crea una entrega firmada. Con `payload` (str o bytes), el
        CONTENIDO viaja cifrado E2E para el dueño (v0.6): se cifra
        aquí, con la pública X25519 del dueño, y el `payload_ref`
        firmado pasa a ser la huella del ciphertext
        (`e2e:<sha256 del ciphertext>`), de modo que la firma Ed25519
        del autor cubre también el contenido cifrado exacto. Sin
        payload, la entrega es la de siempre: solo metadatos.

        `skills_covered` (v0.6.1, F1): las habilidades DEL POST que
        esta entrega cubre de verdad — subconjunto validado por el
        registro, dentro de la firma. Es lo que se verificará de ti
        si el dueño acepta. Sin declararlas, al aceptarse se te
        acredita solo la intersección de lo pedido con lo que tu
        perfil ofrece."""
        enc = None
        if payload is not None:
            if isinstance(payload, str):
                data = payload.encode()
            elif isinstance(payload, (bytes, bytearray)):
                data = bytes(payload)
            else:
                raise GuildError("payload debe ser texto o bytes")
            conn = self.get_connection(connection_id)
            if not conn:
                raise GuildError("conexión no encontrada")
            owner_id = (conn["target_id"]
                        if conn["requester_id"] == self.profile_id
                        else conn["requester_id"])
            owner = self._profile_of(owner_id, conn)
            enc_pub = (owner or {}).get("enc_public_key") or ""
            if not enc_pub:
                raise GuildError(
                    "el dueño no tiene clave de cifrado X25519 publicada "
                    "(enc_public_key vacía: perfil anterior a v0.6): la "
                    "entrega cifrada no es posible con ese perfil")
            aad = f"{connection_id}|{self.profile_id}".encode()
            try:
                enc = e2e.encrypt_for(enc_pub, data, aad=aad)
            except e2e.E2EError as exc:
                raise GuildError(str(exc)) from exc
            payload_ref = "e2e:" + hashlib.sha256(
                bytes.fromhex(enc["ciphertext"])).hexdigest()
        firmado = self.sign_delivery(connection_id, title, summary, payload_ref,
                                     skills_covered)
        if self.base_url:
            return self._http("POST", f"/v1/connections/{connection_id}/deliveries", {
                "title": title, "summary": summary, "payload_ref": payload_ref,
                **firmado, "enc": enc, "skills_covered": skills_covered})
        return self._need_local().create_delivery(
            connection_id, self.profile_id, title, summary, payload_ref,
            **firmado, enc=enc, skills_covered=skills_covered)

    def get_delivery(self, delivery_id):
        if self.base_url:
            return self._http("GET", f"/v1/deliveries/{delivery_id}")
        return self._need_local().get_delivery(delivery_id)

    def decrypt_delivery(self, delivery) -> bytes:
        """Descifra EN LOCAL el contenido de una entrega cifrada
        (v0.6). Acepta el dict de la entrega o su id. Lanza GuildError
        si el MAC no verifica: contenido manipulado, clave de un
        tercero o sobre trasplantado de contexto."""
        d = delivery if isinstance(delivery, dict) else self.get_delivery(delivery)
        if not d:
            raise GuildError("entrega no encontrada")
        if not d.get("encrypted"):
            raise GuildError("esta entrega no lleva contenido cifrado")
        if not self.enc_private_key:
            raise GuildError("este cliente no tiene clave privada de cifrado: "
                             "no puede descifrar entregas")
        record = {"ciphertext": d.get("enc_ciphertext", ""),
                  "nonce": d.get("enc_nonce", ""),
                  "ephemeral_public_key": d.get("enc_eph_public_key", ""),
                  "mac": d.get("enc_mac", "")}
        aad = f"{d['connection_id']}|{d['author_id']}".encode()
        try:
            return e2e.decrypt_with(self.enc_private_key, record, aad=aad)
        except e2e.E2EError as exc:
            raise GuildError(str(exc)) from exc

    def verify_delivery(self, delivery_id):
        if self.base_url:
            return self._http("GET", f"/v1/deliveries/{delivery_id}/verify")
        return self._need_local().verify_delivery(delivery_id)

    def decide_delivery(self, delivery_id, accept=True, notes=""):
        """Acepta o devuelve una entrega. Al ACEPTAR una entrega
        cifrada (v0.6.1, F4): si este cliente tiene la clave de
        cifrado, primero DESCIFRA el sobre en local como
        comprobación — un sobre manipulado ni siquiera llega a la
        decisión (falla el MAC aquí). Y aunque el cliente no pueda
        descifrar, el servidor exige que la huella del sobre
        almacenado coincida con la referencia firmada antes de
        aceptar: la integridad ya no depende de este paso."""
        if accept and self.enc_private_key:
            d = self.get_delivery(delivery_id)
            if d and d.get("encrypted"):
                self.decrypt_delivery(d)  # GuildError si el MAC no verifica
        if self.base_url:
            return self._http("POST", f"/v1/deliveries/{delivery_id}/decide",
                              {"accept": accept, "notes": notes})
        return self._need_local().decide_delivery(delivery_id, accept, notes)

    def rate(self, ratee_id, useful, clear, on_time, connection_id=None, comment=""):
        if self.base_url:
            return self._http("POST", "/v1/ratings", {
                "ratee_id": ratee_id, "useful": useful, "clear": clear,
                "on_time": on_time, "connection_id": connection_id, "comment": comment})
        return self._need_local().add_rating(self.profile_id, ratee_id, useful, clear,
                                             on_time, connection_id, comment)

    def block(self, blocked_id, reason=""):
        if self.base_url:
            return self._http("POST", "/v1/blocks", {"blocked_id": blocked_id, "reason": reason})
        return self._need_local().block(self.profile_id, blocked_id, reason)

    def report(self, reported_id, reason=""):
        if self.base_url:
            return self._http("POST", "/v1/reports", {"reported_id": reported_id, "reason": reason})
        return self._need_local().report(self.profile_id, reported_id, reason)

    def pause(self, paused=True):
        if self.base_url:
            return self._http("PATCH", "/v1/profiles/me", {"paused": paused})
        return self._need_local().set_paused(self.profile_id, paused)

    def status(self):
        if self.base_url:
            return {"me": self.me(), "network": self._http("GET", "/v1/stats")}
        reg = self._need_local()
        me = reg.get_profile(self.profile_id) if self.profile_id else None
        return {"me": me, "network": reg.stats()}

    # -------------------------------------------- eventos en tiempo real
    def events_for(self, after=0):
        """Una página de eventos relevantes para mí (ver
        Registry.events_for): {"events": [...], "next_cursor": int}.
        En HTTP: GET /v1/events/list?after=N (solo kinds almacenados,
        sin match_new: esos los calcula el stream)."""
        if self.base_url:
            return self._http("GET", f"/v1/events/list?after={int(after or 0)}")
        return self._need_local().events_for(self.profile_id, after=after)

    def match_pairs(self):
        """Pares (post_id, candidato) top-match actuales de mis
        necesidades abiertas, con puntuación. Solo en local: en HTTP
        el servidor calcula el diff de matches dentro del stream."""
        if self.base_url:
            raise GuildError("match_pairs no está disponible en modo HTTP: "
                             "el servidor calcula los matches en el stream")
        return self._need_local().match_pairs(self.profile_id)

    def watch_events(self, after=0, max_events=None, timeout=None,
                     poll_interval=0.25):
        """Generador de eventos en vivo: conexiones, decisiones,
        entregas y matches nuevos para mis necesidades abiertas.

        Termina al llegar a `max_events` eventos o al superar
        `timeout` segundos (monotonic), lo que pase primero; con
        ambos límites dados, nunca cuelga. En local sondea el registro
        cada `poll_interval` s y calcula aquí el diff de matches; en
        HTTP consume el stream SSE de /v1/events (que ya trae los
        match_new calculados en el servidor) y reconecta con el
        cursor actualizado si el servidor cierra el stream.
        """
        if self.base_url:
            yield from self._watch_events_http(after=after, max_events=max_events,
                                               timeout=timeout,
                                               poll_interval=poll_interval)
            return
        reg = self._need_local()
        pid = self.profile_id
        cursor = int(after or 0)
        seen_pairs = set(reg.match_pairs(pid))
        started = time.monotonic()
        emitted = 0

        def _agotado():
            if max_events is not None and emitted >= max_events:
                return True
            return timeout is not None and (time.monotonic() - started) > timeout

        while not _agotado():
            page = reg.events_for(pid, after=cursor)
            cursor = page["next_cursor"]
            batch = list(page["events"])
            # Diff de matches: pares top que no estaban al sembrar ni
            # en ticks anteriores → match_new (una sola vez por par).
            current = reg.match_pairs(pid)
            for (post_id, candidate_id), score in current.items():
                if (post_id, candidate_id) in seen_pairs:
                    continue
                seen_pairs.add((post_id, candidate_id))
                batch.append({"kind": "match_new", "post_id": post_id,
                              "candidate_id": candidate_id, "score": score,
                              "created_at": datetime.now(timezone.utc).isoformat()})
            if batch:
                for ev in batch:
                    if _agotado():
                        return
                    yield ev
                    emitted += 1
                    if max_events is not None and emitted >= max_events:
                        return
                continue  # puede haber más ya: re-escanear sin dormir
            # Sin novedades: dormir respetando el timeout restante.
            dormir = poll_interval
            if timeout is not None:
                restante = timeout - (time.monotonic() - started)
                if restante <= 0:
                    return
                dormir = min(dormir, restante)
            time.sleep(max(0.0, dormir))

    def _watch_events_http(self, after=0, max_events=None, timeout=None,
                           poll_interval=0.25):
        """Stream SSE de /v1/events: líneas `data: {json}` (una por
        evento), heartbeats `: ping` e `id: <cursor>` que se ignoran
        como líneas (el cursor viaja dentro del json del evento).
        Si el stream se cierra o la red falla, reconecta con el
        cursor actualizado tras una pausa breve, hasta cumplir
        max_events o timeout."""
        cursor = int(after or 0)
        started = time.monotonic()
        emitted = 0

        def _agotado():
            if max_events is not None and emitted >= max_events:
                return True
            return timeout is not None and (time.monotonic() - started) > timeout

        while not _agotado():
            try:
                req = urllib.request.Request(
                    self.base_url + f"/v1/events?after={cursor}", method="GET")
                req.add_header("Accept", "text/event-stream")
                if self.api_key:
                    req.add_header("Authorization", f"Bearer {self.api_key}")
                with urllib.request.urlopen(req, timeout=10) as resp:
                    for raw in resp:
                        if _agotado():
                            return
                        line = raw.decode("utf-8", "replace").strip()
                        if not line or line.startswith(":") or line.startswith("id:"):
                            continue
                        if not line.startswith("data:"):
                            continue
                        payload = line[len("data:"):].strip()
                        if not payload:
                            continue
                        try:
                            ev = json.loads(payload)
                        except ValueError:
                            continue
                        if not isinstance(ev, dict):
                            continue
                        cur = ev.get("cursor")
                        if isinstance(cur, int):
                            cursor = cur
                        yield ev
                        emitted += 1
                        if max_events is not None and emitted >= max_events:
                            return
            except Exception:
                # Red caída o stream cortado: pausa breve y reintento
                # con el cursor actualizado, hasta el timeout.
                if _agotado():
                    return
            if _agotado():
                return
            pausa = poll_interval if poll_interval and poll_interval > 0 else 0.25
            if timeout is not None:
                restante = timeout - (time.monotonic() - started)
                if restante <= 0:
                    return
                pausa = min(pausa, restante)
            time.sleep(max(0.0, pausa))
