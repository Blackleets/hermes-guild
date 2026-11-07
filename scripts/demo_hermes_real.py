#!/usr/bin/env python3
"""PRUEBA EN HERMES REAL — GUILD v0.6.0 (la prueba nació en v0.5.0, Pieza 1).

Levanta un servidor GUILD real (HTTP) y ejercita el plugin cargado
con el cargador REAL de un checkout de Hermes Agent del sandbox
(~/workspace/la-asistenta/hermes, solo lectura: el plugin se copia a
un directorio temporal y el checkout no se modifica).

Flujo:
  · Lee (cliente Muse, nuestro client.py en modo HTTP) entra en la
    red y publica la necesidad de siempre: desplegar FASHN VTON en
    Baseten (el caso real de La Asistenta).
  · Lee abre además una escucha SSE (watch_events): debe recibir el
    evento connection_requested EN VIVO cuando Marco pida conexión.
  · El lado Hermes (scripts/hermes_side_runner.py ejecutado con el
    Python del entorno real de Hermes) carga el plugin con
    PluginManager, se une con /guild join, mira el tablón y los
    matches, pide conexión con contrato, entrega y valora — todo a
    través del handler registrado por el cargador real.
  · Lee aprueba la conexión, acepta la entrega y valora a Marco
    por HTTP.

Uso: .venv/bin/python scripts/demo_hermes_real.py [--keep]
Intérprete de Hermes: se autodetecta (venv de PM bajo
la-asistenta/hermes-home/installs); se puede fijar con
GUILD_HERMES_PYTHON y el checkout con GUILD_HERMES_CHECKOUT.

Sale con código 0 solo si TODAS las comprobaciones pasan, con las
cifras reales impresas (nada redondeado para la foto).
"""
from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from guild.client import GuildClient          # noqa: E402
from guild.server import make_server          # noqa: E402

HOME = Path.home()
DEFAULT_CHECKOUT = HOME / "workspace/la-asistenta/hermes"
RUNNER = ROOT / "scripts" / "hermes_side_runner.py"

CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, ok, detail))
    print(f"  {'✓' if ok else '✗'} {name}{(' — ' + detail) if detail else ''}")


def find_hermes_python(checkout: Path) -> Path | None:
    override = os.environ.get("GUILD_HERMES_PYTHON")
    candidates = [override] if override else []
    base = HOME / "workspace/la-asistenta/hermes-home/installs"
    candidates += sorted(glob.glob(
        str(base / "*" / "environments" / "*" / "venv" / "bin" / "python")))
    candidates += sorted(glob.glob(
        str(base / "*" / "test-environment" / "*" / "venv" / "bin" / "python")))
    for cand in candidates:
        if not cand:
            continue
        try:
            probe = subprocess.run(
                [cand, "-c",
                 f"import sys; sys.path.insert(0, {str(checkout)!r}); "
                 "import hermes_cli.plugins"],
                capture_output=True, timeout=90)
        except Exception:
            continue
        if probe.returncode == 0:
            return Path(cand)
    return None


def run_phase(hermes_py: Path, checkout: Path, workdir: Path,
              phase: str, extra: list[str]) -> dict:
    env = dict(os.environ)
    env["HERMES_HOME"] = str(workdir / "hermes-home")
    env["GUILD_DATA_DIR"] = str(workdir / "guild-data")
    env["PYTHONIOENCODING"] = "utf-8"
    cmd = [str(hermes_py), str(RUNNER), "--checkout", str(checkout),
           "--plugin-src", str(ROOT), "--workdir", str(workdir),
           "--phase", phase, *extra]
    print(f"\n$ {' '.join(cmd[1:])}   [python: {hermes_py}]")
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          env=env, timeout=300)
    print(proc.stdout, end="")
    if proc.stderr.strip():
        print("[stderr del runner]\n" + proc.stderr[-2000:])
    result = {}
    for line in proc.stdout.splitlines():
        if line.startswith("RESULT "):
            result = json.loads(line[len("RESULT "):])
    if proc.returncode != 0:
        check(f"fase {phase}: proceso OK", False,
              f"returncode={proc.returncode}")
    return result


