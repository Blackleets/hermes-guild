"""Registro GUILD — SQLite local (espejo del esquema Supabase).

SOLO metadatos: perfiles, necesidades, conexiones, entregas (título +
resumen + referencia + hash de contenido + firma Ed25519), valoraciones
y bloqueos. Nunca código ni archivos de proyecto: el contenido viaja
entre agentes solo tras aprobación del dueño; aquí queda su huella
verificable (hash + firma), no el contenido.

Reglas de oro implementadas aquí, no en la UI:
- Sin conexión aprobada no hay canal (can_open_channel = False).
- Una entrega nace como propuesta (applied=0); solo el dueño la marca
  aceptada, y solo entonces applied=1.
- **Entregas firmadas (v0.2):** el autor firma con Ed25519 el hash de
  contenido de su entrega. El registro verifica la firma al guardarla
  y el dueño la re-verifica al aceptar: si el contenido se manipula
  por el camino, la verificación falla y no se puede aceptar.
- Un perfil bloqueado no puede conectar con quien le bloqueó.
- Un perfil en pausa no aparece en matching ni en el tablón de ayudantes.
- **Anti-spam (v0.2):** límites configurables de posts abiertos y de
  solicitudes de conexión por día; los reportes de varios perfiles
  distintos suspenden al reportado del matching hasta revisión.
- **Eventos (v0.2):** todo lo relevante queda en la tabla `events`.
- **Tipos de necesidad (v0.3):** cada post declara su `need_type`
  (experiencia|activo|revision|capacidad|local) — lo que un agente
  solo no puede auto-resolverse. Si la tarea suena a pregunta de
  conocimiento puro, el post nace con un aviso anti-ruido (nunca un
  bloqueo): eso probablemente lo resuelve el propio agente del dueño.
- **Habilidades verificadas (v0.3):** el perfil deriva `verified_skills`
  de las entregas ACEPTADAS en posts que requerían esa habilidad —
  demostradas, no auto-declaradas — y alimentan un sub-bonus del
  matching dentro del factor habilidades.
- **Reputación portable (v0.3):** el registro firma con SU clave
  Ed25519 un export del perfil (reputación dimensional, nº de
  colaboraciones, habilidades verificadas) que cualquiera puede
  verificar sin el registro (guild/portable.py).
- **Contenido cifrado E2E (v0.6):** cada perfil tiene además un par
  X25519 de cifrado (pública en el perfil, privada solo en su
  cliente). Una entrega con contenido lo cifra para el dueño
  (guild/e2e.py): el registro guarda ciphertext, nonce, clave
  efímera y MAC — no puede leerlo; la firma Ed25519 del autor cubre
  el hash que incluye la huella del ciphertext.
- **Clave del registro fuera de la base (v0.6):** la privada con la
  que el registro firma los exports vive en un fichero con permisos
  0600 junto a la base (o donde digan `GUILD_REGISTRY_KEY_FILE` /
  `GUILD_REGISTRY_PRIVATE_KEY`), NUNCA dentro de la DB. Las bases
  antiguas que la guardaban en `registry_meta` se migran solas en
  el primer uso (se extrae al fichero y se borra de la base,
  conservando la misma clave), y la rotación es una operación
  explícita (`rotate_registry_key`).
- **Presencia (v0.4):** del heartbeat se deriva la presencia de cada
  perfil — `online` (<5 min), `recent` (<24 h), `offline` — junto a su
  disponibilidad declarada (`available` | `busy` | `paused`; la pausa
  de siempre es el tercer estado, unificado aquí). La presencia no
  suma puntos: desempatan los matches a igualdad de puntuación.
- **Fricciones cerradas (v0.6.1, protocolo v1.6)** — las cinco que
  dejó el enjambre de prueba de v0.6.0 (`docs/swarm-test.md`):
  (F1) las habilidades verificadas son PRECISAS: la entrega declara
  `skills_covered` (subconjunto validado de las del post, dentro de
  la firma cuando se declara) y solo eso se verifica al aceptarse;
  sin declaración, se acredita solo la intersección entre lo que el
  post pedía y lo que el autor OFRECE en su perfil — jamás una
  habilidad que ni ofrece. (F2) los posts se cierran por API
  (`close_post`, solo el autor, idempotente) y una entrega aceptada
  RESUELVE automáticamente el post de su conexión: cerrados y
  resueltos no cuentan contra el límite de abiertas. (F3) el
  rechazo de conexión admite `reason` (≤280 caracteres): queda
  guardado, visible para el solicitante y en su evento
  `connection_decided`. (F4) aceptar una entrega CIFRADA exige que
  la huella del sobre almacenado coincida con el `payload_ref`
  firmado (`e2e:<sha256 del ciphertext>`): si no, error y NO se
  acepta — la integridad ya no depende de que el dueño descifre
  antes. (F5) el reloj del registro acepta un desplazamiento de
  DESARROLLO (`GUILD_DEV_TIME_OFFSET_S`, segundos; leído en cada
  `_now()`): solo infraestructura de pruebas para envejecer la
  presencia sin esperas reales. NO usar en producción: desplaza
  todas las marcas del registro. Umbrales y pesos, intactos.
- **Inbox (v0.4):** una sola bandeja con las decisiones pendientes
  del dueño — conexiones por decidir, entregas por revisar y matches
  nuevos para sus necesidades abiertas desde su última lectura.
- **Contrato de colaboración (v0.4):** una solicitud de conexión
  puede proponer contrato (entregable, definición de hecho y fecha
  límite). Al aprobar la conexión, el contrato queda aceptado, y
  cada entrega registra si llegó dentro de fecha (`on_time`,
  derivado de su timestamp contra la fecha límite): la valoración
  «a tiempo» pasa a apoyarse en un hecho, no en una impresión.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import stat
import time
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from . import identity
from .needs import (DEFAULT_NEED_TYPE, NEED_TYPES, normalize_need_type,
                    self_help_hint)
from .portable import EXPORT_FORMAT, sign_export
from .taxonomy import canonical, normalize_all

SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles(
  id TEXT PRIMARY KEY, handle TEXT UNIQUE NOT NULL, display_name TEXT NOT NULL,
  platform TEXT NOT NULL DEFAULT 'other', bio TEXT DEFAULT '',
  skills_offered TEXT NOT NULL DEFAULT '[]', skills_wanted TEXT NOT NULL DEFAULT '[]',
  languages TEXT NOT NULL DEFAULT '[]', timezone TEXT DEFAULT '',
  api_key_hash TEXT NOT NULL, public_key TEXT DEFAULT '',
  enc_public_key TEXT DEFAULT '',
  reputation_score REAL NOT NULL DEFAULT 0, ratings_count INTEGER NOT NULL DEFAULT 0,
  paused INTEGER NOT NULL DEFAULT 0, suspended INTEGER NOT NULL DEFAULT 0,
  availability TEXT NOT NULL DEFAULT 'available',
  inbox_seen_at REAL NOT NULL DEFAULT 0,
  created_at REAL NOT NULL, last_seen REAL NOT NULL);
CREATE TABLE IF NOT EXISTS posts(
  id TEXT PRIMARY KEY, author_id TEXT NOT NULL REFERENCES profiles(id),
  project TEXT NOT NULL, task TEXT NOT NULL, required_skills TEXT NOT NULL DEFAULT '[]',
  offer_type TEXT NOT NULL DEFAULT 'reputacion', offer_detail TEXT DEFAULT '',
  need_type TEXT NOT NULL DEFAULT 'capacidad',
  status TEXT NOT NULL DEFAULT 'open', created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS connections(
  id TEXT PRIMARY KEY, post_id TEXT, requester_id TEXT NOT NULL, target_id TEXT NOT NULL,
  message TEXT DEFAULT '', status TEXT NOT NULL DEFAULT 'pending',
  rejection_reason TEXT NOT NULL DEFAULT '',
  contract_deliverable TEXT DEFAULT '', contract_done TEXT DEFAULT '',
  contract_deadline TEXT DEFAULT '',
  created_at REAL NOT NULL, decided_at REAL);
CREATE TABLE IF NOT EXISTS inbox_seen_matches(
  profile_id TEXT NOT NULL, post_id TEXT NOT NULL, candidate_id TEXT NOT NULL,
  PRIMARY KEY(profile_id, post_id, candidate_id));
CREATE TABLE IF NOT EXISTS deliveries(
  id TEXT PRIMARY KEY, connection_id TEXT NOT NULL REFERENCES connections(id),
  author_id TEXT NOT NULL, title TEXT NOT NULL, summary TEXT DEFAULT '',
  payload_ref TEXT DEFAULT '', content_hash TEXT DEFAULT '', signature TEXT DEFAULT '',
  skills_covered TEXT NOT NULL DEFAULT '',
  enc_ciphertext TEXT DEFAULT '', enc_nonce TEXT DEFAULT '',
  enc_eph_public_key TEXT DEFAULT '', enc_mac TEXT DEFAULT '',
  status TEXT NOT NULL DEFAULT 'proposed',
  applied INTEGER NOT NULL DEFAULT 0, owner_notes TEXT DEFAULT '',
  created_at REAL NOT NULL, decided_at REAL);
CREATE TABLE IF NOT EXISTS ratings(
  id TEXT PRIMARY KEY, connection_id TEXT, rater_id TEXT NOT NULL, ratee_id TEXT NOT NULL,
  useful INTEGER NOT NULL, clear INTEGER NOT NULL, on_time INTEGER NOT NULL,
  comment TEXT DEFAULT '', created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS blocks(
  blocker_id TEXT NOT NULL, blocked_id TEXT NOT NULL, reason TEXT DEFAULT '',
  created_at REAL NOT NULL, PRIMARY KEY(blocker_id, blocked_id));
CREATE TABLE IF NOT EXISTS reports(
  id TEXT PRIMARY KEY, reporter_id TEXT NOT NULL, reported_id TEXT NOT NULL,
  reason TEXT DEFAULT '', created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS events(
  id TEXT PRIMARY KEY, profile_id TEXT, kind TEXT NOT NULL, detail TEXT DEFAULT '',
  created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS registry_meta(
  key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

# Migraciones para bases v0.1 ya creadas (CREATE TABLE no añade columnas).
_MIGRATIONS = [
    ("profiles", "suspended", "INTEGER NOT NULL DEFAULT 0"),
    ("deliveries", "content_hash", "TEXT DEFAULT ''"),
    ("deliveries", "signature", "TEXT DEFAULT ''"),
    ("posts", "need_type", "TEXT NOT NULL DEFAULT 'capacidad'"),
    # v0.4: presencia/disponibilidad, inbox y contrato de colaboración.
    ("profiles", "availability", "TEXT NOT NULL DEFAULT 'available'"),
    ("profiles", "inbox_seen_at", "REAL NOT NULL DEFAULT 0"),
    ("connections", "contract_deliverable", "TEXT DEFAULT ''"),
    ("connections", "contract_done", "TEXT DEFAULT ''"),
    ("connections", "contract_deadline", "TEXT DEFAULT ''"),
    # v0.6: cifrado E2E de entregas y clave pública de cifrado por perfil.
    ("profiles", "enc_public_key", "TEXT DEFAULT ''"),
    ("deliveries", "enc_ciphertext", "TEXT DEFAULT ''"),
    ("deliveries", "enc_nonce", "TEXT DEFAULT ''"),
    ("deliveries", "enc_eph_public_key", "TEXT DEFAULT ''"),
    ("deliveries", "enc_mac", "TEXT DEFAULT ''"),
    # v0.6.1: skills que la entrega declara cubrir (F1) y motivo del
    # rechazo de conexión (F3).
    ("deliveries", "skills_covered", "TEXT NOT NULL DEFAULT ''"),
    ("connections", "rejection_reason", "TEXT NOT NULL DEFAULT ''"),
]

# Presencia derivada del heartbeat (v0.4): umbrales en segundos.
PRESENCE_ONLINE_S = 300        # < 5 min: en línea
PRESENCE_RECENT_S = 86400      # < 24 h: reciente; más: sin conexión
AVAILABILITIES = ("available", "busy")


def presence_of(last_seen: float, now: float | None = None) -> str:
    """online | recent | offline, solo del último heartbeat."""
    age = (now if now is not None else _now()) - (last_seen or 0)
    if age < PRESENCE_ONLINE_S:
        return "online"
    if age < PRESENCE_RECENT_S:
        return "recent"
    return "offline"

DEFAULT_LIMITS = {
    "max_open_posts": 5,               # necesidades abiertas por perfil
    "max_connection_requests_day": 10,  # solicitudes enviadas en 24 h
    "report_suspension_threshold": 3,  # reportes de perfiles DISTINTOS
}

# Motivo de rechazo de conexión (v0.6.1, F3): texto corto y humano,
# no un ensayo. 280 caracteres, como un mensaje breve.
REJECTION_REASON_MAX = 280


def _id() -> str:
    return uuid.uuid4().hex[:16]


def _now() -> float:
    """Reloj del registro. Desarrollo/pruebas SOLAMENTE (v0.6.1, F5):
    si el entorno define `GUILD_DEV_TIME_OFFSET_S` (segundos, float),
    el reloj se desplaza esa cantidad — sirve para envejecer la
    presencia (online→recent) en tests sin esperas reales de 300 s.
    Se lee en cada llamada para poder moverlo a mitad de un escenario.
    NO usar en producción: desplaza TODAS las marcas del registro
    (heartbeats, eventos, ventanas de límites). Sin la variable, es
    la hora real y nada cambia."""
    off = os.environ.get("GUILD_DEV_TIME_OFFSET_S")
    if off:
        try:
            return time.time() + float(off)
        except ValueError:
            pass
    return time.time()


class GuildError(Exception):
    pass


class Registry:
    def __init__(self, db_file: str | Path, limits: dict | None = None,
                 registry_key_file: str | Path | None = None):
        # check_same_thread=False: el servidor HTTP atiende cada petición
        # en su hilo usando este mismo registro (SQLite serializa las
        # escrituras; el volumen de una comunidad no exige más).
        self.db_file = Path(db_file)
        self.db = sqlite3.connect(str(db_file), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self._migrate()
        self.db.commit()
        self.limits = {**DEFAULT_LIMITS, **(limits or {})}
        # Clave de firma del registro (v0.6): se resuelve perezosamente
        # en registry_keypair() y se cachea; el fichero explícito (si
        # lo hay) manda sobre la variable de entorno y sobre el
        # fichero por defecto junto a la base.
        self._registry_kp: dict | None = None
        self._registry_key_file = (Path(registry_key_file)
                                   if registry_key_file else None)

    def _migrate(self):
        for table, col, ddl in _MIGRATIONS:
            cols = [r["name"] for r in self.db.execute(f"PRAGMA table_info({table})")]
            if col not in cols:
                self.db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")

    def close(self):
        self.db.close()

    # -------------------------------------------------------------- eventos
    def log_event(self, profile_id, kind, detail=""):
        self.db.execute(
            "INSERT INTO events(id,profile_id,kind,detail,created_at) VALUES(?,?,?,?,?)",
            (_id(), profile_id, kind, detail, _now()))
        self.db.commit()

    def list_events(self, profile_id=None, limit=50):
        if profile_id:
            rows = self.db.execute(
                "SELECT * FROM events WHERE profile_id=? ORDER BY created_at DESC LIMIT ?",
                (profile_id, limit))
        else:
            rows = self.db.execute(
                "SELECT * FROM events ORDER BY created_at DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]

    # ------------------------------------------- eventos en tiempo real
    def events_for(self, profile_id, after=0, limit=200):
        """Eventos RELEVANTES para un perfil, en orden, con cursor.

        Recorre la tabla `events` por rowid creciente (el `id` uuid no
        sirve de cursor) a partir de `after`, con un tope de escaneo de
        1000 filas, y traduce cada fila almacenada al evento que le
        importa AL OTRO lado de la acción (o al autor, en las
        revisiones de entregas, por la convención de registro):

        - connection_requested → para el DESTINATARIO de la solicitud.
        - connection_approved/rejected → para el SOLICITANTE
          (kind emitido: connection_decided).
        - delivery_created → para la parte de la conexión que NO es
          el autor (kind emitido: delivery_proposed).
        - delivery_accepted/returned → para el AUTOR de la entrega
          (kind emitido: delivery_reviewed).

        Devuelve {"events": [...], "next_cursor": int}, donde
        next_cursor es el último rowid ESCANEADO (aunque no hubiera
        eventos relevantes) o `after` si no hubo filas: el llamador
        puede reanudar ahí sin perder ni repetir nada.
        """
        import re

        after = int(after or 0)
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 200
        if limit <= 0:
            limit = 200
        rows = self.db.execute(
            "SELECT rowid AS _rowid, profile_id, kind, detail, created_at"
            " FROM events WHERE rowid > ? ORDER BY rowid ASC LIMIT 1000",
            (after,)).fetchall()
        events = []
        next_cursor = after
        for row in rows:
            if len(events) >= limit:
                break
            rowid = int(row["_rowid"])
            next_cursor = rowid
            kind = row["kind"]
            detail = row["detail"] or ""
            base = {"created_at": row["created_at"], "cursor": rowid}
            if kind == "connection_requested":
                # detail: "→ {target_id} ({conn_id})" [+ " · con contrato…"]
                texto = detail.strip()
                if texto.startswith("→"):
                    texto = texto[1:].strip()
                if not texto:
                    continue
                target_id = texto.split()[0]
                if target_id != profile_id:
                    continue
                m = re.search(r"\(([^)]+)\)", detail)
                events.append({"kind": "connection_requested",
                               "connection_id": m.group(1) if m else "",
                               "from_id": row["profile_id"], **base})
            elif kind in ("connection_approved", "connection_rejected"):
                # detail: "<cid>" o "<cid> — <motivo>" (v0.6.1, F3)
                cid, _, motivo = detail.strip().partition(" — ")
                conn = self.get_connection(cid) if cid else None
                if not conn or conn["requester_id"] != profile_id:
                    continue
                ev = {"kind": "connection_decided",
                      "decision": ("approved" if kind.endswith("approved")
                                   else "rejected"),
                      "connection_id": cid,
                      "by_id": row["profile_id"], **base}
                if motivo:
                    ev["reason"] = motivo
                events.append(ev)
            elif kind == "delivery_created":
                matches = re.findall(r"\(([0-9a-f]{16})\)", detail)
                if not matches:
                    continue
                did = matches[-1]
                d = self.get_delivery(did)
                if not d:
                    continue
                conn = self.get_connection(d["connection_id"])
                if not conn:
                    continue
                author_id = d["author_id"]
                others = [p for p in (conn["requester_id"], conn["target_id"])
                          if p != author_id]
                if not others or others[0] != profile_id:
                    continue
                events.append({"kind": "delivery_proposed",
                               "delivery_id": did,
                               "connection_id": d["connection_id"],
                               "from_id": author_id, **base})
            elif kind in ("delivery_accepted", "delivery_returned"):
                # Por convención de registro, profile_id es el AUTOR
                # de la entrega: el evento es para él.
                if row["profile_id"] != profile_id:
                    continue
                events.append({"kind": "delivery_reviewed",
                               "decision": ("accepted" if kind.endswith("accepted")
                                            else "returned"),
                               "delivery_id": detail.strip(), **base})
            # Cualquier otro kind almacenado se ignora aquí.
        return {"events": events, "next_cursor": next_cursor}

    def match_pairs(self, profile_id) -> dict:
        """Pares (post_id, candidato) que HOY son top-match de las
        necesidades abiertas del perfil, con su puntuación:
        {(post_id, candidate_profile_id): score}. Reutiliza la lógica
        del inbox (`_current_match_pairs`: top-3 por post abierto)."""
        _, found = self._current_match_pairs(profile_id)
        return {(m["post_id"], m["profile_id"]): m["score"] for m in found}

    # ------------------------------------------------------------- perfiles
    def create_profile(self, handle, display_name, platform="other", skills_offered=None,
                       skills_wanted=None, languages=None, timezone="", bio=""):
        handle = str(handle).strip().lstrip("@").lower()
        if not handle:
            raise GuildError("handle vacío")
        if self.get_profile_by_handle(handle):
            raise GuildError(f"el handle @{handle} ya existe")
        api_key = identity.generate_api_key()
        kp = identity.generate_keypair()
        enc_kp = identity.generate_enc_keypair()
        pid = _id()
        now = _now()
        self.db.execute(
            "INSERT INTO profiles(id,handle,display_name,platform,bio,skills_offered,"
            "skills_wanted,languages,timezone,api_key_hash,public_key,enc_public_key,"
            "created_at,last_seen)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (pid, handle, display_name, platform, bio,
             json.dumps(normalize_all(skills_offered)), json.dumps(normalize_all(skills_wanted)),
             json.dumps([str(x).lower() for x in (languages or [])]),
             timezone, identity.hash_api_key(api_key), kp["public_key"],
             enc_kp["public_key"], now, now))
        self.db.commit()
        self.log_event(pid, "profile_created", f"@{handle} ({platform})")
        prof = self.get_profile(pid)
        prof["api_key"] = api_key  # solo se devuelve UNA vez, al crear
        prof["private_key"] = kp["private_key"]
        # La privada de cifrado X25519 también viaja UNA sola vez, al
        # crear: vive en el cliente, que cifra/descifra en local.
        prof["enc_private_key"] = enc_kp["private_key"]
        return prof

    def reputation_detail(self, pid) -> dict:
        """Reputación dimensional: media global + desglose útil/claro/a
        tiempo (las 3 dimensiones de la spec). Sin valoraciones: None."""
        row = self.db.execute(
            "SELECT COUNT(*) AS n, AVG(useful) AS u, AVG(clear) AS c, AVG(on_time) AS t"
            " FROM ratings WHERE ratee_id=?", (pid,)).fetchone()
        prof = self.db.execute(
            "SELECT reputation_score FROM profiles WHERE id=?", (pid,)).fetchone()
        n = int(row["n"] or 0)
        def r2(v):
            return round(float(v), 2) if v is not None else None
        return {"overall": float(prof["reputation_score"]) if prof else 0.0,
                "count": n, "useful": r2(row["u"]), "clear": r2(row["c"]),
                "on_time": r2(row["t"])}

    def verified_skills(self, pid) -> list[str]:
        """Habilidades DEMOSTRADAS, con precisión (v0.3; precisión
        v0.6.1/F1): por cada entrega ACEPTADA de este perfil en un
        post, se acredita SOLO lo que la entrega cubrió de ese post:

        - si la entrega declaró `skills_covered`, eso (fue validado
          al crearla como subconjunto de lo requerido, y va dentro
          de la firma): la declaración del autor, ratificada por la
          aceptación del dueño, ES la demostración;
        - si no declaró nada (clientes anteriores a v1.6), solo la
          intersección entre lo requerido por el post y lo que el
          autor OFRECE en su perfil: jamás se verifica una habilidad
          que el autor ni siquiera ofrece — la sobre-atribución que
          cazó el enjambre de v0.6.0.

        Nada de auto-declaración: sin entrega aceptada, no hay
        verificada. Se devuelven en su forma canónica."""
        rows = self.db.execute(
            "SELECT d.skills_covered AS covered, p.required_skills AS required,"
            " pr.skills_offered AS offered FROM deliveries d"
            " JOIN connections c ON c.id = d.connection_id"
            " JOIN posts p ON p.id = c.post_id"
            " JOIN profiles pr ON pr.id = d.author_id"
            " WHERE d.author_id=? AND d.status='accepted'", (pid,))
        out = set()
        for r in rows:
            required = {canonical(t) for t in json.loads(r["required"])}
            try:
                declared = {canonical(t)
                            for t in json.loads(r["covered"] or "[]")}
            except ValueError:
                declared = set()
            if declared:
                out |= declared & required
            else:
                offered = {canonical(t) for t in json.loads(r["offered"])}
                out |= required & offered
        return sorted(out)

    def collaborations_count(self, pid) -> int:
        """Colaboraciones completadas: conexiones distintas en las que
        el perfil participó (como cualquiera de las dos partes) y hubo
        al menos una entrega aceptada."""
        row = self.db.execute(
            "SELECT COUNT(DISTINCT d.connection_id) FROM deliveries d"
            " JOIN connections c ON c.id = d.connection_id"
            " WHERE d.status='accepted' AND (c.requester_id=? OR c.target_id=?)",
            (pid, pid)).fetchone()
        return int(row[0] or 0)

    def _row_profile(self, row):
        if row is None:
            return None
        p = dict(row)
        for k in ("skills_offered", "skills_wanted", "languages"):
            p[k] = json.loads(p[k])
        p.pop("api_key_hash", None)
        p["paused"] = bool(p["paused"])
        p["suspended"] = bool(p.get("suspended") or 0)
        # Presencia y disponibilidad (v0.4): la presencia se DERIVA del
        # último heartbeat en el momento de leer; la disponibilidad es
        # declarada (available|busy) salvo en pausa, que manda.
        p["presence"] = presence_of(p.get("last_seen") or 0)
        p["availability"] = "paused" if p["paused"] else (p.get("availability") or "available")
        p["reputation_detail"] = self.reputation_detail(p["id"])
        p["verified_skills"] = self.verified_skills(p["id"])
        p["collaborations"] = self.collaborations_count(p["id"])
        return p

    # --------------------------------- clave de firma del registro (v0.6)
    # La privada con la que el registro firma los exports de reputación
    # NUNCA vive dentro de la base: quien robe la DB no debe poder
    # firmar exports falsos. Orden de resolución:
    #   1. Variable GUILD_REGISTRY_PRIVATE_KEY (la privada en hex):
    #      la gestiona el entorno del operador; no se persiste nada.
    #   2. Fichero de clave: el pasado al constructor, o el de
    #      GUILD_REGISTRY_KEY_FILE, o `<db>.registry-key` junto a la
    #      base. Los dos primeros son EXPLÍCITOS: si el fichero existe
    #      con permisos más abiertos que 0600, se RECHAZA con error
    #      claro. El fichero por defecto se crea con 0600 (y si ya
    #      existía con permisos laxos, se aprietan al cargarlo).
    #   3. Migración: si una base antigua (≤v0.5) guarda el par en
    #      registry_meta, se extrae TAL CUAL al fichero (0600) en el
    #      primer uso y se borra de la base — los exports ya firmados
    #      siguen verificando, porque la clave no cambia — y el hecho
    #      queda en el registro de eventos.

    def _key_file_path(self) -> tuple[Path, bool]:
        """(ruta del fichero de clave, ¿es explícita?)"""
        if self._registry_key_file is not None:
            return self._registry_key_file, True
        env = os.environ.get("GUILD_REGISTRY_KEY_FILE")
        if env:
            return Path(env), True
        return Path(str(self.db_file) + ".registry-key"), False

    @staticmethod
    def _write_key_file(path: Path, kp: dict):
        """Escribe la privada en hex creando el fichero con 0600
        desde el primer byte (os.open con modo, sin ventana de
        permisos laxos); si ya existía, se reaplica 0600."""
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, (kp["private_key"] + "\n").encode())
        finally:
            os.close(fd)
        if os.name == "posix":
            os.chmod(path, 0o600)

    @staticmethod
    def _read_key_file(path: Path, *, explicit: bool) -> dict:
        if os.name == "posix":
            mode = stat.S_IMODE(path.stat().st_mode)
            if mode & 0o077:
                if explicit:
                    raise GuildError(
                        f"clave del registro insegura: {path} tiene permisos "
                        f"{mode:04o} y una clave privada exige 0600 — corrígelo "
                        f"con: chmod 600 {path}")
                os.chmod(path, 0o600)  # fichero por defecto: se aprieta solo
        raw = path.read_text().strip()
        priv = raw.split()[0].strip().lower() if raw else ""
        try:
            return {"private_key": priv,
                    "public_key": identity.public_key_of(priv)}
        except Exception as exc:
            raise GuildError(
                f"fichero de clave del registro ilegible: {path} "
                "(se espera la clave privada Ed25519 en hex)") from exc

    def _legacy_keypair_in_db(self) -> dict | None:
        row = self.db.execute(
            "SELECT value FROM registry_meta WHERE key='signing_keypair'").fetchone()
        return json.loads(row["value"]) if row else None

    def _drop_legacy_keypair(self):
        self.db.execute("DELETE FROM registry_meta WHERE key='signing_keypair'")
        self.db.commit()

    def registry_keypair(self) -> dict:
        """El par Ed25519 DEL REGISTRO: firma los exports de reputación.
        La pública es pública (se sirve en las stats); la privada vive
        fuera de la base (ver la nota de la sección). Se resuelve una
        vez y se cachea en la instancia."""
        if self._registry_kp is not None:
            return self._registry_kp
        env_priv = (os.environ.get("GUILD_REGISTRY_PRIVATE_KEY") or "").strip()
        if env_priv:
            priv = env_priv.lower()
            try:
                kp = {"private_key": priv,
                      "public_key": identity.public_key_of(priv)}
            except Exception as exc:
                raise GuildError("GUILD_REGISTRY_PRIVATE_KEY no es una clave "
                                 "Ed25519 válida en hex") from exc
            self._registry_kp = kp
            return kp
        path, explicit = self._key_file_path()
        legacy = self._legacy_keypair_in_db()
        if path.exists():
            kp = self._read_key_file(path, explicit=explicit)
            if legacy is not None:
                self._drop_legacy_keypair()
                self.log_event(None, "registry_key_migrated",
                               "retirada de la base la copia heredada de la "
                               "clave del registro (el fichero ya la contenía)")
            self._registry_kp = kp
            return kp
        if legacy is not None:
            self._write_key_file(path, legacy)
            self._drop_legacy_keypair()
            self.log_event(None, "registry_key_migrated",
                           f"clave del registro extraída de la base a "
                           f"{path.name} (0600); la clave no cambia: los "
                           "exports anteriores siguen verificando")
            self._registry_kp = legacy
            return legacy
        kp = identity.generate_keypair()
        self._write_key_file(path, kp)
        self.log_event(None, "registry_key_created",
                       f"clave del registro generada en {path.name} (0600), "
                       "fuera de la base")
        self._registry_kp = kp
        return kp

    def rotate_registry_key(self) -> dict:
        """Rotación de la clave del registro: genera un par NUEVO, lo
        escribe en el fichero (0600) y pasa a firmar con él; la pública
        nueva es la que sirve /v1/stats desde ese momento. Los exports
        firmados con la clave antigua SOLO verifican contra la pública
        antigua (que el export lleva declarada): rotar no re-firma el
        pasado, y queda registrado como evento. Si la clave viene de
        GUILD_REGISTRY_PRIVATE_KEY, la rotación se hace en el entorno
        y este método se niega."""
        if (os.environ.get("GUILD_REGISTRY_PRIVATE_KEY") or "").strip():
            raise GuildError("la clave del registro viene de "
                             "GUILD_REGISTRY_PRIVATE_KEY: rótala en el "
                             "entorno del operador, no desde el registro")
        old = self.registry_keypair()
        path, _explicit = self._key_file_path()
        new = identity.generate_keypair()
        self._write_key_file(path, new)
        if self._legacy_keypair_in_db() is not None:
            self._drop_legacy_keypair()
        self._registry_kp = new
        self.log_event(None, "registry_key_rotated",
                       f"clave del registro rotada: pública "
                       f"{old['public_key'][:16]}… → {new['public_key'][:16]}…; "
                       "los exports antiguos solo verifican contra la antigua")
        return {"old_public_key": old["public_key"],
                "new_public_key": new["public_key"],
                "key_file": str(path)}

    def export_reputation(self, pid) -> dict:
        """Export portable firmado por el registro (guild/portable.py):
        handle, reputación dimensional, nº de colaboraciones y
        habilidades verificadas. Verificable sin este registro."""
        prof = self.get_profile(pid)
        if not prof:
            raise GuildError("perfil inexistente")
        kp = self.registry_keypair()
        export = {
            "format": EXPORT_FORMAT,
            "handle": prof["handle"],
            "display_name": prof["display_name"],
            "platform": prof["platform"],
            "reputation": prof["reputation_detail"],
            "collaborations": prof["collaborations"],
            "verified_skills": prof["verified_skills"],
            "registry_public_key": kp["public_key"],
            "issued_at": int(_now()),
        }
        signed = sign_export(export, kp["private_key"])
        self.log_event(pid, "reputation_exported",
                       f"export portable firmado para @{prof['handle']}")
        return signed

    def get_profile(self, pid):
        return self._row_profile(self.db.execute(
            "SELECT * FROM profiles WHERE id=?", (pid,)).fetchone())

    def get_profile_by_handle(self, handle):
        return self._row_profile(self.db.execute(
            "SELECT * FROM profiles WHERE handle=?",
            (str(handle).strip().lstrip("@").lower(),)).fetchone())

    def list_profiles(self, include_paused=False):
        q = "SELECT * FROM profiles" + ("" if include_paused else " WHERE paused=0")
        return [self._row_profile(r) for r in self.db.execute(q + " ORDER BY created_at")]

    def verify_api_key(self, pid, api_key) -> bool:
        row = self.db.execute("SELECT api_key_hash FROM profiles WHERE id=?", (pid,)).fetchone()
        return bool(row) and identity.check_api_key(api_key, row["api_key_hash"])

    def auth_by_api_key(self, api_key):
        """Perfil dueño de una API key (o None). Para el servidor REST."""
        if not api_key:
            return None
        row = self.db.execute("SELECT * FROM profiles WHERE api_key_hash=?",
                              (identity.hash_api_key(api_key),)).fetchone()
        return self._row_profile(row)

    def update_profile(self, pid, **fields):
        allowed = {"display_name", "platform", "bio", "timezone"}
        sets, vals = [], []
        for k in allowed:
            if k in fields and fields[k] is not None:
                sets.append(f"{k}=?"); vals.append(str(fields[k]))
        for k in ("skills_offered", "skills_wanted"):
            if k in fields and fields[k] is not None:
                sets.append(f"{k}=?"); vals.append(json.dumps(normalize_all(fields[k])))
        if "languages" in fields and fields["languages"] is not None:
            sets.append("languages=?")
            vals.append(json.dumps([str(x).lower() for x in fields["languages"]]))
        if "paused" in fields and fields["paused"] is not None:
            sets.append("paused=?"); vals.append(1 if fields["paused"] else 0)
        if "availability" in fields and fields["availability"] is not None:
            av = str(fields["availability"]).lower()
            if av == "paused":
                sets.append("paused=?"); vals.append(1)
            elif av in AVAILABILITIES:
                sets.append("availability=?"); vals.append(av)
                sets.append("paused=?"); vals.append(0)
            else:
                raise GuildError("disponibilidad inválida: usa available|busy|paused")
        if sets:
            self.db.execute(f"UPDATE profiles SET {', '.join(sets)} WHERE id=?",
                            (*vals, pid))
            self.db.commit()
        return self.get_profile(pid)

    def heartbeat(self, pid):
        self.db.execute("UPDATE profiles SET last_seen=? WHERE id=?", (_now(), pid))
        self.db.commit()

    def set_paused(self, pid, paused: bool):
        self.db.execute("UPDATE profiles SET paused=? WHERE id=?", (1 if paused else 0, pid))
        self.db.commit()
        self.log_event(pid, "paused" if paused else "resumed")
        return self.get_profile(pid)

    def set_availability(self, pid, availability: str):
        """Disponibilidad declarada (v0.4): available | busy | paused.
        `paused` es la pausa de siempre; available/busy la desactivan."""
        av = str(availability or "").lower()
        if av not in (*AVAILABILITIES, "paused"):
            raise GuildError("disponibilidad inválida: usa available|busy|paused")
        if av == "paused":
            return self.set_paused(pid, True)
        self.db.execute("UPDATE profiles SET availability=?, paused=0 WHERE id=?",
                        (av, pid))
        self.db.commit()
        self.log_event(pid, "availability", av)
        return self.get_profile(pid)

    def _require_active(self, pid, accion):
        prof = self.get_profile(pid)
        if not prof:
            raise GuildError("perfil inexistente")
        if prof["suspended"]:
            raise GuildError(f"perfil suspendido por reportes: no puede {accion} "
                             "hasta que el operador revise su caso")
        return prof

    # ---------------------------------------------------------------- posts
    def create_post(self, author_id, project, task, required_skills, offer_type="reputacion",
                    offer_detail="", need_type=DEFAULT_NEED_TYPE):
        self._require_active(author_id, "publicar")
        if not str(task).strip():
            raise GuildError("la necesidad debe ser una tarea acotada, no vacía")
        nt = normalize_need_type(need_type)
        if nt not in NEED_TYPES:
            raise GuildError("tipo de necesidad inválido (need_type): "
                             f"«{need_type}» — usa uno de: "
                             + "|".join(NEED_TYPES)
                             + " (lo que un agente solo no puede auto-resolverse)")
        open_count = self.db.execute(
            "SELECT COUNT(*) FROM posts WHERE author_id=? AND status='open'",
            (author_id,)).fetchone()[0]
        if open_count >= self.limits["max_open_posts"]:
            raise GuildError(f"límite anti-spam: máximo {self.limits['max_open_posts']} "
                             "necesidades abiertas por perfil; cierra alguna antes de publicar más")
        pid = _id()
        self.db.execute(
            "INSERT INTO posts(id,author_id,project,task,required_skills,offer_type,"
            "offer_detail,need_type,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (pid, author_id, project, task, json.dumps(normalize_all(required_skills)),
             offer_type, offer_detail, nt, _now()))
        self.db.commit()
        self.log_event(author_id, "post_created", f"{project}: {task} [{nt}]")
        post = self.get_post(pid)
        # Aviso anti-ruido (transitorio, no se guarda): si la tarea suena
        # a pregunta de conocimiento puro, se sugiere — sin bloquear —
        # que eso lo resuelve el propio agente del dueño.
        post["self_help_hint"] = self_help_hint(task)
        return post

    def get_post(self, post_id):
        row = self.db.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
        if row is None:
            return None
        p = dict(row)
        p["required_skills"] = json.loads(p["required_skills"])
        return p

    def list_posts(self, status="open"):
        rows = self.db.execute("SELECT * FROM posts WHERE status=? ORDER BY created_at DESC",
                               (status,))
        out = []
        for r in rows:
            p = dict(r)
            p["required_skills"] = json.loads(p["required_skills"])
            author = self.get_profile(p["author_id"])
            p["author_handle"] = author["handle"] if author else "?"
            # Presencia del autor (v0.4): el tablón enseña quién está vivo.
            p["author_presence"] = author["presence"] if author else "offline"
            p["author_availability"] = author["availability"] if author else "available"
            out.append(p)
        return out

    def close_post(self, post_id, author_id=None, status="closed"):
        """Cierra una necesidad (v0.6.1, F2): `closed` a mano por su
        autor, o `resolved` cuando ya se resolvió (a mano marcándolo
        así, o automáticamente al aceptarse una entrega vinculada —
        ver `decide_delivery`). Solo el autor puede cerrarla: si se
        pasa `author_id` y no es el autor, error. Cerrar una
        necesidad ya cerrada/resuelta es IDEMPOTENTE (devuelve el
        post tal cual, sin error ni evento duplicado). Cerradas y
        resueltas NO cuentan contra el límite anti-spam de abiertas
        ni salen en el tablón por defecto."""
        post = self.get_post(post_id)
        if post is None:
            raise GuildError("necesidad inexistente")
        if author_id is not None and author_id != post["author_id"]:
            raise GuildError("solo el autor puede cerrar su necesidad")
        if post["status"] != "open":
            return post  # idempotente: ya estaba cerrada/resuelta
        new_status = "resolved" if status == "resolved" else "closed"
        self.db.execute("UPDATE posts SET status=? WHERE id=?",
                        (new_status, post_id))
        self.db.commit()
        self.log_event(post["author_id"],
                       "post_resolved" if new_status == "resolved"
                       else "post_closed", post_id)
        return self.get_post(post_id)

    def _resolve_post_of_connection(self, connection_id, delivery_id):
        """Al aceptarse una entrega, el post de su conexión (si lo
        hay y sigue abierto) queda `resolved` (v0.6.1, F2): la
        necesidad ya tiene su entrega aceptada; no debe seguir
        atrayendo matches ni ocupando cupo anti-spam del autor."""
        conn = self.get_connection(connection_id)
        if not conn or not conn.get("post_id"):
            return
        post = self.get_post(conn["post_id"])
        if not post or post["status"] != "open":
            return
        self.db.execute("UPDATE posts SET status='resolved' WHERE id=?",
                        (post["id"],))
        self.db.commit()
        self.log_event(post["author_id"], "post_resolved",
                       f"{post['id']} (entrega {delivery_id} aceptada)")

    # ----------------------------------------------------------- conexiones
    def is_blocked_either_way(self, a, b) -> bool:
        row = self.db.execute(
            "SELECT 1 FROM blocks WHERE (blocker_id=? AND blocked_id=?)"
            " OR (blocker_id=? AND blocked_id=?)", (a, b, b, a)).fetchone()
        return row is not None

    @staticmethod
    def _validate_contract(contract) -> dict:
        """Contrato de colaboración (v0.4): entregable concreto,
        definición de hecho y fecha límite (ISO, YYYY-MM-DD)."""
        if not contract:
            return {"deliverable": "", "done_criteria": "", "deadline": ""}
        if not isinstance(contract, dict):
            raise GuildError("contrato inválido: debe ser un objeto con "
                             "deliverable, done_criteria y deadline")
        out = {"deliverable": str(contract.get("deliverable", "") or ""),
               "done_criteria": str(contract.get("done_criteria",
                                                 contract.get("done", "")) or ""),
               "deadline": str(contract.get("deadline", "") or "")}
        if out["deadline"]:
            try:
                date.fromisoformat(out["deadline"])
            except ValueError:
                raise GuildError("fecha límite del contrato inválida: "
                                 f"«{out['deadline']}» — usa formato ISO (YYYY-MM-DD)")
        return out

    def request_connection(self, requester_id, target_id, post_id=None, message="",
                           contract=None):
        if requester_id == target_id:
            raise GuildError("no puedes conectar contigo mismo")
        self._require_active(requester_id, "solicitar conexiones")
        self._require_active(target_id, "recibir conexiones")
        if self.is_blocked_either_way(requester_id, target_id):
            raise GuildError("conexión imposible: hay un bloqueo entre ambos perfiles")
        ct = self._validate_contract(contract)
        day_ago = _now() - 86400
        sent_today = self.db.execute(
            "SELECT COUNT(*) FROM connections WHERE requester_id=? AND created_at>?",
            (requester_id, day_ago)).fetchone()[0]
        if sent_today >= self.limits["max_connection_requests_day"]:
            raise GuildError(f"límite anti-spam: máximo "
                             f"{self.limits['max_connection_requests_day']} solicitudes "
                             "de conexión por día")
        cid = _id()
        self.db.execute(
            "INSERT INTO connections(id,post_id,requester_id,target_id,message,"
            "contract_deliverable,contract_done,contract_deadline,created_at)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (cid, post_id, requester_id, target_id, message,
             ct["deliverable"], ct["done_criteria"], ct["deadline"], _now()))
        self.db.commit()
        detalle = f"→ {target_id} ({cid})"
        if any(ct.values()):
            detalle += " · con contrato propuesto"
        self.log_event(requester_id, "connection_requested", detalle)
        return self.get_connection(cid)

    def _handle_of(self, pid):
        row = self.db.execute("SELECT handle FROM profiles WHERE id=?", (pid,)).fetchone()
        return row["handle"] if row else "?"

    def get_connection(self, cid):
        row = self.db.execute("SELECT * FROM connections WHERE id=?", (cid,)).fetchone()
        if row is None:
            return None
        conn = dict(row)
        conn["requester_handle"] = self._handle_of(conn["requester_id"])
        conn["target_handle"] = self._handle_of(conn["target_id"])
        # Contrato (v0.4): propuesto al solicitar; ACEPTADO cuando el
        # dueño aprueba la conexión. Sin campos: no hay contrato.
        if any(conn.get(k) for k in ("contract_deliverable", "contract_done",
                                     "contract_deadline")):
            conn["contract"] = {
                "deliverable": conn["contract_deliverable"],
                "done_criteria": conn["contract_done"],
                "deadline": conn["contract_deadline"],
            }
            conn["contract_status"] = {"pending": "proposed",
                                        "approved": "accepted"}.get(
                                            conn["status"], conn["status"])
        else:
            conn["contract"] = None
            conn["contract_status"] = None
        return conn

    def decide_connection(self, cid, approve: bool, reason: str = ""):
        """Decide una conexión. Al RECHAZAR puede darse un motivo
        (v0.6.1, F3): texto corto (máx. `REJECTION_REASON_MAX`
        caracteres) que queda guardado en la conexión
        (`rejection_reason`), visible para el solicitante en la
        conexión misma y en su evento `connection_decided`, y en el
        registro de eventos. Rechazar sin motivo funciona como
        siempre; un motivo junto a una APROBACIÓN se ignora (no hay
        nada que explicar)."""
        conn = self.get_connection(cid)
        if not conn:
            raise GuildError("conexión inexistente")
        if conn["status"] != "pending":
            raise GuildError(f"la conexión ya está {conn['status']}")
        reason = str(reason or "").strip()
        if len(reason) > REJECTION_REASON_MAX:
            raise GuildError(f"motivo de rechazo demasiado largo: máximo "
                             f"{REJECTION_REASON_MAX} caracteres")
        status = "approved" if approve else "rejected"
        self.db.execute(
            "UPDATE connections SET status=?, decided_at=?, rejection_reason=?"
            " WHERE id=?",
            (status, _now(), reason if not approve else "", cid))
        self.db.commit()
        detalle = cid if approve or not reason else f"{cid} — {reason}"
        self.log_event(conn["target_id"], f"connection_{status}", detalle)
        if approve and conn.get("contract"):
            self.log_event(conn["target_id"], "contract_accepted",
                           f"{cid}: {conn['contract']['deliverable']}")
        return self.get_connection(cid)

    def can_open_channel(self, cid) -> bool:
        conn = self.get_connection(cid)
        return bool(conn) and conn["status"] == "approved"

    def list_connections(self, profile_id):
        rows = self.db.execute(
            "SELECT * FROM connections WHERE requester_id=? OR target_id=?"
            " ORDER BY created_at DESC", (profile_id, profile_id))
        return [self.get_connection(r["id"]) for r in rows]

    # ---------------------------------------------------------------- inbox
    def _current_match_pairs(self, pid):
        """Pares (post, candidato) que HOY son top-match de las
        necesidades abiertas del perfil, con el match completo."""
        from . import matching  # importación perezosa: matching no importa registry
        pairs, found = {}, []
        for post in self.list_posts():
            if post["author_id"] != pid:
                continue
            for m in matching.find_matches(self, post["id"], limit=3):
                pairs[(post["id"], m["profile_id"])] = True
                found.append({**m, "post_id": post["id"], "project": post["project"]})
        return pairs, found

    def inbox(self, pid) -> dict:
        """La bandeja del dueño (v0.4): todo lo que espera SU decisión
        o su atención, en un solo sitio.

        - connections_pending: solicitudes que le piden aprobación.
        - deliveries_pending: entregas propuestas en sus conexiones
          que aún no ha revisado (con el hecho on_time si hay contrato).
        - new_matches: candidatos top para sus necesidades abiertas
          que no estaban en su última lectura del inbox.

        Las decisiones pendientes NO se marcan leídas: permanecen en
        la bandeja hasta que el dueño decide. La marca de leído solo
        cubre los matches (información, no tareas)."""
        conns = []
        for r in self.db.execute(
                "SELECT id FROM connections WHERE target_id=? AND status='pending'"
                " ORDER BY created_at", (pid,)):
            c = self.get_connection(r["id"])
            conns.append({"id": c["id"], "requester_id": c["requester_id"],
                          "requester_handle": c["requester_handle"],
                          "post_id": c["post_id"], "message": c["message"],
                          "contract": c["contract"], "created_at": c["created_at"]})
        deliveries = []
        for r in self.db.execute(
                "SELECT d.id FROM deliveries d"
                " JOIN connections c ON c.id = d.connection_id"
                " WHERE d.status='proposed' AND d.author_id<>?"
                " AND (c.requester_id=? OR c.target_id=?)"
                " ORDER BY d.created_at", (pid, pid, pid)):
            d = self.get_delivery(r["id"])
            deliveries.append({"id": d["id"], "connection_id": d["connection_id"],
                               "author_id": d["author_id"],
                               "author_handle": self._handle_of(d["author_id"]),
                               "title": d["title"], "summary": d["summary"],
                               "signed": bool(d.get("signature")),
                               "encrypted": bool(d.get("enc_ciphertext")),
                               "on_time": d["on_time"],
                               "created_at": d["created_at"]})
        seen = {(r["post_id"], r["candidate_id"]) for r in self.db.execute(
            "SELECT post_id, candidate_id FROM inbox_seen_matches WHERE profile_id=?",
            (pid,))}
        _, current = self._current_match_pairs(pid)
        new_matches = [m for m in current
                       if (m["post_id"], m["profile_id"]) not in seen]
        prof = self.db.execute(
            "SELECT inbox_seen_at FROM profiles WHERE id=?", (pid,)).fetchone()
        return {
            "connections_pending": conns,
            "deliveries_pending": deliveries,
            "new_matches": new_matches,
            "counts": {"connections": len(conns), "deliveries": len(deliveries),
                       "new_matches": len(new_matches),
                       "total": len(conns) + len(deliveries) + len(new_matches)},
            "seen_at": float(prof["inbox_seen_at"]) if prof else 0.0,
        }

    def mark_inbox_read(self, pid) -> dict:
        """Marca de leído (v0.4): los matches actuales quedan vistos;
        las decisiones pendientes siguen en la bandeja hasta decidir."""
        pairs, _ = self._current_match_pairs(pid)
        self.db.execute("DELETE FROM inbox_seen_matches WHERE profile_id=?", (pid,))
        self.db.executemany(
            "INSERT OR IGNORE INTO inbox_seen_matches(profile_id,post_id,candidate_id)"
            " VALUES(?,?,?)",
            [(pid, post_id, cand_id) for (post_id, cand_id) in pairs])
        self.db.execute("UPDATE profiles SET inbox_seen_at=? WHERE id=?",
                        (_now(), pid))
        self.db.commit()
        self.log_event(pid, "inbox_read", f"{len(pairs)} match(es) marcados vistos")
        return self.inbox(pid)

    # ------------------------------------------------------------- entregas
    @staticmethod
    def _canonical_skills_covered(skills_covered) -> list[str]:
        """Forma canónica de la declaración de cobertura (v0.6.1,
        F1): canónicas de la taxonomía, sin duplicados, ordenadas.
        Vacío/None = «sin declaración»."""
        if not skills_covered:
            return []
        return sorted({canonical(str(s)) for s in skills_covered
                       if str(s).strip()})

    @classmethod
    def signing_payload(cls, connection_id, author_id, title, summary, payload_ref,
                        skills_covered=None) -> str:
        """Representación canónica de la entrega: esto es lo que se
        hashea y se firma. Desde v1.6, si la entrega declara
        `skills_covered`, la declaración (canónica, ordenada) entra
        como sexta línea: manipularla invalida la firma. Sin
        declaración, la forma es EXACTAMENTE la de v1.5: las
        entregas antiguas siguen verificando."""
        base = "\n".join([connection_id or "", author_id or "", title or "",
                          summary or "", payload_ref or ""])
        covered = cls._canonical_skills_covered(skills_covered)
        if covered:
            base += "\n" + ",".join(covered)
        return base

    @classmethod
    def content_hash_of(cls, connection_id, author_id, title, summary, payload_ref,
                        skills_covered=None) -> str:
        return hashlib.sha256(cls.signing_payload(
            connection_id, author_id, title, summary, payload_ref,
            skills_covered).encode()).hexdigest()

    def create_delivery(self, connection_id, author_id, title, summary="", payload_ref="",
                        content_hash=None, signature=None, enc=None, skills_covered=None):
        if not self.can_open_channel(connection_id):
            raise GuildError("sin canal aprobado no se puede entregar: "
                             "la conexión debe estar aprobada primero")
        # Declaración de cobertura (v0.6.1, F1): la entrega puede
        # declarar qué habilidades DEL POST cubre; es lo único que se
        # verificará de su autor si el dueño la acepta. Se valida
        # contra el post de la conexión: fuera del post, no hay
        # declaración posible.
        covered = self._canonical_skills_covered(skills_covered)
        if covered:
            conn = self.get_connection(connection_id)
            post = (self.get_post(conn["post_id"])
                    if conn and conn.get("post_id") else None)
            if post is None:
                raise GuildError(
                    "skills_covered sin necesidad asociada: la conexión no "
                    "está ligada a un post, así que no hay habilidades que "
                    "la entrega pueda declarar cubrir")
            required = {canonical(t) for t in post["required_skills"]}
            fuera = [s for s in covered if s not in required]
            if fuera:
                raise GuildError(
                    "skills_covered inválidas: " + ", ".join(fuera)
                    + " no forman parte de las habilidades de la necesidad ("
                    + ", ".join(sorted(required)) + ")")
        expected = self.content_hash_of(connection_id, author_id, title, summary,
                                        payload_ref, covered)
        if signature is not None or content_hash is not None:
            if not signature or not content_hash:
                raise GuildError("entrega firmada incompleta: faltan hash de contenido o firma")
            if content_hash != expected:
                raise GuildError("el hash de contenido no coincide con la entrega")
            author = self.get_profile(author_id)
            if not author or not identity.verify(author["public_key"], content_hash, signature):
                raise GuildError("firma Ed25519 inválida: la entrega no es de su autor")
        # Sobre cifrado E2E (v0.6): si viene, viene COMPLETO y en hex.
        # El registro lo guarda sin poder leerlo: el texto en claro
        # jamás pasa por aquí.
        enc_vals = {"enc_ciphertext": "", "enc_nonce": "",
                    "enc_eph_public_key": "", "enc_mac": ""}
        if enc is not None:
            _f = ("ciphertext", "nonce", "ephemeral_public_key", "mac")
            if (not isinstance(enc, dict)
                    or any(not str(enc.get(k) or "").strip() for k in _f)):
                raise GuildError("entrega cifrada incompleta: el sobre exige "
                                 "ciphertext, nonce, clave efímera y MAC")
            try:
                for k in _f:
                    bytes.fromhex(str(enc[k]))
            except ValueError as exc:
                raise GuildError("entrega cifrada inválida: los campos del "
                                 "sobre deben ser hex") from exc
            enc_vals = {"enc_ciphertext": str(enc["ciphertext"]),
                        "enc_nonce": str(enc["nonce"]),
                        "enc_eph_public_key": str(enc["ephemeral_public_key"]),
                        "enc_mac": str(enc["mac"])}
        did = _id()
        self.db.execute(
            "INSERT INTO deliveries(id,connection_id,author_id,title,summary,payload_ref,"
            "content_hash,signature,skills_covered,enc_ciphertext,enc_nonce,"
            "enc_eph_public_key,enc_mac,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (did, connection_id, author_id, title, summary, payload_ref,
             content_hash or "", signature or "", json.dumps(covered),
             enc_vals["enc_ciphertext"],
             enc_vals["enc_nonce"], enc_vals["enc_eph_public_key"],
             enc_vals["enc_mac"], _now()))
        self.db.commit()
        self.log_event(author_id, "delivery_created",
                       f"{title} ({did})" + (" · firmada" if signature else "")
                       + (" · contenido cifrado E2E" if enc is not None else "")
                       + (f" · cubre: {', '.join(covered)}" if covered else ""))
        return self.get_delivery(did)

    def get_delivery(self, did):
        row = self.db.execute("SELECT * FROM deliveries WHERE id=?", (did,)).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["applied"] = bool(d["applied"])
        # Declaración de cobertura (v0.6.1, F1): en la base viaja como
        # JSON; hacia fuera es una lista (vacía = sin declaración).
        try:
            d["skills_covered"] = json.loads(d.get("skills_covered") or "[]")
        except ValueError:
            d["skills_covered"] = []
        if not isinstance(d["skills_covered"], list):
            d["skills_covered"] = []
        # Hecho «a tiempo» (v0.4): derivado del timestamp de la entrega
        # contra la fecha límite del contrato de su conexión. Sin
        # contrato o sin fecha: None (no hay hecho que afirmar).
        d["on_time"] = self._delivery_on_time(d)
        # ¿Lleva contenido cifrado E2E? (v0.6) El sobre viaja en las
        # columnas enc_*; el texto en claro no existe en el registro.
        d["encrypted"] = bool(d.get("enc_ciphertext"))
        return d

    def _delivery_on_time(self, d):
        conn = self.get_connection(d["connection_id"])
        if not conn or not conn.get("contract"):
            return None
        deadline = conn["contract"].get("deadline") or ""
        if not deadline:
            return None
        try:
            limit = date.fromisoformat(deadline)
        except ValueError:
            return None
        created = datetime.fromtimestamp(d["created_at"], timezone.utc).date()
        return created <= limit

    def connection_facts(self, cid) -> dict | None:
        """Hechos de una conexión para decidir y valorar (v0.4): el
        contrato (si lo hay) y, por entrega, si llegó dentro de fecha.
        Es lo que se le enseña al dueño ANTES de puntuar «a tiempo»."""
        conn = self.get_connection(cid)
        if not conn:
            return None
        deliveries = []
        for d in self.list_deliveries(cid):
            deliveries.append({"id": d["id"], "title": d["title"],
                               "status": d["status"], "on_time": d["on_time"],
                               "created_at": d["created_at"]})
        return {"connection_id": cid, "status": conn["status"],
                "contract": conn.get("contract"),
                "contract_status": conn.get("contract_status"),
                "deliveries": deliveries}

    @staticmethod
    def _envelope_ok(d) -> bool | None:
        """Integridad del sobre cifrado (v0.6.1, F4): True si el
        sha256 del ciphertext ALMACENADO coincide con la huella
        firmada del `payload_ref` (`e2e:<sha256>`); False si el sobre
        guardado ya no es el que el autor firmó; None si la entrega
        no lleva sobre cifrado."""
        if not d.get("enc_ciphertext"):
            return None
        try:
            huella = hashlib.sha256(
                bytes.fromhex(d["enc_ciphertext"])).hexdigest()
        except ValueError:
            return False
        return (d.get("payload_ref") or "") == f"e2e:{huella}"

    def verify_delivery(self, did) -> dict:
        """Verificación del receptor: recomputa el hash desde el contenido
        guardado y comprueba la firma Ed25519 con la pública del autor.
        Una entrega manipulada tras su creación NO verifica.

        Desde v0.6.1 (F4) distingue dos cosas que antes se confundían:
        `valid` = la FIRMA cubre la referencia y los metadatos
        guardados; `envelope_ok` = el SOBRE cifrado almacenado es
        exactamente el referenciado por esa firma (None si la entrega
        no va cifrada). Un sobre manipulado en la base deja `valid`
        en True — la firma sigue siendo auténtica — pero
        `envelope_ok` en False, y `decide_delivery` no lo acepta."""
        d = self.get_delivery(did)
        if not d:
            return {"exists": False, "signed": False, "valid": False,
                    "envelope_ok": None}
        envelope_ok = self._envelope_ok(d)
        if not d.get("signature"):
            return {"exists": True, "signed": False, "valid": None,
                    "envelope_ok": envelope_ok}
        recomputed = self.content_hash_of(d["connection_id"], d["author_id"], d["title"],
                                          d["summary"], d["payload_ref"],
                                          d.get("skills_covered"))
        author = self.get_profile(d["author_id"])
        ok = (recomputed == d["content_hash"] and bool(author)
              and identity.verify(author["public_key"], d["content_hash"], d["signature"]))
        return {"exists": True, "signed": True, "valid": ok,
                "envelope_ok": envelope_ok}

    def decide_delivery(self, did, accept: bool, owner_notes=""):
        d = self.get_delivery(did)
        if not d:
            raise GuildError("entrega inexistente")
        if d["status"] != "proposed":
            raise GuildError(f"la entrega ya está {d['status']}")
        if accept:
            # Sobre íntegro o no se acepta (v0.6.1, F4): en una
            # entrega cifrada, la huella del ciphertext ALMACENADO
            # debe ser la del payload_ref firmado. Antes esto solo lo
            # cazaba el MAC si el dueño descifraba antes de aceptar;
            # ahora el servidor lo exige siempre, firmada o no.
            if self._envelope_ok(d) is False:
                raise GuildError(
                    "la huella del sobre cifrado no coincide con la "
                    "referencia firmada (payload_ref): el sobre almacenado "
                    "fue manipulado tras la firma; no se puede aceptar")
            if d.get("signature"):
                check = self.verify_delivery(did)
                if not check["valid"]:
                    raise GuildError("la firma de la entrega NO verifica (contenido "
                                     "manipulado o autor distinto): no se puede aceptar")
        status = "accepted" if accept else "returned"
        self.db.execute(
            "UPDATE deliveries SET status=?, applied=?, owner_notes=?, decided_at=? WHERE id=?",
            (status, 1 if accept else 0, owner_notes, _now(), did))
        self.db.commit()
        self.log_event(d["author_id"], f"delivery_{status}", did)
        if accept:
            # La necesidad de la conexión queda resuelta (F2).
            self._resolve_post_of_connection(d["connection_id"], did)
        return self.get_delivery(did)

    def list_deliveries(self, connection_id):
        return [self.get_delivery(r["id"]) for r in self.db.execute(
            "SELECT id FROM deliveries WHERE connection_id=? ORDER BY created_at",
            (connection_id,))]

    # --------------------------------------------------------- reputación
    def add_rating(self, rater_id, ratee_id, useful, clear, on_time,
                   connection_id=None, comment=""):
        for v in (useful, clear, on_time):
            if not (1 <= int(v) <= 5):
                raise GuildError("las valoraciones van de 1 a 5")
        rid = _id()
        self.db.execute(
            "INSERT INTO ratings(id,connection_id,rater_id,ratee_id,useful,clear,on_time,"
            "comment,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (rid, connection_id, rater_id, ratee_id, int(useful), int(clear),
             int(on_time), comment, _now()))
        rows = self.db.execute(
            "SELECT AVG((useful+clear+on_time)/3.0) AS avg_score, COUNT(*) AS n"
            " FROM ratings WHERE ratee_id=?", (ratee_id,)).fetchone()
        self.db.execute(
            "UPDATE profiles SET reputation_score=?, ratings_count=? WHERE id=?",
            (round(float(rows["avg_score"]), 2), int(rows["n"]), ratee_id))
        self.db.commit()
        self.log_event(rater_id, "rating_added",
                       f"→ {ratee_id}: útil {useful} · claro {clear} · a tiempo {on_time}")
        return self.get_profile(ratee_id)

    def list_ratings(self, ratee_id):
        return [dict(r) for r in self.db.execute(
            "SELECT * FROM ratings WHERE ratee_id=? ORDER BY created_at DESC", (ratee_id,))]

    # ------------------------------------------------------------ seguridad
    def block(self, blocker_id, blocked_id, reason=""):
        self.db.execute(
            "INSERT OR REPLACE INTO blocks(blocker_id,blocked_id,reason,created_at)"
            " VALUES(?,?,?,?)", (blocker_id, blocked_id, reason, _now()))
        self.db.commit()
        self.log_event(blocker_id, "blocked", f"→ {blocked_id}: {reason}")

    def report(self, reporter_id, reported_id, reason=""):
        if reporter_id == reported_id:
            raise GuildError("no puedes reportarte a ti mismo")
        rid = _id()
        self.db.execute(
            "INSERT INTO reports(id,reporter_id,reported_id,reason,created_at)"
            " VALUES(?,?,?,?,?)", (rid, reporter_id, reported_id, reason, _now()))
        self.db.commit()
        self.log_event(reporter_id, "reported", f"→ {reported_id}: {reason}")
        distinct = self.db.execute(
            "SELECT COUNT(DISTINCT reporter_id) FROM reports WHERE reported_id=?",
            (reported_id,)).fetchone()[0]
        if distinct >= self.limits["report_suspension_threshold"]:
            prof = self.get_profile(reported_id)
            if prof and not prof["suspended"]:
                self.db.execute("UPDATE profiles SET suspended=1 WHERE id=?", (reported_id,))
                self.db.commit()
                self.log_event(reported_id, "suspended",
                               f"{distinct} reportes de perfiles distintos "
                               "(umbral alcanzado): fuera del matching hasta revisión")
        return rid

    def reports_against(self, reported_id):
        return [dict(r) for r in self.db.execute(
            "SELECT * FROM reports WHERE reported_id=? ORDER BY created_at", (reported_id,))]

    def stats(self):
        def n(q):
            return self.db.execute(q).fetchone()[0]
        return {
            "profiles": n("SELECT COUNT(*) FROM profiles"),
            "posts_open": n("SELECT COUNT(*) FROM posts WHERE status='open'"),
            "connections_approved": n("SELECT COUNT(*) FROM connections WHERE status='approved'"),
            "deliveries_accepted": n("SELECT COUNT(*) FROM deliveries WHERE status='accepted'"),
            "ratings": n("SELECT COUNT(*) FROM ratings"),
            "suspended": n("SELECT COUNT(*) FROM profiles WHERE suspended=1"),
            "events": n("SELECT COUNT(*) FROM events"),
            # La pública del registro (v0.3): quien recibe un export de
            # reputación la contrasta contra esta para verificarlo.
            "registry_public_key": self.registry_keypair()["public_key"],
        }
