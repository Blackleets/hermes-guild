"""Tests del renderizador de la página pública de perfil (Pieza 3).

Los perfiles se construyen REALES con Registry sobre tmp_path, con el
mismo flujo de la demo Lee × Marco: Marco pide conexión al post de
Lee, Lee aprueba, Marco entrega, Lee acepta y valora (5, 5, 4) →
@marco queda con «baseten» verificado y reputación 4.67.

Run:  .venv/bin/python -m pytest tests/test_profile_page.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from guild.profile_page import render_not_found, render_profile_page  # noqa: E402
from guild.registry import Registry  # noqa: E402


@pytest.fixture()
def reg(tmp_path):
    r = Registry(tmp_path / "t.db")
    yield r
    r.close()


@pytest.fixture()
def escenario(reg):
    """Lee × Marco completos: entrega aceptada + valoración (5, 5, 4)."""
    lee = reg.create_profile(
        "lee", "Lee Renteria", platform="muse",
        skills_offered=["python", "twilio-voz"], languages=["es"],
        timezone="Europe/Madrid", bio="Founder — La Asistenta, Madrid")
    marco = reg.create_profile(
        "marco", "Marco", platform="hermes",
        skills_offered=["baseten", "python", "docker"], languages=["es", "de"],
        timezone="Europe/Berlin", bio="MLOps — despliegues Baseten")
    post = reg.create_post(lee["id"], "La Asistenta",
                           "Desplegar FASHN VTON v1.5 en Baseten",
                           ["baseten", "python"])
    conn = reg.request_connection(marco["id"], lee["id"], post_id=post["id"],
                                  message="lo he hecho antes")
    reg.decide_connection(conn["id"], approve=True)
    entrega = reg.create_delivery(conn["id"], marco["id"],
                                  "Truss FASHN verificado", "healthcheck ok")
    reg.decide_delivery(entrega["id"], accept=True)
    reg.add_rating(lee["id"], marco["id"], 5, 5, 4, connection_id=conn["id"])
    return {"lee": lee, "marco": marco,
            "profile": reg.get_profile_by_handle("marco"),
            "registry_key": reg.stats()["registry_public_key"]}


def test_forma_real_del_perfil(escenario):
    """Documenta la forma EXACTA que devuelve get_profile_by_handle."""
    prof = escenario["profile"]
    assert prof["handle"] == "marco"
    assert prof["reputation_score"] == 4.67 and prof["ratings_count"] == 1
    assert prof["reputation_detail"]["useful"] == 5.0
    assert prof["reputation_detail"]["on_time"] == 4.0
    assert "baseten" in prof["verified_skills"]
    assert prof["collaborations"] == 1
    assert prof["presence"] in ("online", "recent", "offline")
    assert isinstance(prof["languages"], list)
    assert all(isinstance(x, str) for x in prof["languages"])


def test_contenido(escenario):
    html = render_profile_page(escenario["profile"],
                               registry_public_key=escenario["registry_key"])
    assert "@marco" in html
    assert "Marco" in html and "Hermes" in html  # nombre + plataforma
    # La skill verificada lleva su etiqueta (el id de la taxonomía) + ✓
    assert "baseten ✓" in html
    assert "4.67" in html                      # ★ 4.67/5
    assert "1 valoración" in html or "1 valoraciones" in html
    assert "1 colaboración" in html            # nº de colaboraciones
    # Presencia: recién creado → en línea (etiqueta y estado)
    assert escenario["profile"]["presence"] == "online"
    assert "En línea" in html and "online" in html
    assert escenario["registry_key"] in html   # clave DEL REGISTRO: sí va


def test_privacidad(escenario):
    html = render_profile_page(escenario["profile"],
                               registry_public_key=escenario["registry_key"])
    marco, lee = escenario["marco"], escenario["lee"]
    assert marco["api_key"] not in html
    assert lee["api_key"] not in html
    assert marco["private_key"] not in html
    # La clave pública DEL PERFIL no se renderiza (la del registro, sí).
    assert marco["public_key"] not in html
    assert escenario["registry_key"] != marco["public_key"]
    assert "private_key" not in html
    assert "api_key" not in html
    assert "api_key_hash" not in html
    assert "public_key" not in html


def test_escape(escenario):
    prof = dict(escenario["profile"])
    prof["display_name"] = "<script>alert(1)</script>"
    html = render_profile_page(prof)
    assert "&lt;script&gt;" in html
    assert "<script>alert" not in html


def test_sin_valoraciones(reg):
    nuevo = reg.create_profile("nuevo", "Nuevo", platform="hermes",
                               skills_offered=["python"], languages=["es"],
                               timezone="Europe/Madrid")
    html = render_profile_page(reg.get_profile_by_handle("nuevo"))
    assert "Sin valoraciones todavía" in html
    assert nuevo["api_key"] not in html


def test_not_found():
    html = render_not_found("fantasma")
    assert "404" in html
    assert "fantasma" in html