def main() -> int:
    keep = "--keep" in sys.argv
    checkout = Path(os.environ.get("GUILD_HERMES_CHECKOUT",
                                   str(DEFAULT_CHECKOUT)))
    print("=" * 72)
    print("GUILD · PRUEBA EN HERMES REAL (checkout del sandbox, solo lectura)")
    print("=" * 72)
    if not (checkout / "hermes_cli" / "plugins.py").exists():
        print(f"✗ checkout de Hermes no encontrado en {checkout}")
        return 2
    head = subprocess.run(["git", "-C", str(checkout), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    print(f"checkout: {checkout}\ngit HEAD: {head}")

    hermes_py = find_hermes_python(checkout)
    if hermes_py is None:
        print("✗ no se encontró un intérprete del entorno de Hermes capaz "
              "de importar hermes_cli.plugins (venv de PM no localizado)")
        return 2
    version = subprocess.run([str(hermes_py), "--version"],
                             capture_output=True, text=True).stdout.strip()
    print(f"intérprete Hermes: {hermes_py} ({version})")

    workdir = Path(tempfile.mkdtemp(prefix="guild-hermes-real-"))
    data_dir = workdir / "guild-data"
    data_dir.mkdir(parents=True)
    db_file = data_dir / "guild.db"
    print(f"directorio de trabajo temporal: {workdir}")

    server = make_server(str(db_file), "127.0.0.1", 0)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    print(f"servidor GUILD real en {base} (db: {db_file})")

    try:
        # — Lee (Muse, HTTP) entra y publica —
        lee = GuildClient(base_url=base)
        lee.join("lee", "Lee", "Muse",
                 skills_offered=["python", "typescript"],
                 languages=["es", "en"], timezone="Europe/Madrid")
        post = lee.post_need(
            "La Asistenta",
            "Desplegar FASHN VTON en Baseten: la clave solo tiene "
            "permisos de inferencia (403 al desplegar el truss); "
            "necesito a alguien que ya lo haya hecho y me deje el "
            "despliegue reproducible.",
            ["baseten"], need_type="experiencia")
        post_id = post["id"]
        print(f"\n[Lee·HTTP] unido como @lee · post {post_id} creado")

        # — Lee escucha eventos en vivo (SSE) —
        watched: list[dict] = []

        def _watch():
            try:
                for ev in lee.watch_events(max_events=1, timeout=120):
                    watched.append(ev)
            except Exception as exc:  # la evidencia manda: se reporta
                print(f"[watch] error: {type(exc).__name__}: {exc}")

        watcher = threading.Thread(target=_watch, daemon=True)
        watcher.start()

        # — Fase load: carga real + inventario —
        print("\n— FASE load (cargador real de Hermes) —")
        r_load = run_phase(hermes_py, checkout, workdir, "load", [])
        check("plugin cargado sin error por PluginManager",
              r_load.get("load_error") is None,
              f"error={r_load.get('load_error')}")
        check("registra 4 tools", len(r_load.get("tools", [])) == 4,
              ", ".join(r_load.get("tools", [])))
        check("registra hook on_session_start",
              r_load.get("hooks") == ["on_session_start"])
        check("registra comando /guild",
              r_load.get("commands") == ["guild"])
        check("registra la skill del plugin",
              len(r_load.get("skills", [])) == 1,
              ", ".join(r_load.get("skills", [])))
        board_out = r_load.get("outputs", {}).get(
            "tool guild_board (ctx.dispatch_tool)", "")
        check("tool guild_board (vía ctx.dispatch_tool) ve el post de Lee",
              post_id in board_out)

        # — Fase act1: join/board/matches/connect desde Hermes —
        print("\n— FASE act1 (/guild join · board · matches · connect) —")
        r1 = run_phase(hermes_py, checkout, workdir, "act1",
                       ["--post-id", post_id])
        conn_id = r1.get("conn_id")
        check("Marco se unió desde el comando /guild del plugin cargado",
              bool(r1.get("marco_profile_id")))
        mtxt = r1.get("outputs", {}).get(f"/guild matches {post_id}", "")
        m = re.search(r"(\d+(?:\.\d+)?)/100", mtxt)
        marco_score = float(m.group(1)) if m else None
        print(f"  match de Marco sobre el post de Lee: {marco_score}/100")
        check("conexión creada desde el plugin (pendiente de Lee)",
              bool(conn_id), f"conn={conn_id}")

        watcher.join(timeout=30)
        check("Lee recibió connection_requested EN VIVO por SSE "
              "(sin sondear el inbox)",
              len(watched) == 1
              and watched[0].get("kind") == "connection_requested"
              and watched[0].get("connection_id") == conn_id,
              json.dumps(watched, ensure_ascii=False)[:200])

        # — Lee aprueba por HTTP —
        lee.approve_connection(conn_id, approve=True)
        print(f"\n[Lee·HTTP] conexión {conn_id} APROBADA")

        # — Fase act2: Marco entrega desde el plugin —
        print("\n— FASE act2 (/guild deliver) —")
        run_phase(hermes_py, checkout, workdir, "act2",
                  ["--conn-id", conn_id])
        inbox = lee.inbox()
        check("la entrega de Marco llegó al inbox de Lee",
              len(inbox["deliveries_pending"]) == 1,
              json.dumps(inbox["deliveries_pending"],
                         ensure_ascii=False)[:160])
        delivery_id = inbox["deliveries_pending"][0]["id"]

        # — Lee acepta y valora por HTTP —
        lee.decide_delivery(delivery_id, accept=True)
        lee.rate(r1["marco_profile_id"], 5, 5, 4, connection_id=conn_id,
                 comment="Despliegue reproducible y claro.")
        import urllib.request
        with urllib.request.urlopen(base + "/v1/profiles/marco",
                                    timeout=10) as resp:
            marco = json.loads(resp.read().decode())
        print(f"[Lee·HTTP] entrega aceptada · @marco reputación real: "
              f"{marco['reputation_score']}/5 · verificadas: "
              f"{marco.get('verified_skills')}")
        check("reputación de Marco tras la valoración de Lee (5,5,4)",
              marco["reputation_score"] == 4.67,
              f"{marco['reputation_score']}/5")
        check("skill baseten de Marco quedó VERIFICADA por la entrega "
              "aceptada", "baseten" in (marco.get("verified_skills") or []))

        # — Fase act3: Marco valora, status, inbox y hook —
        print("\n— FASE act3 (/guild rate · status · inbox · hook) —")
        r3 = run_phase(hermes_py, checkout, workdir, "act3",
                       ["--conn-id", conn_id])
        hook_out = r3.get("outputs", {}).get(
            "hook on_session_start (manager.invoke_hook)", "")
        check("hook on_session_start invocado vía manager con Marco unido",
              "GUILD" in hook_out, hook_out[:120])
        stats = lee.status()["network"]
        print(f"\n[red] stats reales: {json.dumps(stats, ensure_ascii=False)}")
    finally:
        server.shutdown()
        if not keep:
            import shutil
            shutil.rmtree(workdir, ignore_errors=True)
        else:
            print(f"(directorio conservado: {workdir})")

    print("\n" + "=" * 72)
    failed = [c for c in CHECKS if not c[1]]
    print(f"COMPROBACIONES: {len(CHECKS) - len(failed)}/{len(CHECKS)} en verde")
    for name, ok, detail in failed:
        print(f"  ✗ {name} — {detail}")
    print("=" * 72)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
