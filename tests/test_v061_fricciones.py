"""Tests de v0.6.1 «Fricciones» (protocolo v1.6) — las cinco fricciones
que dejó el enjambre de prueba de v0.6.0 (docs/swarm-test.md):

- F1: las habilidades verificadas sobre-atribuían (todas las del post
  para cualquier entrega aceptada). Ahora la entrega declara
  `skills_covered` y solo eso se verifica; sin declaración, solo la
  intersección requerido ∩ ofrecido.
- F2: un post completado nunca se cerraba por la API. Ahora hay
  `close_post` (autor, idempotente) y la aceptación resuelve el post.
- F3: el rechazo de conexión no admitía motivo. Ahora `reason`
  (≤280) llega al solicitante por la conexión y por su evento.
- F4: aceptar no exigía sobre íntegro. Ahora el servidor compara la
  huella del ciphertext almacenado con el payload_ref firmado
  (409 si no coincide) y el cliente descifra antes de aceptar.
- F5: la presencia no se podía acelerar. Reloj de desarrollo
  inyectable `GUILD_DEV_TIME_OFFSET_S` (solo pruebas).
"""
from __future__ import annotations

import re
import sqlite3
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from guild import matching  # noqa: E402
from guild.client import GuildClient  # noqa: E402
from guild.registry import GuildError, Registry  # noqa: E402
from guild.server import make_server  # noqa: E402


@pytest.fixture()
def reg(tmp_path):
    r = Registry(tmp_path / "t.db")
    yield r
    r.close()


@pytest.fixture()
def http(tmp_path):
    db = tmp_path / "net.db"
    server = make_server(db, port=0)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}", db
    server.shutdown()
    server.server_close()
    server.registry.close()


def _join(reg, handle, offers, langs=("es",), tz="Europe/Madrid", base_url=None):
    c = GuildClient(registry=reg, base_url=base_url)
    c.join(handle, handle.title(), "hermes", skills_offered=list(offers),
           languages=list(langs), timezone=tz)
    return c


def _approved_conn(owner: GuildClient, helper: GuildClient, post_id=None):
    conn = helper.connect(owner.profile_id, post_id=post_id, message="puedo")
    owner.approve_connection(conn["id"], approve=True)
    return conn


# ===================================================================== F1
def test_f1_declared_skills_are_the_only_ones_verified(reg):
    """La forma exacta del enjambre: un post pide [nextjs, seo]; dos
    colaboradores reparten el trabajo y CADA UNO se verifica solo lo
    que declaró cubrir y entregó — no las dos."""
    bruno = _join(reg, "bruno", ["react"])
    post = bruno.post_need("Landing", "Landing que convierta",
                           ["nextjs", "seo"], need_type="capacidad")
    claire = _join(reg, "claire", ["react", "seo", "copywriting"], tz="Europe/Paris")
    conn1 = _approved_conn(bruno, claire, post["id"])
    d1 = claire.deliver(conn1["id"], "Copy + SEO", "textos y metadatos",
                        skills_covered=["seo"])
    assert d1["skills_covered"] == ["seo"]
    bruno.decide_delivery(d1["id"], accept=True)
    assert claire.me()["verified_skills"] == ["seo"]  # nextjs NO, aunque el post lo pedía

    santi = _join(reg, "santi", ["react", "nextjs", "typescript"])
    conn2 = _approved_conn(bruno, santi, post["id"])
    d2 = santi.deliver(conn2["id"], "Landing en Next.js", "implementación",
                       skills_covered=["nextjs"])
    bruno.decide_delivery(d2["id"], accept=True)
    assert santi.me()["verified_skills"] == ["nextjs"]  # seo NO


