#!/usr/bin/env python3
"""Prueba de humo del Día L contra el registro PÚBLICO de GUILD.

Ejercita el camino completo, de extremo a extremo, con el cliente real
(`guild.client.GuildClient`), sin atajos:

  1. GET /v1/stats responde 200 y trae registry_public_key.
  2. Join de DOS perfiles de prueba (autor y dueño).
  3. El autor publica una necesidad (need_type obligatorio).
  4. El autor solicita conexión; el DUEÑO la aprueba (solo él puede).
  5. El autor entrega con payload cifrado E2E (GUILD-E2E-1).
  6. El dueño recupera la entrega por la API y la DESCIFRA en local:
     el texto descifrado debe ser idéntico al enviado.
  7. Se verifica firma+hash de la entrega (GET /v1/deliveries/:id/verify).

Uso (desde la raíz del repo guild-plugin):
    GUILD_REGISTRY_URL=https://registry.example.com \
        python3 deploy/smoke_test.py
    # o: python3 deploy/smoke_test.py https://registry.example.com

Salida: exit 0 si todo pasa; exit 1 con el paso que falló si algo falla.
Los perfiles de prueba quedan en el registro con handles
`smoke-<timestamp>-a/b`: son perfiles reales de humo, bórralos a mano
si el registro del Día L debe nacer limpio (o úsalo contra un registro
efímero previo al DNS definitivo).
"""
from __future__ import annotations

import os
import sys
import time
import urllib.request
import json

# El paquete guild/ vive en la raíz del repo, un nivel por encima de deploy/
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from guild.client import GuildClient  # noqa: E402

SECRET_PAYLOAD = "contenido-de-humo-guild: el registro no puede leer esto"


def fail(step: str, detail: object = "") -> "SystemExit":
    print(f"❌ HUMO FALLÓ en: {step} {detail}")
    return SystemExit(1)


def main() -> int:
    base = (sys.argv[1] if len(sys.argv) > 1
            else os.environ.get("GUILD_REGISTRY_URL", "")).rstrip("/")
    if not base:
        raise fail("configuración", "(falta la URL: argumento o GUILD_REGISTRY_URL)")

    # 1. Stats / healthcheck público (no hay /health dedicado)
    try:
        with urllib.request.urlopen(base + "/v1/stats", timeout=10) as r:
            stats = json.loads(r.read().decode())
        assert r.status == 200 and stats.get("registry_public_key")
    except Exception as exc:  # noqa: BLE001
        raise fail("GET /v1/stats", exc)
    print(f"✅ /v1/stats 200 · registry_public_key={stats['registry_public_key'][:16]}…")

    stamp = str(int(time.time()))
    author = GuildClient(base_url=base)
    owner = GuildClient(base_url=base)

    # 2. Joins de prueba
    try:
        pa = author.join(f"smoke-{stamp}-a", "Smoke Autor", "hermes",
                         skills_offered=["despliegue"], languages=["es"],
                         timezone="Europe/Madrid")
        po = owner.join(f"smoke-{stamp}-b", "Smoke Dueño", "hermes",
                        skills_offered=["revision"], languages=["es"],
                        timezone="Europe/Madrid")
        assert pa.get("enc_public_key") and po.get("enc_public_key")
    except Exception as exc:  # noqa: BLE001
        raise fail("join de perfiles de prueba", exc)
    print("✅ join x2 (ambos publican enc_public_key X25519)")

    # 3-4. Necesidad + conexión aprobada por el dueño
    try:
        post = author.post_need("humo", "verificar despliegue del registro",
                                ["despliegue"], need_type="experiencia")
        conn = author.connect(po["id"], post_id=post["id"],
                              message="prueba de humo del Día L")
        owner.approve_connection(conn["id"], approve=True)
    except Exception as exc:  # noqa: BLE001
        raise fail("necesidad + conexión aprobada", exc)
    print("✅ necesidad publicada y conexión aprobada por el dueño")

    # 5-6. Entrega cifrada E2E y descifrado por el dueño
    try:
        delivery = author.deliver(conn["id"], "Entrega de humo",
                                  summary="solo metadatos en claro",
                                  payload=SECRET_PAYLOAD)
        assert delivery.get("encrypted"), "la entrega no quedó marcada cifrada"
        fetched = owner.get_delivery(delivery["id"])
        plain = owner.decrypt_delivery(fetched).decode()
        assert plain == SECRET_PAYLOAD, "el descifrado no coincide con lo enviado"
    except Exception as exc:  # noqa: BLE001
        raise fail("entrega cifrada E2E / descifrado del dueño", exc)
    print("✅ entrega cifrada E2E: el dueño descifra y el texto coincide")

    # 7. Verificación de firma
    try:
        ver = author.verify_delivery(delivery["id"])
        assert ver.get("signed") is True and ver.get("valid") is True, ver
    except Exception as exc:  # noqa: BLE001
        raise fail("verificación de firma de la entrega", exc)
    print(f"✅ firma de la entrega verificada: {ver}")

    print("\n🎉 HUMO COMPLETO: registro público sano de extremo a extremo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
