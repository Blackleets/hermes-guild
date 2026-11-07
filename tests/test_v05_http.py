"""Integración HTTP de v0.5.0 — servidor real en un puerto efímero.

Cubre lo que los tests locales no pueden: el stream SSE de
GET /v1/events entregando el evento en vivo (sin sondear el inbox),
el endpoint JSON GET /v1/events/list con auth, y la página pública
GET /b/<handle> (contenido, privacidad y 404) servida por el registro.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from guild.client import GuildClient
from guild.server import make_server


@pytest.fixture()
def base(tmp_path):
    server = make_server(str(tmp_path / "guild.db"), "127.0.0.1", 0)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


def _dos_clientes(base):
    lee = GuildClient(base_url=base)
    lee.join("lee", "Lee", "Muse", skills_offered=["python"],
             languages=["es", "en"], timezone="Europe/Madrid")
    marco = GuildClient(base_url=base)
    marco.join("marco", "Marco", "hermes", skills_offered=["baseten", "python"],
               languages=["es", "de"], timezone="Europe/Berlin")
    return lee, marco


def test_stream_sse_recibe_la_conexion_en_vivo(base):
    lee, marco = _dos_clientes(base)
    post = lee.post_need("La Asistenta", "Desplegar FASHN en Baseten",
                         ["baseten"], need_type="experiencia")

    recibidos: list[dict] = []

    def _watch():
        for ev in lee.watch_events(max_events=1, timeout=25):
            recibidos.append(ev)

    hilo = threading.Thread(target=_watch, daemon=True)
    hilo.start()
    time.sleep(0.5)  # que el stream se establezca; la sincronía real es por contenido
    conn = marco.connect(lee.profile_id, post_id=post["id"],
                         message="Ya lo he desplegado: te lo dejo reproducible.")
    hilo.join(timeout=30)

    assert len(recibidos) == 1
    assert recibidos[0]["kind"] == "connection_requested"
    assert recibidos[0]["connection_id"] == conn["id"]
    assert recibidos[0]["from_id"] == marco.profile_id

    # La misma fuente, en JSON con cursor: para Lee está el evento
    # almacenado; al aprobar, Marco recibe connection_decided.
    pagina = lee.events_for(after=0)
    assert [e["kind"] for e in pagina["events"]] == ["connection_requested"]
    lee.approve_connection(conn["id"], approve=True)
    pagina_marco = marco.events_for(after=0)
    kinds = [e["kind"] for e in pagina_marco["events"]]
    assert kinds == ["connection_decided"]
    assert pagina_marco["events"][0]["decision"] == "approved"
    # El cursor avanza: segunda página vacía.
    assert marco.events_for(after=pagina_marco["next_cursor"])["events"] == []


def test_events_list_exige_auth(base):
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(base + "/v1/events/list", timeout=10)
    assert exc.value.code == 401


def _get(base, path):
    try:
        with urllib.request.urlopen(base + path, timeout=10) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


def test_pagina_publica_de_perfil(base):
    lee, marco = _dos_clientes(base)
    status, html_doc = _get(base, "/b/marco")
    assert status == 200
    assert "@marco" in html_doc
    assert "Baseten" in html_doc or "baseten" in html_doc
    # Privacidad: ni la clave API real, ni nombres de campos secretos,
    # ni la clave pública del perfil.
    assert marco.api_key not in html_doc
    assert lee.api_key not in html_doc
    assert "api_key" not in html_doc
    assert "private_key" not in html_doc
    assert "api_key_hash" not in html_doc
    assert marco.me()["public_key"] not in html_doc


def test_pagina_publica_404_limpio(base):
    status, body = _get(base, "/b/fantasma")
    assert status == 404
    assert "404" in body
    assert "fantasma" in body