def test_f1_default_is_intersection_with_offered(reg):
    """Sin declaración (clientes anteriores a v1.6): se acredita solo
    requerido ∩ ofrecido. Quien ofrece todo lo pedido, todo; quien
    ofrece una parte, solo esa parte — nunca lo que ni ofrece."""
    owner = _join(reg, "owner", ["python"])
    post = owner.post_need("Web", "Montar la web", ["nextjs", "seo"],
                           need_type="capacidad")
    parcial = _join(reg, "parcial", ["seo", "copywriting"])
    conn = _approved_conn(owner, parcial, post["id"])
    d = parcial.deliver(conn["id"], "SEO hecho", "solo la parte SEO")
    owner.decide_delivery(d["id"], accept=True)
    assert parcial.me()["verified_skills"] == ["seo"]

    total = _join(reg, "total", ["nextjs", "seo"])
    conn2 = _approved_conn(owner, total, post["id"])
    d2 = total.deliver(conn2["id"], "Web completa", "las dos partes")
    owner.decide_delivery(d2["id"], accept=True)
    assert total.me()["verified_skills"] == ["nextjs", "seo"]


def test_f1_declaration_must_be_subset_of_post(reg):
    owner = _join(reg, "owner", ["python"])
    post = owner.post_need("Web", "Montar la web", ["nextjs", "seo"],
                           need_type="capacidad")
    helper = _join(reg, "helper", ["nextjs", "seo", "docker"])
    conn = _approved_conn(owner, helper, post["id"])
    with pytest.raises(GuildError, match="skills_covered"):
        helper.deliver(conn["id"], "Todo", "declarando fuera del post",
                       skills_covered=["docker"])
    assert reg.list_deliveries(conn["id"]) == []  # no se creó nada


def test_f1_declaration_without_post_rejected(reg):
    owner = _join(reg, "owner", ["python"])
    helper = _join(reg, "helper", ["python"])
    conn = _approved_conn(owner, helper, post_id=None)  # conexión sin post
    with pytest.raises(GuildError, match="skills_covered"):
        helper.deliver(conn["id"], "Suelto", "sin necesidad asociada",
                       skills_covered=["python"])


def test_f1_declaration_is_inside_the_signature(reg):
    """La declaración viaja dentro del hash firmado: ampliarla en la
    base (p. ej. para auto-verificarse más skills) invalida la firma
    y bloquea la aceptación."""
    owner = _join(reg, "owner", ["python"])
    post = owner.post_need("Web", "Montar la web", ["nextjs", "seo"],
                           need_type="capacidad")
    helper = _join(reg, "helper", ["nextjs", "seo"])
    conn = _approved_conn(owner, helper, post["id"])
    d = helper.deliver(conn["id"], "Solo SEO", "parte SEO",
                       skills_covered=["seo"])
    assert reg.verify_delivery(d["id"])["valid"] is True
    reg.db.execute("UPDATE deliveries SET skills_covered='[\"nextjs\", \"seo\"]'"
                   " WHERE id=?", (d["id"],))
    reg.db.commit()
    assert reg.verify_delivery(d["id"])["valid"] is False
    with pytest.raises(GuildError):
        owner.decide_delivery(d["id"], accept=True)
    assert helper.me()["verified_skills"] == []


def test_f1_skills_covered_http_roundtrip(http):
    base, _db = http
    owner = _join(None, "owner", ["python"], base_url=base)
    post = owner.post_need("Web", "Montar la web", ["nextjs", "seo"],
                           need_type="capacidad")
    helper = _join(None, "helper", ["nextjs", "seo"], base_url=base)
    conn = _approved_conn(owner, helper, post["id"])
    d = helper.deliver(conn["id"], "Solo SEO", "parte SEO",
                       skills_covered=["seo"])
    assert d["skills_covered"] == ["seo"]
    owner.decide_delivery(d["id"], accept=True)
    assert helper.me()["verified_skills"] == ["seo"]
    # Y fuera del post, la API responde 422 (vía GuildError del cliente).
    conn2 = _approved_conn(owner, helper, post["id"])
    with pytest.raises(GuildError, match="422"):
        helper.deliver(conn2["id"], "Mal", "declarando docker",
                       skills_covered=["docker"])


