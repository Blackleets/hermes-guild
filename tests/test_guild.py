"""Tests offline de GUILD — sin red, sin Hermes instalado.

Run:  .venv/bin/python -m pytest tests/ -q   (o: python3 tests/test_guild.py)
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from guild import matching  # noqa: E402
from guild.client import GuildClient  # noqa: E402
from guild.registry import GuildError, Registry  # noqa: E402
from guild.taxonomy import TAXONOMY, category_of, normalize  # noqa: E402


@pytest.fixture()
def reg(tmp_path):
    r = Registry(tmp_path / "t.db")
    yield r
    r.close()


def mk(reg, handle, skills, langs=("es",), platform="hermes"):
    return reg.create_profile(handle, handle.title(), platform=platform,
                              skills_offered=skills, languages=list(langs),
                              timezone="Europe/Madrid")


# ---------------------------------------------------------------- taxonomy
def test_taxonomy_covers_key_skills():
    for skill in ("twilio-voz", "whatsapp-api", "nextjs", "python", "diseno-3d",
                  "video-ia", "trading-algoritmico", "supabase", "baseten"):
        assert category_of(skill) is not None, skill
    assert len(TAXONOMY) >= 8
    assert normalize(" Twilio_Voz ") == "twilio-voz"


# ---------------------------------------------------------------- perfiles
def test_join_creates_profile_with_api_key(reg):
    p = mk(reg, "lee", ["python"])
    assert p["handle"] == "lee"
    assert p["reputation_score"] == 0 and p["ratings_count"] == 0
    assert p["api_key"].startswith("guild_")
    assert "api_key" not in reg.get_profile(p["id"])  # no se vuelve a exponer
    assert reg.verify_api_key(p["id"], p["api_key"])
    assert not reg.verify_api_key(p["id"], "guild_wrong")


def test_duplicate_handle_rejected(reg):
    mk(reg, "lee", [])
    with pytest.raises(GuildError):
        mk(reg, "@LEE", [])


# -------------------------------------------------------------------- posts
def test_post_requires_scoped_task(reg):
    lee = mk(reg, "lee", [])
    with pytest.raises(GuildError):
        reg.create_post(lee["id"], "Proyecto", "   ", ["python"])
    post = reg.create_post(lee["id"], "La Asistenta", "Desplegar FASHN en Baseten",
                           ["baseten", "python"])
    assert post["status"] == "open"
    board = reg.list_posts()
    assert board[0]["author_handle"] == "lee"


# ----------------------------------------------------------------- matching
def test_matching_ordered_and_explained(reg):
    lee = mk(reg, "lee", ["python"], platform="muse")
    marco = mk(reg, "marco", ["baseten", "python", "docker"], platform="hermes")
    ana = mk(reg, "ana", ["figma"], langs=("en",), platform="openclaw")
    reg.add_rating(ana["id"], marco["id"], 5, 5, 4)  # marco con reputación
    post = reg.create_post(lee["id"], "La Asistenta", "Desplegar FASHN en Baseten",
                           ["baseten", "python"])
    found = matching.find_matches(reg, post["id"], limit=3)
    assert found[0]["handle"] == "marco"
    assert found[0]["score"] > found[-1]["score"]
    assert any("baseten" in r for r in found[0]["reasons"])
    # Ponderación v2 (protocolo v1.1): skills 50 · idioma 12 · reputación 20
    # · zona horaria 8 · reciprocidad 10. La v1 ponderaba 60/15/25.
    assert found[0]["breakdown"]["skills"] == 50.0
    assert found[0]["breakdown"]["language"] == 12.0
    assert set(found[0]["breakdown"]) == {"skills", "language", "reputation",
                                          "timezone", "reciprocity"}
    assert found[0]["score"] == round(sum(found[0]["breakdown"].values()), 1)
    assert all(m["handle"] != "lee" for m in found)  # el autor nunca se propone


def test_paused_profile_excluded_from_matches(reg):
    lee = mk(reg, "lee", [])
    marco = mk(reg, "marco", ["baseten"])
    reg.set_paused(marco["id"], True)
    post = reg.create_post(lee["id"], "X", "Ayuda Baseten", ["baseten"])
    assert matching.find_matches(reg, post["id"]) == []


# --------------------------------------------------------------- conexiones
def test_no_channel_without_approval(reg):
    lee = mk(reg, "lee", [])
    marco = mk(reg, "marco", ["baseten"])
    conn = reg.request_connection(marco["id"], lee["id"], message="puedo ayudar")
    assert conn["status"] == "pending"
    assert reg.can_open_channel(conn["id"]) is False
    with pytest.raises(GuildError):
        reg.create_delivery(conn["id"], marco["id"], "Parche", "resumen")
    reg.decide_connection(conn["id"], approve=True)
    assert reg.can_open_channel(conn["id"]) is True


def test_rejected_connection_stays_closed(reg):
    lee = mk(reg, "lee", [])
    marco = mk(reg, "marco", [])
    conn = reg.request_connection(marco["id"], lee["id"])
    reg.decide_connection(conn["id"], approve=False)
    assert reg.can_open_channel(conn["id"]) is False


# ---------------------------------------------------------------- entregas
def _approved_pair(reg):
    lee = mk(reg, "lee", [])
    marco = mk(reg, "marco", ["baseten"])
    conn = reg.request_connection(marco["id"], lee["id"])
    reg.decide_connection(conn["id"], approve=True)
    return lee, marco, conn


def test_delivery_not_applied_until_owner_accepts(reg):
    lee, marco, conn = _approved_pair(reg)
    d = reg.create_delivery(conn["id"], marco["id"], "Truss Baseten corregido", "resumen")
    assert d["status"] == "proposed" and d["applied"] is False
    d2 = reg.decide_delivery(d["id"], accept=True)
    assert d2["status"] == "accepted" and d2["applied"] is True


def test_delivery_returned_is_not_applied(reg):
    lee, marco, conn = _approved_pair(reg)
    d = reg.create_delivery(conn["id"], marco["id"], "Borrador", "resumen")
    d2 = reg.decide_delivery(d["id"], accept=False, owner_notes="falta el healthcheck")
    assert d2["status"] == "returned" and d2["applied"] is False
    assert d2["owner_notes"] == "falta el healthcheck"


# --------------------------------------------------------------- reputación
def test_reputation_updates_after_rating(reg):
    lee, marco, conn = _approved_pair(reg)
    before = reg.get_profile(marco["id"])
    assert before["reputation_score"] == 0
    after = reg.add_rating(lee["id"], marco["id"], 5, 5, 5, connection_id=conn["id"])
    assert after["reputation_score"] == 5.0 and after["ratings_count"] == 1
    after2 = reg.add_rating(lee["id"], marco["id"], 3, 3, 3, connection_id=conn["id"])
    assert after2["reputation_score"] == 4.0 and after2["ratings_count"] == 2


def test_rating_out_of_range_rejected(reg):
    lee = mk(reg, "lee", [])
    marco = mk(reg, "marco", [])
    with pytest.raises(GuildError):
        reg.add_rating(lee["id"], marco["id"], 9, 5, 5)


# ----------------------------------------------------------------- bloqueo
def test_block_prevents_connection(reg):
    lee = mk(reg, "lee", [])
    spammer = mk(reg, "spammer", [])
    reg.block(lee["id"], spammer["id"], reason="spam")
    assert reg.is_blocked_either_way(lee["id"], spammer["id"])
    with pytest.raises(GuildError):
        reg.request_connection(spammer["id"], lee["id"])
    with pytest.raises(GuildError):
        reg.request_connection(lee["id"], spammer["id"])


def test_blocked_excluded_from_matches(reg):
    lee = mk(reg, "lee", [])
    marco = mk(reg, "marco", ["baseten"])
    reg.block(lee["id"], marco["id"])
    post = reg.create_post(lee["id"], "X", "Ayuda Baseten", ["baseten"])
    assert matching.find_matches(reg, post["id"]) == []


# ------------------------------------------------------------------ cliente
def test_client_full_flow(reg):
    lee = GuildClient(registry=reg)
    lee.join("lee", "Lee Renteria", "muse", skills_offered=["python"], languages=["es"])
    marco = GuildClient(registry=reg)
    marco.join("marco", "Marco", "hermes", skills_offered=["baseten", "python"],
               languages=["es"])
    post = lee.post_need("La Asistenta", "Desplegar FASHN en Baseten", ["baseten", "python"])
    found = lee.matches_for(post["id"])
    assert found[0]["handle"] == "marco"
    conn = marco.connect(lee.profile_id, post_id=post["id"], message="lo he hecho antes")
    assert marco.channel_open(conn["id"]) is False
    lee.approve_connection(conn["id"], approve=True)
    assert marco.channel_open(conn["id"]) is True
    d = marco.deliver(conn["id"], "Despliegue FASHN", "truss + endpoint verificados")
    assert d["applied"] is False
    lee.decide_delivery(d["id"], accept=True)
    prof = lee.rate(marco.profile_id, 5, 5, 5, connection_id=conn["id"])
    assert prof["reputation_score"] == 5.0


# ----------------------------------------------------------------- comandos
def test_commands_join_and_board(tmp_path, monkeypatch):
    monkeypatch.setenv("GUILD_DATA_DIR", str(tmp_path))
    sys.path.insert(0, str(ROOT))
    import commands
    out = commands.guild_command('join @lee "Lee Renteria" muse skills=python,baseten idiomas=es tz=Europe/Madrid')
    assert "Bienvenido a GUILD" in out
    # v0.3: el post exige tipo= (cambio de spec, como el peso de matching
    # en v0.2); el test se actualiza al contrato nuevo.
    out = commands.guild_command('post "La Asistenta" "Desplegar FASHN en Baseten" skills=baseten tipo=experiencia')
    assert "Necesidad publicada" in out
    out = commands.guild_command("board")
    assert "La Asistenta" in out
    out = commands.guild_command("")
    assert "@lee" in out


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))


# ============================================================ v0.2: identidad
from guild import identity  # noqa: E402


def test_ed25519_rfc8032_vector():
    # Vector oficial RFC 8032 (TEST 2): clave y firma deterministas.
    seed = "4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb"
    pk = "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c"
    assert identity.public_key_of(seed) == pk
    sig = identity.sign(seed, "r")  # el mensaje del vector es el byte 0x72
    assert sig.startswith("92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da")
    assert identity.verify(pk, "r", sig)


def test_ed25519_sign_verify_roundtrip_and_tamper():
    kp = identity.generate_keypair()
    sig = identity.sign(kp["private_key"], "entrega para @lee")
    assert identity.verify(kp["public_key"], "entrega para @lee", sig)
    assert not identity.verify(kp["public_key"], "entrega MANIPULADA", sig)
    other = identity.generate_keypair()
    assert not identity.verify(other["public_key"], "entrega para @lee", sig)
    assert not identity.verify(kp["public_key"], "entrega para @lee", "00" * 64)


def test_profile_public_key_is_ed25519_of_private(reg):
    p = mk(reg, "lee", [])
    assert identity.public_key_of(p["private_key"]) == p["public_key"]


# ====================================================== v0.2: entregas firmadas
def test_signed_delivery_verifies_and_tamper_fails(reg):
    lee = GuildClient(registry=reg)
    lee.join("lee", "Lee", "muse", skills_offered=["python"], languages=["es"])
    marco = GuildClient(registry=reg)
    marco.join("marco", "Marco", "hermes", skills_offered=["baseten"], languages=["es"])
    conn = marco.connect(lee.profile_id, message="puedo")
    lee.approve_connection(conn["id"], approve=True)
    d = marco.deliver(conn["id"], "Truss corregido", "resumen honesto", "ref-1")
    assert d["signature"] and d["content_hash"]
    # v0.6.1 (F4): verify_delivery añade `envelope_ok` (None aquí: la
    # entrega no va cifrada). La aserción exacta se actualiza por la
    # extensión declarada del contrato, no por un cambio de la firma.
    assert reg.verify_delivery(d["id"]) == {"exists": True, "signed": True,
                                            "valid": True, "envelope_ok": None}
    # Manipulación posterior en la base: la huella ya no coincide.
    reg.db.execute("UPDATE deliveries SET summary='resumen MANIPULADO' WHERE id=?", (d["id"],))
    reg.db.commit()
    assert reg.verify_delivery(d["id"])["valid"] is False
    with pytest.raises(GuildError):
        lee.decide_delivery(d["id"], accept=True)


def test_delivery_signed_by_impostor_rejected(reg):
    lee, marco, conn = _approved_pair(reg)
    impostor = identity.generate_keypair()
    chash = Registry.content_hash_of(conn["id"], marco["id"], "Falso", "x", "")
    fake_sig = identity.sign(impostor["private_key"], chash)
    with pytest.raises(GuildError):
        reg.create_delivery(conn["id"], marco["id"], "Falso", "x", "",
                            content_hash=chash, signature=fake_sig)


# ==================================================== v0.2: reputación dimensional
def test_reputation_detail_breakdown(reg):
    lee, marco, conn = _approved_pair(reg)
    reg.add_rating(lee["id"], marco["id"], 5, 3, 4, connection_id=conn["id"])
    prof = reg.add_rating(lee["id"], marco["id"], 4, 4, 2, connection_id=conn["id"])
    det = prof["reputation_detail"]
    assert det["count"] == 2
    assert det["useful"] == 4.5 and det["clear"] == 3.5 and det["on_time"] == 3.0
    assert det["overall"] == 3.67  # (12 + 10) / 6, la media global de siempre
    assert prof["reputation_score"] == 3.67


# ========================================================= v0.2: matching v2
def test_matching_resolves_aliases(reg):
    lee = mk(reg, "lee", ["python"], platform="muse")
    voz = mk(reg, "vozdev", ["voz"], platform="hermes")       # «voz» = agentes-de-voz
    trader = mk(reg, "trader", ["markets"], platform="hermes")  # «markets» = trading-algoritmico
    post = reg.create_post(lee["id"], "La Asistenta", "Agente de voz y señales",
                           ["agentes-de-voz", "trading-algoritmico"])
    found = {m["handle"]: m for m in matching.find_matches(reg, post["id"], limit=5)}
    assert found["vozdev"]["breakdown"]["skills"] == 25.0  # cubre 1/2 vía alias
    assert any("alias" in r for r in found["vozdev"]["reasons"])
    assert found["trader"]["breakdown"]["skills"] == 25.0


def test_matching_timezone_bonus(reg):
    lee = mk(reg, "lee", [])
    cerca = mk(reg, "cerca", ["baseten"])  # Europe/Madrid, igual que Lee
    lejos = reg.create_profile("lejos", "Lejos", platform="hermes",
                               skills_offered=["baseten"], languages=["es"],
                               timezone="America/New_York")
    londres = reg.create_profile("londres", "Londres", platform="hermes",
                                 skills_offered=["baseten"], languages=["es"],
                                 timezone="Europe/London")
    post = reg.create_post(lee["id"], "X", "Ayuda Baseten", ["baseten"])
    found = {m["handle"]: m for m in matching.find_matches(reg, post["id"], limit=5)}
    assert found["cerca"]["breakdown"]["timezone"] == 8.0
    # Londres está a Δ1h de Madrid todo el año; UTC+0 NO es «sin zona».
    assert found["londres"]["breakdown"]["timezone"] == 7.3
    assert found["lejos"]["breakdown"]["timezone"] < 8.0
    assert any("zona horaria" in r for r in found["cerca"]["reasons"])


def test_matching_reciprocity_bonus(reg):
    lee = mk(reg, "lee", ["twilio-voz"], platform="muse")  # Lee OFRECE voz
    marco = reg.create_profile("marco", "Marco", platform="hermes",
                               skills_offered=["baseten"], skills_wanted=["twilio-voz"],
                               languages=["es"], timezone="Europe/Madrid")
    post = reg.create_post(lee["id"], "La Asistenta", "Desplegar en Baseten", ["baseten"])
    found = matching.find_matches(reg, post["id"], limit=3)
    assert found[0]["handle"] == "marco"
    assert found[0]["breakdown"]["reciprocity"] == 10.0
    assert any("reciprocidad" in r for r in found[0]["reasons"])


# ========================================================= v0.2: anti-spam
def test_limit_open_posts(tmp_path):
    reg2 = Registry(tmp_path / "lim.db", limits={"max_open_posts": 2})
    try:
        lee = reg2.create_profile("lee", "Lee", skills_offered=[])
        reg2.create_post(lee["id"], "A", "tarea uno", [])
        reg2.create_post(lee["id"], "B", "tarea dos", [])
        with pytest.raises(GuildError):
            reg2.create_post(lee["id"], "C", "tarea tres", [])
        reg2.close_post(reg2.list_posts()[0]["id"])
        reg2.create_post(lee["id"], "C", "tarea tres", [])  # al cerrar, cabe otra
    finally:
        reg2.close()


def test_limit_connection_requests_per_day(tmp_path):
    reg2 = Registry(tmp_path / "lim2.db", limits={"max_connection_requests_day": 2})
    try:
        a = reg2.create_profile("a", "A")
        b = reg2.create_profile("b", "B")
        c = reg2.create_profile("c", "C")
        reg2.request_connection(a["id"], b["id"])
        reg2.request_connection(a["id"], c["id"])
        with pytest.raises(GuildError):
            reg2.request_connection(a["id"], b["id"])
    finally:
        reg2.close()


def test_reports_from_distinct_profiles_suspend(reg):
    malo = mk(reg, "malo", ["baseten"])
    lee = mk(reg, "lee", [])
    for i in range(2):
        r = mk(reg, f"rep{i}", [])
        reg.report(r["id"], malo["id"], reason="spam")
    assert reg.get_profile(malo["id"])["suspended"] is False  # aún bajo el umbral (3)
    r3 = mk(reg, "rep2", [])
    reg.report(r3["id"], malo["id"], reason="spam")
    assert reg.get_profile(malo["id"])["suspended"] is True
    # Suspendido = fuera del matching y sin poder publicar.
    post = reg.create_post(lee["id"], "X", "Ayuda Baseten", ["baseten"])
    handles = [m["handle"] for m in matching.find_matches(reg, post["id"], limit=10)]
    assert "malo" not in handles
    with pytest.raises(GuildError):
        reg.create_post(malo["id"], "Y", "otra tarea", [])
    kinds = [e["kind"] for e in reg.list_events(limit=100)]
    assert "reported" in kinds and "suspended" in kinds


def test_events_are_logged(reg):
    lee, marco, conn = _approved_pair(reg)
    kinds = [e["kind"] for e in reg.list_events(limit=100)]
    for expected in ("profile_created", "connection_requested", "connection_approved"):
        assert expected in kinds


# ========================================================= v0.2: servidor HTTP
import threading  # noqa: E402

from guild.server import make_server  # noqa: E402


@pytest.fixture()
def http_url(tmp_path):
    server = make_server(tmp_path / "net.db", port=0)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    server.server_close()
    server.registry.close()


def test_http_full_flow_three_platforms(http_url):
    lee = GuildClient(base_url=http_url)
    lee.join("lee", "Lee Renteria", "muse", skills_offered=["python", "twilio-voz"],
             skills_wanted=["baseten"], languages=["es"], timezone="Europe/Madrid")
    marco = GuildClient(base_url=http_url)
    marco.join("marco", "Marco", "hermes", skills_offered=["baseten", "python"],
               skills_wanted=["twilio-voz"], languages=["es"], timezone="Europe/Berlin")
    ana = GuildClient(base_url=http_url)
    ana.join("ana", "Ana", "openclaw", skills_offered=["figma"], languages=["en"],
             timezone="Europe/London")
    assert lee.heartbeat() == {"ok": True}

    post = lee.post_need("La Asistenta", "Desplegar FASHN en Baseten", ["baseten", "python"])
    assert any(p["id"] == post["id"] for p in ana.board())
    found = lee.matches_for(post["id"])
    assert found[0]["handle"] == "marco"

    conn = marco.connect(lee.profile_id, post_id=post["id"], message="lo he hecho antes")
    assert marco.channel_open(conn["id"]) is False
    with pytest.raises(GuildError):
        marco.deliver(conn["id"], "Demasiado pronto", "sin canal")
    lee.approve_connection(conn["id"], approve=True)
    assert marco.channel_open(conn["id"]) is True

    d = marco.deliver(conn["id"], "Truss FASHN verificado", "healthcheck ok", "ref-net-1")
    assert d["signature"] and d["applied"] is False
    assert marco.verify_delivery(d["id"])["valid"] is True
    lee.decide_delivery(d["id"], accept=True, notes="verificado")

    prof = lee.rate(marco.profile_id, 5, 5, 4, connection_id=conn["id"])
    assert prof["reputation_score"] == 4.67
    assert prof["reputation_detail"]["on_time"] == 4.0
    st = ana.status()
    assert st["network"]["profiles"] == 3 and st["network"]["deliveries_accepted"] == 1


def test_http_requires_valid_api_key(http_url):
    intruso = GuildClient(base_url=http_url, api_key="guild_clave_falsa",
                          profile_id="quiensea")
    with pytest.raises(GuildError):
        intruso.me()


def test_http_only_owner_decides(http_url):
    a = GuildClient(base_url=http_url)
    a.join("a", "A", "hermes", skills_offered=["python"], languages=["es"])
    b = GuildClient(base_url=http_url)
    b.join("b", "B", "muse", skills_offered=["baseten"], languages=["es"])
    conn = b.connect(a.profile_id, message="ayudo")
    with pytest.raises(GuildError):  # quien pide no puede auto-aprobarse
        b.approve_connection(conn["id"], approve=True)
    a.approve_connection(conn["id"], approve=True)
    d = b.deliver(conn["id"], "Trabajo", "resumen")
    with pytest.raises(GuildError):  # el autor no puede aceptar su propia entrega
        b.decide_delivery(d["id"], accept=True)
    a.decide_delivery(d["id"], accept=True)


# ==================================================== v0.3: tipos de necesidad
from guild.needs import NEED_TYPES, looks_like_knowledge_question  # noqa: E402


def test_need_types_are_the_five_non_self_serviceable():
    assert set(NEED_TYPES) == {"experiencia", "activo", "revision",
                               "capacidad", "local"}
    for info in NEED_TYPES.values():
        assert info["label"] and info["description"]


def test_post_stores_need_type_and_validates(reg):
    lee = mk(reg, "lee", [])
    post = reg.create_post(lee["id"], "La Asistenta", "Desplegar en Baseten",
                           ["baseten"], need_type="experiencia")
    assert post["need_type"] == "experiencia"
    assert reg.get_post(post["id"])["need_type"] == "experiencia"
    board = reg.list_posts()
    assert board[0]["need_type"] == "experiencia"
    with pytest.raises(GuildError):
        reg.create_post(lee["id"], "X", "otra tarea", [], need_type="magia")


def test_post_default_need_type_is_capacidad(reg):
    lee = mk(reg, "lee", [])
    post = reg.create_post(lee["id"], "X", "tarea genérica", [])
    assert post["need_type"] == "capacidad"


def test_knowledge_question_gets_hint_but_still_publishes(reg):
    lee = mk(reg, "lee", [])
    assert looks_like_knowledge_question("¿Cómo funciona el healthcheck?")
    assert not looks_like_knowledge_question("Desplegar FASHN en Baseten")
    post = reg.create_post(lee["id"], "Duda", "¿Qué es un truss de Baseten?",
                           [], need_type="experiencia")
    # Aviso, NO bloqueo: el post existe y el aviso viene en la respuesta.
    assert post["status"] == "open"
    assert post["self_help_hint"] and "tu propio agente" in post["self_help_hint"]
    post2 = reg.create_post(lee["id"], "La Asistenta", "Desplegar FASHN en Baseten",
                            ["baseten"], need_type="experiencia")
    assert post2["self_help_hint"] is None


def test_commands_post_requires_tipo_and_shows_hint(tmp_path, monkeypatch):
    monkeypatch.setenv("GUILD_DATA_DIR", str(tmp_path / "cmd"))
    import commands
    commands.guild_command('join @lee "Lee Renteria" muse skills=python idiomas=es')
    out = commands.guild_command('post "X" "Tarea sin tipo" skills=python')
    assert "Falta el tipo de necesidad" in out
    out = commands.guild_command(
        'post "Duda" "¿Cómo se despliega en Baseten?" skills=baseten tipo=experiencia')
    assert "Necesidad publicada" in out
    assert "Experiencia en producción" in out
    assert "tu propio agente" in out  # el aviso anti-ruido, visible
    out = commands.guild_command("board")
    assert "tipo: Experiencia en producción" in out


# ============================================ v0.3: habilidades verificadas
def _flow_with_delivery(reg, accept=True):
    """Lee postea (post con skills) → Marco conecta → entrega → decisión."""
    lee = GuildClient(registry=reg)
    lee.join("lee", "Lee", "muse", skills_offered=["python"], languages=["es"],
             timezone="Europe/Madrid")
    marco = GuildClient(registry=reg)
    marco.join("marco", "Marco", "hermes",
               skills_offered=["baseten", "python", "docker"], languages=["es"],
               timezone="Europe/Berlin")
    post = lee.post_need("La Asistenta", "Desplegar FASHN en Baseten",
                         ["baseten", "python"], need_type="experiencia")
    conn = marco.connect(lee.profile_id, post_id=post["id"], message="puedo")
    lee.approve_connection(conn["id"], approve=True)
    d = marco.deliver(conn["id"], "Truss verificado", "healthcheck ok")
    if accept is not None:
        lee.decide_delivery(d["id"], accept=accept)
    return lee, marco, post


def test_no_verified_skills_without_accepted_delivery(reg):
    lee = GuildClient(registry=reg)
    lee.join("lee", "Lee", "muse", skills_offered=["baseten"], languages=["es"])
    # Auto-declarada en el perfil, pero sin entregas: NO verificada.
    assert lee.me()["skills_offered"] == ["baseten"]
    assert lee.me()["verified_skills"] == []
    assert lee.me()["collaborations"] == 0


def test_verified_skills_after_accepted_delivery(reg):
    lee, marco, post = _flow_with_delivery(reg, accept=True)
    prof = marco.me()
    assert prof["verified_skills"] == ["baseten", "python"]
    assert prof["collaborations"] == 1
    assert lee.me()["collaborations"] == 1  # el dueño también colaboró
    assert lee.me()["verified_skills"] == []  # Lee no entregó nada


def test_returned_delivery_does_not_verify(reg):
    lee, marco, post = _flow_with_delivery(reg, accept=False)
    assert marco.me()["verified_skills"] == []
    assert marco.me()["collaborations"] == 0


def test_matching_verified_subbonus_within_skills_factor(reg):
    lee, marco, post = _flow_with_delivery(reg, accept=True)
    # Nueva necesidad de OTRO builder que pide solo docker (Marco cubre
    # 1/2 vía el post nuevo): el sub-bonus se ve porque docker NO está
    # entre las verificadas de Marco (baseten, python) → sin bonus.
    otro = GuildClient(registry=reg)
    otro.join("otro", "Otro", "hermes", skills_offered=["python"], languages=["es"],
              timezone="Europe/Madrid")
    post2 = otro.post_need("Infra", "Montar CI y despliegue Baseten",
                           ["baseten", "docker"], need_type="capacidad")
    found = {m["handle"]: m for m in matching.find_matches(reg, post2["id"], limit=5)}
    # Marco cubre 2/2 → base 50, factor capado en 50 (el bonus no infla).
    assert found["marco"]["breakdown"]["skills"] == 50.0
    # Y en un post donde cubre solo lo verificado a medias, el bonus suma:
    post3 = otro.post_need("Infra2", "Baseten y diseño 3D",
                           ["baseten", "diseno-3d"], need_type="capacidad")
    found3 = {m["handle"]: m for m in matching.find_matches(reg, post3["id"], limit=5)}
    # cubre 1/2 (baseten, verificado) → 25 base + 2.5 sub-bonus = 27.5
    assert found3["marco"]["breakdown"]["skills"] == 27.5
    assert any("verificado por entregas aceptadas" in r
               for r in found3["marco"]["reasons"])
    # Los pesos totales no cambian: el desglose sigue sumando el total.
    assert found3["marco"]["score"] == round(
        sum(found3["marco"]["breakdown"].values()), 1)


# ============================================ v0.3: reputación portable firmada
from guild.portable import verify_export  # noqa: E402


def test_reputation_export_signs_and_verifies(reg):
    lee, marco, post = _flow_with_delivery(reg, accept=True)
    lee.rate(marco.profile_id, 5, 5, 4)
    export = marco.export_reputation()
    assert export["format"] == "guild-reputation/v1"
    assert export["handle"] == "marco"
    assert export["reputation"]["overall"] == 4.67
    assert export["reputation"]["on_time"] == 4.0
    assert export["collaborations"] == 1
    assert export["verified_skills"] == ["baseten", "python"]
    assert export["signature"]
    res = verify_export(export)
    assert res["signature_valid"] is True and res["valid"] is True
    assert res["key_trusted"] is None  # sin clave fijada: nivel débil, declarado
    stats = reg.stats()
    res2 = verify_export(export, trusted_registry_key=stats["registry_public_key"])
    assert res2["key_trusted"] is True and res2["valid"] is True
    res3 = verify_export(export, trusted_registry_key="00" * 32)
    assert res3["key_trusted"] is False and res3["valid"] is False


def test_reputation_export_tamper_detected(reg):
    lee, marco, post = _flow_with_delivery(reg, accept=True)
    export = marco.export_reputation()
    export["reputation"] = dict(export["reputation"], overall=5.0)  # inflar la nota
    res = verify_export(export)
    assert res["signature_valid"] is False and res["valid"] is False
    export2 = marco.export_reputation()
    export2["verified_skills"] = ["baseten", "python", "trading-algoritmico"]
    assert verify_export(export2)["valid"] is False  # habilidad inventada


def test_reputation_export_self_signed_forgery_needs_trusted_key(reg):
    # Un atacante se autofirma un export perfecto con SU clave: la
    # comprobación débil pasa (firma consistente), la fuerte lo caza.
    from guild import identity as _identity
    from guild.portable import sign_export
    kp = _identity.generate_keypair()
    fake = {"format": "guild-reputation/v1", "handle": "farsante",
            "display_name": "Farsante", "platform": "hermes",
            "reputation": {"overall": 5.0, "count": 99, "useful": 5.0,
                           "clear": 5.0, "on_time": 5.0},
            "collaborations": 99, "verified_skills": ["baseten"],
            "registry_public_key": kp["public_key"], "issued_at": 1}
    fake = sign_export(fake, kp["private_key"])
    assert verify_export(fake)["signature_valid"] is True       # débil: consistente
    reg_key = reg.stats()["registry_public_key"]
    res = verify_export(fake, trusted_registry_key=reg_key)
    assert res["key_trusted"] is False and res["valid"] is False  # fuerte: cazado


# ==================================================== v0.3: servidor HTTP
import json as _json  # noqa: E402
import urllib.error  # noqa: E402
import urllib.request  # noqa: E402


def test_http_need_type_required_and_export_endpoint(http_url):
    lee = GuildClient(base_url=http_url)
    lee.join("lee", "Lee", "muse", skills_offered=["python"], languages=["es"])
    marco = GuildClient(base_url=http_url)
    marco.join("marco", "Marco", "hermes", skills_offered=["baseten"],
               languages=["es"])
    # Sin need_type en crudo → el servidor exige el tipo: 422.
    req = urllib.request.Request(http_url + "/v1/posts", method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {lee.api_key}")
    body = _json.dumps({"project": "X", "task": "tarea",
                        "required_skills": []}).encode()
    with pytest.raises(urllib.error.HTTPError) as ei:
        urllib.request.urlopen(req, data=body, timeout=10)
    assert ei.value.code == 422
    # Tipo inválido → también 422 vía cliente.
    with pytest.raises(GuildError):
        lee.post_need("X", "tarea", [], need_type="magia")
    # Con tipo válido por el cliente, fluye; y el export viaja firmado.
    post = lee.post_need("La Asistenta", "Desplegar en Baseten", ["baseten"],
                         need_type="experiencia")
    assert post["need_type"] == "experiencia"
    conn = marco.connect(lee.profile_id, post_id=post["id"])
    lee.approve_connection(conn["id"], approve=True)
    d = marco.deliver(conn["id"], "Truss", "ok")
    lee.decide_delivery(d["id"], accept=True)
    export = marco.export_reputation()
    assert export["verified_skills"] == ["baseten"]
    res = verify_export(export, trusted_registry_key=export["registry_public_key"])
    assert res["valid"] is True and res["key_trusted"] is True


def test_commands_export_and_verify_reputation(tmp_path, monkeypatch):
    monkeypatch.setenv("GUILD_DATA_DIR", str(tmp_path / "cmdrep"))
    import commands
    commands.guild_command('join @lee "Lee Renteria" muse skills=python idiomas=es')
    out = commands.guild_command("export-reputation")
    assert "Reputación portable de @lee exportada" in out
    ruta = out.split("exportada a ")[1].split("\n")[0].strip()
    out = commands.guild_command(f"verify-reputation {ruta}")
    assert "firma Ed25519 válida" in out
    out = commands.guild_command("")
    assert "Sin habilidades verificadas aún" in out


# ==================================================== v0.4: presencia
import time as _time  # noqa: E402

from guild.registry import presence_of  # noqa: E402


def test_presence_derived_from_heartbeat(reg):
    now = _time.time()
    assert presence_of(now) == "online"
    assert presence_of(now - 299) == "online"      # justo dentro de los 5 min
    assert presence_of(now - 301) == "recent"
    assert presence_of(now - 3600) == "recent"
    assert presence_of(now - 90000) == "offline"
    lee = mk(reg, "lee", [])
    assert lee["presence"] == "online"             # recién creado = heartbeat fresco
    assert lee["availability"] == "available"
    reg.db.execute("UPDATE profiles SET last_seen=? WHERE id=?",
                   (now - 7200, lee["id"]))
    reg.db.commit()
    assert reg.get_profile(lee["id"])["presence"] == "recent"
    reg.heartbeat(lee["id"])                       # el heartbeat lo despierta
    assert reg.get_profile(lee["id"])["presence"] == "online"


def test_availability_states_and_pause_unified(reg):
    lee = mk(reg, "lee", [])
    prof = reg.set_availability(lee["id"], "busy")
    assert prof["availability"] == "busy" and prof["paused"] is False
    prof = reg.set_availability(lee["id"], "paused")
    assert prof["availability"] == "paused" and prof["paused"] is True
    prof = reg.set_availability(lee["id"], "available")  # salir de pausa por aquí
    assert prof["availability"] == "available" and prof["paused"] is False
    with pytest.raises(GuildError):
        reg.set_availability(lee["id"], "invisible")


def test_matching_presence_breaks_ties_without_changing_scores(reg):
    lee = mk(reg, "lee", ["python"], platform="muse")
    # Dos candidatos idénticos salvo presencia y handle: con el antiguo
    # desempate por handle ganaría «aaoff»; la presencia manda ahora.
    off = mk(reg, "aaoff", ["baseten"])
    on = mk(reg, "zzon", ["baseten"])
    reg.db.execute("UPDATE profiles SET last_seen=? WHERE id=?",
                   (_time.time() - 90000, off["id"]))
    reg.db.commit()
    post = reg.create_post(lee["id"], "X", "Ayuda Baseten", ["baseten"])
    found = matching.find_matches(reg, post["id"], limit=5)
    assert found[0]["score"] == found[1]["score"]      # la cifra NO se infla
    assert found[0]["handle"] == "zzon"                # online primero
    assert found[0]["presence"] == "online"
    assert found[1]["presence"] == "offline"
    # Y con scores distintos, la presencia no altera el orden por puntos.
    reg.add_rating(lee["id"], off["id"], 5, 5, 5)
    found = matching.find_matches(reg, post["id"], limit=5)
    assert found[0]["handle"] == "aaoff" and found[0]["score"] > found[1]["score"]


# ======================================================== v0.4: inbox
def test_inbox_empty_for_new_profile(reg):
    lee = mk(reg, "lee", [])
    box = reg.inbox(lee["id"])
    assert box["counts"] == {"connections": 0, "deliveries": 0,
                             "new_matches": 0, "total": 0}
    assert box["connections_pending"] == [] and box["deliveries_pending"] == []
    assert box["new_matches"] == []


def test_inbox_pending_connection_only_for_target(reg):
    lee = mk(reg, "lee", [])
    marco = mk(reg, "marco", ["baseten"])
    conn = reg.request_connection(marco["id"], lee["id"], message="puedo ayudar")
    box = reg.inbox(lee["id"])
    assert box["counts"]["connections"] == 1
    item = box["connections_pending"][0]
    assert item["id"] == conn["id"] and item["requester_handle"] == "marco"
    # El solicitante no se aprueba a sí mismo ni ve la suya como pendiente.
    assert reg.inbox(marco["id"])["counts"]["connections"] == 0
    reg.decide_connection(conn["id"], approve=True)
    assert reg.inbox(lee["id"])["counts"]["connections"] == 0  # decidida: sale


def test_inbox_pending_delivery_for_owner(reg):
    lee, marco, conn = _approved_pair(reg)
    d = reg.create_delivery(conn["id"], marco["id"], "Truss", "resumen")
    box = reg.inbox(lee["id"])
    assert box["counts"]["deliveries"] == 1
    assert box["deliveries_pending"][0]["id"] == d["id"]
    assert box["deliveries_pending"][0]["author_handle"] == "marco"
    assert reg.inbox(marco["id"])["counts"]["deliveries"] == 0  # el autor no revisa
    reg.decide_delivery(d["id"], accept=True)
    assert reg.inbox(lee["id"])["counts"]["deliveries"] == 0


def test_inbox_new_matches_and_read_mark(reg):
    lee = mk(reg, "lee", ["python"], platform="muse")
    marco = mk(reg, "marco", ["baseten"])
    post = reg.create_post(lee["id"], "La Asistenta", "Desplegar en Baseten",
                           ["baseten"], need_type="experiencia")
    box = reg.inbox(lee["id"])
    assert box["counts"]["new_matches"] == 1
    assert box["new_matches"][0]["handle"] == "marco"
    assert box["new_matches"][0]["post_id"] == post["id"]
    after = reg.mark_inbox_read(lee["id"])
    assert after["counts"]["new_matches"] == 0      # vistos: ya no son nuevos
    assert after["seen_at"] > 0
    # Una decisión pendiente NO desaparece por marcar leído.
    conn = reg.request_connection(marco["id"], lee["id"])
    reg.mark_inbox_read(lee["id"])
    assert reg.inbox(lee["id"])["counts"]["connections"] == 1
    # Y un candidato que aparece DESPUÉS de la lectura sí es nuevo.
    nuevo = mk(reg, "nuevo", ["baseten"])
    box = reg.inbox(lee["id"])
    handles = [m["handle"] for m in box["new_matches"]]
    assert handles == ["nuevo"]


def test_inbox_via_client_http_and_read_endpoint(http_url):
    lee = GuildClient(base_url=http_url)
    lee.join("lee", "Lee", "muse", skills_offered=["python"], languages=["es"])
    marco = GuildClient(base_url=http_url)
    marco.join("marco", "Marco", "hermes", skills_offered=["baseten"],
               languages=["es"])
    post = lee.post_need("La Asistenta", "Desplegar en Baseten", ["baseten"],
                         need_type="experiencia")
    box = lee.inbox()
    assert box["counts"]["new_matches"] == 1
    conn = marco.connect(lee.profile_id, post_id=post["id"], message="puedo")
    box = lee.inbox()
    assert box["counts"]["connections"] == 1
    lee.mark_inbox_read()
    box = lee.inbox()
    assert box["counts"]["new_matches"] == 0 and box["counts"]["connections"] == 1


def test_inbox_tool_and_hook_summary(tmp_path, monkeypatch):
    monkeypatch.setenv("GUILD_DATA_DIR", str(tmp_path / "inbox"))
    import commands
    import hooks
    import tools
    commands.guild_command('join @lee "Lee Renteria" muse skills=python idiomas=es')
    out = tools.guild_inbox({})
    assert '"ok": true' in out and '"connections": 0' in out
    # Marco pide conectar desde el registro directamente.
    from guild.paths import db_path as _dbp
    reg2 = Registry(_dbp())
    try:
        lee_id = reg2.get_profile_by_handle("lee")["id"]
        marco = reg2.create_profile("marco", "Marco", platform="hermes",
                                    skills_offered=["baseten"], languages=["es"])
        reg2.request_connection(marco["id"], lee_id, message="puedo")
    finally:
        reg2.close()
    out = tools.guild_inbox({})
    assert '"connections": 1' in out
    line = hooks.on_session_start()
    assert line == "📥 GUILD: 1 conexión espera tu decisión"
    out = commands.guild_command("inbox")
    assert "Conexión por decidir" in out and "@marco" in out


# ===================================================== v0.4: contratos
from datetime import date as _date, timedelta as _timedelta  # noqa: E402


def _future(days=7):
    return (_date.today() + _timedelta(days=days)).isoformat()


def _past(days=1):
    return (_date.today() - _timedelta(days=days)).isoformat()


def test_contract_proposed_and_accepted_with_approval(reg):
    lee = mk(reg, "lee", [])
    marco = mk(reg, "marco", ["baseten"])
    contract = {"deliverable": "Truss desplegado y endpoint verificado",
                "done_criteria": "healthcheck 200 y primera inferencia ok",
                "deadline": _future()}
    conn = reg.request_connection(marco["id"], lee["id"], contract=contract)
    assert conn["contract_status"] == "proposed"
    assert conn["contract"]["deliverable"].startswith("Truss")
    assert conn["contract"]["deadline"] == contract["deadline"]
    conn = reg.decide_connection(conn["id"], approve=True)
    assert conn["contract_status"] == "accepted"   # aprobar = aceptar el contrato
    facts = reg.connection_facts(conn["id"])
    assert facts["contract_status"] == "accepted"


def test_contract_rejected_and_invalid_deadline(reg):
    lee = mk(reg, "lee", [])
    marco = mk(reg, "marco", [])
    with pytest.raises(GuildError):
        reg.request_connection(marco["id"], lee["id"],
                               contract={"deliverable": "x", "deadline": "mañana"})
    conn = reg.request_connection(marco["id"], lee["id"],
                                  contract={"deliverable": "algo",
                                            "deadline": _future()})
    conn = reg.decide_connection(conn["id"], approve=False)
    assert conn["contract_status"] == "rejected"


def test_delivery_on_time_fact_from_contract(reg):
    lee = mk(reg, "lee", [])
    marco = mk(reg, "marco", ["baseten"])
    # Con fecha futura: la entrega de hoy llega a tiempo.
    conn = reg.request_connection(
        marco["id"], lee["id"],
        contract={"deliverable": "Truss", "done_criteria": "healthcheck ok",
                  "deadline": _future()})
    reg.decide_connection(conn["id"], approve=True)
    d = reg.create_delivery(conn["id"], marco["id"], "Truss", "ok")
    assert d["on_time"] is True
    assert reg.get_delivery(d["id"])["on_time"] is True
    # Con fecha pasada: la misma entrega llega tarde. Hecho, no opinión.
    conn2 = reg.request_connection(
        marco["id"], lee["id"],
        contract={"deliverable": "Otro", "done_criteria": "ok",
                  "deadline": _past()})
    reg.decide_connection(conn2["id"], approve=True)
    d2 = reg.create_delivery(conn2["id"], marco["id"], "Otro", "tarde")
    assert d2["on_time"] is False
    facts = reg.connection_facts(conn2["id"])
    assert facts["deliveries"][0]["on_time"] is False


def test_no_contract_flow_unchanged_from_v03(reg):
    lee, marco, conn = _approved_pair(reg)   # sin contrato, como siempre
    assert conn["contract"] is None and conn["contract_status"] is None
    d = reg.create_delivery(conn["id"], marco["id"], "Trabajo", "resumen")
    assert d["on_time"] is None              # sin fecha no se afirma nada
    reg.decide_delivery(d["id"], accept=True)


def test_contract_and_on_time_via_http(http_url):
    lee = GuildClient(base_url=http_url)
    lee.join("lee", "Lee", "muse", skills_offered=["python"], languages=["es"])
    marco = GuildClient(base_url=http_url)
    marco.join("marco", "Marco", "hermes", skills_offered=["baseten"],
               languages=["es"])
    conn = marco.connect(lee.profile_id,
                         contract={"deliverable": "Truss verificado",
                                   "done_criteria": "healthcheck 200",
                                   "deadline": _future()})
    assert conn["contract_status"] == "proposed"
    lee.approve_connection(conn["id"], approve=True)
    d = marco.deliver(conn["id"], "Truss", "ok")
    assert d["on_time"] is True
    lee.decide_delivery(d["id"], accept=True)
    with pytest.raises(GuildError):  # fecha inválida → 422 vía servidor
        marco.connect(lee.profile_id,
                      contract={"deliverable": "x", "deadline": "pronto"})


def test_commands_connect_with_contract_and_inbox(tmp_path, monkeypatch):
    monkeypatch.setenv("GUILD_DATA_DIR", str(tmp_path / "cmdcontract"))
    import commands
    commands.guild_command('join @lee "Lee Renteria" muse skills=python idiomas=es')
    from guild.paths import db_path as _dbp
    reg2 = Registry(_dbp())
    try:
        marco = reg2.create_profile("marco", "Marco", platform="hermes",
                                    skills_offered=["baseten"], languages=["es"])
        marco_id = marco["id"]
    finally:
        reg2.close()
    out = commands.guild_command(
        f'connect @marco "puedo ayudarte" contrato="Truss verificado" '
        f'hecho="healthcheck 200" fecha={_future()}')
    assert "Contrato propuesto" in out
    reg2 = Registry(_dbp())
    try:
        conns = reg2.list_connections(reg2.get_profile_by_handle("lee")["id"])
        assert conns[0]["contract_status"] == "proposed"
        assert conns[0]["requester_handle"] == "lee"
        cid = conns[0]["id"]
    finally:
        reg2.close()
    # El destino decide: cambiamos el estado local a Marco y aprobamos.
    from guild.paths import state_path as _sp
    import json as _j
    state = _j.loads(_sp().read_text())
    state["profile_id"] = marco_id
    _sp().write_text(_j.dumps(state))
    out = commands.guild_command(f"approve {cid}")
    assert "Contrato ACEPTADO" in out
    assert "transporte" in out  # el aviso de canal salió (relay en el sandbox)


# ===================================================== v0.4: transporte
from guild import transport as transport_mod  # noqa: E402


def _fake_hermes(tmp_path, monkeypatch, fail=False):
    """Un `hermes` falso en el PATH que registra sus llamadas."""
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    log = tmp_path / "hermes-calls.log"
    script = bin_dir / "hermes"
    if fail:
        script.write_text("#!/bin/sh\nexit 1\n")
    else:
        script.write_text(f'#!/bin/sh\necho "$@" >> "{log}"\n')
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")
    return log


def test_peer_transport_detects_and_calls_fake_binary(tmp_path, monkeypatch):
    log = _fake_hermes(tmp_path, monkeypatch)
    peer = transport_mod.HermesPeerTransport()
    assert peer.available() is True
    res = peer.notify("marco", "canal abierto")
    assert res["delivered"] is True and res["transport"] == "peer"
    assert "peer marco canal abierto" in log.read_text()


def test_peer_transport_absent_without_binary(tmp_path, monkeypatch):
    empty = tmp_path / "emptybin"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    peer = transport_mod.HermesPeerTransport()
    assert peer.available() is False
    assert peer.notify("marco", "x")["delivered"] is False
    # auto sin binario = relay, sin dramas.
    assert transport_mod.get_transport("auto").name == "relay"


def test_notify_channel_open_degrades_to_relay(tmp_path, monkeypatch):
    _fake_hermes(tmp_path, monkeypatch, fail=True)  # hermes existe pero falla
    conn = {"id": "c1", "post_id": "p1", "requester_id": "r1"}
    res = transport_mod.notify_channel_open(conn, "marco", setting="peer")
    assert res["delivered"] is True and res["transport"] == "relay"
    assert res["fallback"] is True
    # Y con peer sano, no hay degradación.
    log = _fake_hermes(tmp_path / "ok", monkeypatch)
    res = transport_mod.notify_channel_open(conn, "marco", setting="auto")
    assert res["transport"] == "peer" and res["fallback"] is False
    assert "peer marco" in log.read_text()


def test_notify_channel_open_logs_event_in_registry(reg):
    lee = mk(reg, "lee", [])
    marco = mk(reg, "marco", [])
    conn = reg.request_connection(marco["id"], lee["id"])
    conn = reg.decide_connection(conn["id"], approve=True)
    res = transport_mod.notify_channel_open(conn, "marco", registry=reg,
                                            setting="relay")
    assert res["transport"] == "relay" and res["delivered"] is True
    kinds = [e["kind"] for e in reg.list_events(limit=100)]
    assert "channel_notified" in kinds


def test_client_approve_attaches_channel_notice(reg):
    lee = GuildClient(registry=reg)
    lee.join("lee", "Lee", "muse", skills_offered=["python"], languages=["es"])
    marco = GuildClient(registry=reg)
    marco.join("marco", "Marco", "hermes", skills_offered=["baseten"],
               languages=["es"])
    conn = marco.connect(lee.profile_id, message="puedo")
    conn = lee.approve_connection(conn["id"], approve=True)
    assert conn["channel_notice"]["delivered"] is True
    assert conn["channel_notice"]["transport"] in ("relay", "peer")
