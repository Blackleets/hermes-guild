"""Tests offline de los eventos en tiempo real de GUILD (Pieza 2).

Solo modo local: los tests HTTP/SSE los pone el coordinador.

Run:  .venv/bin/python -m pytest tests/test_events_realtime.py -q
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from guild.client import GuildClient  # noqa: E402
from guild.registry import Registry  # noqa: E402


@pytest.fixture()
def reg(tmp_path):
    r = Registry(tmp_path / "t.db")
    yield r
    r.close()


def mk(reg, handle, skills, langs=("es",), platform="hermes"):
    return reg.create_profile(handle, handle.title(), platform=platform,
                              skills_offered=skills, languages=list(langs),
                              timezone="Europe/Madrid")


# ------------------------------------------------------- Registry.events_for
def test_events_for_relevancia_y_cursor(reg):
    lee = mk(reg, "lee", ["python"], platform="muse")
    marco = mk(reg, "marco", ["baseten", "python"])
    post = reg.create_post(lee["id"], "La Asistenta", "Desplegar FASHN en Baseten",
                           ["baseten", "python"])
    conn = reg.request_connection(marco["id"], lee["id"], post_id=post["id"],
                                  message="puedo ayudar")
    reg.decide_connection(conn["id"], approve=True)
    d = reg.create_delivery(conn["id"], marco["id"], "Truss Baseten", "resumen")
    reg.decide_delivery(d["id"], accept=True)

    # --- Marco (solicitante y autor de la entrega)
    page_m = reg.events_for(marco["id"])
    kinds_m = [e["kind"] for e in page_m["events"]]
    assert "connection_decided" in kinds_m
    assert "delivery_reviewed" in kinds_m
    assert "connection_requested" not in kinds_m       # esa era PARA Lee
    assert "delivery_proposed" not in kinds_m          # esa era PARA Lee
    dec = next(e for e in page_m["events"] if e["kind"] == "connection_decided")
    assert dec["decision"] == "approved"
    assert dec["connection_id"] == conn["id"]
    assert dec["by_id"] == lee["id"]
    rev = next(e for e in page_m["events"] if e["kind"] == "delivery_reviewed")
    assert rev["decision"] == "accepted"
    assert rev["delivery_id"] == d["id"]

    # --- Lee (destinatario de la solicitud y revisor de la entrega)
    page_l = reg.events_for(lee["id"])
    kinds_l = [e["kind"] for e in page_l["events"]]
    assert "connection_requested" in kinds_l
    assert "delivery_proposed" in kinds_l
    assert "connection_decided" not in kinds_l         # esa era PARA Marco
    assert "delivery_reviewed" not in kinds_l          # esa era PARA Marco
    req = next(e for e in page_l["events"] if e["kind"] == "connection_requested")
    assert req["connection_id"] == conn["id"]
    assert req["from_id"] == marco["id"]
    prop = next(e for e in page_l["events"] if e["kind"] == "delivery_proposed")
    assert prop["delivery_id"] == d["id"]
    assert prop["connection_id"] == conn["id"]
    assert prop["from_id"] == marco["id"]

    # --- Cursores: enteros y crecientes; reanudar no repite nada
    for page in (page_m, page_l):
        cursors = [e["cursor"] for e in page["events"]]
        assert all(isinstance(c, int) for c in cursors)
        assert cursors == sorted(cursors) and len(set(cursors)) == len(cursors)
        assert isinstance(page["next_cursor"], int)
        assert page["next_cursor"] >= cursors[-1]
        segunda = reg.events_for(marco["id"] if page is page_m else lee["id"],
                                 after=page["next_cursor"])
        assert segunda["events"] == []
        assert segunda["next_cursor"] == page["next_cursor"]


# ------------------------------------------------- watch local: conexión
def test_watch_events_local_recibe_conexion_sin_polling(tmp_path):
    db = tmp_path / "watch.db"
    reg = Registry(db)
    try:
        lee = GuildClient(registry=reg)
        lee.join("lee", "Lee Renteria", "muse", skills_offered=["python"],
                 languages=["es"])
        marco = GuildClient(registry=reg)
        marco.join("marco", "Marco", "hermes", skills_offered=["baseten"],
                   languages=["es"])
        post = lee.post_need("La Asistenta", "Desplegar FASHN en Baseten",
                             ["baseten"])
        lee_id, marco_id, post_id = lee.profile_id, marco.profile_id, post["id"]

        def _pide_conexion():
            time.sleep(0.3)
            reg2 = Registry(db)
            try:
                reg2.request_connection(marco_id, lee_id, post_id=post_id,
                                        message="puedo ayudar")
            finally:
                reg2.close()

        hilo = threading.Thread(target=_pide_conexion, daemon=True)
        hilo.start()
        eventos = list(lee.watch_events(max_events=1, timeout=10))
        hilo.join(timeout=5)
    finally:
        reg.close()
    assert len(eventos) == 1
    assert eventos[0]["kind"] == "connection_requested"
    assert eventos[0]["from_id"] == marco_id


# --------------------------------------------------- watch local: match_new
def test_watch_events_match_new(tmp_path):
    db = tmp_path / "watch2.db"
    reg = Registry(db)
    holder = {}
    try:
        lee = GuildClient(registry=reg)
        lee.join("lee", "Lee Renteria", "muse", skills_offered=["python"],
                 languages=["es"])
        lee.post_need("La Asistenta", "Desplegar FASHN en Baseten", ["baseten"])

        def _une_marco():
            time.sleep(0.3)
            reg2 = Registry(db)
            try:
                marco = reg2.create_profile(
                    "marco", "Marco", platform="hermes",
                    skills_offered=["baseten"], languages=["es"],
                    timezone="Europe/Madrid")
                holder["marco_id"] = marco["id"]
            finally:
                reg2.close()

        hilo = threading.Thread(target=_une_marco, daemon=True)
        hilo.start()
        eventos = list(lee.watch_events(max_events=1, timeout=10))
        hilo.join(timeout=5)
    finally:
        reg.close()
    assert len(eventos) == 1
    assert eventos[0]["kind"] == "match_new"
    assert eventos[0]["candidate_id"] == holder["marco_id"]
    assert eventos[0]["post_id"]


# ------------------------------------------------------------ comando watch
def test_comando_watch(tmp_path, monkeypatch):
    monkeypatch.setenv("GUILD_DATA_DIR", str(tmp_path / "watchcmd"))
    sys.path.insert(0, str(ROOT))
    import commands
    from guild.paths import db_path

    out = commands.guild_command(
        'join @lee "Lee Renteria" muse skills=python idiomas=es tz=Europe/Madrid')
    assert "Bienvenido a GUILD" in out

    reg2 = Registry(db_path())
    try:
        lee_id = reg2.get_profile_by_handle("lee")["id"]
        marco = reg2.create_profile("marco", "Marco", platform="hermes",
                                    skills_offered=["baseten"], languages=["es"])
        marco_id = marco["id"]
    finally:
        reg2.close()

    def _pide_conexion():
        time.sleep(0.3)
        reg3 = Registry(db_path())
        try:
            reg3.request_connection(marco_id, lee_id, message="puedo ayudar")
        finally:
            reg3.close()

    hilo = threading.Thread(target=_pide_conexion, daemon=True)
    hilo.start()
    out = commands.guild_command("watch 8 1")
    hilo.join(timeout=5)
    assert "🔔" in out
    assert "pide conexión" in out
    assert "@marco" in out
    assert out.strip().splitlines()[-1] == "👂 GUILD · fin de la escucha (1 eventos)."