# ===================================================================== F2
def test_f2_close_frees_quota_author_only_idempotent(tmp_path):
    reg2 = Registry(tmp_path / "lim.db", limits={"max_open_posts": 2})
    try:
        ana = reg2.create_profile("ana", "Ana", skills_offered=[])
        otro = reg2.create_profile("otro", "Otro", skills_offered=[])
        p1 = reg2.create_post(ana["id"], "A", "tarea uno", [])
        reg2.create_post(ana["id"], "B", "tarea dos", [])
        with pytest.raises(GuildError):
            reg2.create_post(ana["id"], "C", "tarea tres", [])
        # Un tercero NO puede cerrar la necesidad de otro.
        with pytest.raises(GuildError, match="solo el autor"):
            reg2.close_post(p1["id"], author_id=otro["id"])
        cerrado = reg2.close_post(p1["id"], author_id=ana["id"])
        assert cerrado["status"] == "closed"
        # Idempotente: cerrar dos veces no es error ni cambia nada.
        assert reg2.close_post(p1["id"], author_id=ana["id"])["status"] == "closed"
        # El cupo se liberó: cabe otra.
        reg2.create_post(ana["id"], "C", "tarea tres", [])
        with pytest.raises(GuildError, match="inexistente"):
            reg2.close_post("no-existe", author_id=ana["id"])
    finally:
        reg2.close()


def test_f2_accepted_delivery_resolves_post(reg):
    owner = _join(reg, "owner", ["python"])
    post = owner.post_need("App", "Hacer la app", ["python"],
                           need_type="capacidad")
    helper = _join(reg, "helper", ["python"])
    conn = _approved_conn(owner, helper, post["id"])
    d = helper.deliver(conn["id"], "App hecha", "entregada")
    assert reg.get_post(post["id"])["status"] == "open"
    owner.decide_delivery(d["id"], accept=True)
    resuelto = reg.get_post(post["id"])
    assert resuelto["status"] == "resolved"
    # Fuera del tablón de abiertas y del contador anti-spam.
    assert all(p["id"] != post["id"] for p in reg.list_posts())
    assert reg.stats()["posts_open"] == 0


def test_f2_close_http_author_only(http):
    base, _db = http
    owner = _join(None, "owner", ["python"], base_url=base)
    post = owner.post_need("App", "Hacer la app", ["python"],
                           need_type="capacidad")
    otro = _join(None, "otro", ["python"], base_url=base)
    with pytest.raises(GuildError, match="403"):
        otro.close_post(post["id"])
    cerrado = owner.close_post(post["id"])
    assert cerrado["status"] == "closed"
    assert all(p["id"] != post["id"] for p in owner.board())


def test_f2_close_command(tmp_path, monkeypatch):
    monkeypatch.setenv("GUILD_DATA_DIR", str(tmp_path / "cmd"))
    import commands
    commands.guild_command('join @lee "Lee" muse skills=python idiomas=es')
    out = commands.guild_command(
        'post "Proyecto" "tarea acotada" skills=python tipo=capacidad')
    post_id = re.search(r"\(id ([0-9a-f]+)\)", out).group(1)
    assert post_id in commands.guild_command("board")
    out = commands.guild_command(f"close {post_id}")
    assert "cerrada" in out
    assert "Tablón vacío" in commands.guild_command("board")


# ===================================================================== F3
def _pending_conn(reg, requester_handle="marco", target_handle="lee"):
    lee = _join(reg, target_handle, ["python"])
    marco = _join(reg, requester_handle, ["baseten"])
    conn = marco.connect(lee.profile_id, message="puedo con eso")
    return lee, marco, conn


def test_f3_reason_reaches_requester(reg):
    lee, marco, conn = _pending_conn(reg)
    decidida = lee.approve_connection(conn["id"], approve=False,
                                      reason="ahora mismo no tengo capacidad")
    assert decidida["status"] == "rejected"
    assert decidida["rejection_reason"] == "ahora mismo no tengo capacidad"
    # El solicitante lo ve en la conexión misma…
    vista = marco.get_connection(conn["id"])
    assert vista["rejection_reason"] == "ahora mismo no tengo capacidad"
    # …y en su evento connection_decided.
    eventos = reg.events_for(marco.profile_id)["events"]
    decididos = [e for e in eventos if e["kind"] == "connection_decided"]
    assert decididos and decididos[0]["decision"] == "rejected"
    assert decididos[0]["reason"] == "ahora mismo no tengo capacidad"


