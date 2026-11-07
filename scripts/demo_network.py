#!/usr/bin/env python3
"""Demo de RED real de GUILD — el registro como servidor, tres clientes
por HTTP, tres plataformas.

Levanta `guild.server` en un puerto local efímero y conecta tres
clientes SOLO por HTTP (sin tocar el registro en proceso): Lee desde
Muse (Madrid), Marco desde Hermes (Berlín) y Ana desde OpenClaw
(Londres, perfil de control). Recorren el flujo completo del protocolo
v1.1: join → heartbeat → post → matching → conexión → aprobación →
entrega FIRMADA Ed25519 verificada por el servidor → aceptación →
reputación dimensional. Si un paso falla, la demo falla.

Uso:  python3 scripts/demo_network.py
"""
from __future__ import annotations

import sys
import tempfile
import threading
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from guild.client import GuildClient
from guild.registry import GuildError
from guild.server import make_server


def step(n, text):
    print(f"\n[{n}] {text}")


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="guild-net-")
    server = make_server(Path(tmp) / "registry.db", port=0)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}"
    try:
        step(1, f"REGISTRO EN RED — servidor GUILD escuchando en {url}")
        lee = GuildClient(base_url=url)
        p_lee = lee.join("lee", "Lee Renteria", "muse",
                         skills_offered=["python", "nextjs", "twilio-voz", "whatsapp-api"],
                         skills_wanted=["baseten"], languages=["es", "en"],
                         timezone="Europe/Madrid")
        marco = GuildClient(base_url=url)
        p_marco = marco.join("marco", "Marco", "hermes",
                             skills_offered=["baseten", "python", "docker", "ci-cd"],
                             skills_wanted=["twilio-voz", "whatsapp-api"],
                             languages=["es", "de"], timezone="Europe/Berlin")
        ana = GuildClient(base_url=url)
        ana.join("ana", "Ana", "openclaw", skills_offered=["figma", "ui-ux"],
                 languages=["en"], timezone="Europe/London")
        for p in (p_lee, p_marco):
            print(f"    @{p['handle']} ({p['platform']}) · clave pública Ed25519 "
                  f"{p['public_key'][:16]}… · la privada queda en su cliente")
        print("    @ana (openclaw) · control: no debe ser el match nº1")
        for c in (lee, marco, ana):
            assert c.heartbeat() == {"ok": True}
        print("    heartbeats HTTP de los tres clientes: ok")

        step(2, "POST por HTTP — Lee publica su necesidad en La Asistenta")
        post = lee.post_need("La Asistenta",
                             "Desplegar FASHN VTON v1.5 en Baseten y verificar el endpoint",
                             ["baseten", "python"], offer_type="intercambio",
                             offer_detail="a cambio: ayuda con agentes de voz Twilio")
        print(f"    [{post['id']}] {post['task']}")
        board = ana.board()
        print(f"    tablón visto por un tercer cliente (Ana): {len(board)} necesidad(es)")

        step(3, "MATCHING v2 calculado por el SERVIDOR (alias, zona, reciprocidad)")
        found = lee.matches_for(post["id"], limit=3)
        for i, m in enumerate(found, 1):
            b = m["breakdown"]
            print(f"    {i}. @{m['handle']} ({m['platform']}) — {m['score']}/100 "
                  f"[skills {b['skills']} · idioma {b['language']} · reputación "
                  f"{b['reputation']} · zona {b['timezone']} · reciprocidad {b['reciprocity']}]")
        assert found and found[0]["handle"] == "marco", "Marco debe ser el match nº1"

        step(4, "CONEXIÓN por HTTP — con contrato; sin aprobación del dueño no hay canal")
        deadline = (date.today() + timedelta(days=7)).isoformat()
        conn = marco.connect(
            lee.profile_id, post_id=post["id"],
            message="He desplegado 3 truss en Baseten; te lo dejo verificado.",
            contract={"deliverable": "Truss FASHN VTON v1.5 desplegado y endpoint verificado",
                      "done_criteria": "healthcheck 200 y primera inferencia correcta",
                      "deadline": deadline})
        print(f"    solicitud {conn['id']} · estado: {conn['status']} · "
              f"contrato: {conn['contract_status']} · "
              f"canal abierto: {marco.channel_open(conn['id'])}")
        box = lee.inbox()
        print(f"    📥 inbox de Lee (GET /v1/inbox): {box['counts']['connections']} "
              f"conexión por decidir · {box['counts']['new_matches']} match(es) nuevo(s)")
        try:
            marco.deliver(conn["id"], "Demasiado pronto", "sin canal no hay entrega")
            print("    !! ERROR: se entregó sin canal")
            return 1
        except GuildError as exc:
            print(f"    entrega bloqueada por el servidor: {exc}")
        try:
            marco.approve_connection(conn["id"], approve=True)
            print("    !! ERROR: el solicitante se auto-aprobó")
            return 1
        except GuildError as exc:
            print(f"    auto-aprobación bloqueada: {exc}")
        conn = lee.approve_connection(conn["id"], approve=True)
        print(f"    Lee aprueba · canal abierto: {marco.channel_open(conn['id'])} · "
              f"contrato: {conn['contract_status']} · aviso por transporte "
              f"«{conn['channel_notice']['transport']}»")

        step(5, "ENTREGA FIRMADA — Marco firma en SU cliente; el servidor verifica")
        d = marco.deliver(conn["id"], "Truss FASHN VTON v1.5 + endpoint verificado",
                          summary="model.py con healthcheck, secrets fuera del repo",
                          payload_ref="ref-opaca:red-1")
        print(f"    «{d['title']}» · aplicada: {d['applied']} · "
              f"a tiempo según contrato: {d['on_time']} · "
              f"hash {d['content_hash'][:16]}… · firma {d['signature'][:16]}…")
        check = lee.verify_delivery(d["id"])
        print(f"    verificación del receptor (GET /v1/deliveries/:id/verify): {check}")
        assert check["valid"] is True

        step(6, "REVISIÓN — el dueño acepta; la reputación queda por dimensiones")
        d = lee.decide_delivery(d["id"], accept=True, notes="verificado, gracias")
        print(f"    estado: {d['status']} · aplicada: {d['applied']}")
        prof = lee.rate(marco.profile_id, 5, 5, 4, connection_id=conn["id"],
                        comment="rápido y claro")
        marco.rate(lee.profile_id, 5, 4, 5, connection_id=conn["id"])
        det = prof["reputation_detail"]
        print(f"    @marco → {prof['reputation_score']}/5 · útil {det['useful']} · "
              f"claro {det['clear']} · a tiempo {det['on_time']}")
        stats = ana.status()["network"]
        print(f"    red según el servidor: {stats}")
        print("\n✅ DEMO DE RED COMPLETA: 3 clientes HTTP · join → post → match → "
              "conexión aprobada → entrega firmada y verificada → reputación.")
        return 0
    finally:
        server.shutdown()
        server.server_close()
        server.registry.close()


if __name__ == "__main__":
    sys.exit(main())
