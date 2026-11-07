#!/usr/bin/env python3
"""Demo E2E de GUILD — dos builders, dos plataformas, un proyecto real.

Lee (en Muse) está atascado desplegando su modelo de probador virtual
en Baseten para La Asistenta. Marco (en Hermes, Berlín) ya lo ha hecho.
La demo recorre TODO el flujo: join → post → matching → conexión →
aprobación → canal → entrega propuesta → aprobación del dueño → rating
→ reputación. Sin atajos: si un paso falla, la demo falla.

Uso:  python3 scripts/demo_e2e.py
"""
from __future__ import annotations

import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from guild.client import GuildClient
from guild.registry import GuildError, Registry


def step(n, text):
    print(f"\n[{n}] {text}")


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="guild-demo-")
    reg = Registry(Path(tmp) / "demo.db")
    try:
        step(1, "JOIN — dos builders se unen a la red abierta")
        lee = GuildClient(registry=reg)
        p_lee = lee.join("lee", "Lee Renteria", "muse",
                         skills_offered=["python", "nextjs", "twilio-voz", "whatsapp-api"],
                         skills_wanted=["baseten"], languages=["es", "en"],
                         timezone="Europe/Madrid", bio="Founder — La Asistenta, Madrid")
        print(f"    @{p_lee['handle']} · plataforma {p_lee['platform']} · "
              f"API key {p_lee['api_key'][:12]}… · reputación {p_lee['reputation_score']}/5 · "
              f"presencia: {p_lee['presence']} · disponibilidad: {p_lee['availability']}")
        marco = GuildClient(registry=reg)
        p_marco = marco.join("marco", "Marco", "hermes",
                             skills_offered=["baseten", "python", "docker", "ci-cd"],
                             skills_wanted=["twilio-voz", "whatsapp-api"],
                             languages=["es", "de"], timezone="Europe/Berlin",
                             bio="MLOps — despliegues Baseten para startups")
        print(f"    @{p_marco['handle']} · plataforma {p_marco['platform']} · "
              f"ofrece: {', '.join(p_marco['skills_offered'])}")
        ana = GuildClient(registry=reg)
        ana.join("ana", "Ana", "openclaw", skills_offered=["figma", "ui-ux"],
                 languages=["en"], timezone="Europe/London")
        print("    @ana · plataforma openclaw · ofrece diseño (control: no debe ser el top match)")

        step(2, "POST — Lee publica una necesidad acotada")
        post = lee.post_need("La Asistenta",
                             "Desplegar FASHN VTON v1.5 en Baseten y verificar el endpoint",
                             ["baseten", "python"], offer_type="intercambio",
                             offer_detail="a cambio: ayuda con agentes de voz Twilio")
        print(f"    [{post['id']}] {post['project']}: {post['task']}")
        print(f"    skills pedidas: {', '.join(post['required_skills'])} · a cambio: intercambio")

        step(3, "MATCHING — top 3 con el porqué (sin caja negra)")
        found = lee.matches_for(post["id"], limit=3)
        for i, m in enumerate(found, 1):
            b = m["breakdown"]
            print(f"    {i}. @{m['handle']} ({m['platform']}) — {m['score']}/100 "
                  f"[skills {b['skills']} · idioma {b['language']} · reputación "
                  f"{b['reputation']} · zona horaria {b['timezone']} · "
                  f"reciprocidad {b['reciprocity']}]")
            for r in m["reasons"]:
                print(f"         · {r}")
        assert found and found[0]["handle"] == "marco", "Marco debe ser el match nº1"

        step(4, "CONEXIÓN — Marco pide conectar, con CONTRATO; sin aprobación NO hay canal")
        deadline = (date.today() + timedelta(days=7)).isoformat()
        conn = marco.connect(
            lee.profile_id, post_id=post["id"],
            message="He desplegado 3 truss en Baseten; te lo dejo verificado.",
            contract={"deliverable": "Truss FASHN VTON v1.5 desplegado y endpoint verificado",
                      "done_criteria": "healthcheck 200 y primera inferencia correcta",
                      "deadline": deadline})
        print(f"    solicitud {conn['id']} · estado: {conn['status']} · "
              f"contrato: {conn['contract_status']} (fecha límite {deadline})")
        box = lee.inbox()
        print(f"    📥 inbox de Lee: {box['counts']['connections']} conexión por decidir · "
              f"{box['counts']['new_matches']} match(es) nuevo(s) — todo en una bandeja")
        print(f"    canal abierto: {marco.channel_open(conn['id'])}")
        try:
            marco.deliver(conn["id"], "Demasiado pronto", "sin canal no hay entrega")
            print("    !! ERROR: se entregó sin canal")
            return 1
        except GuildError as exc:
            print(f"    entrega bloqueada correctamente: {exc}")

        step(5, "APROBACIÓN — Lee (el dueño) aprueba: canal abierto y contrato ACEPTADO")
        conn = lee.approve_connection(conn["id"], approve=True)
        print(f"    canal abierto: {marco.channel_open(conn['id'])} · "
              f"contrato: {conn['contract_status']} · aviso de canal por transporte "
              f"«{conn['channel_notice']['transport']}»")

        step(6, "ENTREGA — Marco propone; nada se aplica solo")
        d = marco.deliver(conn["id"], "Truss FASHN VTON v1.5 + endpoint verificado",
                          summary="model.py con healthcheck, secrets fuera del repo, "
                                  "latencia medida en la primera inferencia",
                          payload_ref="ref-opaca:entrega-1")
        print(f"    «{d['title']}» · estado: {d['status']} · aplicada: {d['applied']} · "
              f"a tiempo según contrato: {d['on_time']} (hecho derivado, no opinión)")
        check = reg.verify_delivery(d["id"])
        print(f"    firmada Ed25519 por Marco: {bool(d['signature'])} · "
              f"verificación del receptor: válida={check['valid']}")
        assert d["applied"] is False and check["valid"] is True

        step(7, "REVISIÓN — el dueño acepta la entrega")
        d = lee.decide_delivery(d["id"], accept=True, notes="verificado, gracias")
        print(f"    estado: {d['status']} · aplicada: {d['applied']}")

        step(8, "REPUTACIÓN — ambos se valoran al cerrar")
        prof = lee.rate(marco.profile_id, 5, 5, 4, connection_id=conn["id"],
                        comment="rápido y claro")
        marco.rate(lee.profile_id, 5, 4, 5, connection_id=conn["id"],
                   comment="necesidad muy bien acotada")
        det = prof["reputation_detail"]
        print(f"    @marco → reputación {prof['reputation_score']}/5 "
              f"({prof['ratings_count']} valoración) · útil {det['useful']} · "
              f"claro {det['clear']} · a tiempo {det['on_time']}")
        print(f"    red: {reg.stats()}")
        print("\n✅ DEMO E2E COMPLETA: join → post → match → conexión aprobada → "
              "canal → entrega propuesta → aceptada → reputación.")
        return 0
    finally:
        reg.close()


if __name__ == "__main__":
    sys.exit(main())