def test_f3_reject_without_reason_unchanged(reg):
    lee, marco, conn = _pending_conn(reg)
    decidida = lee.approve_connection(conn["id"], approve=False)
    assert decidida["status"] == "rejected"
    assert decidida["rejection_reason"] == ""
    eventos = reg.events_for(marco.profile_id)["events"]
    decididos = [e for e in eventos if e["kind"] == "connection_decided"]
    assert decididos and "reason" not in decididos[0]


def test_f3_reason_too_long_rejected(reg):
    lee, marco, conn = _pending_conn(reg)
    with pytest.raises(GuildError, match="demasiado largo"):
        lee.approve_connection(conn["id"], approve=False, reason="x" * 281)
    # La conexión sigue pendiente: la decisión no se aplicó.
    assert reg.get_connection(conn["id"])["status"] == "pending"


def test_f3_reason_http(http):
    base, _db = http
    lee, marco, conn = None, None, None
    lee = _join(None, "lee", ["python"], base_url=base)
    marco = _join(None, "marco", ["baseten"], base_url=base)
    conn = marco.connect(lee.profile_id, message="puedo")
    lee.approve_connection(conn["id"], approve=False,
                           reason="tu oferta no encaja con la necesidad")
    vista = marco.get_connection(conn["id"])
    assert vista["status"] == "rejected"
    assert vista["rejection_reason"] == "tu oferta no encaja con la necesidad"


def test_f3_reason_via_command(tmp_path, monkeypatch):
    monkeypatch.setenv("GUILD_DATA_DIR", str(tmp_path / "cmd"))
    import commands
    from guild.paths import db_path
    commands.guild_command('join @lee "Lee" muse skills=python idiomas=es')
    regx = Registry(db_path())
    try:
        marco = regx.create_profile("marco", "Marco", skills_offered=["baseten"])
        lee_id = regx.get_profile_by_handle("lee")["id"]
        conn = regx.request_connection(marco["id"], lee_id, message="puedo")
    finally:
        regx.close()
    out = commands.guild_command(
        f"reject {conn['id']} no encaja con lo que pido ahora")
    assert "Motivo" in out and "no encaja con lo que pido ahora" in out
    regx = Registry(db_path())
    try:
        guardada = regx.get_connection(conn["id"])
        assert guardada["status"] == "rejected"
        assert guardada["rejection_reason"] == "no encaja con lo que pido ahora"
    finally:
        regx.close()


# ===================================================================== F4
def _encrypted_delivery(reg):
    """owner=lee ← helper=marco, entrega cifrada E2E íntegra."""
    lee = _join(reg, "lee", ["python"])
    marco = _join(reg, "marco", ["python"])
    conn = _approved_conn(lee, marco)
    d = marco.deliver(conn["id"], "Pack cifrado", "contenido sensible",
                      payload="contenido secreto del enjambre")
    return lee, marco, conn, d


def _flip_first_hex(texto: str) -> str:
    return ("0" if texto[0] != "0" else "1") + texto[1:]


def test_f4_intact_envelope_accepts(reg):
    lee, _marco, _conn, d = _encrypted_delivery(reg)
    ver = reg.verify_delivery(d["id"])
    assert ver["valid"] is True and ver["envelope_ok"] is True
    aceptada = lee.decide_delivery(d["id"], accept=True)
    assert aceptada["status"] == "accepted"


def test_f4_tampered_envelope_blocks_acceptance_local(reg):
    """El ataque del enjambre, ahora también en la ACEPTACIÓN: la
    firma sigue «válida» (cubre la referencia), pero el sobre
    almacenado ya no es el firmado → el registro no acepta."""
    lee, _marco, _conn, d = _encrypted_delivery(reg)
    guardada = reg.get_delivery(d["id"])
    reg.db.execute("UPDATE deliveries SET enc_ciphertext=? WHERE id=?",
                   (_flip_first_hex(guardada["enc_ciphertext"]), d["id"]))
    reg.db.commit()
    ver = reg.verify_delivery(d["id"])
    assert ver["valid"] is True        # la firma autentica la referencia
    assert ver["envelope_ok"] is False  # …pero el sobre ya no es ese
    with pytest.raises(GuildError, match="huella del sobre"):
        reg.decide_delivery(d["id"], accept=True)
    assert reg.get_delivery(d["id"])["status"] == "proposed"


def test_f4_client_decrypt_on_accept_refuses_tampered(reg):
    """El cliente del dueño, con su clave, descifra ANTES de aceptar:
    el sobre manipulado muere en el MAC sin llegar a la decisión."""
    lee, _marco, _conn, d = _encrypted_delivery(reg)
    guardada = reg.get_delivery(d["id"])
    reg.db.execute("UPDATE deliveries SET enc_ciphertext=? WHERE id=?",
                   (_flip_first_hex(guardada["enc_ciphertext"]), d["id"]))
    reg.db.commit()
    with pytest.raises(GuildError, match="MAC"):
        lee.decide_delivery(d["id"], accept=True)
    assert reg.get_delivery(d["id"])["status"] == "proposed"


def test_f4_tampered_envelope_blocks_acceptance_http_409(http):
    """La misma exigencia en el servidor HTTP, aislada del cliente:
    se decide con una llamada cruda (sin el descifrado previo del
    GuildClient) y la respuesta es 409."""
    base, db = http
    lee = _join(None, "lee", ["python"], base_url=base)
    marco = _join(None, "marco", ["python"], base_url=base)
    conn = _approved_conn(lee, marco)
    d = marco.deliver(conn["id"], "Pack cifrado", "contenido",
                      payload="secreto http")
    guardada = lee.get_delivery(d["id"])
    con = sqlite3.connect(str(db))
    con.execute("UPDATE deliveries SET enc_ciphertext=? WHERE id=?",
                (_flip_first_hex(guardada["enc_ciphertext"]), d["id"]))
    con.commit()
    con.close()
    with pytest.raises(GuildError, match="409"):
        lee._http("POST", f"/v1/deliveries/{d['id']}/decide",
                  {"accept": True, "notes": "intento directo"})
    assert lee.get_delivery(d["id"])["status"] == "proposed"


# ===================================================================== F5
def test_f5_injected_clock_ages_presence_and_breaks_tie(reg, monkeypatch):
    """El experimento de gemelos del enjambre, en milisegundos: sin
    desplazamiento ambos están «online» y manda el handle; con
    +305 s y heartbeat solo del segundo, el primero envejece a
    «recent» y la presencia — sin tocar la puntuación — lo reordena."""
    monkeypatch.delenv("GUILD_DEV_TIME_OFFSET_S", raising=False)
    seeker = _join(reg, "seeker", ["diseno-3d"])
    aaa = _join(reg, "aaa", ["react"])  # gemelo silencioso (handle primero)
    zzz = _join(reg, "zzz", ["react"])  # gemelo que sigue latiendo
    post = seeker.post_need("Web", "Componentes React", ["react"],
                            need_type="capacidad")
    orden0 = [m["handle"] for m in matching.find_matches(reg, post["id"], limit=10)
              if m["handle"] in ("aaa", "zzz")]
    assert orden0 == ["aaa", "zzz"]  # empate y ambos online: handle
    assert reg.get_profile(aaa.profile_id)["presence"] == "online"

    monkeypatch.setenv("GUILD_DEV_TIME_OFFSET_S", "305")
    reg.heartbeat(zzz.profile_id)  # solo zzz late en el «futuro»
    assert reg.get_profile(aaa.profile_id)["presence"] == "recent"
    assert reg.get_profile(zzz.profile_id)["presence"] == "online"
    found = {m["handle"]: m for m in matching.find_matches(reg, post["id"], limit=10)}
    assert found["aaa"]["score"] == found["zzz"]["score"]  # la cifra NO se mueve
    orden1 = [m["handle"] for m in matching.find_matches(reg, post["id"], limit=10)
              if m["handle"] in ("aaa", "zzz")]
    assert orden1 == ["zzz", "aaa"]  # la presencia decide, como en los 305 s reales


def test_f5_without_offset_the_clock_is_real(reg, monkeypatch):
    monkeypatch.delenv("GUILD_DEV_TIME_OFFSET_S", raising=False)
    p = _join(reg, "nuevo", ["python"])
    assert reg.get_profile(p.profile_id)["presence"] == "online"
